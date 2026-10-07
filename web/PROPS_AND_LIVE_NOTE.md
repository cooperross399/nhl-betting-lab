# Props + live scores — handoff note

Built on `cooperross399/nhl-betting-lab@main` `web/` as of 2026-10-07 (copied into this project's `web/`). The project-root pages are an older copy without Season; they were not touched.

## New JSON fields the pipeline must write (build_site_json.py)

board.json
- `props.status`, `props.note`, `props.marketNotes`, `props.rows[]` (row fields as in the brief), plus optional `props.rows[].espnId`
- `games[].pick.side` ("away" | "home" | "over" | "under") and `games[].pick.line` (totals). Without them a pick's live status reads "unavailable"
- `unitDollars` (optional; the page already defaulted to 25)
- Rule: never write `kind: "bet"` on a row with `starterConfirmed: false`

results.json
- `props.status`, `props.note`
- `props.summary` {w, l, p, units, ungraded}, `props.season` {w, l, p, units, nights} — best bets only, kept apart from team picks
- `props.rows[]`: board row fields + `actual`, `result`, `profitUnits`

Full shapes: SCHEMA.md → "Additions (props and live scores)".

## Files touched (all under web/)
- Board.dc.html — sticky tabs (Tonight · Props · Results · Season · Archive), scoreboard strip, one-line collapsible game cards, live box, live pick status, per-game props drawer, Props tab, light/dark tokens. Existing data fields, stale banner, record strip and pick logic unchanged; "Updated" now reads "Board built" beside a separate "Live scores" stamp
- Results.dc.html — Props section with its own record strip, same sticky tabs, light/dark tokens
- lib/sports.js — added `nhlProps`, `nhlPropResults`, `PROP_MARKETS`, `PROPS_DISCLOSURE`, two HOW_TO_READ entries; `ADAPTERS.nhl` gains `props` / `propResults`. Nothing existing edited
- lib/format.js — added `fmtAgo`, `fmtIn`
- SCHEMA.md — additions section

## New files
- lib/live.js — ESPN URLs, team-code map, matching, poller (25 s live / ≤5 min pre / stop when final / paused when hidden / backoff), pick status, prop stat map
- data/sample/board_props.json, board_props_no_lines.json, board_props_abstain.json
- data/sample/results_props.json, results_props_no_lines.json, results_props_abstain.json
- data/sample/espn_scoreboard.json, espn_summary_401802031/32/33.json (preview fixtures; includes one unmatched ESPN game)

## Checked on arrival (2026-10-07, desktop session)
- ESPN team codes, read from real scoreboards for 2026-10-06 to 10-14 (all 32 clubs): only TB, NJ, SJ and LA differ from the board's codes, and `ESPN_TO_BOARD` maps all four.
- ESPN box-score columns, read from a real game (401891815): shots on goal is key `shotsTotal`, label "S". **ESPN's "SOG" label is shootout goals** (key `shootoutGoals`), so the "SOG" label fallback was removed from `PROP_STATS.shots_on_goal`. ESPN has no points column, and points = goals + assists, as the table already did.
- `pick.side` / `pick.line` are now written by `web/build_site_json.py::pick_side_and_line` (tests/test_a_pick_carries_its_side_and_line.py).
- Added: each game card lists Cooper's drought-rule players (`games[].drought`, `droughtNote`; see SCHEMA.md). The collapsed card shows "Drought rule ×N", and the expanded card shows the list with price, heavy-juice flag and the live tracker. The pipeline half is a separate PR.

## Still not verified
- Season, Archive and Graphic pages keep their light-only styling and old nav.
