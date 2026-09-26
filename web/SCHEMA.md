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
resultsThrough   "YYYY-MM-DD" | null — the last league date whose results the model was fitted on; null when no model was.
                 The day's frozen history/<boardDate>.json is replaced by a board with a later resultsThrough until the
                 first game starts, and never after (web/site_history.py::supersedes)
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
  away | home    {abbr, record, projGoals, winProb, b2b, goalie:{name, status:"confirmed"|"projected"}}  — everything after abbr optional
  moneyline      {open:{away,home} | null, current:{away,home}, fair:{away,home}}  — open is the day's first line-movement capture, null when none was captured
  puckLine       {favorite, line, price, coverProb}
  total          {open | null, current, overPrice, underPrice, proj, overProb}
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
  pick           {market, label, price, result:"win"|"loss"|"push"}
```

`web/build_site_json.py` is the reference writer. Source mapping in nhl-betting-lab: `moneyline`/`puckLine`/`total`/`regulation` come from `reports/card_pricing.price_team_markets` (TeamModel), `pick` from `reports/gameday_card.build_card` selections, `record.forward` from `forward_evidence.py` + `closing_lines.py`, finals from the boxscore cache via `build_datasets.load_team_games`.
