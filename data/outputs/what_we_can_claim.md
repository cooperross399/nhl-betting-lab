# What the evidence actually supports

Generated from the measurement outputs, so it cannot drift from them. The hand-written rules live in `docs/what_we_can_and_cannot_claim.md`.

- Generated: 2026-08-29T00:21:37+00:00

**No demonstrated edge in any market.** 9 market(s) have been measured against real prices. Nothing survives correcting for the number of markets tested and then holds on a window it was not found on. What *has* survived both tests is a loss: `points`. A replicated deficit is a finding, not a null result, and it is the finding the model has.

## Across every measured market

-3.2% over 36,449 bets. The interval excludes zero on this sample.

## Measured against real prices

- `shots_on_goal`: -2.2% over 16,925 bets, 95% interval -3.8% to -0.7%. The interval excludes zero even after correcting for the 7 markets measured on the same data — which is not the same as an edge that will persist, and means nothing until it replicates on a window it was not found on.
- `points`: -6.6% over 9,047 bets, 95% interval -8.6% to -4.6%. **Replicated** on the player_props_backtest_2025-26 window.
- `goals`: -3.8% over 282 bets, 95% interval -18.1% to +10.6%. **No demonstrated edge**.
- `assists`: -3.6% over 4,127 bets, 95% interval -6.2% to -1.0%. Correcting for the 7 markets measured on the same data, it does not exclude zero. **No demonstrated edge**.
- `goalie_saves`: -5.7% over 3,118 bets, 95% interval -9.0% to -2.3%. The interval excludes zero even after correcting for the 7 markets measured on the same data — which is not the same as an edge that will persist, and means nothing until it replicates on a window it was not found on.
- `blocked_shots`: +4.5% over 2,950 bets, 95% interval +0.7% to +8.3%. Measured again on the player_props_backtest_2025-26 window and **not confirmed** there, so **no demonstrated edge**.
- `moneyline`: -2.4% over 1,504 bets, 95% interval -8.0% to +3.1%. **No demonstrated edge**.
- `puck_line`: -4.3% over 1,541 bets, 95% interval -8.7% to +0.1%. **No demonstrated edge**.
- `total_goals`: -0.5% over 1,150 bets, 95% interval -6.0% to +5.0%. **No demonstrated edge**.

## Not measured against real prices

- `hits` has **no price-based measurement**: Not offered in any historical snapshot across 256 probed events spanning two seasons, so it cannot be measured against past prices. It is served live; its evidence must accumulate forward. It has been calibration-checked on 616,730 walk-forward samples, which can rule the model out and can never rule it in. That is not evidence of an edge and is not offered as any.
- `regulation_3_way` has **no price-based measurement**: the provider serves it per-event only, with no bulk history; its evidence accumulates forward once the season starts.
- `team_total` has **no price-based measurement**: no historical prices have been bought for it yet.

A market in this list is **not** a market judged to have no value. It is a market with no price-based evidence either way, and nothing in this repository will present the two as the same thing.

## How much data would settle it

| If the true edge were | Bets needed to separate it from zero |
|----------------------:|-------------------------------------:|
| +5% | ~1,537 |
| +8% | ~601 |
| +10% | ~385 |
| +15% | ~171 |

The NHL's advantage over a smaller league is volume: about 1,312 regular-season games a season with many prop markets per game. That is the reason props are the centre of this lab — not because prop edges are believed to be larger, but because props are the only part of the system that can accumulate enough bets to ever be measured.

## What the card is actually allowed to use

- Provider policy: **Allowlisted**
- Allowlisted markets: **assists, blocked_shots, goalie_saves, goals, hits, moneyline, points, puck_line, regulation_3_way, shots_on_goal, total_goals**

## Standing notes

- An interval that includes zero means **no demonstrated edge**. Not 'promising', not 'trending positive', not 'small but positive'.
- Calibration can rule a model out. It can never rule one in. A market with only a calibration number has no price-based evidence, and this document will not present one as though it did.
- Prop prices are one-sided at most books, so every measured prop edge here is understated rather than overstated.
- The first genuinely out-of-sample evidence this project will ever have is the season being played, one game-day at a time. That is worth more than any further slicing of the seasons already in the file.
- No market reaches the card without a reviewed human approval, whatever the numbers above say.
- A result has to clear three things before it counts: enough bets, an interval that survives correcting for how many markets were tested, and then holding on a window it was not found on. Clearing the first two and failing the third is the ordinary outcome, not a surprise.
