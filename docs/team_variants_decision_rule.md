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

## Result (Shadow Stats run 39550297681, 2026-10-21)

3,798 games every variant priced, 2023-11-22 to 2026-10-19, bought team
prices. Units are ROI x bets as the report prints them (ROI to 0.1%, so each
figure is good to about half a unit per market).

| Ratings | `late` units (ML / PL / totals = sum) | `early` units (sum) |
|:--|:--|:--|
| xG ratings (live) | -17.8 / +6.0 / -42.5 = **-54.3** | +23.5 / +29.6 / -15.2 = **+37.9** |
| Context xG (PostHockey) | -16.7 / +11.2 / -57.3 = -62.8 | +30.2 / +22.4 / -18.2 = +34.4 |
| Shooter-adjusted xG (PostHockey) | -2.7 / +1.3 / +3.0 = +1.6 | +30.1 / +21.7 / -36.8 = +15.0 |
| xG + per-team home ice | -1.8 / +11.3 / -52.9 = -43.4 | +28.0 / +32.8 / -23.4 = +37.4 |

- Context xG: worse than live in both windows. Fails rule 1.
- Shooter-adjusted xG: +55.9u better in `late`, 22.9u worse in `early`.
  Fails rule 1.
- Per-team home ice: +10.9u better in `late`, level in `early` (-0.5u, inside
  rounding), and its `late` totals lose 10.4u against live. Fails rule 2.

Every interval in every row spans zero: no demonstrated edge for any of them,
live included. **Nothing switches.** The card keeps the live xG ratings.

The Props Form Test re-run (run 39549738985, `card` window) repeated the
2026-10-09 result: recent form -33.7u over 24,714 against long-run -0.7u over
28,549, -32.9u. It does not switch either.

## What happened next (2026-10-21)

Cooper overrode the rule the same day: "I dont give a shit if you find that
it makes more money. I am telling you that i want it to affect the model. I
know it will", and "We will always be betting picks the day of". From the
card of 2026-10-22 the team markets are priced on shooter-adjusted xG with
GSAx(sh) and each team's own home ice, together. The rule above is left as
written; this switch did not pass it, and is his decision.
