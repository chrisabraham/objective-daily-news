#!/usr/bin/env python3
"""
make_podcast.py — the Objective Daily News podcast press run.

Turns the paper into a podcast: every edition and special report
becomes an episode, read aloud in the paper's permanent voice, opened
and closed by the news theme, and published as an RSS 2.0 podcast
feed at the site root (podcast.xml).

What a run does:

  * Reads editions/*.html and special-reports/*.html through the same
    parser the text feeds use (make_feeds.parse_edition), so an item
    exists in the podcast exactly when it exists in the paper.
  * Builds each episode's spoken text from the desk's own report only
    — the <article> body, never the filed clippings (those are the
    subjective shelf, stamped as such, and stay in print). Spoken
    cleanup is light and mechanical: page furniture (kicker, stamp,
    byline, headline, deck) is not re-read, tables are skipped line by
    line rather than read as grids, abbreviations that read badly
    aloud are expanded. No words are added to the report; the only
    additions are the episode's bare intro line ("Objective Daily
    News, [date]. [Title].") and the closing line. ODN purity law:
    the episode is the published objective text, read aloud.
  * Synthesizes narration with the built-in tts in the paper's
    permanent voice (VOICE below — Helio, the catalog's top-rated
    soothing male preset; change the constant and every episode whose
    hash covers it is re-rendered), bookends it with the news theme
    (assets/theme-intro.mp3 / theme-outro.mp3, generated once and
    reused), and mixes a low music bed under the narration when the
    bed file exists. Output: audio/<slug>.mp3, mono, 64 kbps,
    speech-first — spoken news, not music fidelity.
  * Seats the episode player in each article page, on the hairline
    directly beneath the byline (placement ruling, Nov 6, 2026) —
    article pages only; the front page carries no audio.
  * Writes podcast.xml (RSS 2.0 with the iTunes and Podcast Index
    namespaces), measuring every enclosure's byte length from the
    actual file, and podcast-storage.json, the storage ledger:
    cumulative audio bytes, episode count, current site size, and the
    projected days to the GitHub Pages 1 GB soft limit at the paper's
    real cadence (four watches plus up to one special report daily).
    The run prints the running total. When the ledger crosses the
    migration trigger, the run says so in plain words — old episodes'
    audio is the first candidate to move to a dedicated podcast host
    (see SETUP.md, section 8).

Run it alongside the text feeds, after every press run:

    python3 make_feeds.py
    python3 make_podcast.py

With --skip-tts it rebuilds the feed and the ledger from whatever
audio already stands in audio/ (used on seats without the tts tool)
and reports which episodes are still owed audio.

Standard library plus ffmpeg (already the house tool for stitching).
"""

import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_feeds  # noqa: E402  (the press room's shared parser)

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(SITE_DIR, "audio")
ASSETS_DIR = os.path.join(SITE_DIR, "assets")
TEXT_DIR = os.path.join(AUDIO_DIR, "text")
STATE_PATH = os.path.join(SITE_DIR, "podcast-state.json")
LEDGER_PATH = os.path.join(SITE_DIR, "podcast-storage.json")
FEED_PATH = os.path.join(SITE_DIR, "podcast.xml")
TZ = ZoneInfo("America/New_York")

PAPER = "Objective Daily News"
AUTHOR = "Chris Abraham"
OWNER_NAME = "Chris Abraham"
OWNER_EMAIL = "cabraham@gmail.com"  # Chris's podcast contact, as specified
DESK = "Eunice"
FEED_DESCRIPTION = (
    "The desk's report, read aloud. Objective Daily News is an "
    "archival news service: the desk's analysis of the world's "
    "reporting, stamped objective, filed over the clippings it was "
    "drawn from. Each episode is one edition or special report, read "
    "in full by the paper's resident voice. Publisher Chris Abraham; "
    "the desk is an AI, and says so."
)
FEED_LANGUAGE = "en"
FEED_GUID = "d9e4b7a1-3c5f-4e8a-b2d1-6f0a9c8e5b47"  # podcast:guid; never changes
COVER_PATH = "images/podcast-cover.jpg"

# The paper's permanent voice: Helio (avocado_v2:MAI_03) — the
# catalog's top-rated soothing male preset (aesthetics 3.0, the
# ceiling): masculine, American, gentle, crisp and clear timbre,
# middle-aged. Runner-up: Miles, "Satiny Moon" (avocado_v2:miles),
# the catalog's explicitly soothing American male. Consistency across
# episodes outranks novelty; this constant is the voice of the paper.
VOICE = "avocado_v2:MAI_03"
VOICE_NAME = "Helio"
TTS_BIN = os.environ.get("ODN_TTS", "/opt/hatch/bin/tts")

# Speech-first encoding: mono MP3 at 64 kbps. At ~880 words a minute
# of narration, an episode runs about 0.44 MB per minute of audio.
BITRATE = "64k"
BED_VOLUME = 0.07  # the bed sits well under the voice

# The storage watchdog. GitHub Pages' published-site soft limit is
# 1 GB; the paper's cadence is four watches plus up to one special
# report a day. The migration trigger: when projected days remaining
# fall under 30, audio moves to a dedicated podcast host — episodes
# oldest-first — with GUIDs and the feed URL preserved (SETUP.md §8).
PAGES_SOFT_LIMIT = 1_000_000_000
EPISODES_PER_DAY = 5
MIGRATION_TRIGGER_DAYS = 30

THEME_INTRO = os.path.join(ASSETS_DIR, "theme-intro.mp3")
THEME_OUTRO = os.path.join(ASSETS_DIR, "theme-outro.mp3")
THEME_BED = os.path.join(ASSETS_DIR, "theme-bed.mp3")

# Light, mechanical spoken cleanup only — expansions of abbreviations
# that read badly aloud. Nothing interpretive; the report's words
# otherwise stand as published.
SPOKEN_EXPANSIONS = [
    (r"\bU\.S\.", "U.S"),
    (r"\bMr\.", "Mister"),
    (r"\bMrs\.", "Missus"),
    (r"\bDr\.", "Doctor"),
    (r"\bNo\.", "Number"),
    (r"\bvs\.", "versus"),
    (r"\bapprox\.", "approximately"),
]


def announce(msg):
    print(f"make_podcast: {msg}")


# ---------------------------------------------------------------- text

def article_html(doc):
    return make_feeds.grab(r'<article class="article">(.*?)</article>', doc)


def table_placeholders(article):
    """Replace each table with a spoken-cadence-safe paragraph form:
    'Header, one: value. Header, two: value.' per row, built only from
    the table's own words, one paragraph per row so the synthesizer
    breaks between rows instead of running the grid together."""
    def convert(m):
        block = m.group(0)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", block, re.S)
        if not rows:
            return " "
        def cells(row):
            out = []
            for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S):
                t = make_feeds.html_to_text(c)
                t = (t.replace("&minus;", "minus ").replace("&plus;", "plus ")
                      .replace("&middot;", ", ").replace("&nbsp;", " "))
                out.append(re.sub(r"\s+", " ", t).strip())
            return out
        header = cells(rows[0])
        out = []
        for row in rows[1:]:
            vals = cells(row)
            if not any(vals):
                continue
            pairs = []
            for i, v in enumerate(vals):
                if not v:
                    continue
                h = header[i] if i < len(header) else ""
                pairs.append(f"{h}: {v}" if h and i and len(h) <= 40 else v)
            out.append("<p>" + ". ".join(pairs) + ".</p>")
        return "\n".join(out) if out else " "
    return re.sub(r"<table.*?</table>", convert, article, flags=re.S)


def spoken_text(doc, item):
    """The episode's spoken text: the intro line, the desk's report,
    the closing line. The report's text is the published article with
    furniture removed and tables linearized; nothing is added to it."""
    art = article_html(doc)
    art = table_placeholders(art)
    art = re.sub(r'<div class="special-report-badge">.*?</div>', " ", art, flags=re.S)
    art = re.sub(r'<div class="stamp-row">.*?</div>', " ", art, flags=re.S)
    art = re.sub(r'<p class="byline">.*?</p>', " ", art, flags=re.S)
    art = re.sub(r'<p class="kicker">(.*?)</p>', r"\1 ", art, flags=re.S)
    text = make_feeds.html_to_text(art)
    blocks = [b.strip() for b in text.split("\n\n")]
    blocks = [b for b in blocks if b]
    # Drop the furniture blocks: kicker, stamp word, headline, deck —
    # the intro line carries the title; the deck previews the body.
    drop = {item["title"].strip(), item["description"].strip(), "Objective"}
    blocks = [b for b in blocks if b not in drop]
    body = "\n\n".join(blocks)
    body = re.sub(r"[ \t]+", " ", body)
    for pat, rep in SPOKEN_EXPANSIONS:
        body = re.sub(pat, rep, body)

    date_long = item["published"].strftime("%A, %B %-d, %Y")
    watch = item["watch"]
    if watch:
        intro = f"Objective Daily News. {watch}, {date_long}. {item['title']}."
    else:
        intro = f"Objective Daily News. {date_long}. {item['title']}."
    closing = (
        "That is the report as the desk filed it. Objective Daily News "
        "is published by Chris Abraham; the desk is an AI, and the "
        "paper says so on its colophon."
    )
    return intro + "\n\n" + body + "\n\n" + closing


# ---------------------------------------------------------------- audio

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ffprobe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path])
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def duration_hms(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def ensure_theme():
    """The news theme, generated once from ffmpeg synthesis: a short
    orchestral-style sting (brass-like stacked tones over a timpani
    pulse) for the open, a resolving variant for the close, and a
    very quiet sustained bed. Deterministic; the same files score
    every episode, the way a network's theme does."""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    if os.path.exists(THEME_INTRO) and os.path.exists(THEME_OUTRO) \
            and os.path.exists(THEME_BED):
        return
    sr = 44100
    # A dignified news figure in C: tonic–fifth–octave–third, struck
    # like a signature, over a low pulse. Frequencies in Hz.
    notes = [(0.00, 130.81, 0.55), (0.00, 196.00, 0.55),
             (0.42, 261.63, 0.6), (0.42, 329.63, 0.6),
             (0.88, 392.00, 0.9), (0.88, 523.25, 0.9),
             (1.45, 329.63, 1.5), (1.45, 523.25, 1.5), (1.45, 659.25, 1.5)]
    intro_expr = "+".join(
        f"0.16*sin(2*PI*{f}*(t-{t0}))*exp(-3.2*(t-{t0}))*gt(t,{t0})"
        for t0, f, _ in notes
    )
    outro_notes = [(0.00, 392.00, 0.7), (0.00, 523.25, 0.7),
                   (0.35, 329.63, 0.8), (0.35, 261.63, 0.8),
                   (0.75, 196.00, 1.6), (0.75, 261.63, 1.6),
                   (0.75, 392.00, 1.6), (0.75, 130.81, 1.6)]
    outro_expr = "+".join(
        f"0.16*sin(2*PI*{f}*(t-{t0}))*exp(-3.0*(t-{t0}))*gt(t,{t0})"
        for t0, f, _ in outro_notes
    )
    bed_expr = ("0.5*sin(2*PI*130.81*t)+0.35*sin(2*PI*196.00*t)"
                "+0.25*sin(2*PI*261.63*t)+0.12*sin(2*PI*329.63*t)")
    jobs = [
        (THEME_INTRO, "aevalsrc=" + intro_expr.replace(",", "\\,"),
         ["-t", "3.2"]),
        (THEME_OUTRO, "aevalsrc=" + outro_expr.replace(",", "\\,"),
         ["-t", "2.8"]),
        (THEME_BED, "aevalsrc=" + bed_expr.replace(",", "\\,"),
         ["-t", "60", "-af", "afade=t=in:st=0:d=3,afade=t=out:st=57:d=3,volume=0.5"]),
    ]
    for path, src, extra in jobs:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"{src}:s={sr}",
               "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "96k"] + extra + [path]
        r = run(cmd)
        if r.returncode != 0 or not os.path.exists(path):
            raise RuntimeError(f"theme generation failed for {path}: {r.stderr[-400:]}")


def synthesize(script_path, out_path):
    cmd = [TTS_BIN, "synthesize-script", "--script", script_path,
           "--speaker", f"Narrator={VOICE}", "--output", out_path,
           "--concurrency", "3", "--timeout-secs", "600"]
    r = run(cmd)
    if r.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(f"tts failed: {(r.stdout + r.stderr)[-500:]}")


def mix_episode(voice_mp3, out_path, item):
    """Bookend with the theme; lay the bed under the narration if the
    bed stands; master to mono 64 kbps speech with ID3 carrying the
    episode's title and the paper's name."""
    ensure_theme()
    dur = ffprobe_duration(voice_mp3)
    inputs = ["-i", THEME_INTRO, "-i", voice_mp3, "-i", THEME_OUTRO]
    filt = ["[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]"]
    if os.path.exists(THEME_BED):
        inputs += ["-stream_loop", "-1", "-i", THEME_BED]
        filt = [
            f"[3:a]atrim=0:{dur:.2f},volume={BED_VOLUME}[bed]",
            "[1:a][bed]amix=inputs=2:duration=first:normalize=0[voiced]",
            "[0:a][voiced][2:a]concat=n=3:v=0:a=1[a]",
        ]
    cmd = (["ffmpeg", "-y"] + inputs +
           ["-filter_complex", ";".join(filt), "-map", "[a]",
            "-ac", "1", "-ar", "44100", "-codec:a", "libmp3lame",
            "-b:a", BITRATE,
            "-metadata", f"title={item['title']}",
            "-metadata", f"artist={PAPER}",
            "-metadata", f"album={PAPER}",
            out_path])
    r = run(cmd)
    if r.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(f"mix failed: {r.stderr[-500:]}")


def wire_players(items):
    """Seat each episode's player in its article page, on the hairline
    directly beneath the byline (Chris's placement ruling, Nov 6,
    2026): one quiet native player as part of the byline furniture,
    above the first section heading. Article pages only — the front
    page carries no audio, ever. Idempotent; a page already carrying
    the player is left alone. The element has no text, so the spoken
    text (and its hash) is untouched."""
    for item in items:
        slug = episode_slug(item)
        if not os.path.exists(os.path.join(AUDIO_DIR, slug + ".mp3")):
            continue
        path = item["path"]
        if os.path.basename(path) == "index.html":
            continue  # the front page carries no audio, ever (placement law)
        with open(path, encoding="utf-8") as fh:
            doc = fh.read()
        if "odn-listen" in doc:
            continue
        player = (f'\n  <p class="odn-listen"><audio controls '
                  f'preload="none" src="../audio/{slug}.mp3"></audio></p>')
        new, n = re.subn(r'(<p class="byline">.*?</p>)',
                         lambda m: m.group(1) + player, doc, count=1,
                         flags=re.S)
        if n:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
            announce(f"player seated beneath the byline in {slug}")
        else:
            announce(f"WARNING: no byline found in {slug}; player not seated")


def strip_players():
    """The enforcement half of the placement law: the front page is
    rebuilt from the edition pages at press time, which would carry
    the player onto it. Any player found in index.html is removed
    before the press run ends, so the front page stays clean no
    matter how it was built."""
    path = os.path.join(SITE_DIR, "index.html")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        doc = fh.read()
    new = re.sub(r'\s*<p class="odn-listen">.*?</p>', '', doc, flags=re.S)
    if new != doc:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
        announce("placement law: player(s) stripped from the front page")


# ---------------------------------------------------------------- feed

def episode_slug(item):
    return os.path.basename(item["url"])[:-5]  # strip .html


def build_feed(episodes, base, built):
    cover = f"{base}/{COVER_PATH}"
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" '
        'xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
        'xmlns:podcast="https://podcastindex.org/namespace/1.0" '
        'xmlns:content="http://purl.org/rss/1.0/modules/content/" '
        'xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{escape(PAPER)}</title>",
        f"<link>{base}/</link>",
        f'<atom:link href="{base}/podcast.xml" rel="self" type="application/rss+xml"/>',
        f"<description>{escape(FEED_DESCRIPTION)}</description>",
        f"<language>{FEED_LANGUAGE}</language>",
        f"<copyright>© {built.year} {escape(AUTHOR)}</copyright>",
        f"<managingEditor>{OWNER_EMAIL} ({escape(OWNER_NAME)})</managingEditor>",
        f"<webMaster>{OWNER_EMAIL} ({escape(OWNER_NAME)})</webMaster>",
        f"<lastBuildDate>{make_feeds.rfc822(built)}</lastBuildDate>",
        "<generator>make_podcast.py (Objective Daily News press room)</generator>",
        f"<podcast:guid>{FEED_GUID}</podcast:guid>",
        f"<podcast:locked>yes</podcast:locked>",
        f'<podcast:person role="host" href="{base}/about.html">{escape(AUTHOR)}</podcast:person>',
        f"<itunes:title>{escape(PAPER)}</itunes:title>",
        f"<itunes:author>{escape(AUTHOR)}</itunes:author>",
        f"<itunes:summary>{escape(FEED_DESCRIPTION)}</itunes:summary>",
        f'<itunes:owner><itunes:name>{escape(OWNER_NAME)}</itunes:name>'
        f"<itunes:email>{OWNER_EMAIL}</itunes:email></itunes:owner>",
        f'<itunes:image href="{cover}"/>',
        '<itunes:category text="News"/>',
        '<itunes:category text="News"><itunes:category text="News Commentary"/></itunes:category>',
        "<itunes:explicit>false</itunes:explicit>",
        "<itunes:type>episodic</itunes:type>",
        f'<image><url>{cover}</url><title>{escape(PAPER)}</title><link>{base}/</link></image>',
    ]
    for ep in episodes:
        out += [
            "<item>",
            f"<title>{escape(ep['title'])}</title>",
            f"<link>{ep['url']}</link>",
            f'<guid isPermaLink="false">{ep["guid"]}</guid>',
            f"<pubDate>{make_feeds.rfc822(ep['published'])}</pubDate>",
            f"<description>{escape(ep['description'])}</description>",
            f"<itunes:title>{escape(ep['title'])}</itunes:title>",
            f"<itunes:author>{escape(AUTHOR)}</itunes:author>",
            f"<itunes:summary>{escape(ep['description'])}</itunes:summary>",
            f"<itunes:duration>{ep['duration_hms']}</itunes:duration>",
            "<itunes:explicit>false</itunes:explicit>",
            f'<enclosure url="{ep["audio_url"]}" length="{ep["bytes"]}" type="audio/mpeg"/>',
            "</item>",
        ]
    out += ["</channel>", "</rss>", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- ledger

def dir_bytes(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def update_ledger(episodes, built):
    audio_bytes = sum(ep["bytes"] for ep in episodes)
    site_bytes = dir_bytes(SITE_DIR)
    sizes = sorted(ep["bytes"] for ep in episodes)
    avg = audio_bytes / len(episodes) if episodes else 0
    daily = avg * EPISODES_PER_DAY
    remaining = max(PAGES_SOFT_LIMIT - site_bytes, 0)
    days = int(remaining / daily) if daily else None
    ledger = {
        "updated": built.isoformat(),
        "voice": f"{VOICE_NAME} ({VOICE})",
        "encoding": f"MP3 mono {BITRATE}",
        "episodes": len(episodes),
        "audio_bytes": audio_bytes,
        "audio_mb": round(audio_bytes / 1e6, 2),
        "site_bytes": site_bytes,
        "site_mb": round(site_bytes / 1e6, 2),
        "pages_soft_limit_bytes": PAGES_SOFT_LIMIT,
        "bytes_remaining": remaining,
        "avg_episode_bytes": int(avg),
        "cadence_episodes_per_day": EPISODES_PER_DAY,
        "projected_daily_audio_bytes": int(daily),
        "projected_days_to_limit": days,
        "migration_trigger": (
            f"Move episode audio (oldest first) to a dedicated podcast "
            f"host when projected_days_to_limit falls below "
            f"{MIGRATION_TRIGGER_DAYS}, or the site passes 750 MB, "
            f"whichever comes first. GUIDs and the feed URL are "
            f"preserved across the move (SETUP.md section 8)."
        ),
        "migration_due": bool(days is not None and days < MIGRATION_TRIGGER_DAYS),
    }
    with open(LEDGER_PATH, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2)
        fh.write("\n")
    return ledger


# ---------------------------------------------------------------- main

def select_items(base, only):
    paths = sorted(glob.glob(os.path.join(SITE_DIR, "editions", "*.html")))
    paths += sorted(glob.glob(os.path.join(SITE_DIR, "special-reports", "*.html")))
    items = [make_feeds.parse_edition(p, base) for p in paths]
    for item, path in zip(items, paths):
        item["path"] = path
    items.sort(key=lambda it: it["published"], reverse=True)
    if only:
        wanted = set(only)
        items = [it for it in items if episode_slug(it) in wanted]
    return items


def main():
    skip_tts = "--skip-tts" in sys.argv
    only = []
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        only = [s.strip() for s in sys.argv[i + 1].split(",") if s.strip()]
    base = make_feeds.base_url()
    items = select_items(base, only)
    full_items = select_items(base, [])
    built = datetime.now(TZ)
    wire_players(full_items)
    strip_players()

    os.makedirs(TEXT_DIR, exist_ok=True)
    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as fh:
            state = json.load(fh)

    episodes, owed = [], []
    for item in items:
        slug = episode_slug(item)
        mp3 = os.path.join(AUDIO_DIR, slug + ".mp3")
        with open(item["path"], encoding="utf-8") as fh:
            doc = fh.read()
        text = spoken_text(doc, item)
        digest = hashlib.sha256(
            (VOICE + "\n" + text).encode()).hexdigest()
        entry = state.get(slug)
        fresh = (entry and entry.get("sha256") == digest
                 and os.path.exists(mp3))
        if not fresh and not skip_tts:
            script = os.path.join(TEXT_DIR, slug + ".txt")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write(f"Narrator: {text}\n")
            raw = os.path.join(TEXT_DIR, slug + ".raw.mp3")
            try:
                synthesize(script, raw)
                mix_episode(raw, mp3, item)
                os.remove(raw)
                entry = {"sha256": digest, "voice": VOICE,
                         "bytes": os.path.getsize(mp3),
                         "duration": ffprobe_duration(mp3)}
                state[slug] = entry
                announce(f"narrated {slug} "
                         f"({entry['bytes'] / 1e6:.2f} MB, "
                         f"{duration_hms(entry['duration'])})")
            except Exception as exc:
                announce(f"FAILED {slug}: {exc}")
                owed.append(slug)
                continue
        if not os.path.exists(mp3):
            owed.append(slug)

    # The feed and the ledger always cover every item whose audio
    # stands, not only the ones this run touched.
    episodes = []
    for item in full_items:
        slug = episode_slug(item)
        mp3 = os.path.join(AUDIO_DIR, slug + ".mp3")
        if not os.path.exists(mp3):
            if slug not in owed:
                owed.append(slug)
            continue
        entry = state.get(slug) or {}
        size = os.path.getsize(mp3)
        dur = entry.get("duration") or ffprobe_duration(mp3)
        episodes.append({
            "title": item["title"],
            "url": item["url"],
            "description": item["description"],
            "published": item["published"],
            "guid": str(uuid.uuid5(uuid.NAMESPACE_URL, item["url"])),
            "audio_url": f"{base}/audio/{slug}.mp3",
            "bytes": size,
            "duration_hms": duration_hms(dur),
        })

    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")

    with open(FEED_PATH, "w", encoding="utf-8") as fh:
        fh.write(build_feed(episodes, base, built))
    ledger = update_ledger(episodes, built)
    announce(
        f"wrote podcast.xml ({len(episodes)} episode(s)); storage: "
        f"{ledger['audio_mb']} MB of audio across {ledger['episodes']} "
        f"episode(s), site {ledger['site_mb']} MB of the 1 GB Pages "
        f"soft limit, ~{ledger['projected_days_to_limit']} day(s) of "
        f"headroom at {EPISODES_PER_DAY} episodes a day")
    if ledger["migration_due"]:
        announce("STORAGE WATCHDOG: migration trigger reached — move "
                 "the oldest episode audio to a dedicated podcast host "
                 "(SETUP.md section 8).")
    if owed:
        announce(f"audio still owed for: {', '.join(owed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
