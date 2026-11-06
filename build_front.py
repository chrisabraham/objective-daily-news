#!/usr/bin/env python3
"""Build the ODN front page (index.html) from the newest publications.

Doctrine (SPEC.md, "Front-page doctrine — the briefing broadsheet",
Chris rulings Nov 6, 2026): the front page is a BRIEFING broadsheet,
not the full record and not the kitchen sink.

  - Lead position (the headline slot): the NEWEST PUBLICATION OF ANY
    KIND by publication time — edition or special report. A special
    report holds the lead from its publication until the next desk
    report (watch edition) publishes; symmetrically, no older item
    leads over a newer one. The lead is resolved at press time from
    the newest item's own title block (kicker, stamp, headline, deck,
    byline travel with the item) — never hardwired to a fixed title,
    watch, or item type.
  - BELOW THE LEAD the sheet is COMPOSED EDITORIALLY, never a
    mechanical reverse-chron stream: the desk selects and orders the
    sub-lead zone at press time (weight, subject grouping, natural
    adjacency), within the fixed container budgets. In this builder
    the composition step is the desk's explicit choice of the second
    brief and of the special-report band contents/order; everything
    not chosen stays off the front. Blog-format tells (infinite
    stream, uniform post cards, "recent posts" placement logic) are
    banned below the fold.
  - Brief shape: the lead is briefed in depth — title block plus
    whole sections complete in themselves until the briefing budget
    (~1,100 words of body) is spent; the next section contributes its
    first paragraph and a "briefing continues in the edition" road
    in. The clippings link rides at the lead's foot when the lead is
    an edition. The full text lives on the item's own page.
  - Second brief: title block and its first two sections in full,
    then the continue line.
  - Rail: The Briefs capped at twelve (the SPEC's own number); The
    Log So Far capped at the latest six editions plus a link to the
    full log on the Watches page. The rail is cut to the sheet so the
    two columns close together; the broadsheet does not grow to bury
    a mismatch.
  - Everything else on the page — masthead, folio, edition line, the
    special-report bands above the fold, the remaining rail boxes,
    the clippings strip, the footer — is carried over from the
    existing index.html untouched. Per-edition facts that live in
    those carried-over regions (edition line, Watches Today, Still
    Uncalled, In This Edition, the strip) remain the desk's per-run
    edits, as they were under the dated build-front scripts this
    replaces.

Usage: build_front.py [lead_file second_file]
With no arguments it rebuilds the Nov 6, 2026 state: lead = Edition
No. 11 (Midday Watch, newest publication at press time, 1200 EST),
second = Edition No. 10 (Overnight Watch). The desk passes the lead
and second files explicitly at each press run — that explicit choice
IS the composition step; internal links inside article bodies are
rebased to the site root (editions/…, special-reports/…).
"""
import re
import sys

SITE = '/home/hatch/workspace/objective-daily-news/site'
BRIEF_BUDGET = 1100  # words of body in the lead brief, title block excluded
BRIEFS_CAP = 12
LOG_CAP = 6


def words(s):
    import html as H
    t = re.sub(r'<[^>]+>', ' ', s)
    return len(H.unescape(t).split())


def article_inner(path):
    doc = open(path, encoding='utf-8').read()
    return re.search(r'<article class="article">(.*?)</article>', doc, re.S).group(1)


def rebase(art):
    # Front page carries NO audio anything (standing law, Chris Nov 6):
    # strip listen players the podcast build embeds in edition bodies.
    art = re.sub(r'\s*<p class="odn-listen">.*?</p>', '', art, flags=re.S)
    art = re.sub(r'href="(20\d\d-\d\d-\d\d-[^"]+)"', r'href="editions/\1"', art)
    art = art.replace('href="../special-reports/', 'href="special-reports/')
    art = art.replace('href="../editions/', 'href="editions/')
    return art


def title_block(art, ed_url):
    tb = re.split(r'(?=<h2)', art, maxsplit=1)[0]
    tb = tb.replace(
        '<div class="stamp-row"><span class="stamp stamp-objective">Objective</span></div>',
        '<p><span class="stamp stamp-objective">Objective</span></p>')
    m = re.search(r'<h1>(.*?)</h1>', tb, re.S)
    tb = (tb[:m.start()]
          + f'<h1 class="headline"><a href="{ed_url}">' + m.group(1) + '</a></h1>'
          + tb[m.end():])
    return tb.strip()


def sections(art):
    rest = art[art.find('<h2'):]
    return [s for s in re.split(r'(?=<h2)', rest) if s.startswith('<h2')]


def lead_brief(art, ed_url, clips_count=None, continue_label='the edition'):
    body, total = [], 0
    secs = sections(art)
    for i, s in enumerate(secs):
        w = words(s)
        if total + w <= BRIEF_BUDGET or not body:
            body.append(s.strip())
            total += w
            continue
        p1 = re.search(r'(<h2.*?</h2>)\s*(<p[^>]*>.*?</p>)', s, re.S)
        if p1 and total + words(p1.group(2)) <= BRIEF_BUDGET + 220:
            body.append(p1.group(1) + '\n' + p1.group(2) + '\n'
                        f'    <p class="continue"><a href="{ed_url}">The briefing continues in {continue_label} &mdash; the full record &rarr;</a></p>')
        break
    inner = title_block(art, ed_url) + '\n\n' + '\n'.join(body)
    if clips_count:
        inner += (f'\n    <p class="continue"><a href="{ed_url}#clippings">'
                  f'The {clips_count} clippings filed with this edition &rarr;</a></p>')
    return '  <article class="lead">\n' + inner + '\n  </article>'


def second_brief(art, ed_url, continue_text):
    secs = sections(art)
    inner = (title_block(art, ed_url) + '\n\n'
             + '\n'.join(s.strip() for s in secs[:2])
             + f'\n    <p class="continue"><a href="{ed_url}">{continue_text}</a></p>')
    return '  <article class="lead second">\n' + inner + '\n  </article>'


def cap_list(src, heading, cap, extra_li=None):
    m = re.search(r'(<h3>' + re.escape(heading) + r'</h3>\s*<ul>)(.*?)(</ul>)', src, re.S)
    assert m, f'box not found: {heading}'
    items = re.findall(r'<li>.*?</li>', m.group(2), re.S)
    kept = items[:cap]
    if extra_li:
        kept.append(extra_li)
    new = (m.group(1) + '\n' + '\n'.join(kept) + '\n      ' + m.group(3))
    return src[:m.start()] + new + src[m.end():]


def item_url(rel):
    return rel if '/' in rel else f'editions/{rel}'


def build(lead_rel, second_rel):
    idx = open(f'{SITE}/index.html', encoding='utf-8').read()

    lead_path = f'{SITE}/{lead_rel}'
    art = rebase(article_inner(lead_path))
    lead_doc = open(lead_path, encoding='utf-8').read()
    clips_count = len(re.findall(r'<div class="clip">', lead_doc)) or None
    lead = lead_brief(art, item_url(lead_rel), clips_count,
                      'the edition' if lead_rel.startswith('editions/') else 'the report')
    m = re.search(r'  <article class="lead">.*?</article>', idx, re.S)
    assert m, 'lead article not found'
    idx = idx[:m.start()] + lead + idx[m.end():]

    art2 = rebase(article_inner(f'{SITE}/{second_rel}'))
    second = second_brief(
        art2, item_url(second_rel),
        'Continue to the full edition &mdash; the rest of the watch, the cocked hat, '
        'and the clippings filed with it &rarr;')
    m = re.search(r'  <article class="lead second">.*?</article>', idx, re.S)
    assert m, 'second article not found'
    idx = idx[:m.start()] + second + idx[m.end():]

    idx = cap_list(idx, 'The Log So Far', LOG_CAP,
                   '<li><a href="watches.html">The full log &mdash; every edition of the paper &rarr;</a></li>')
    idx = cap_list(idx, 'From the Shelf &mdash; The Briefs', BRIEFS_CAP)

    open(f'{SITE}/index.html', 'w', encoding='utf-8').write(idx)
    lead_words = words(lead)
    rail = idx[idx.find('<aside class="rail">'):idx.find('</aside>')]
    print(f'front rebuilt: lead brief {lead_words} words; '
          f'rail {words(rail)} words; index {len(idx)} bytes')


if __name__ == '__main__':
    lead_rel = sys.argv[1] if len(sys.argv) > 1 else 'editions/2026-11-06-midday-watch.html'
    second_rel = sys.argv[2] if len(sys.argv) > 2 else 'editions/2026-11-06-overnight-watch.html'
    build(lead_rel, second_rel)
