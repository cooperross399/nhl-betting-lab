#!/usr/bin/env python3
"""Make moving between the site's pages smooth, at publish.

Every page is a separate document drawn in the browser: `support.js` loads
React from unpkg, the page's own styles arrive inside the drawn page, and only
then does anything paint. Until 2026-11-02 that meant each tab click showed a
blank page in the browser's default white (on a dark site) before the new page
drew, then the fonts and the data each moved it again. Cooper: "the pages also
visibly glitch whenever i click a different tab. the website needs to run
smoother".

    python web/smooth_pages.py dist

In each `dist/*.dc.html` page this adds, right after `<meta charset>`:

- the site's own background and text colour on `html`/`body` and a dark
  `color-scheme`, so the empty page between two tabs is the site's dark, never
  white;
- a cross-document view transition (`@view-transition { navigation: auto }`,
  Chrome and Safari 18.2+; ignored elsewhere), so the browser crossfades from
  the page you left to the one you opened instead of cutting to an empty one;
- preconnects to unpkg and Google Fonts, and preloads of the exact React files
  `support.js` asks for (same URL, same integrity, so the browser reuses them),
  so the scripts start downloading while the page is still being read;
- the header's Site links on their own row on a narrow screen from the first
  paint, so they no longer jump down a row when the page's data arrives, and
  a line kept for the date above each page's headline, which is filled in
  only when the data arrives and used to push the headline down.

Board and Results also draw their tabs before their data loads, and until
2026-11-02 they drew them without Props, Season, Record or Tracker and with an
Archive tab, then redrew the full set; Board opened on "#props" also drew the
Tonight tab first. Cooper: "When i click the props and results tab it still
glitches". `PATCHES` starts those two pages with this site's tabs and the tab
the address asks for. Each patch is an exact string; a page that no longer
holds it fails the publish rather than shipping unpatched.

The shared pages (Board, Results, Archive, Graphic) are pinned byte for byte in
the committed tree; this changes only the published copies, after the pin is
checked. Running it twice adds nothing the second time. Standard library only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARK = "<!-- smooth-pages -->"
CHARSET = re.compile(r"<meta\s+charset=[\"']?utf-8[\"']?\s*/?>", re.IGNORECASE)
CDN = re.compile(r'var (REACT|REACT_DOM)_(URL|SRI) = "([^"]+)";')

# The NHL site's own colours (`--paper` and `--ink` for html[data-sport="nhl"]
# in every page's styles).
PAPER = "#14151a"
INK = "#f1efe9"

# This site's pages (`lib/sports.js` PAGE_KEYS for nhl, and site.json).
PAGES = '["season","record","tracker","methods","game"]'

PATCHES: dict[str, list[tuple[str, str]]] = {
    "Board.dc.html": [
        (
            'tab: "tonight", propView: "model",',
            'tab: /^#(props|drought)$/.test(location.hash) ? "props" : "tonight", '
            'propView: location.hash === "#drought" ? "drought" : "model", '
            f"pages: new Set({PAGES}),",
        ),
        (
            'tabs: tabsFor("tonight", null)',
            'tabs: tabsFor(this.state.tab, { status: "pending", counts: { bets: 0, leans: 0 } })',
        ),
        (
            "showScores: false, isTonight: true, isProps: false,",
            'showScores: false, isTonight: this.state.tab !== "props", isProps: this.state.tab === "props",',
        ),
    ],
    "Results.dc.html": [
        (
            "state = { vm: null, feedNotice: null, loadedFor: null };",
            f"state = {{ vm: null, feedNotice: null, loadedFor: null, pages: new Set({PAGES}), propsTab: true }};",
        ),
    ],
}


def react_files(support: Path) -> list[tuple[str, str]]:
    """(url, integrity) of the React files support.js loads, read from it so a
    runtime update can never leave a preload pointing at the wrong file."""
    if not support.is_file():
        return []
    found: dict[tuple[str, str], str] = {}
    for m in CDN.finditer(support.read_text(encoding="utf-8")):
        found[(m.group(1), m.group(2))] = m.group(3)
    out = []
    for lib in ("REACT", "REACT_DOM"):
        url, sri = found.get((lib, "URL")), found.get((lib, "SRI"))
        if url:
            out.append((url, sri or ""))
    return out


def snippet(react: list[tuple[str, str]]) -> str:
    lines = [
        MARK,
        '<meta name="color-scheme" content="dark">',
        f'<meta name="theme-color" content="{PAPER}">',
        "<style>"
        f"html,body{{margin:0;background:{PAPER};color:{INK};}}"
        "@view-transition{navigation:auto;}"
        '@media (max-width:719px){header>nav[aria-label="Site"]{flex-basis:100%;}}'
        "section div:has(+h1){min-height:1.2em;}"
        'nav[aria-label="Board sections"]{overflow-x:auto;scrollbar-width:none;}'
        'nav[aria-label="Board sections"] a{flex:1 0 auto!important;min-width:0!important;padding:0 7px!important;}'
        '@media (max-width:519px){nav[aria-label="Board sections"] a{font-size:11px!important;letter-spacing:.03em!important;padding:0 5px!important;}}'
        "::view-transition-old(root),::view-transition-new(root){animation-duration:.18s;}"
        "@media (prefers-reduced-motion:reduce){::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){animation:none!important;}}"
        "</style>",
        '<link rel="preconnect" href="https://unpkg.com" crossorigin>',
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
    ]
    for url, sri in react:
        integrity = f' integrity="{sri}"' if sri else ""
        lines.append(f'<link rel="preload" as="script" href="{url}" crossorigin="anonymous"{integrity}>')
    return "\n".join(lines) + "\n"


def patch(name: str, text: str) -> str:
    for old, new in PATCHES.get(name, []):
        if text.count(old) != 1:
            raise SystemExit(f"{name}: expected one {old!r} to patch, found {text.count(old)}")
        text = text.replace(old, new)
    return text


def smooth(dist: Path) -> list[str]:
    add = snippet(react_files(dist / "support.js"))
    changed = []
    for page in sorted(dist.glob("*.dc.html")):
        text = page.read_text(encoding="utf-8")
        if MARK in text:
            continue
        m = CHARSET.search(text)
        if not m:
            continue
        text = patch(page.name, text)
        m = CHARSET.search(text)
        page.write_text(text[: m.end()] + "\n" + add + text[m.end():].lstrip("\n"), encoding="utf-8")
        changed.append(page.name)
    return changed


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: smooth_pages.py DIST", file=sys.stderr)
        return 2
    for name in smooth(Path(args[0])):
        print(f"smoothed {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
