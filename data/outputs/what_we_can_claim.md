# What the evidence actually supports

Generated from the measurement outputs, so it cannot drift from them. The hand-written rules live in `docs/what_we_can_and_cannot_claim.md`.

- Generated: 2026-08-25T20:04:05+00:00

**Nothing in this repository has a demonstrated edge, because nothing has been measured against real prices yet.** That is a statement about the evidence, not about the models.

## Not measured against real prices

- `shots_on_goal` has **no price-based measurement**: no historical prices have been bought for it yet It has been calibration-checked on 250,096 walk-forward samples, which can rule the model out and can never rule it in. That is not evidence of an edge and is not offered as any.
- `points` has **no price-based measurement**: no historical prices have been bought for it yet It has been calibration-checked on 187,572 walk-forward samples, which can rule the model out and can never rule it in. That is not evidence of an edge and is not offered as any.
- `goals` has **no price-based measurement**: no historical prices have been bought for it yet It has been calibration-checked on 125,048 walk-forward samples, which can rule the model out and can never rule it in. That is not evidence of an edge and is not offered as any.
- `assists` has **no price-based measurement**: no historical prices have been bought for it yet It has been calibration-checked on 125,048 walk-forward samples, which can rule the model out and can never rule it in. That is not evidence of an edge and is not offered as any.
- `goalie_saves` has **no price-based measurement**: no historical prices have been bought for it yet It has been calibration-checked on 16,790 walk-forward samples, which can rule the model out and can never rule it in. That is not evidence of an edge and is not offered as any.
- `blocked_shots` has **no price-based measurement**: no historical prices have been bought for it yet It has been calibration-checked on 250,096 walk-forward samples, which can rule the model out and can never rule it in. That is not evidence of an edge and is not offered as any.
- `moneyline` has **no price-based measurement**: no historical prices have been bought for it yet
- `puck_line` has **no price-based measurement**: no historical prices have been bought for it yet
- `total_5_5` has **no price-based measurement**: no historical prices have been bought for it yet

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
