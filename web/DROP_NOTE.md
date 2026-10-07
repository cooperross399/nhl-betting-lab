# Drop: drought-rule design, Props drought view, tab bar + dark theme on every page

Base: `nhl-betting-lab@main` after #304 (Board.dc.html @7c6f15a8d9ad).

## Ship (page files only)
- web/Board.dc.html — drought list redesigned (expanded card) and a "Drought rule" view on the Props tab; `#drought` deep-links to it
- web/Results.dc.html — theme tokens gain `--desk` (no visual change)
- web/Season.dc.html, web/Archive.dc.html — sticky tab bar (Tonight · Props · Results · Season · Archive), About + other sports in the header, light/dark tokens, `theme` preview prop
- web/Graphic.dc.html — tab bar and dark theme on the page around the card; the 1080 × 1350 card keeps fixed colours so the exported image is the same in either theme
- web/data/sample/board_props.json — one pre-game drought row added (Keller, LAK @ UTA) so the fixture shows a not-yet-started entry

## Not touched
- web/lib/sports.js, web/lib/format.js, web/lib/live.js — no changes this drop
- web/SCHEMA.md — no new fields; the page reads `games[].drought` and `droughtNote` exactly as #304 documents

## Drought rule on the page
- Each entry: games-without streak (large), player + team chip, category (1+ point / Anytime goal / 1+ assist), last-season total, price and book or "price not posted", a "Heavy juice" flag (`heavyJuice`), and the live progress bar once the game starts
- Labelled "Your list · not model bets · no stake" on the card and "Not model bets" on the Props view. Outlined, never the filled Best bet box, never units
- Props → Drought rule lists the whole night by game, with empty states for preseason, a board without the field, and a night where nobody qualifies
