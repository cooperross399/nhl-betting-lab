# Season simulation backtest

**Status, 2026-10-26: not yet run. There are no before/after numbers here yet.**

`scripts/backtest_season_sim.py` scores the season engine on 2024-25 and
2025-26. It projects each season from the standings after about 10, 20 and
41 games a team and compares the projection with the final table:

* points RMSE (the projected mean against final points),
* Brier score and log loss of the playoff odds against the sixteen teams that made it,
* 10th-90th range coverage (0.80 is calibrated).

It tunes the jitter (`SIGMA`, either fixed or shrinking with games played)
and the in-season update weight (`K_TEAM_UPDATE`) on 2024-25 and checks the
result on 2025-26. It also scores how far to blend the team strengths toward
the card's PostHockey-style ratings, using weights 0, 0.25, 0.5, 0.75 and 1,
with those ratings rebuilt as of each checkpoint by
`scripts/run_shadow_stats.py --tables-only --ratings-as-of`.

It could not run where it was written. That sandbox has no route to
`api-web.nhle.com`, `api.nhle.com` or `moneypuck.com`, and the
`data/raw/season_sim` cache did not exist there. So nothing was measured and
no engine setting was changed. `SIGMA` stays at 0.05 fixed and
`K_TEAM_UPDATE` at 30.

Two new choices ship without a measurement:

* The blend toward the card's ratings, at 0.5. This is the card's own
  weight for PostHockey's number, and Cooper asked for it.
* The playoff strength shrink of 0.479, which is PostHockey's published value.

Run it from Actions → **Season Sim Backtest** → Run workflow. It needs no
terminal and spends no credit. When it finishes, its `season-sim-backtest`
artifact holds this file with the numbers filled in. A setting changes only
if it holds on the season it was not tuned on.
