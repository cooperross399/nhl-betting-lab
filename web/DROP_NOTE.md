# Drop: EPL and CBB on the NHL page set · one look per site · fewer words

Base: `nhl-betting-lab@main` 0f13534 (#308, #309). The same page files ship to all three repos:
`web/Board.dc.html`, `web/Results.dc.html`, `web/Archive.dc.html`, `web/Graphic.dc.html`, `web/lib/live.js`
(byte-identical in nhl-betting-lab, epl-betting-lab, cbb-betting-lab). `web/Season.dc.html` is NHL only.
`lib/sports.js` and `lib/format.js`: unchanged; EPL and CBB already carry the same bytes as NHL main.

## Per repo
- nhl-betting-lab: the five pages + `web/lib/live.js`
- epl-betting-lab: the four shared pages, `web/lib/live.js` (new to this repo), `web/data/sample/espn_scoreboard.json` (new), `web/data/sample/board.json` (sample picks gain `side`/`line`)
- cbb-betting-lab: same as EPL
Project copies: `web/` (NHL), `epl/web/`, `cbb/web/`.

## Look
- NHL always dark. EPL gray, CBB white; both switch to darker variants (charcoal, navy) with the phone's dark mode
- Chosen from the hostname before the page paints (`html[data-sport]`), then from site.json; the browser bar colour follows
- The share card on Graphic keeps its fixed colours

## Shared with NHL now
- Sticky tabs (EPL: This week · Results · Archive; CBB: Tonight · Results · Archive; Props and Season stay NHL only)
- Scoreboard strip, one-line collapsible cards, live box, live pick status, unmatched marker, poller rules
- No box-score fetches on EPL/CBB (nothing there tracks a player stat)

## lib/live.js (additive; NHL paths untouched)
- `LIVE_SPORTS`, `scoreboardUrlFor`, `parseScoreboardFor`, `stateLabelFor`, `matchEventsFor`, `pickStatusFor`
- EPL: `soccer/eng.1`, one request over the window's dates; ESPN MNC→MCI, MAN→MUN. Clock "67'", HT, FT
- CBB: `basketball/mens-college-basketball`, `groups=50` (Division I). Codes mapped where known (CONN→UCONN, VILL→NOVA …); otherwise a team matches on its board name. ESPN games with neither team on the board are ignored (most of a CBB night); one board team without a match shows "Unmatched"
- Live pick status needs `pick.side` (+ `pick.line`): EPL total/BTTS/1X2/DNB, CBB moneyline/spread/total. Corners are not tracked. **EPL and CBB builders don't write side/line yet**; until they do, no live status shows (no guess)

## Fewer words (all three sites)
- Removed: headline blurbs, strip fine print, footer links, "Recorded, not staked", box/tracker loading text
- Pass reasons shortened to "No play" / "Not priced" / "Abstains"
- Note banners: first sentence, rest behind a tap
- Sample banners: "Sample data, not tonight's board." / "Live feed unreachable · showing sample data."
- Sparkline notes: "▼ 10" (dropped "over N refreshes")
- Also: NHL Total cell as Line / Over / Under / Proj (was missing from main); CBB Current line and price on separate rows; cell values wrap under their label instead of dropping a line
