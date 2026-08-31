# What the evidence actually supports

Generated from the measurement outputs, so it cannot drift from them. The hand-written rules live in `docs/what_we_can_and_cannot_claim.md`.

- Generated: 2026-08-31T21:05:36+00:00

**No demonstrated edge in any market.** 9 market(s) have been measured against real prices. Nothing survives correcting for the number of markets tested and then holds on a window it was not found on. What *has* survived both tests is a loss: `points`. A replicated deficit is a finding, not a null result, and it is the finding the model has.

## Across every measured market

-0.3% over 25,949 bets. The interval includes zero: **no demonstrated edge**.

## Measured against real prices

- `shots_on_goal`: +1.3% over 9,395 bets, 95% interval -0.8% to +3.4%. **No demonstrated edge**.
- `points`: -4.4% over 6,202 bets, 95% interval -6.9% to -1.9%. **Replicated** on the player_props_backtest_2025-26 window.
- `goals`: -6.8% over 564 bets, 95% interval -17.2% to +3.7%. **No demonstrated edge**.
- `assists`: -1.4% over 3,762 bets, 95% interval -4.2% to +1.3%. **No demonstrated edge**.
- `goalie_saves`: -2.5% over 1,733 bets, 95% interval -6.9% to +2.0%. **No demonstrated edge**.
- `blocked_shots`: +5.0% over 4,293 bets, 95% interval +1.8% to +8.1%. Measured again on the player_props_backtest_2025-26 window and **not confirmed** there, so **no demonstrated edge**.
- `moneyline`: +0.0% over 1,366 bets, 95% interval -8.2% to +8.2%. **No demonstrated edge**.
- `puck_line`: -1.3% over 1,762 bets, 95% interval -5.7% to +3.2%. **No demonstrated edge**.
- `total_goals`: -2.5% over 2,201 bets, 95% interval -6.5% to +1.6%. **No demonstrated edge**.

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

- Provider policy: **Nothing allowlisted**
- Allowlisted markets: **none**

## Standing notes

- An interval that includes zero means **no demonstrated edge**. Not 'promising', not 'trending positive', not 'small but positive'.
- Calibration can rule a model out. It can never rule one in. A market with only a calibration number has no price-based evidence, and this document will not present one as though it did.
- Prop prices are one-sided at most books, so every measured prop edge here is understated rather than overstated.
- The first genuinely out-of-sample evidence this project will ever have is the season being played, one game-day at a time. That is worth more than any further slicing of the seasons already in the file.
- No market reaches the card without a reviewed human approval, whatever the numbers above say.
- A result has to clear three things before it counts: enough bets, an interval that survives correcting for how many markets were tested, and then holding on a window it was not found on. Clearing the first two and failing the third is the ordinary outcome, not a surprise.
