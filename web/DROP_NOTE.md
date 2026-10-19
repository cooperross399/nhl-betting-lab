# Drop: Due List row facts

Base: nhl-betting-lab main as of 2026-10-19 (stat-side tag, Due List tracked at 0.25u, Results Due List units and notes all kept; the stat-side tag now shows on every sport). typeof document guard and on-site scenario/ESPN lines kept.

## Ship (page files only)
- web/Board.dc.html → all three repos (byte-identical)
  - Due List rows (game card and Props → Due List): the two muted lines ("bar N · rule", "1 in N for him", "This cell …") become one row of labelled cells: Bar (N, which bar), For him (1 in N), This cell <droughtWindow> (return over wagers, 95% interval beneath). Plain ink, no good/bad colour, no units. Same guards: absent fields show nothing, a null cellRecord reads "no record"
  - `meta` / `record` strings kept for the row's aria-label
- web/PROPS_AND_LIVE_NOTE.md — "Drought List" → "Due List"

- Props view: removed the "No demonstrated edge" badge, the disclosure sentence and the board's props note ("Only best bets are listed; N other priced props…")
- web/Results.dc.html → all three repos: props line now reads "Graded apart from team picks."

- Plain language (Board, Results → all three repos; Season NHL only; hub about.html): pages swap the shared lib's jargon for display only (`Component.PLAIN`): "edge bar", "allowlisted", "Recorded, not staked", "Profit on turnover", "Time to an answer", "ROI", "95%" → plain words. Due List cells read Games needed / How rare / Past picks like this <window> · likely range. The aria/meta/record strings the drought test pins are unchanged
- about.html: "How picks are chosen", "How results are graded" and "Reading a board" rewritten in plain words

- Board/Results: `Component.plainNotice` keeps only visitor-relevant sentences of the builders' `notice` and says them plainly ("Nothing worth a bet this week.", "No picks tonight. Projections and odds are shown.", "Preseason games. …"). Run diagnostics (staging, artifacts, allowlists, model floors, "no demonstrated edge") are not shown. The collapsible Note block is a single paragraph

- One strip for every sport (Board): the NHL season records (Best bets, Straight up/Favoured side, Totals, Leans). EPL's "Profit on turnover" / "Awaiting results feed" / "Time to an answer" and CBB's per-market ROI / "Time to an answer" cells are gone. EPL's best-bet W–L is derived from the record it publishes today (won / settled − won − void); the other three read a dash until the builder publishes them (deploy/CLAUDE_CODE_PROMPT_PARITY.md)
- EPL cells in the NHL shape: Match result (price · fair), Total 2.5 / Both teams to score / Draw no bet as Open / Current / Fair / Model, fair price computed from the model's probability. Open reads a dash until the builder publishes open prices

- Due List on EPL (and any board without model props): a "Due List" tab with the night's/week's count opens the list view directly (same rows, bars, rarity and note as NHL); the Model props / Due List switcher and the props season lines show only where model props exist. Game headers read "HOME v AWAY" and kickoff on EPL. Live per-player tracking says "unavailable" off NHL rather than guessing. Results' graded Due List and the season line wait on the builder (deploy/CLAUDE_CODE_PROMPT_PARITY.md §3)

- epl web/data/sample/board.json: sample Due List rows + droughtNote so the tab renders in preview. Match result cell shows "fair +163" alone while the feed has no 1X2 price

- Team logos (Board, Results, Graphic): every team circle shows `teams[abbr].logo`, else `./logos/<ABBR>.png`, over the coloured abbreviation (shown when the image is missing). Collapsed rows get 18px logos instead of colour dots. Builder + fetch script in the drop prompt (Part 1b)

## Not touched
- lib/sports.js, lib/format.js, lib/live.js
- web/SCHEMA.md (props.note and PROPS_DISCLOSURE still exist, just not rendered)
