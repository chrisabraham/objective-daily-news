# Objective Daily News — Setup Checklist

Files in this folder are the complete paper, ready to serve as-is (plain static
HTML/CSS, no build step). Chris reserved the repo, DNS, and GitHub setup to
himself; this checklist is the order to do it in. Estimated total: ~15 minutes
plus DNS propagation.

## 0. Put the purchased domain in the CNAME file  ⚠️ DO THIS FIRST

The `CNAME` file in this folder currently contains one placeholder line:

```
REPLACE-WITH-PURCHASED-DOMAIN
```

Replace it with the exact domain purchased (no `https://`, no trailing slash,
no `www.` unless the www host is the one intended), e.g.:

```
objectivedailynews.com
```

Do not push the repo while the placeholder is still in the file — GitHub Pages
would try to bind that name.

## 1. Create the GitHub repository

- New public repo (any name; `objective-daily-news` reads well). Do NOT
  initialize it with a README or .gitignore (this folder has everything).
- Push the **contents of this `site/` folder** to the repo root (index.html,
  CNAME, css/, editions/, editorials/, and the standing pages at top level):

```bash
cd ~/workspace/objective-daily-news/site   # or wherever these files live
git init -b main
git add .
git commit -m "Objective Daily News: founding edition"
git remote add origin git@github.com:<USERNAME>/<REPO>.git
git push -u origin main
```

## 2. Turn on GitHub Pages

- Repo → Settings → Pages → Build and deployment → Source: **Deploy from a
  branch**; Branch: **main**, folder **/ (root)**; Save.
- Under "Custom domain," GitHub should pick the domain up from the CNAME file
  automatically; confirm it shows the purchased domain, then Save again.

## 3. DNS at the registrar

For an **apex domain** (example.com) point it at GitHub Pages:

```
A     @    185.199.108.153
A     @    185.199.109.153
A     @    185.199.110.153
A     @    185.199.111.153
AAAA  @    2606:50c0:8000::153
AAAA  @    2606:50c0:8001::153
AAAA  @    2606:50c0:8002::153
AAAA  @    2606:50c0:8003::153
CNAME www  <USERNAME>.github.io.
```

For a **subdomain** (news.example.com) instead:

```
CNAME news  <USERNAME>.github.io.
```

(Remove any parking/default records on the name that conflict. GitHub's docs —
"Configuring a custom domain for your GitHub Pages site" — are the authority
if any address above ever disagrees with them.)

## 4. HTTPS

- After DNS resolves (minutes to a few hours), return to Settings → Pages and
  tick **Enforce HTTPS** once the certificate shows as issued. GitHub
  provisions the Let's Encrypt certificate automatically for the custom
  domain; it cannot be ticked until the cert exists.

## 5. Verify

- Load the domain: front page renders on the cream stock, masthead centered,
  Edition No. 1 lead in the left column.
- Click through: The Watches, Editorials (and the demonstration page),
  The Shelf, About, The Fine Print, and the full edition page — check the
  OBJECTIVE stamp on the report and a SUBJECTIVE stamp on the clippings.
- Open the **Colophon** from the footer of any page: it should state the
  publisher, the desk, and the bot-run/bot-edited/bot-analyzed disclosure.
- Open each feed from the footer (RSS, Atom, JSON): Edition No. 1 should
  appear in full — the desk's report with its clippings listed beneath it.
  A feed reader pointed at the domain should also discover them on its own
  (autodiscovery tags are in every page's head).
- Check one page on a phone-width window: columns should stack, stamps stay
  legible.

## 6. Housekeeping

- `SETUP.md` (this file) can be deleted from the repo after setup; it is
  served as plain text if left in, which is harmless but untidy.
- New editions land as new files under `editions/` (same template as
  `editions/2026-11-04-morning-watch.html`) plus a front-page update. Eunice
  produces them; they publish when you clear the push — per the house rule,
  nothing expires while it waits.
- **After every new edition, regenerate the feeds** before committing:

  ```bash
  cd ~/workspace/objective-daily-news/site
  python3 make_feeds.py
  ```

  The script rebuilds `feed.xml` (RSS), `atom.xml` (Atom), and `feed.json`
  (JSON Feed) from whatever sits in `editions/`, full text, clippings
  included, and alongside them `sitemap.xml`, `news-sitemap.xml` (the
  Google News sitemap), `robots.txt`, `llms.txt`, and `llms-full.txt`.
  Run it again with `--ping` once the new files are live on the domain
  to fire the WebSub hub ping and the IndexNow submission for the new
  edition. It reads the domain from the
  `CNAME` file; while the CNAME still holds the placeholder it builds
  against a default name and warns — so after step 0 above, run it once
  more and commit the regenerated feeds and sitemaps with everything else.
  One string to check if the purchased domain is anything other than
  `objectivedailynews.com`: the canonical links in the page heads are
  written against that name — tell Eunice and she will re-point them and
  re-run the script; it is a five-minute fix, but it must not ship wrong.

## 7. Court the aggregators (owner-only, after DNS is live)

The site is built to be attractive to Google News and the other news
services — complete NewsArticle structured data with dated bylines, a
news sitemap, full-text feeds, a colophon and an About page that say
plainly who publishes and who writes. Inclusion itself **cannot be
guaranteed, only courted**.

**The regime changed in 2024–25, and this section was rewritten on
Nov 6, 2026 to match it.** Google retired manual Google News
submission: Publisher Center no longer accepts publication or feed
submissions for Google News, manually built publication pages are
gone, and inclusion is **automated eligibility only** — Google's
systems identify and rank eligible content from the crawl. Publisher
Center remains only for branding side products (News Showcase,
Reader Revenue Manager); it decides nothing about inclusion. Bing
PubHub's RSS submission path is retired the same way.

What courting means now is the record itself plus three owner clicks:

- **Google Search Console** (the one step that still matters):
  verify the domain property for `objectivedailynews.com`, then
  submit both sitemaps (`sitemap.xml`, `news-sitemap.xml`) and
  confirm they read without errors. Afterwards: keep an eye on
  Coverage and on Security & Manual Actions — that is where Google
  would say if anything were wrong.
- **Bing Webmaster Tools**: verify the same domain (it can import
  the verification from Search Console). IndexNow is already wired
  on the desk side: the key file stands at the site root and
  `make_feeds.py --ping` announces each new edition to Bing, Yandex,
  Naver, Seznam, and Yep the moment the press run lands.
- **Publisher Center**: optional, branding only. Nothing to file for
  News inclusion; do not spend an afternoon looking for the form —
  there isn't one anymore.

Already wired on the site itself, so no step is needed: full-text
RSS, Atom, and JSON feeds with WebSub push (the feeds advertise
Google's public hub, and the press run pings it); a news sitemap on
the Google News protocol carrying the last 48 hours; `llms.txt` and
`llms-full.txt` for language models; a robots.txt that names and
welcomes every documented AI crawler, per the paper's pickup
doctrine; NewsArticle and NewsMediaOrganization structured data with
dated bylines and timestamps in Eastern Time; a colophon that names
the publisher and discloses that the desk is an AI; and an About page
that states what the paper is. Keep it that way — the transparency
is part of the eligibility, not decoration.
- Monetization (AdSense, mentioned as a possibility) is deliberately NOT
  wired in. If the paper draws an audience, ask Eunice to plan it: the layout
  has no ad slots yet by design.

## 8. The podcast (added Nov 6, 2026, on Chris's commission)

The paper is also a podcast. Every edition and special report becomes
an episode, read aloud in the paper's permanent voice, and published
in the podcast feed at the site root:

```
https://objectivedailynews.com/podcast.xml
```

- **Run it with the press run**, right after the text feeds:

  ```bash
  cd ~/workspace/objective-daily-news/site
  python3 make_feeds.py
  python3 make_podcast.py
  ```

  `make_podcast.py` narrates whatever is new or changed (a hash of
  voice + spoken text in `podcast-state.json` decides), mixes the
  episode, rewrites `podcast.xml`, and updates the storage ledger
  (`podcast-storage.json`). `--skip-tts` rebuilds feed and ledger
  from audio already on disk; `--only slug,slug` narrates named
  episodes only (used for the launch backfill).
- **The voice** is a house constant in `make_podcast.py` (Helio,
  `avocado_v2:MAI_03`, the catalog's top-rated soothing male preset).
  One voice for every episode, forever, unless Chris rules otherwise;
  changing the constant re-renders the back catalog on the next run.
- **What is read**: the desk's report only — the article body, never
  the filed clippings (the subjective shelf stays in print). Spoken
  cleanup is mechanical: furniture is not re-read, tables are
  linearized, abbreviations are expanded. The only added words are
  the intro line ("Objective Daily News, [date]. [Title].") and the
  closing line. No commentary, ever — the purity law applies to
  audio exactly as to print.
- **The music**: a synthesized news theme opens every episode
  (3.2 s), a low sustained bed runs under the narration, and a
  resolving variant closes it (2.8 s). The theme files stand in
  `assets/` and are generated once by the script; every episode is
  scored identically, the way a network's theme works. Episodes are
  mono MP3 at 64 kbps, speech-first.
- **Cover art**: `images/podcast-cover.jpg` (3000×3000, RGB, under
  500 KB; a PNG twin stands beside it). The feed references the JPG.
- **Autodiscovery**: every page head carries a podcast feed link
  beside the RSS link; the front-page footer lists the Podcast feed.

### The storage watchdog

GitHub Pages' published-site soft limit is 1 GB. Audio is the only
fast-growing weight the paper carries. `podcast-storage.json` tracks
cumulative audio bytes, episode count, total site size, and the
projected days to the limit at the real cadence (four watches plus
up to one special report a day); the press run prints the running
total every time, and flags the trigger in plain words.

**Migration trigger**: when projected days remaining fall below 30,
or the site passes 750 MB — whichever comes first — episode audio
moves to a dedicated podcast host, oldest episodes first. How the
feed survives the move, so no subscriber is lost:

- Episode **GUIDs never change** (they are derived from the article
  URLs, not the audio URLs), so every podcatcher keeps its place.
- Only the enclosure URLs in `podcast.xml` re-point to the host;
  the feed itself stays at `objectivedailynews.com/podcast.xml`
  for as long as the site stands. If the feed itself ever moves,
  the old feed carries an `itunes:new-feed-url` tag (and a 301 where
  the host allows) pointing at the new one.
- A dedicated host also gives Chris the transferable host
  relationship the directories respect: the Apple Podcasts and
  Spotify listings attach to the host account, and the host provides
  the embeddable web player the site can carry.

### Submitting to the directories (owner-only; Chris's clicks)

1. **Apple Podcasts Connect** (podcasters.apple.com): sign in with
   an Apple ID, add a show by RSS feed, paste
   `https://objectivedailynews.com/podcast.xml`. Apple emails a
   verification code to the feed's owner address —
   **cabraham@gmail.com**, the address in the feed — enter it,
   confirm the show details and cover, submit. Review typically
   takes 24–72 hours (Apple says up to five business days).
2. **Spotify for Podcasters** (podcasters.spotify.com): add a show,
   paste the same feed URL. Spotify sends an 8-digit verification
   code to the same owner email; enter it, confirm ownership and
   category, submit. Listing usually appears within a few hours.
3. The Podcast Index and the smaller directories ingest the same
   feed URL; most pull from Apple or the Index once the show stands
   there. There is nothing else to file — one feed, two
   verifications, both against cabraham@gmail.com.

### Binary transfer from this seat (the open gap, Nov 6, 2026)

Episode MP3s (6–12 MB each) and the cover cannot be pushed from this
seat: the GitHub connector passes file contents on its command line,
and the operating system caps a single argument at ~128 KB (measured:
127 KB passes, 128 KB fails with "Argument list too long"), while the
snapshot validator refuses non-UTF-8 content outright. Small binaries
ride fine — the theme stings (39 KB and 35 KB) and the favicon set
went up this way. The cover at 425 KB and every episode MP3 exceed
the cap by one to two orders of magnitude, and SSH git access from
this seat is proxy-reset (the same wall the weblog's share-card PNGs
hit). **Until a seat with working git write access pushes them, the
live feed's enclosures and cover 404**; the feed itself, the pipeline,
and all fourteen episodes stand complete in this workspace. One
ordinary `git push` of `audio/`, `assets/theme-bed.mp3`,
`images/podcast-cover.jpg`, and `images/podcast-cover.png` from
Chris's laptop closes the gap in a single commit — or the audio moves
straight to the dedicated podcast host under the migration plan above,
which the storage watchdog already calls for.
