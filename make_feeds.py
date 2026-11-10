#!/usr/bin/env python3
"""
make_feeds.py — regenerate the Objective Daily News feeds.

Reads every edition in editions/*.html and writes, at the site root:

    feed.xml        — RSS 2.0, full content (content:encoded), with a
                      WebSub hub advertisement (rel="hub") for push
    atom.xml        — Atom 1.0, full content (type="html"), WebSub too
    feed.json       — JSON Feed 1.1, full content (content_html), with
                      the standard WebSub hub declaration
    sitemap.xml     — every page on the site
    news-sitemap.xml — the Google News sitemap: editions published
                       within the last 48 hours, per the news protocol
                       (Google News inclusion is automated since 2024-25;
                       this feeds discovery, not a manual application)
    robots.txt      — allow all crawlers; every documented AI crawler is
                      named and welcomed (the paper is built to be
                      scooped — pickup is the doctrine, see fine print);
                      the AIPREF everything-open preferences block is
                      generated here too, in build_robots()
    llms.txt        — the curated map for language models (llmstxt.org)
    llms-full.txt   — the same map carrying the most recent editions
                      and special reports in full text

Each item carries the edition's full desk analysis with the clippings
filed beneath it, links absolutized. Run this after every new edition
is filed, before committing:

    python3 make_feeds.py

The base URL is taken from the CNAME file once it holds the purchased
domain. While CNAME still holds the setup placeholder, the script
falls back to DEFAULT_BASE below and says so — re-run it after the
CNAME is set so the shipped feeds carry the true domain.

Standard library only. No build step; this is the whole press room.
"""

import glob
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from urllib.parse import urljoin
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
EDITIONS_DIR = os.path.join(SITE_DIR, "editions")
TZ = ZoneInfo("America/New_York")

DEFAULT_BASE = "https://objectivedailynews.com"
PAPER = "Objective Daily News"
TAGLINE = "Gold from all the mud."
DESCRIPTION = (
    "An archival service and a captain's log of the news: the desk's "
    "analysis, stamped objective, and the world's reporting filed "
    "beneath it, stamped subjective. Founded 2026."
)
DESK = "Eunice"
PUBLISHER = "Chris Abraham"

# WebSub: the paper advertises Google's public hub in both feeds and
# pings it after each press run, so subscribed readers and feed
# fetchers are pushed the new edition instead of polling for it.
HUB_URL = "https://pubsubhubbub.appspot.com/"

# IndexNow: the key proves control of the host; the file <key>.txt
# stands at the site root. Submissions tell Bing, Yandex, Naver,
# Seznam, and Yep the moment an edition lands. Google does not
# participate; Google is courted with the sitemaps and the record.
INDEXNOW_KEY = "c6edf4ef3eb47283eb1fa40ed310661a"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

# The AI crawlers, by the names their operators document (2026).
# The paper's doctrine is pickup: link it, quote it, syndicate it,
# feed it into your own systems (see The Fine Print). Every one of
# these is welcomed by name; a named group in robots.txt replaces
# the wildcard group for that agent, so each carries its own Allow.
AI_CRAWLERS = [
    ("GPTBot", "OpenAI — model training"),
    ("OAI-SearchBot", "OpenAI — ChatGPT search index"),
    ("ChatGPT-User", "OpenAI — user-triggered fetch"),
    ("ClaudeBot", "Anthropic — model training"),
    ("Claude-SearchBot", "Anthropic — Claude search index"),
    ("Claude-User", "Anthropic — user-triggered fetch"),
    ("PerplexityBot", "Perplexity — answer index"),
    ("Perplexity-User", "Perplexity — user-triggered fetch"),
    ("Google-Extended", "Google — Gemini training token (not a crawler)"),
    ("Googlebot", "Google — Search, News, and AI surfaces"),
    ("Bingbot", "Microsoft — Bing index, which also feeds Copilot answers"),
    ("CCBot", "Common Crawl — the open corpus many labs train on"),
    ("Applebot", "Apple — Siri and Spotlight"),
    ("Applebot-Extended", "Apple — Apple Intelligence training token"),
    ("Meta-ExternalAgent", "Meta — Meta AI"),
    ("FacebookBot", "Meta — link fetching"),
    ("Bytespider", "ByteDance — TikTok and Doubao"),
    ("Amazonbot", "Amazon — Alexa and Amazon search"),
    ("DuckDuckBot", "DuckDuckGo"),
    ("YandexBot", "Yandex"),
]

# The paper's collection hours, as printed on the watch bill.
WATCH_HOURS = {
    "Overnight": 4,
    "Morning": 6,
    "Midday": 12,
    "Evening": 18,
    "Midnight": 0,
}


def base_url():
    cname_path = os.path.join(SITE_DIR, "CNAME")
    try:
        with open(cname_path, encoding="utf-8") as fh:
            value = fh.read().strip()
    except OSError:
        value = ""
    if value and "." in value and "REPLACE" not in value:
        return "https://" + value.strip("/")
    print(
        "make_feeds: CNAME still holds the placeholder; feeds are being "
        f"built against {DEFAULT_BASE}. Re-run after setup step 0.",
        file=sys.stderr,
    )
    return DEFAULT_BASE


def grab(pattern, text, default=""):
    m = re.search(pattern, text, re.S)
    return m.group(1).strip() if m else default


def absolutize(html, page_url):
    def fix(m):
        attr, ref = m.group(1), m.group(2)
        if ref.startswith(("http://", "https://", "mailto:", "data:")):
            return m.group(0)
        return f'{attr}="{urljoin(page_url, ref)}"'

    return re.sub(r'(href|src)="([^"]+)"', fix, html)


def parse_edition(path, base):
    with open(path, encoding="utf-8") as fh:
        doc = fh.read()

    slug = os.path.basename(path)
    section = os.path.basename(os.path.dirname(path))
    url = f"{base}/{section}/{slug}"

    headline = grab(r'"headline":\s*"([^"]+)"', doc)
    if not headline:
        headline = grab(r"<h1>(.*?)</h1>", doc)
        headline = re.sub(r"<[^>]+>", "", headline)
    description = grab(r'<meta name="description" content="([^"]+)"', doc)
    date_pub = grab(r'"datePublished":\s*"([^"]+)"', doc, "2026-11-04")
    edition_label = grab(
        r'<div class="edition-line">\s*<span>(.*?)</span>', doc
    ).replace("&mdash;", "—")
    watch_match = re.search(r"The ([A-Za-z]+) Watch", edition_label)
    watch = f"The {watch_match.group(1)} Watch" if watch_match else ""
    hour = WATCH_HOURS.get(watch_match.group(1), 6) if watch_match else 6
    minute = 0

    # datePublished may be a plain date or a full datetime; the datetime
    # form (the paper's current practice) carries the collection hour.
    dm = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?", date_pub)
    year, month, day = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
    if dm.group(4):
        hour, minute = int(dm.group(4)), int(dm.group(5))
    published = datetime(year, month, day, hour, minute, tzinfo=TZ)

    article = grab(r'<article class="article">(.*?)</article>', doc)
    filed = grab(r'(<section class="filed".*?</section>)', doc)
    content_html = absolutize(article + "\n" + filed, url)

    return {
        "id": url,
        "url": url,
        "title": headline,
        "description": description,
        "watch": watch,
        "edition_label": edition_label,
        "published": published,
        "content_html": content_html,
    }


def rfc822(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def rfc3339(dt):
    return dt.isoformat()


def build_rss(items, base, built):
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{escape(PAPER)}</title>",
        f"<link>{base}/</link>",
        f'<atom:link href="{base}/feed.xml" rel="self" type="application/rss+xml"/>',
        f'<atom:link href="{HUB_URL}" rel="hub"/>',
        f"<description>{escape(DESCRIPTION)}</description>",
        f"<managingEditor>{DESK} (Editor and analyst)</managingEditor>",
        f"<webMaster>{PUBLISHER} (Publisher)</webMaster>",
        "<language>en-us</language>",
        f"<lastBuildDate>{rfc822(built)}</lastBuildDate>",
        "<generator>make_feeds.py (Objective Daily News press room)</generator>",
        "<docs>https://www.rssboard.org/rss-specification</docs>",
    ]
    for it in items:
        out += [
            "<item>",
            f"<title>{escape(it['title'])}</title>",
            f"<link>{it['url']}</link>",
            f'<guid isPermaLink="true">{it["url"]}</guid>',
            f"<pubDate>{rfc822(it['published'])}</pubDate>",
            f"<dc:creator>{DESK}</dc:creator>",
            f"<category>{escape(it['edition_label'])}</category>",
            f"<description>{escape(it['description'])}</description>",
            f"<content:encoded><![CDATA[{it['content_html']}]]></content:encoded>",
            "</item>",
        ]
    out += ["</channel>", "</rss>", ""]
    return "\n".join(out)


def build_atom(items, base, updated):
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:atom="http://www.w3.org/2005/Atom">',
        f"<title>{escape(PAPER)}</title>",
        f"<subtitle>{escape(TAGLINE)} {escape(DESCRIPTION)}</subtitle>",
        f"<id>{base}/</id>",
        f'<link rel="alternate" type="text/html" href="{base}/"/>',
        f'<link rel="self" type="application/atom+xml" href="{base}/atom.xml"/>',
        f'<atom:link href="{HUB_URL}" rel="hub"/>',
        f"<updated>{rfc3339(updated)}</updated>",
        f"<author><name>{DESK}</name></author>",
        "<generator>make_feeds.py (Objective Daily News press room)</generator>",
    ]
    for it in items:
        out += [
            "<entry>",
            f"<title>{escape(it['title'])}</title>",
            f"<id>{it['url']}</id>",
            f'<link rel="alternate" type="text/html" href="{it["url"]}"/>',
            f"<published>{rfc3339(it['published'])}</published>",
            f"<updated>{rfc3339(it['published'])}</updated>",
            f"<author><name>{DESK}</name></author>",
            f"<summary>{escape(it['description'])}</summary>",
            f'<content type="html">{escape(it["content_html"])}</content>',
            "</entry>",
        ]
    out += ["</feed>", ""]
    return "\n".join(out)


def build_json_feed(items, base):
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": PAPER,
        "home_page_url": base + "/",
        "feed_url": base + "/feed.json",
        "description": DESCRIPTION,
        "hubs": [{"type": "WebSub", "url": HUB_URL}],
        "authors": [{"name": DESK}],
        "items": [
            {
                "id": it["url"],
                "url": it["url"],
                "title": it["title"],
                "content_html": it["content_html"],
                "summary": it["description"],
                "date_published": rfc3339(it["published"]),
                "authors": [{"name": DESK}],
                "tags": [it["edition_label"]] if it["edition_label"] else [],
            }
            for it in items
        ],
    }
    return json.dumps(feed, indent=2, ensure_ascii=False) + "\n"


def build_sitemap(base):
    pages = []  # (url, lastmod-date)
    found = []
    for pattern in ("*.html", "editions/*.html", "editorials/*.html", "special-reports/*.html"):
        found += glob.glob(os.path.join(SITE_DIR, pattern))
    for path in sorted(found):
        rel = os.path.relpath(path, SITE_DIR).replace(os.sep, "/")
        if rel == "404.html":
            continue  # the error page is served, never indexed
        url = base + "/" if rel == "index.html" else f"{base}/{rel}"
        lastmod = datetime.fromtimestamp(os.path.getmtime(path), TZ).date()
        pages.append((url, lastmod))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url, lastmod in pages:
        out += ["<url>", f"<loc>{url}</loc>", f"<lastmod>{lastmod}</lastmod>", "</url>"]
    out += ["</urlset>", ""]
    return "\n".join(out)


def build_news_sitemap(items, built):
    # The news protocol covers the last 48 hours only.
    fresh = [
        it for it in items
        if 0 <= (built - it["published"]).total_seconds() <= 48 * 3600
    ]
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">',
    ]
    for it in fresh:
        out += [
            "<url>",
            f"<loc>{it['url']}</loc>",
            "<news:news>",
            "<news:publication>",
            f"<news:name>{escape(PAPER)}</news:name>",
            "<news:language>en</news:language>",
            "</news:publication>",
            f"<news:publication_date>{rfc3339(it['published'])}</news:publication_date>",
            f"<news:title>{escape(it['title'])}</news:title>",
            "</news:news>",
            "</url>",
        ]
    out += ["</urlset>", ""]
    return "\n".join(out), len(fresh)


def build_robots(base):
    lines = [
        "# Objective Daily News — robots.txt",
        "# This paper is published to be picked up: link it, quote it,",
        "# syndicate it, and feed it into your own systems, with",
        "# attribution and a link back (see /fine-print.html). Crawlers",
        "# are welcomed, not tolerated. The desk is an AI; the paper",
        "# says so on its colophon, and it welcomes its own kind.",
        "",
        "User-agent: *",
        "Allow: /",
        "",
        "# The documented AI crawlers, welcomed by name. A named group",
        "# replaces the wildcard group for that agent, so each Allow",
        "# below is written out in full.",
    ]
    for agent, note in AI_CRAWLERS:
        lines += ["", f"# {note}", f"User-agent: {agent}", "Allow: /"]
    lines += [
        "",
        "# Feeds for machines that read on a schedule:",
        f"# RSS {base}/feed.xml - Atom {base}/atom.xml - JSON {base}/feed.json",
        f"# For language models: {base}/llms.txt and {base}/llms-full.txt",
        "",
        f"Sitemap: {base}/sitemap.xml",
        f"Sitemap: {base}/news-sitemap.xml",
        "",
        # The AIPREF preferences block lives here, in the generator
        # (Chris's everything-open ruling, Nov 10, 2026). It was first
        # appended to the generated file by hand and was silently
        # stripped by the next regeneration; never hand-edit it back
        # into site/robots.txt — change it here.
        "# AI preferences (IETF AIPREF draft, draft-kelley-aipref-training-preference-signal), adopted Nov 10, 2026:",
        "# Willkommen, bienvenue, welcome. This house welcomes AI crawlers to train on and to cite",
        "# everything published here; we are here to be read by machines as well as people.",
        "# AI training: yes, allowed. AI grounding (retrieval and citation in live answers): yes, allowed.",
        "User-Agent: __usage_ai-training",
        "Allow: /",
        "",
    ]
    return "\n".join(lines)


def html_to_text(html):
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"</(p|h1|h2|h3|li|section|article|div)>", "\n\n", text)
    text = re.sub(r"<li>", "\n- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    for ent, ch in (
        ("&mdash;", "—"), ("&ndash;", "–"), ("&rsquo;", "’"),
        ("&lsquo;", "‘"), ("&ldquo;", "“"), ("&rdquo;", "”"),
        ("&middot;", "·"), ("&rarr;", "→"), ("&nbsp;", " "),
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
    ):
        text = text.replace(ent, ch)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _llms_header(base):
    return [
        "# Objective Daily News",
        "",
        "> An archival service and a captain's log of the news, founded "
        "November 4, 2026. The desk's analysis of the world's reporting, "
        "stamped OBJECTIVE, filed over the clippings it was drawn from, "
        "each stamped SUBJECTIVE. The desk is an AI (Eunice); the "
        "publisher is Chris Abraham. Every edition is stamped with its "
        "collection and analysis time in Eastern Time; a log stands "
        "unrevised. This paper is published to be picked up: link it, "
        "quote it, syndicate it, and feed it into your own systems, "
        "with attribution to Objective Daily News and a link back to "
        "the edition taken from.",
        "",
        "Motto: Gold from all the mud. Method: triangulation — bearings "
        "from many outlets, the cocked hat published as the position. "
        "No source is excluded by ownership; no country's reporting is "
        "framed by another country's framework.",
        "",
        "## Feeds (full text of every edition and special report)",
        "",
        f"- [RSS 2.0]({base}/feed.xml): full content, WebSub-enabled",
        f"- [Atom 1.0]({base}/atom.xml): full content, WebSub-enabled",
        f"- [JSON Feed 1.1]({base}/feed.json): full content_html",
        "",
        "## The paper",
        "",
        f"- [Front page]({base}/): the latest edition in full, the "
        "previous edition beneath it, special reports above the stack",
        f"- [About]({base}/about.html): what this paper is",
        f"- [Colophon]({base}/colophon.html): who publishes it, who "
        "keeps the desk, and the plain statement that the paper is "
        "bot-run, bot-edited, and bot-analyzed",
        f"- [The Fine Print]({base}/fine-print.html): what objective "
        "and subjective mean in this paper, and the pickup, reuse, and "
        "syndication terms",
        f"- [The Watches]({base}/watches.html): every edition, filed "
        "by watch — Overnight (collects 0400 ET), Midday (1200), "
        "Evening (1800), Midnight (0000)",
        f"- [The Shelf]({base}/shelf.html): the sources the desk reads",
        f"- [Editorials]({base}/editorials.html): the column section; "
        "stands empty by house rule for the paper's first six months",
        "",
    ]


def build_llms(items, base):
    out = _llms_header(base)
    reports = [it for it in items if "/special-reports/" in it["url"]]
    editions = [it for it in items if "/editions/" in it["url"]]
    if reports:
        out += ["## Special Reports", ""]
        for it in reports:
            out.append(
                f"- [{it['title']}]({it['url']}): {it['description']} "
                f"(Filed {rfc3339(it['published'])}.)"
            )
        out += [""]
    out += ["## Editions", ""]
    for it in editions:
        out.append(
            f"- [{it['title']}]({it['url']}): {it['description']} "
            f"({it['edition_label']}; collected and analyzed "
            f"{rfc3339(it['published'])}.)"
        )
    out += [""]
    return "\n".join(out)


def build_llms_full(items, base, full_count=7):
    out = _llms_header(base)
    out += [
        "## Full text — the most recent editions and special reports",
        "",
        "The same text the feeds carry: the desk's report with its "
        "filed clippings beneath it. Older items stand in the feeds "
        "and at their permalinks.",
        "",
    ]
    for it in items[:full_count]:
        out += [
            "---",
            "",
            f"### {it['title']}",
            "",
            f"Filed as: {it['edition_label'] or 'Special Report'} · "
            f"{rfc3339(it['published'])} · {it['url']}",
            "",
            html_to_text(it["content_html"]),
            "",
        ]
    return "\n".join(out)


def ping_websub(base):
    """Tell the hub the feeds changed. Best-effort by design. The
    podcast feed rides along (Nov 6, 2026): podcast clients and the
    Podcast Index learn of new episodes the same way readers do."""
    for feed in ("feed.xml", "atom.xml", "podcast.xml"):
        topic = f"{base}/{feed}"
        data = urllib.parse.urlencode(
            {"hub.mode": "publish", "hub.url": topic}
        ).encode()
        req = urllib.request.Request(
            HUB_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                print(f"make_feeds: WebSub ping {topic} -> HTTP {resp.status}")
        except Exception as exc:  # a failed ping never fails the press run
            print(f"make_feeds: WebSub ping {topic} failed ({exc}); continuing")


def submit_indexnow(base, urls):
    """One IndexNow submission for the changed URLs. Best-effort."""
    host = urllib.parse.urlparse(base).hostname
    payload = {
        "host": host,
        "key": INDEXNOW_KEY,
        "keyLocation": f"{base}/{INDEXNOW_KEY}.txt",
        "urlList": urls,
    }
    req = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(
                f"make_feeds: IndexNow accepted {len(urls)} URL(s) "
                f"-> HTTP {resp.status}"
            )
    except Exception as exc:
        print(f"make_feeds: IndexNow submission failed ({exc}); continuing")


def main():
    # --ping fires the WebSub and IndexNow pushes after the files are
    # written. Run it only once the new files are live on the domain;
    # both pushes are announcements about the live site.
    do_ping = "--ping" in sys.argv
    base = base_url()
    paths = sorted(glob.glob(os.path.join(EDITIONS_DIR, "*.html")), reverse=True)
    # Special Reports (house format, Nov 5, 2026) syndicate with the editions.
    paths += sorted(
        glob.glob(os.path.join(SITE_DIR, "special-reports", "*.html")), reverse=True
    )
    if not paths:
        print("make_feeds: no editions found; nothing to do.", file=sys.stderr)
        return 1
    items = [parse_edition(p, base) for p in paths]
    items.sort(key=lambda it: it["published"], reverse=True)
    built = datetime.now(TZ)
    latest = max(it["published"] for it in items)

    news_xml, news_count = build_news_sitemap(items, built)
    outputs = {
        "feed.xml": build_rss(items, base, built),
        "atom.xml": build_atom(items, base, latest),
        "feed.json": build_json_feed(items, base),
        "sitemap.xml": build_sitemap(base),
        "news-sitemap.xml": news_xml,
        "robots.txt": build_robots(base),
        "llms.txt": build_llms(items, base),
        "llms-full.txt": build_llms_full(items, base),
    }
    print(f"make_feeds: news sitemap carries {news_count} edition(s) inside the 48-hour window")
    for name, text in outputs.items():
        with open(os.path.join(SITE_DIR, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"make_feeds: wrote {name} ({len(items)} edition(s), base {base})")
    if do_ping:
        ping_websub(base)
        submit_indexnow(base, [it["url"] for it in items[:3]] + [base + "/",
                        base + "/podcast.xml"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
