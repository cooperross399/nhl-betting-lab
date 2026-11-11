# A stricter rule for shots on goal overs: the ship rule

Written 2026-11-11, before `scripts/run_sog_over_rule_study.py` was written or
run, and not edited after any result was read. Cooper's decision of
2026-11-10 ("ALL" on a decision card): "test a stricter rule for shots overs
and only switch it on if it passes on past prices."

## Why

The `shots_on_goal` overs the model selects run high: on the over
player-nights population B picked, its mean beat the realised count by 0.27
to 0.50 shots, and regressing the count on the model's mean and the
de-vigged market's gives the model 0.20 and the market 0.91. Forward
population B shots overs from 2026-10-28 hit 14.8% against a modelled 26.7%
(310 wagers, -93.1u, the coordinator's read). The own-games spread fix
passed on log-likelihood and failed on the bought card-window prices
(`docs/sog_dispersion_decision_rule.md`), so it did not ship. Shrinking the
mean toward the market is arithmetically the same as raising the bar, so
this tests the bar and its relatives directly, and nothing in the model.

## The candidates (fixed here, three, no others)

Each acts on `shots_on_goal` **overs only**; unders and every other market
are untouched. Each is a constant in `reports/gameday_card.py`, in the
pattern the card already uses for points and assists.

1. **`bar`: a higher edge bar, 12%.** A shots over is listed (and so can be
   staked) only when its edge is at least 12%, the card's own prop best-bet
   bar (`BEST_BET_PROP_EDGE`), where every other prop needs 6%. 12% is chosen
   because it is a bar the card already uses, not because of any result.
2. **`cap`: a price cap, +200.** A shots over priced longer than +200 is
   neither listed nor staked, the cap `LEAN_MAX_PRICE` already puts on points
   overs. Long overs are the high rungs, where the one league-wide spread
   overstates the tail (5.5+ overs modelled 5.8%, landed 4.5%).
3. **`exclude`: the side excluded.** Shots overs are neither listed nor
   staked (`LEAN_EXCLUDED_SIDES`, as for points and assists unders).

## What is measured

For each candidate, **R** is the set of population-B shots overs it removes.
Its improvement is **D = -(units of R)**: removing a set that lost improves
the card by what it lost. Flat 1u at the best price, one bet per wager.

- **Bought prices (history).** The bought `card` window
  (`historical_prop_prices.csv`, `run_backtest(phase="card")`), one bet per
  wager at the best price, priced by the walk-forward props model with the
  layers the card prices shots with today (`team_form`, `position_matchup`,
  `scoring_env`, the back-to-back verdict in force; `sog_options` empty, as
  on the card), population B at the 6% prop bar. Seasons are 2024-25 and
  2025-26, split on the game date (before or from 2025-08-01).
- **Forward ledger.** `forward_evidence.csv` as Gameday Refresh carries it:
  `shots_on_goal`, `snapshot_date` from **2026-10-22**, collapsed to the
  best frozen price per wager (`closing_lines.collapse_to_best`), settled
  (won, lost, push), clearing the 6% bar on the frozen edge
  (`forward_evidence.clears_edge_bar`), selection `over`. Halves: the
  distinct settled snapshot dates in order, the first half being the first
  ceil(n/2) dates.

Intervals are game-clustered (`stats.clustered_mean_interval`, game = home,
away, league game date), as the props backtest and forward report count
since #455 and #258.

## The rule

A candidate **passes** only if every one of these holds:

1. **History improves, in both seasons.** D > 0 on the bought card-window
   prices pooled, and D > 0 in 2024-25 and in 2025-26 separately.
2. **The ledger improves, in both halves.** D > 0 on the forward ledger from
   2026-10-22 pooled, and D > 0 in each half.
3. **The ledger's improvement is demonstrated, corrected for three
   candidates.** The return of R on the forward ledger, game-clustered, with
   its Bonferroni interval across the 3 candidates (two-sided 1 - 0.05/3,
   `looks=3`), sits wholly below zero.
4. **Enough to read.** R holds at least 30 wagers on each source.

If more than one passes, the one that removes the **fewest** forward-ledger
overs ships, as the least change that passes. If none passes, the card is
unchanged, `clv_staking.BUMP_HELD_SIDES` keeps holding shots overs at x1,
and the result is recorded in `CLAUDE.md`.

Every figure is reported with its sample size: D, R's units, return and
both intervals (plain 95% and corrected), on each source, pooled and split,
and the overs kept. An interval that includes zero is no demonstrated edge,
whatever the rule says.

## What shipping changes

Stakes and listing only. The snapshot is frozen before `build_card`, so the
forward ledger, population B and the 2027-04-25 registered test are
unchanged: the ledger keeps freezing and settling shots overs, so the rule's
own evidence keeps accumulating. The model, the edge bars of every other
market and side, the market list and the allowlist are unchanged.
