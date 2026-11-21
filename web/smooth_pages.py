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

import json
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

# This site's pages (`lib/sports.js` PAGE_KEYS, and site.json). Record and
# Tracker were one page from 2026-11-03: Record.dc.html holds both and
# Tracker.dc.html sends its visitors there. "tracker" stays in the set because
# the shared tabsFor draws an Archive tab when it is missing; the published
# lib/sports.js (SPORTS_PATCHES) draws it as nothing.
PAGES = '["season","record","tracker","methods","game"]'

# Hold each page back until it is drawn (2026-11-03). Every page draws twice:
# once from its template, then again when its data arrives, and the second
# draw moved everything (measured on Results: one layout shift of 0.44 as the
# night's games arrived and pushed the footer and the site links down). The
# page draws nothing (the browser keeps showing the page you left) until the same-site data it asked for has
# arrived, the fonts are in and nothing has changed for 120 ms, and then it
# appears once, whole. It never waits longer than 1.6 s.
#
# Until this, a cross-document view transition crossfaded into each new page.
# It was taken out with the gate: the transition shows the new page the moment
# it first renders, which with the gate is an empty page, while without it the
# browser keeps the page you left on screen until the new one paints something
# (paint holding, Chrome and Safari). So the old page now stays up until the
# new one is ready and the two swap in one frame.
GATE = (
    "<script>(function(){var d=document.documentElement;d.classList.add('sp-wait');"
    "var n=0,saw=0,last=Date.now(),t0=last,done=0,f=window.fetch;"
    "function own(u){try{return new URL(u&&u.url||u,location.href).origin===location.origin}catch(e){return 0}}"
    "if(f)window.fetch=function(u){var o=own(u);if(o)n++;var p=f.apply(this,arguments);"
    "if(o){var e=function(){n--;saw=1;last=Date.now()};p.then(e,e)}return p};"
    "function show(){if(done)return;done=1;d.classList.remove('sp-wait')}"
    "function tick(){if(done)return;var now=Date.now(),fo=!document.fonts||document.fonts.status==='loaded';"
    "if(now-t0>1600||(saw&&!n&&fo&&now-last>120&&document.readyState!=='loading'))show();else setTimeout(tick,40)}"
    "new MutationObserver(function(){last=Date.now()}).observe(d,{subtree:true,childList:true,characterData:true,attributes:true});"
    "setTimeout(tick,40)})();</script>"
)

# Chrome draws the page a tab points at while the pointer rests on it, so the
# click shows a page already drawn, data and all. Ignored by other browsers.
SPECULATION = (
    '<script type="speculationrules">{"prerender":[{"where":{"href_matches":"/*.dc.html"},'
    '"eagerness":"moderate"}]}</script>'
)

# Record and Tracker are one page (Record.dc.html) on every site from
# 2026-11-03 (Cooper: "combine record/tracker into one page for all of the
# sports on the website"). The shared pages and lib/sports.js still draw a
# Tracker tab, or an Archive tab where a site has no Tracker; this draws
# neither. Each pattern must match exactly once, as the patches below.
NO_TRACKER_TAB: dict[str, re.Pattern[str]] = {
    "Board.dc.html": re.compile(r'\.\.\.\(hasPage\("tracker"\) \? \[tabLink\("Tracker"[^\]]*\] : \[tabLink\("Archive"[^\]]*\]\),'),
    "Results.dc.html": re.compile(r', \.\.\.\(hasPage\("tracker"\) \? \[tab\("Tracker"[^\]]*\] : \[tab\("Archive"[^\]]*\]\)'),
    "Archive.dc.html": re.compile(r', \.\.\.\(hasPage\("tracker"\) \? \[tab\("Tracker"[^\]]*\] : \[tab\("Archive"[^\]]*\]\)'),
    "Graphic.dc.html": re.compile(r', \.\.\.\(hasPage\("tracker"\) \? \[tab\("Tracker"[^\]]*\] : \[tab\("Archive"[^\]]*\]\)'),
    "lib/sports.js": re.compile(r'\n    \.\.\.\(has\("tracker"\) \? \[tab\("Tracker"[^\]]*\] : \[tab\("Archive"[^\]]*\]\),'),
}

# Under each season record on the board, how it would have paid at a stake a
# bet (1u since 2026-11-21; 0.25u before) (Cooper, 2026-11-03: "I want a tracked profit/loss for best
# bets/totals/leans/straight up underneath the record", ".25u per bet. to win
# .25u for -odds"). build_site_json.season_record writes `units` beside each
# record; a record without it keeps the old line.
PL = ('const pl = (key, alt) => { const m = r.season && r.season.money && r.season.money[key]; '
      'return m && typeof m.units === "number" ? '
      '`${m.units > 0.004 ? "+" : m.units < -0.004 ? "−" : ""}${Math.abs(m.units).toFixed(2)}u at ${m.stake ?? 1}u a bet` : alt; };\n  ')

#: The Due List's box label span, which the Hot List row relabels.
SPAN = ("<span style=\"font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.08em;"
        "text-transform:uppercase;color:var(--mute);\">")

#: The Hot List row (2026-11-19), the Due List row's shape so the same template
#: draws it. Defined beside drRow; every read is guarded.
HOT_ROW = (
    "    const HOT_UNITS = { points: [\"point\", \"points\", \"Hot · 1+ point\", \"a point\"], goals: [\"goal\", \"goals\", \"Hot · anytime goal\", \"a goal\"],\n"
    "      assists: [\"assist\", \"assists\", \"Hot · 1+ assist\", \"an assist\"] };\n"
    "    const hotRow = (x, gid) => {\n"
    "      const u = HOT_UNITS[x.market] || [x.market, x.market, `Hot · ${x.market}`, x.market], t = T[x.team] || {}, priced = typeof x.price === \"number\";\n"
    "      const isStreak = x.rule === \"streak\", n = isStreak ? x.streak : x.last5;\n"
    "      const form = isStreak ? `${x.streak} straight games with ${u[3]}` : `${x.last5} ${x.last5 === 1 ? u[0] : u[1]} in his last 5 games`;\n"
    "      const facts = [\n"
    "        typeof x.last5 === \"number\" ? { label: \"Last 5 games\", value: `${x.last5} ${x.last5 === 1 ? u[0] : u[1]}`, sub: \"\" } : null,\n"
    "        typeof x.streak === \"number\" ? { label: \"Streak\", value: `${x.streak} straight`, sub: `games with ${u[3]}` } : null,\n"
    "        typeof x.stake === \"number\" ? { label: \"Tracked at\", value: `${x.stake}u`, sub: \"on the Hot List record\" } : null,\n"
    "        typeof x.modelChance === \"number\" ? { label: \"Model's chance\", value: `${Math.round(x.modelChance * 100)}%`, sub: typeof x.modelEdge === \"number\" ? `${x.modelEdge > 0 ? \"+\" : \"\"}${(x.modelEdge * 100).toFixed(1)} pts vs the price` : \"\" } : null,\n"
    "      ].filter(Boolean);\n"
    "      return { boxLabel: isStreak ? \"straight\" : \"in last 5\", player: x.player, team: x.team || \"\", color: t.color || \"var(--ink)\", fg: t.fg || \"var(--paper)\",\n"
    "        streak: n != null ? String(n) : \"—\", category: u[2], history: `${x.lastSeason ?? \"—\"} ${u[1]} last season · ${form}`, facts, hasFacts: facts.length > 0,\n"
    "        price: priced ? F.fmtOdds(x.price) : \"—\", book: priced ? x.book || \"\" : \"price not posted\", priceColor: priced ? \"var(--ink)\" : \"var(--mute)\", juice: !!x.heavyJuice,\n"
    "        track: track({ ...x, gameId: gid, side: \"over\", line: typeof x.line === \"number\" ? x.line : 0.5, unitOne: u[0], unitMany: u[1] }),\n"
    "        aria: `${x.player}, ${u[2]}, ${form}, ${priced ? F.fmtOdds(x.price) : \"price not posted\"}` };\n"
    "    };\n"
)


PATCHES: dict[str, list[tuple[str, str]]] = {
    # The graphic's props card said every prop best bet was 0.1u, a stake
    # the card stopped using long ago; since 2026-11-21 (a 1u base) the card's
    # stake varies by tier, so the line names the count alone.
    "Graphic.dc.html": [
        (
            '${bets.length} best bet${bets.length === 1 ? "" : "s"} · 0.1u each`',
            '${bets.length} best bet${bets.length === 1 ? "" : "s"}`',
        ),
    ],
    "lib/sports.js": [
        (
            "  const strip = [\n    { label: \"Best bets · season\"",
            "  " + PL + "const strip = [\n    { label: \"Best bets · season\"",
        ),
        (
            'sub: kept(r.picks) ? `${F.winRate(r.picks.w || 0, r.picks.l || 0)} · ${nights}${missed}` : untallied',
            'sub: kept(r.picks) ? pl("picks", `${F.winRate(r.picks.w || 0, r.picks.l || 0)} · ${nights}${missed}`) : untallied',
        ),
        (
            'sub: kept(r.straightUp) ? `${F.winRate(r.straightUp.w || 0, r.straightUp.l || 0)} of games` : untallied',
            'sub: kept(r.straightUp) ? pl("straightUp", `${F.winRate(r.straightUp.w || 0, r.straightUp.l || 0)} of games`) : untallied',
        ),
        (
            'sub: kept(r.totals) ? "model side of the line" : untallied',
            'sub: kept(r.totals) ? pl("totals", "model side of the line") : untallied',
        ),
        (
            'sub: kept(r.leans) ? "recorded, not staked" : untallied',
            'sub: kept(r.leans) ? pl("leans", "recorded, not staked") : untallied',
        ),
        (
            '[{ label: "Best bets · season", value: F.recStr(data.seasonRecord.picks) }]',
            '[{ label: "Best bets · season", value: F.recStr(data.seasonRecord.picks), ...((m) => (m && typeof m.units === "number" ? { sub: `${m.units > 0.004 ? "+" : m.units < -0.004 ? "−" : ""}${Math.abs(m.units).toFixed(2)}u at ${m.stake ?? 1}u a bet` } : {}))((data.seasonRecord.money || {}).picks) }]',
        ),
    ],
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
        # The prop leans' season line with its profit at 1u a lean (0.25u until 2026-11-21)
        # (build_site_json.lean_season_line; Cooper, 2026-11-08).
        (
            'label: "Prop leans", tag: "no stake", record: rec(R.propLeans), units: "", unitsColor: "var(--ink-2)",',
            'label: "Prop leans", tag: "1u each", record: rec(R.propLeans), units: un(R.propLeans.units), unitsColor: col(R.propLeans.units),',
        ),
        # Plus-money Due List entries are tracked smaller, by price (Cooper,
        # 2026-11-10; hat tricks 0.1u from 2026-11-09 until then).
        (
            '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:var(--mute);border:1px solid var(--rule);padding:2px 6px;">Not model bets · tracked at 0.25u each</span>',
            '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:var(--mute);border:1px solid var(--rule);padding:2px 6px;">Not model bets · 1u each, less at +200 and longer</span>',
        ),
        # The tail only, so the patch holds whichever font the label is set in
        # (the 2026-11-14 redesign moved it from Barlow Condensed to Inter).
        (
            'padding:4px 9px;white-space:nowrap;">Not model bets · tracked at 0.25u each</span>',
            'padding:4px 9px;white-space:nowrap;">Not model bets · 1u each, less at +200 and longer</span>',
        ),
        # Each Due List row shows the size the season record tracks it at,
        # and a band that lost in testing is tagged (Cooper, 2026-11-10:
        # "All three"; build_site_json.drought_for_game stake, lostInTesting).
        (
            'const meta = [bar != null ? `bar ${bar} · ${x.rule}` : "", forHim].filter(Boolean).join(" · ");',
            'const meta = [x.lostInTesting === true ? "⚠ lost in testing" : "", bar != null ? `bar ${bar} · ${x.rule}` : "", forHim].filter(Boolean).join(" · ");',
        ),
        (
            'chance != null ? { label: "Model\'s chance"',
            'typeof x.stake === "number" ? { label: "Tracked at", value: `${x.stake}u`, sub: "on the season record" } : null,\n'
            '        x.lostInTesting === true ? { label: "Warning", value: "Lost in testing", sub: "this group lost money on past seasons" } : null,\n'
            '        chance != null ? { label: "Model\'s chance"',
        ),
        # 2+ point games joined the Due List on 2026-11-17 (Cooper), tracked
        # live as points over 1.5.
        (
            '      shutout: ["shutout", "shutouts", "Shutout", "a shutout", "starts", "shutout"] };',
            '      two_points: ["point", "points", "2+ points", "a 2-point game", "games", "points"],\n'
            '      shutout: ["shutout", "shutouts", "Shutout", "a shutout", "starts", "shutout"] };',
        ),
        # Cooper's Hot List (2026-11-19; nhl_betting_lab.hot_list, web/SCHEMA.md
        # games[].hot): players on a streak, listed beside the Due List in the
        # same view and the same game panel, each row labelled "Hot".
        (
            "    const byGameProps = {};",
            HOT_ROW + "    const byGameProps = {};",
        ),
        (
            'const dr = droughtRows(r.drought).map((x) => drRow(x, g.id));',
            'const dr = [...droughtRows(r.drought).map((x) => drRow(x, g.id)), ...droughtRows(r.hot).map((x) => hotRow(x, g.id))];',
        ),
        (
            'return { player: x.player, team: x.team || "", color: t.color || "var(--ink)", fg: t.fg || "var(--paper)", streak: x.drought',
            'return { boxLabel: "games w/o", player: x.player, team: x.team || "", color: t.color || "var(--ink)", fg: t.fg || "var(--paper)", streak: x.drought',
        ),
        (
            "\n" + " " * 30 + SPAN + "games w/o</span>",
            "\n" + " " * 30 + SPAN + "{{ r.boxLabel }}</span>",
        ),
        (
            "\n" + " " * 20 + SPAN + "games w/o</span>",
            "\n" + " " * 20 + SPAN + "{{ r.boxLabel }}</span>",
        ),
        (
            '>Due List · potential bets</span>',
            '>Due &amp; Hot Lists · potential bets</span>',
        ),
        (
            'drought: dr.length ? `Due List ×${dr.length}` : "",',
            'drought: dr.length ? `Due/Hot ×${dr.length}` : "",',
        ),
        # Props has three tabs (Cooper, 2026-11-19: "separate the due and hot
        # lists in two different tabs under props"): Model props, Due List and
        # Hot List. The Hot List tab is propView "hot" (#hot), drawn by the
        # Due List's own view from games[].hot; the game panel keeps both.
        (
            'const dHasField = dGames.some((g) => Array.isArray(g.drought));',
            'const dHasField = dGames.some((g) => Array.isArray((S.propView === "hot" ? g.hot : g.drought)));',
        ),
        (
            'const dGroups = dGames.filter((g) => droughtRows(g.drought).length).map((g) => {',
            'const dGroups = dGames.filter((g) => droughtRows((S.propView === "hot" ? g.hot : g.drought)).length).map((g) => {',
        ),
        (
            'e.away.score != null, rows = droughtRows(g.drought);',
            'e.away.score != null, rows = droughtRows((S.propView === "hot" ? g.hot : g.drought));',
        ),
        (
            'rows: rows.map((x) => drRow(x, g.id)) };',
            'rows: rows.map((x) => (S.propView === "hot" ? hotRow(x, g.id) : drRow(x, g.id))) };',
        ),
        (
            'const isDrought = S.propView === "drought";',
            'const isDrought = S.propView === "drought" || S.propView === "hot";',
        ),
        (
            'viewBtn("drought", `Due List · ${dCount}`)',
            'viewBtn("drought", `Due List · ${dGames.reduce((n, g) => n + droughtRows(g.drought).length, 0)}`), '
            'viewBtn("hot", `Hot List · ${dGames.reduce((n, g) => n + droughtRows(g.hot).length, 0)}`)',
        ),
        (
            'grid-template-columns:1fr 1fr;border:1px solid var(--ink);margin-top:16px;',
            'grid-template-columns:repeat(3,minmax(0,1fr));border:1px solid var(--ink);margin-top:16px;',
        ),
        (
            'title: "Due List starts with the regular season"',
            'title: `${S.propView === "hot" ? "Hot" : "Due"} List starts with the regular season`',
        ),
        (
            'title: "No Due List on this board"',
            'title: `No ${S.propView === "hot" ? "Hot" : "Due"} List on this board`',
        ),
        (
            'title: "Nobody on the Due List tonight"',
            'title: `Nobody on the ${S.propView === "hot" ? "Hot" : "Due"} List tonight`',
        ),
        (
            'propView === "drought" ? "#drought" : "#props"',
            'propView === "drought" ? "#drought" : propView === "hot" ? "#hot" : "#props"',
        ),
        (
            '(pv && /^#(props|drought)$/.test(location.hash))',
            '(pv && /^#(props|drought|hot)$/.test(location.hash))',
        ),
        (
            'propView: location.hash === "#drought" || !pv ? "drought" : "model"',
            'propView: pv && location.hash === "#hot" ? "hot" : location.hash === "#drought" || !pv ? "drought" : "model"',
        ),
        (
            'if (tab === "props" && this.state.propView === "drought") for (const g of data.games || []) { const e = byGame[g.id]; if (Array.isArray(g.drought) && g.drought.length',
            'if (tab === "props" && (this.state.propView === "drought" || this.state.propView === "hot")) for (const g of data.games || []) { const e = byGame[g.id]; if (Array.isArray(this.state.propView === "hot" ? g.hot : g.drought) && (this.state.propView === "hot" ? g.hot : g.drought).length',
        ),
    ],
    "Results.dc.html": [
        # The strip's sub line is in the shared Results page itself since
        # betting-lab-shared v14 (the CBB units under each record), so it is
        # no longer patched in here.
        (
            "state = { vm: null, feedNotice: null, loadedFor: null };",
            f"state = {{ vm: null, feedNotice: null, loadedFor: null, pages: new Set({PAGES}), propsTab: true }};",
        ),
        (
            'sub: RP.seasonLeans.nights ? rate(RP.seasonLeans) : "No night settled yet"',
            'sub: RP.seasonLeans.nights ? (typeof RP.seasonLeans.units === "number" ? `${sgn(RP.seasonLeans.units)}u at 1u a lean (less at +200 and longer) · ${rate(RP.seasonLeans)}` : rate(RP.seasonLeans)) : "No night settled yet"',
        ),
        (
            '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:var(--mute);border:1px solid var(--rule);padding:2px 6px;">Not model bets · tracked at 0.25u each</span>',
            '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:var(--mute);border:1px solid var(--rule);padding:2px 6px;">Not model bets · 1u each, less at +200 and longer</span>',
        ),
        (
            'hat_trick: ["Hat trick", "goal", "goals"], shutout: ["Shutout", "shutout", "shutouts"] };',
            'hat_trick: ["Hat trick", "goal", "goals"], two_points: ["2+ points", "point", "points"], '
            'shutout: ["Shutout", "shutout", "shutouts"] };',
        ),
        (
            '...["two_goals", "hat_trick", "shutout"].filter(',
            '...["two_goals", "hat_trick", "two_points", "shutout"].filter(',
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


def snippet(react: list[tuple[str, str]], sport: str = "nhl") -> str:
    dark = sport == "nhl"
    colours = f"html,body{{margin:0;background:{PAPER};color:{INK};}}" if dark else ""
    lines = [
        MARK,
        *(['<meta name="color-scheme" content="dark">', f'<meta name="theme-color" content="{PAPER}">'] if dark else []),
        "<style>"
        f"{colours}"
        '@media (max-width:719px){header>nav[aria-label="Site"]{flex-basis:100%;}}'
        "section div:has(+h1){min-height:1.2em;}"
        'nav[aria-label="Board sections"]{overflow-x:auto;scrollbar-width:none;}'
        'nav[aria-label="Board sections"] a{flex:1 0 auto!important;min-width:0!important;padding:0 7px!important;}'
        '@media (max-width:519px){nav[aria-label="Board sections"] a{font-size:11px!important;letter-spacing:.03em!important;padding:0 5px!important;}}'
        "html.sp-wait body{visibility:hidden;}"
        "</style>",
        GATE,
        SPECULATION,
        '<link rel="preconnect" href="https://unpkg.com" crossorigin>',
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
    ]
    for url, sri in react:
        integrity = f' integrity="{sri}"' if sri else ""
        lines.append(f'<link rel="preload" as="script" href="{url}" crossorigin="anonymous"{integrity}>')
    return "\n".join(lines) + "\n"


def drop_tracker_tab(name: str, text: str) -> str:
    pat = NO_TRACKER_TAB.get(name)
    if pat is None:
        return text
    found = len(pat.findall(text))
    if found != 1:
        raise SystemExit(f"{name}: expected one Tracker/Archive tab to drop, found {found}")
    return pat.sub("", text)


def site_sport(dist: Path) -> str:
    try:
        return json.loads((dist / "site.json").read_text(encoding="utf-8")).get("sport") or "nhl"
    except (OSError, ValueError, AttributeError):
        return "nhl"


def patch(name: str, text: str, sport: str = "nhl") -> str:
    text = drop_tracker_tab(name, text)
    for old, new in (PATCHES.get(name, []) if sport == "nhl" else []):
        if text.count(old) != 1:
            raise SystemExit(f"{name}: expected one {old!r} to patch, found {text.count(old)}")
        text = text.replace(old, new)
    return text


def smooth(dist: Path) -> list[str]:
    sport = site_sport(dist)
    add = snippet(react_files(dist / "support.js"), sport)
    changed = []
    lib = dist / "lib" / "sports.js"
    if lib.is_file():
        js = lib.read_text(encoding="utf-8")
        if NO_TRACKER_TAB["lib/sports.js"].search(js):
            lib.write_text(patch("lib/sports.js", js, sport), encoding="utf-8")
            changed.append("lib/sports.js")
    for page in sorted(dist.glob("*.dc.html")):
        text = page.read_text(encoding="utf-8")
        if MARK in text or "support.js" not in text:
            # Already smoothed, or a plain page that draws once (the Tracker
            # address that forwards to Record).
            continue
        m = CHARSET.search(text)
        if not m:
            continue
        text = patch(page.name, text, sport)
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
