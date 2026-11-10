# Shots on goal's own-games spread: the ship rule

Written 2026-11-10, before `scripts/run_sog_model_study.py` was run, and not
edited after it was read. Coordinator's brief, on Cooper's ask to fix the
shots overs.

## The candidate

`player_props.SOG_OPTIONS` = {`dispersion`, `shrinkage`}: the negative-binomial
spread of shots on goal measured inside each player's own games (the hits
model's method of moments, no rink), paired with the empirical-Bayes
shrinkage of each shot rate measured against that spread. The baseline is the
model as it prices shots today (`sog_options` empty). `dispersion` alone is
measured for information and cannot ship on its own.

## The rule

The candidate goes on the card, and the x1 hold on `shots_on_goal` overs
(`clv_staking.BUMP_HELD_SIDES`) is lifted, only if all three hold:

1. **Out-of-sample log-likelihood improves.** On the walk-forward samples of
   the cached history (`generate_prop_samples`, the back-to-back verdict in
   force, every shots line in `DEFAULT_LINES`), the candidate's mean
   negative-binomial log-likelihood per player-game, paired against the
   baseline on the same player-games, has a 95% interval (bootstrap over
   games) wholly above zero.
2. **It does not lose units on the bought card-window prices overall.** At
   the 6% prop bar, one bet per wager at the best price (`run_backtest`,
   `phase="card"`), overs and unders together: the candidate's total units are
   at least zero, and at least the baseline's.
3. **It does not lose units on the forward-ledger replay.** The settled
   `shots_on_goal` wagers in the forward ledger from 2026-09-29, one per wager
   at the best frozen price, re-priced by each walk-forward model (refit every
   7 days, as the layer scoring does), population B (6% bar on the re-priced
   probability): the candidate's total units are at least zero, and at least
   the baseline's.

"Does not lose units" is read both ways (not below zero, and not below the
baseline) because the brief can be read either way; the stricter reading is
the rule. Overs and unders are reported separately in conditions 2 and 3 but
the rule reads the totals. Every interval is reported; an interval that
includes zero is no demonstrated edge, whatever the rule says.

If it fails, the card is unchanged, the hold stays, and the result is recorded
in `CLAUDE.md`.
