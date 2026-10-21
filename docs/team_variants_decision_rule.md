# Team-rating variants and per-team home ice: the rule, fixed before the run

Written 2026-10-21 05:35 UTC, before any result from the extended
`run_shadow_stats.py --price-backtest` (Shadow Stats, `price_backtest`) was
read. Cooper asked for the shadow models and per-team home ice to be re-tested
and switched on if they win ("Yes do all tht", 2026-10-21).

Candidates, each against the live xG ratings (`xg_luck`) on identical games
and the bought team prices (moneyline, puck line, totals), one bet per wager at
the best price, flat stakes, the measurement's edge bar:

- `xg_context_luck` (PostHockey context xG)
- `xg_shooter_gsax` (PostHockey shooter-adjusted xG)
- `xg_team_home` (live ratings plus per-team home ice, two years of goals,
  shrunk at 150 games; constants fixed in the script before the run)

A candidate replaces the live ratings on the card only if **all** hold:

1. Summed over the three markets, its units beat the live ratings' in the
   `late` window AND in the `early` window.
2. In the `late` window (nearer the card's), no single market loses more than
   5 units against the live ratings.
3. If more than one candidate passes, the one with the larger `late`-window
   gain ships; candidates are not combined (a combination was never measured).

Otherwise nothing changes. No edge is claimed either way: every interval is
expected to span zero, and choosing among three is a search. A switch, if one
happens, restarts the team-market half of the forward test as the
2026-10-05 xG switch did.

The Props Form Test (recent form vs long-run rates on bought prop prices) is
held to the same shape: it ships only if it beats long-run in both the `card`
window it reports and its overall total. Its 2026-10-09 result was -33.7u over
24,714 bets against long-run; the bought prices have not changed since, so the
re-run is expected to repeat it.
