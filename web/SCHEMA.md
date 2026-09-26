# Daily JSON contract for the NHL Projections page

The page reads two files that `Gameday Refresh` should write and commit alongside the static site:

- `data/board.json` — tonight's slate (board + graphic view)
- `data/results.json` — yesterday's settled slate (results page)

All times are UTC ISO-8601; the page renders them in the viewer's local zone. American odds are integers (`-150`, `135`). Probabilities are 0–1. `teams` is a lookup keyed by abbreviation so team colors and names ship with the data.

## board.json

```
generatedAt      ISO instant the card was built
season           "2026–27"
phase            "preseason" | "regular"  — preseason games carry schedule fields only; the page renders dashes and "model abstains"
notice           optional sentence shown under the headline (why the board is thin, degraded run, etc.)
boardDate        "YYYY-MM-DD" (league date of the slate)
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
  priced         true when this build attached market prices to the game; false renders "Not priced", never a pass
  away | home    {abbr, record, projGoals, winProb, b2b, goalie:{name, status:"confirmed"|"projected"}}  — everything after abbr optional;
                 b2b is the schedule fact (played the previous league day) and is published under either
                 verdict; projGoals, winProb and the market figures below include the back-to-back
                 adjustment only while the recorded team_b2b verdict ships it
  moneyline      {open:{away,home} | null, current:{away,home}, fair:{away,home}}  — open is the game's moneyline at the first capture in
                 line_movement/<day>.csv that held it (one capture, never the day pooled); null when none was captured, which
                 today is every game: the capture asks for no bulk h2h
  puckLine       {favorite, line, price, coverProb}
  total          {open | null, current, overPrice, underPrice, proj, overProb}  — current is the most common line among the
                 staged bulk (featured) totals, never an alternate-ladder rung; open is null, because every total a capture
                 holds is an alternate_totals rung and no row says which line is the featured one
  regulation     {away, draw, home, prices:{away,draw,home}}
  pick           {market, label, price, edgePct} | null   ← one best market per game; null on a priced game means nothing cleared the edge bar, on an unpriced game it means nothing was assessed
```

## results.json

```
generatedAt, season, phase, notice (shown when games is empty)
resultsDate      "YYYY-MM-DD"
summary          {straightUp:{w,l}, picks:{w,l,p}, totals:{w,l,p}}
teams[ABBR]      {name, short, color, fg}
games[]
  id, startUtc
  away | home    {abbr, projGoals, final}
  finish         "REG" | "OT" | "SO"
  projWinner     ABBR
  total          {line, proj, result:"over"|"under"|"push"}
  priced         the frozen board's `priced` for this game (a board frozen before that flag: whether it carried a moneyline)
  pick           {market, label, price, edgePct, result:"win"|"loss"|"push"} | null  ← null when the board carried no pick for the game;
                 the page renders it "Not priced" unless priced is true, "No play" when it is, and grades neither and shows no price
```

`web/build_site_json.py` is the reference writer. Source mapping in nhl-betting-lab: `projGoals`/`winProb`/`moneyline`/`puckLine`/`total`/`regulation` come from `models/team_model.TeamModel`, called directly rather than through `reports/card_pricing.price_team_markets`; the back-to-back adjustment reaches them only while `verdicts.ships("team_b2b")`, read from the lab's `data/outputs` as the card reads it, says it ships, so the board and the card price under one policy. `pick` is read from `data/outputs/gameday_card.json`, which `reports/gameday_card.save_card` writes from `build_card`'s card: the highest-edge team-market best bet or lean it holds for a game the staged prices matched. `record.forward` is `load_record` over `data/outputs/forward_evidence.json`, the report `forward_evidence.build_forward_report` writes: the ledger's size (wagers, markets, first and last date, unsettleable), never its return. Results finals (`final`, `finish`) are fetched live by `settle()` through `schedule_for`, a GET of the NHL schedule endpoint `api-web.nhle.com/v1/schedule/<date>` keeping games whose `gameState` is `OFF` or `FINAL`, so a Results build with no network settles nothing. The lab's game history (`build_datasets.load_team_games`) is read only to fit the model above, never to settle a game.
