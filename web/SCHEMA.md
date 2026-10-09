# Daily JSON contract for the NHL Projections page

The page reads two files that `Gameday Refresh` should write and commit alongside the static site:

- `data/board.json` — tonight's slate (board + graphic view)
- `data/results.json` — yesterday's settled slate (results page)

and the Season page reads a third, written by `Season Sim` and laid over the committed baseline by Publish Site:

- `data/season.json` — the season simulation (season page)

All times are UTC ISO-8601; the page renders them in the viewer's local zone. American odds are integers (`-150`, `135`). Probabilities are 0–1. `teams` is a lookup keyed by abbreviation so team colors and names ship with the data.

## board.json

```
generatedAt      ISO instant the card was built
season           "2026–27"
phase            "preseason" | "regular"  — preseason games carry schedule fields only; the page renders dashes and "model abstains"
notice           optional sentence shown under the headline (why the board is thin, degraded run, etc.)
boardDate        "YYYY-MM-DD" (league date of the slate)
cardGeneratedAt  ISO instant the Gameday card this board was built from was generated; null when no card was restored.
                 A regular-season board with games whose card was generated on an earlier New York day is shown but
                 never frozen into history/ (web/site_history.py::built_on_stale_state)
ratings          "xg" | "goals" | null — what every projection below is rated on. "xg": recent expected goals with a
                 finishing and a goaltending (GSAx) factor, from data/processed/shadow_team_ratings.json, which Publish
                 Site builds from the NHL play-by-play (web/build_site_json.py::rate_on_xg). "goals": that file was
                 missing or stale and the card's goals ratings were used. null: nothing was projected. The pick is
                 always the card's, whose team markets are priced on the same xG ratings (models/team_ratings.py).
record
  straightUp     {w, l} | null        — the season so far (season_record); null until a night has settled
  picks          {w, l, p} | null     — best bets, the season so far; absent/null until a night has settled
  leans          {w, l, p} | null     — leans, the season so far, kept apart from picks
  puckLine       {w, l, p} | null     — null: nothing grades the model's puck line
  totals         {w, l, p} | null     — the season so far; null until a night has settled
  season         {nights, firstDate, lastDate, missingNights, ...the four tallies}  — absent until a night has settled
  forward        {sealed: true, decisionDate, wagers, rows, markets, firstDate, lastDate, unsettleable}
                 wagers = forward_evidence.json's `wagers`: one per selection at the best price, on slates
                 whose games have all finished (null when an older report carries no wager count);
                 rows = ledger rows, one per book quote, not rendered. The return (ROI, interval, CLV) is
                 sealed until the decision date and is never in this file. The page does not show this
                 block (owner's call, 2026-10-05).
teams[ABBR]      {name, short, color, fg}
games[]
  id, startUtc, venue, city, tv
  gameType       the NHL API's game type (1 preseason, 2 regular season, 3 playoffs). Anything but 2 is published as
                 schedule only — no projection, no market figure, no pick — even on a "regular" night, and is never
                 settled; the page renders 1 as "Exhibition · model abstains"
  priced         true when this build attached market prices to the game; false renders "Not priced", never a pass
  away | home    {abbr, record, projGoals, winProb, b2b, goalie:{name, status:"confirmed"|"projected"}}  — everything after abbr optional;
                 b2b is the schedule fact (played the previous league day) and is published under either
                 verdict; projGoals, winProb and the market figures below include the back-to-back
                 adjustment only while the recorded team_b2b verdict ships it
  moneyline      {open:{away,home} | null, current:{away,home}, fair:{away,home}}  — open is the game's moneyline at the first capture in
                 line_movement/<day>.csv that held it (one capture, never the day pooled); null when none was captured (a day
                 captured before the capture asked the bulk h2h, or a build with no line_movement restored)
  puckLine       {favorite, line, price, coverProb}
  total          {open | null, current, overPrice, underPrice, proj, overProb}  — current is the most common line among the
                 staged bulk (featured) totals, never an alternate-ladder rung; open is null, because a capture's totals mix
                 alternate_totals rungs with the featured line and the board does not tell them apart
  regulation     {away, draw, home, prices:{away,draw,home}}
  pick           {kind:"bet"|"lean", market, label, price, edgePct} | null   ← one market per game: the card's highest-edge best bet, or
                 its highest-edge lean only when the game holds no best bet; null on a priced game means nothing cleared the edge bar,
                 on an unpriced game it means nothing was assessed. A pick without `kind` (frozen before it existed) reads as "bet"
```

## results.json

```
generatedAt, season, phase, notice (shown when games is empty)
resultsDate      "YYYY-MM-DD"
summary          {straightUp:{w,l}, picks:{w,l,p}, leans:{w,l,p}, totals:{w,l,p}}   ← picks counts best bets only; leans are tallied apart
seasonRecord     the same object as board.json's record.season: every frozen board before today, settled and summed.
                 Before a night has settled it is {nights: 0, firstDate: null, lastDate: null, missingNights} with no tallies
teams[ABBR]      {name, short, color, fg}
games[]
  id, startUtc
  away | home    {abbr, projGoals, final}
  finish         "REG" | "OT" | "SO"
  projWinner     ABBR
  total          {line, proj, result:"over"|"under"|"push"}
  priced         the frozen board's `priced` for this game (a board frozen before that flag: whether it carried a moneyline)
  pick           {kind, market, label, price, edgePct, result:"win"|"loss"|"push"} | null  ← null when the board carried no pick for the game;
                 the page renders it "Not priced" unless priced is true, "No play" when it is, and grades neither and shows no price
```

`web/build_site_json.py` is the reference writer. Source mapping in nhl-betting-lab: `projGoals`/`winProb`/`moneyline`/`puckLine`/`total`/`regulation` come from `models/team_model.TeamModel`, called directly rather than through `reports/card_pricing.price_team_markets`; the back-to-back adjustment reaches them only while `verdicts.ships("team_b2b")`, read from the lab's `data/outputs` as the card reads it, says it ships, so the board and the card price under one policy. `pick` is read from `data/outputs/gameday_card.json`, which `reports/gameday_card.save_card` writes from `build_card`'s card: the highest-edge team-market best bet or lean it holds for a game the staged prices matched. `record.forward` is `load_record` over `data/outputs/forward_evidence.json`, which `forward_evidence.save_forward_report` writes from `build_forward_report`'s report: the ledger's size (wagers, markets, first and last date, unsettleable), never its return. Results finals (`final`, `finish`) are fetched live by `settle()` through `schedule_for`, a GET of the NHL schedule endpoint `api-web.nhle.com/v1/schedule/<date>` keeping games whose `gameState` is `OFF` or `FINAL`. Without the network the build fails outright: `fetch_json` does not catch the error, `build_board` calls `schedule_for` first, and neither `board.json` nor `results.json` is written. The lab's game history (`build_datasets.load_team_games`) fits the model above, dates the published `b2b` chip (`rest.last_played_dates`) and decides the thin-history gate behind the schedule-only board; it is never read to settle a game.

## season.json

Written by `web/build_season_json.py` (model under `web/season_sim/`). Every figure is a projection over `sims` simulated seasons; nothing in it is a price or a pick.

```
generatedAt        ISO instant the simulation ran
season             "2026–27"
games              games per team in this season's schedule (84 from 2026-27)
sims               simulated seasons
asOf               league date the standings were read at
phase              "preseason" | "regular"  — preseason: nothing played, the whole schedule simulated
leagueGamesPlayed  games final league-wide; remainingGames = games simulated; pctPlayed = share of the season played
notice             optional sentence shown under the headline
teams[]            sorted by projected points
  abbr, name, short, color, fg, conf ("E"|"W"), div
  now              {gp, w, l, otl, pts, gf, ga, rw, row}   — the standings to date (all zero in preseason)
  proj             {pts, p10, p90, sd, w, l, otl, gf, ga}  — full-season mean and 10th/90th percentiles
  odds             {playoff, div, conf1, pres, last, bottom5, divRankDist[8], avgDivRank}  — shares of simulated seasons
  lastSeason       {pts, gp, gf, ga} | null  — the previous season's final line, for the "vs last" column
  rating           {off, ga, diff, tdOff, buOff, onIceXgf, tdXga, onIceXga, goalieGsax}  — goals per game, the model's components
  scorers[]        top five by projected points: {name, pos, age, gp, g, a, p, now:{gp,g,a,p}, last:{gp,g,a,p}|null}
  goalies[]        {name, team, age, share, starts, wins, p10, p90, p30, p35, p40, gsax60, sv3, now:{gs,w,sv}, last:{gs,w,sv}|null}
leaders            {points[30], goals[20], wins[20]}  — the same player and goalie shapes, each with `team`
notes              {asOf, returning[], out[], unknown[]}  — the availability list as read from data/season_sim/roster_notes.json,
                   and any name in it the stats API did not know (published so a typo is visible, never silently dropped)
method             {sigma, hfa, tieRate, leagueAvgPts}  — the engine's calibration, printed on the page
```

Standings to date come from the NHL standings endpoint (`api-web.nhle.com/v1/standings/<date>`) and finals from each club's season schedule (`club-schedule-season`); the previous season's line is read at the last standings day the API states for it. The page never recomputes a record: in season, `now` is the league's own table and `proj` adds the simulated remainder to it.


## Additions (props and live scores)

### board.json
```
unitDollars      number — dollars per unit for the stake line ("1 unit · $25"); default 25
games[].pick     + side   "away" | "home" | "over" | "under"  — which side the pick is on; drives the live winning/losing status
                 + line   number | null — the total's or puck line's number; null for moneyline and regulation
                 Written by build_site_json.py::pick_side_and_line from the card candidate's own selection and line.
games[].drought  [] on every regular-season game — Cooper's Due List (2026-10-07; that evening the two bars below replaced
                 the flat 5-game rule of #307), an unstaked list he picks from: 70+ points, 30+ goals or 30+ assists last regular
                 season, and a drought in that category (games dressed without one, carried across the season boundary) that
                 has reached EITHER bar. Rows come in the card's order: points, goals, assists; then rarity ascending (rarest
                 first); then drought descending; then name.
  []             {player, playerId, team, market ("points"|"goals"|"assists"), line (0.5), lastSeason (that category's total),
                 drought (games in a row without one, entering tonight), price (best American odds | null: not posted),
                 book (string | null), heavyJuice (bool: shorter than -160),
                 tierBar      int | null — the bar his last-season total sets: points 100+ 3, 85-99 4, 70-84 5;
                              goals 40+ 3, 35-39 4, 30-34 5; assists 60+ 3, 45-59 4, 30-44 5
                 surpriseBar  int | null — his own equal-surprise bar, the smallest n >= 1 with (1 - hitRate)^n <= 0.05;
                              null when hitRate is 0 (that bar never lists him; 1 when hitRate is 1)
                 hitRate      float | null — prior-season regular-season games with one in the category over games dressed
                 rarity       float | null — (1 - hitRate)^drought, rounded to 4 dp: how unlikely a drought this long is for HIM
                 oneIn        int | null — N in "1 in N for him", round(1 / (1 - hitRate)^drought) from the UNROUNDED figure
                              (the card's one_in), so the rarest rows are not quantised by rarity's 4 dp (0.25^7 is 1 in
                              16,384, where rarity 0.0001 would read 1 in 10,000); null when the figure is 0 (hitRate 1).
                              The page prints "1 in N for him" from it, with a thousands separator. A row without it (written
                              before the field existed) reads N = round(1 / rarity) instead, and a rarity of exactly 0 prints
                              the card's two spellings: "never last season" when hitRate is 1, otherwise "rarer than 1 in
                              10,000 for him". The line is omitted only when oneIn and rarity are both null.
                 rule         "tier" | "surprise" | "both" | null — which bars his drought has reached
                 band         string | null — the tier band label: "100+", "85-99", "70-84", "40+", ..., "60+", "45-59", "30-44"
                 cellRecord   {wagers, returnPct, lowPct, highPct} | null — that band's measured record from
                              data/outputs/drought_rule_backtest.json (card window, both seasons, bucket "TIER <band> @<bar>"):
                              wagers, the return and its 95% interval as percents rounded to 1 dp (the card's roi, ci_low,
                              ci_high × 100); null when the file lacks the cell, and the page then says "no record for this
                              cell". The page prints it as "This cell <droughtWindow>: ..." (the window from the board, below),
                              a number beside a number, never coloured good or bad. The keys are
                              not the forward ledger's spellings (roiPct, ciLow, ciHigh), which
                              tests/test_site_publishes_no_forward_return.py keeps off the Board page: this is the historical
                              backtest's cell, the same measurement droughtNote prints, not the sealed forward return.}
                 Each field past heavyJuice is read from the card's drought_list.json row (tier_bar, surprise_bar, hit_rate,
                 rarity, one_in, rule, band, cell_record) and is null when the row lacks it — a list the flat-rule card wrote still
                 publishes, with nulls. Nothing is computed or filled in here, and a missing price still renders "price not
                 posted". The page guards every one of these reads: a board without the drought field (EPL, CBB) and an NHL
                 board frozen before they existed render exactly as before.
droughtNote      one sentence shown above each game's list: the Due List rule (both bars, either lists him) and the
                 backtest headline, read from data/outputs/drought_rule_backtest.json
droughtWindow    string | null — the seasons the cell records were measured on, as the page's label ("2024-26": the first
                 season start to the last season's end), read from that file's card-window buckets by
                 build_site_json.py::drought_window; null when the file is missing or names no season, and the page then
                 prints "This cell:" with no window rather than a season the record was not measured on
props            {status, note, marketNotes, rows[]} | absent (absent renders "Props are not on this board")
  status         "ok" | "no_lines" | "abstain"
  note           optional sentence under the heading (or the body of the empty state)
  marketNotes    {[market]: string} — honesty badge per market, e.g. "Tested as a loss over two seasons"
  rows[]         gameId, player, playerId, team, opp, position, market, line, side ("over"|"under"), price, book,
                 projection, modelProb, fairPrice, edgePct, kind ("bet"|"lean"|"pass"), tier ("A"|"B"|null), units (number|null),
                 allowlisted (bool), starterConfirmed (true|false|null — null: not a goalie market),
                 espnId (optional — ESPN athlete id; the live tracker matches on it before falling back to name + team)
                 A row with starterConfirmed false is never written as kind "bet".
```

### results.json
```
props            {status, note, summary, season, rows[]} | absent
  summary        {w, l, p, units, ungraded} — best bets only, this date; units = profit in units
  season         {w, l, p, units, nights}   — best bets only, every settled night so far
  rows[]         the board row's gameId, player, team, opp, position, market, line, side, price, book, kind, tier, units, plus
                 actual (number | null — the player's final stat; null when he did not play),
                 result ("win"|"loss"|"push"|"void"|null), profitUnits (number, best bets only)
```
Props are never counted in `summary.picks` or `record`; team picks are never counted in `props.summary`.

### Live scores (browser only, not written by the pipeline)
The Board reads ESPN's public scoreboard (`site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates=YYYYMMDD`, from `boardDate`) and, for open live games, the game summary (`.../summary?event=ID`). Mapping tables live in `lib/live.js`: `ESPN_TO_BOARD` (team codes) and `PROP_STATS` (prop market → box-score column).


## Additions (season tracking: props leans, Due List)

board.json
```
record.props       {w, l, p, units, nights}  — prop best bets, the season so far
record.propLeans   {w, l, p, nights}         — prop leans, the season so far (no units)
record.dueList     {w, l, p, nights, stake, units, staked} — the Due List (games[].drought), the season so far, tracked as if `stake` (0.25u) were bet on every priced entry (nothing is bet)
```
results.json
```
props.seasonLeans  {w, l, p, nights}
dueList            {summary, season, rows[]} | absent (absent hides the section)
  summary          {w, l, p}  — this date
  season           {w, l, p, nights, impliedPct, stake, units, staked, returnPct, byMarket: {points|goals|assists: {w, l, units?}},
                    source ("ledger"|"boards"), and from the ledger: firstDate, lastDate, wagers, unpriced, void,
                    backfilledNights[], cardPriced}
                   impliedPct = mean implied probability of the posted prices graded (optional)
                   units = profit as if `stake` (0.25u) were bet on every priced entry; staked = stake × priced entries
                   source "ledger": read from data/processed/drought_forward.csv (the lab's Due List ledger) and
                   data/processed/drought_list/sources.json; source "boards": summed from the frozen boards
  rows[]           the board's drought entry (player, team, opp, market, line, lastSeason, drought, price, book, heavyJuice)
                   + actual (number | null), result ("win"|"loss"|"push"|"void"|null), units (number | null),
                   priceSource ("card" when the entry was published with no price and takes the card's frozen
                   price from that morning, as the lab's ledger settled it; absent otherwise)
```
Every entry on a frozen board's Due List is graded, whether or not it had a price. An entry with no price at all is graded and counted in w/l but carries no units; it shows "price not posted". Units are notional: nothing on the Due List is bet, and none of it is in `summary.picks`, `record.picks` or the props tallies.

`backfilledNights` are nights of the season before the list was first recorded (2026-10-07), rebuilt by the lab (`drought_forward.backfill_lists`) with today's rule from the games before each night and priced at the card's frozen prices that morning. `cardPriced` counts entries recorded with no price that the lab graded at the card's frozen price (`drought_forward.fill_prices`).
