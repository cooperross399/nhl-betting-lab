# Drop: Due List rename + season-long tracking for props and the Due List

Base: main after nhl #310 / epl #358 / cbb #110 (node theme guard kept).

## Ship (page files only)
- web/Board.dc.html → all three repos (byte-identical)
  - Props tab: drought view renamed "Due List"; rule text removed from the view and its empty states
  - Props tab: one season line under the toggle: Props best bets · Props leans · Due List (from `record.props`, `record.propLeans`, `record.dueList`; dash until a night settles)
- web/Results.dc.html → all three repos (byte-identical)
  - Props strip gains "Props · leans · season" (`props.seasonLeans`)
  - New Due List section: last night, season, and season by category (1+ point / Anytime goal / 1+ assist), each W–L with hit rate; season also shows the prices' implied rate when given. Rows: player, category, final stat, price/book or "price not posted", Hit/Miss. Outlined, no units. Hidden when `dueList` is absent (EPL, CBB)
- web/SCHEMA.md — "Additions (season tracking: props leans, Due List)"
- web/data/sample/board_props.json, web/data/sample/results_props.json — fixture data for the above

## Pipeline must write (build_site_json.py; not shipped here)
- board.json `record.props`, `record.propLeans`, `record.dueList`
- results.json `props.seasonLeans`, `dueList {summary, season, rows}`
- Grade every Due List entry on each frozen board, priced or not; never units

## Not touched
- lib/sports.js, lib/format.js, lib/live.js
