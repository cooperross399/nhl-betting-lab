# What the evidence actually supports

Generated from the measurement outputs, so it cannot drift from them. The hand-written rules live in `docs/what_we_can_and_cannot_claim.md`.

- Generated: 2026-08-26T01:39:06+00:00

**No demonstrated edge in any market.** 6 market(s) have been measured against real prices. Nothing survives correcting for the number of markets tested and then holds on a window it was not found on.

## Across every measured market

+1.2% over 4,777 bets. The interval includes zero: **no demonstrated edge**.

## Measured against real prices

- `shots_on_goal`: +2.4% over 2,476 bets, 95% interval -1.5% to +6.4%. **No demonstrated edge**.
- `points`: -4.5% over 913 bets, 95% interval -11.1% to +2.0%. **No demonstrated edge**.
- `goals`: +14.8% over 37 bets, 95% interval -29.4% to +59.0%. **No demonstrated edge**.
- `assists`: -6.1% over 386 bets, 95% interval -14.8% to +2.7%. **No demonstrated edge**.
- `goalie_saves`: -2.5% over 410 bets, 95% interval -11.6% to +6.6%. **No demonstrated edge**.
- `blocked_shots`: +11.8% over 555 bets, 95% interval +3.2% to +20.5%. Correcting for the 7 markets measured on the same data, it does not exclude zero. **No demonstrated edge**.

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
- A result has to clear three things before it counts: enough bets, an interval that survives correcting for how many markets were tested, and then holding on a window it was not found on. Clearing the first two and failing the third is the ordinary outcome, not a surprise.
