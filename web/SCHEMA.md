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
record
  straightUp     {w, l} | null        — null until a season tally is kept; nothing tallies one today, so it is null
  puckLine       {w, l, p} | null     — null: nothing grades the model's puck line
  totals         {w, l, p} | null     — null until a season tally is kept
  forward        {sealed: true, decisionDate, wagers, rows, markets, firstDate, lastDate, unsettleable}
                 wagers = forward_evidence.json's `wagers`: one per selection at the best price, on slates
                 whose games have all finished (null when an older report carries no wager count);
                 rows = ledger rows, one per book quote, not rendered. The return (ROI, interval, CLV) is
                 sealed until the decision date and is never in this file.
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
summary          {straightUp:{w,l}, picks:{w,l,p}, totals:{w,l,p}}   ← picks counts best bets only; a lean is graded on its row and not here
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
