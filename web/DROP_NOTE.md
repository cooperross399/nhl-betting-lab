# Drop: Game pages, Track record, Methods (2026-10-26)

Pages only. Builders and workflows are the repo's.

## New files (nhl-betting-lab only)
- `web/Game.dc.html?id=<gameId>` — reads `data/board.json` (`games[]`, with optional `factors[]`, `ratings`, `goalie`, `final`) and `data/record.json` (for the uncertainty band on the win bar). Replaces the draft `Game.html`.
- `web/Record.dc.html` — reads `data/record.json`. Replaces `Record.html`. Never shows ROI, units or profit.
- `web/Methods.dc.html` — reads `data/ratings.json`. Replaces `Methods.html`. Anchors: `#xg #xg-sh #score-venue #gsax #goalies #lineup #home-ice #rest #form #referees #pregame #proj-goals #win #fair #edge #bet-lean #graded #changelog #ratings #defence-ratings`.
- `web/data/sample/board_game.json`, `record.json`, `record_empty.json`, `ratings.json`, `ratings_nodef.json` — preview fixtures, all labelled Sample on the page.

Off the domain the pages load the fixtures; on `*.maverickhightower.com` they always read `./data/*.json` (#305 rule).

## Shared Board (byte-identical in nhl / epl / cbb)
- Expanded card: `Where the number comes from →` → `Game.dc.html?id=`. NHL only, and only when `home.winProb` is a number.
- Expanded card: a small `?` on the Moneyline / Puck line / Total cell titles and on the pick heading, linking to the Methods anchor. NHL only.
- Tab bar: `Record` after `Season`. NHL only.
- Header: `Methods` link. NHL only.

## Usability pass (same day)
- Game: eight-step summary strip under the win bar (taps to the detail), prev/next game arrows, short band note with the long version on hover, markets stack as cards under 640px, dark team colours get a ring behind the logo.
- Record: one-sentence plain summary above the chart; tonight's biggest favourite marked on the chart and linked to its game page (reads `board.json`).
- Methods: entries fold on phones (definition always visible; a hash opens its entry), TOC follows scroll, `All 32 / Tonight` filter on the ratings table with a per-team link to the game page (reads `board.json`).
- Footer identical on Game / Record / Methods.

## Loop-closing pass (same day)
- Game: `&date=` resolves against `data/history/` like Board; breadcrumb reads "Archived board"; prev/next keep the date.
- Results (shared, NHL-gated): each settled game links to `Game.dc.html?id=&date=<resultsDate>`, so the archive copy must keep the game `id`.
- Graphic (shared, NHL-gated): "Best bet of the night" band with the eight-step bar when the top best bet has `factors`. Preview control `scenario: Sample night` off-site only.
- Hub `index.html`: NHL card gains Record and Methods links and one calibration line from `record.json` (largest bucket, no return). `about.html`: NHL blurb updated, links to Methods and Record, "Not priced" defined.
- Claude Code prompt: `deploy/CLAUDE_CODE_PROMPT_GAME_PAGES.md`.

## Efficiency pass (same day, second prompt: `CLAUDE_CODE_PROMPT_2.md`)
- Board (shared, NHL-gated): "Tonight in 60 seconds" paragraph; game link hands the game to Game.dc.html via sessionStorage.
- Archive (shared): season selector once two seasons exist.
- Record: optional `markets`, `sealed`, `dueList` blocks (shapes in the prompt); sample record extended.
- Methods: `ENTRIES[].updated` → "changed <date>" per entry.
- Not done here, in the prompt: shared repo for the six identical files, logo resize (Pillow), Pages cache headers. Background-tab polling already pauses in lib/live.js.

## Data the pages design for (absence handled)
- `game.priced:false` or no `moneyline` → "Not priced" (never "pass").
- No `factors` → "Breakdown not available for this game".
- No `goalie.name` → "Goalie not confirmed".
- `record.nights == 0` → "No night settled yet".
- `ratings.defence == null` → "Defensive ratings appear once the shift charts are cached".
- `game.final {away, home, finish, pickResult}` → After-the-game section (builder to write it after settlement; `pickResult` in win/loss/push/void).
- `total.openOverPrice/openUnderPrice` are read if present for the open → now column; otherwise the open total line is shown.

## Builder asks
- Write `data/record.json` and `data/ratings.json` on the publish run (shapes in the design prompt).
- Write `games[].factors`, `games[].ratings` into `board.json` (already in the draft shape).
- Hard-link checks in tests: the Methods anchor list above is referenced from Game.dc.html.
