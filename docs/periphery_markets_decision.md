# The periphery markets: what is wired, what is not, and why

Recorded 2026-08-27, before the 2026-27 season, so the reasoning outlives the
session that did it. The provider's NHL catalogue is larger than this lab's
eleven measured markets; this file is the decision record for all of it. The
rule applied throughout: **a market is wired only when this lab can model it
and settle it from data it already caches.** Fetching prices nothing can
consume spends credits on rows no join will ever find; pricing without honest
settlement manufactures evidence.

## What the probe established — and what it could not

`scripts/discover_nhl_markets.py` probed 43 candidate keys individually on
2026-08-26 (5 credits). Served that evening: the bulk trio, `h2h_3_way`, and
`h2h_p1` (one book, first-period moneyline). Everything else returned
nothing — **which, six weeks before the season, establishes nothing.** Books
hang props, ladders and team totals near puck drop. The same evening's
combined per-event fetch, which already asks for `alternate_spreads` and
`alternate_totals`, returned rows without error: asking for an unquoted
market is accepted and costs nothing. That asymmetry is the whole economics
of this file — carrying a speculative market in the fetch list is free until
the day it exists, at which point it is exactly what we wanted.

## Wired (2026-08-27)

- **Prop alternate ladders** (`player_points_alternate`,
  `player_goals_alternate`, `player_assists_alternate`,
  `player_shots_on_goal_alternate`, `player_blocked_shots_alternate`,
  `player_total_saves_alternate`) → the same six project markets. More lines,
  not new markets: the samples store distributions, so every rung prices
  exactly, settles identically, and lands inside markets the receipt already
  approves.
- **Anytime goal scorer** (`player_goal_scorer_anytime`) → `goals` at 0.5.
  One market, one model, one settlement — the scorer shape (player in the
  outcome name, priced as a yes) is normalised at the door, and `settle`
  already speaks yes/no.
- **Team totals** (`team_totals`, `alternate_team_totals`) → the new
  `team_total` market, the side carried in the selection
  (`home_over` … `away_under`). Priced as a marginal of the existing
  scoreline matrix (overtime goal split evenly on a regulation tie, the same
  stated assumption the moneyline makes) and settled from the boxscore's
  final. **Not in any acceptance receipt**: the card excludes it while its
  opinions freeze into the forward ledger — the same road every approved
  market walked. Approving it later is a receipt amendment in Cooper's
  hands, once the forward sample says something.

Alongside the wiring, the per-event fetch gained a **one-day horizon**: the
board holds every posted upcoming game (32 of them one August evening) and
the credit cap spends front-to-back, so an unwindowed fetch starves today's
slate to buy prices tomorrow's run would refetch anyway. The workflow cap
rose to 320 — sixteen games at nineteen asked markets under the pessimistic
bound — while the realistic bill stays what books actually quote.

## Deferred, with the reason on the record

- **Period markets** (`h2h_p1`, `spreads_p1`, `totals_p1`, and the deeper
  periods): one book already quotes `h2h_p1`. Not wired because **no period
  model exists** — the team model prices full games, and a first-period
  price derived by scaling would be an unmeasured model shipped under a
  measured one's name, the exact thing the verdicts door exists to prevent.
  Wiring collection-only would spend a credit per event per day on prices
  nothing consumes. If a period model is ever built, it starts life the way
  everything here did: walk-forward, measured against prices, gated.
- **First / last goal scorer**: settlement needs the order of goals, which
  the cached boxscores do not carry, and the model needs within-game
  dynamics no component here produces. Both would have to be built and
  measured first.
- **`player_power_play_points`, `player_penalty_minutes`,
  `player_faceoffs_won`, `player_time_on_ice`, `player_giveaways`,
  `player_takeaways`, `player_shots`**: refused by the probe, no US book
  known to quote them for NHL, and each needs its own fitted, calibrated,
  price-measured model before it could honestly appear anywhere. Deferred,
  not forgotten — the discovery workflow re-answers "is it quoted now?" for
  a handful of credits any time.
- **`outrights`** (Stanley Cup futures): a season-long liability with no
  walk-forward settlement inside this lab's day-as-unit ledger. Out of
  scope by design.

## How this gets revisited

Run the discovery workflow in-season (October, when the board is real), read
what is actually quoted, and promote a deferred market only through the full
pipeline: model, walk-forward measurement, price backtest where history
exists, forward evidence where it does not, and a human receipt before the
card may touch it.
