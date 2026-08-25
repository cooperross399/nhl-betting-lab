# What the evidence actually supports

Generated from the measurement outputs, so it cannot drift from them. The hand-written rules live in `docs/what_we_can_and_cannot_claim.md`.

- Generated: 2026-08-25T22:49:36+00:00

6 market(s) measured against real prices; at least one interval excludes zero on this sample. Read the per-market lines and the sample sizes before doing anything with that.

## Across every measured market

+4.7% over 556 bets. The interval includes zero: **no demonstrated edge**.

## Measured against real prices

- `shots_on_goal`: +18.1% over 263 bets, 95% interval +6.5% to +29.8%. The interval excludes zero on this sample and this data, which is not the same as an edge that will persist.
- `points`: -16.4% over 137 bets, 95% interval -32.7% to -0.1%. The interval excludes zero on this sample and this data, which is not the same as an edge that will persist.
- `goals`: -49.6% over 3 bets, 95% interval -148.4% to +49.3%. The interval includes zero, which means **no demonstrated edge**.
- `assists`: -2.4% over 72 bets, 95% interval -21.5% to +16.6%. The interval includes zero, which means **no demonstrated edge**.
- `goalie_saves`: +20.8% over 14 bets, 95% interval -28.2% to +69.8%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: +1.5% over 67 bets, 95% interval -25.1% to +28.0%. The interval includes zero, which means **no demonstrated edge**.

## Not measured against real prices

- `moneyline` has **no price-based measurement**: no historical prices have been bought for it yet.
- `puck_line` has **no price-based measurement**: no historical prices have been bought for it yet.
- `total_goals` has **no price-based measurement**: no historical prices have been bought for it yet.

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
