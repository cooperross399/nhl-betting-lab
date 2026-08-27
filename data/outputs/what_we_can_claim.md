# What the evidence actually supports

Generated from the measurement outputs, so it cannot drift from them. The hand-written rules live in `docs/what_we_can_and_cannot_claim.md`.

- Generated: 2026-08-27T05:59:10+00:00

**No demonstrated edge in any market.** 9 market(s) have been measured against real prices. Nothing survives correcting for the number of markets tested and then holds on a window it was not found on.

## Across every measured market

+1.4% over 4,830 bets. The interval includes zero: **no demonstrated edge**.

## Measured against real prices

- `shots_on_goal`: +3.0% over 2,508 bets, 95% interval -0.9% to +7.0%. **No demonstrated edge**.
- `points`: -5.5% over 940 bets, 95% interval -11.9% to +0.9%. **No demonstrated edge**.
- `goals`: +10.6% over 34 bets, 95% interval -34.8% to +56.0%. **No demonstrated edge**.
- `assists`: -4.5% over 403 bets, 95% interval -13.0% to +4.1%. **No demonstrated edge**.
- `goalie_saves`: -1.7% over 397 bets, 95% interval -10.9% to +7.5%. **No demonstrated edge**.
- `blocked_shots`: +11.9% over 548 bets, 95% interval +3.2% to +20.6%. Correcting for the 7 markets measured on the same data, it does not exclude zero. **No demonstrated edge**.
- `moneyline`: -2.4% over 1,504 bets, 95% interval -8.0% to +3.1%. **No demonstrated edge**.
- `puck_line`: -4.3% over 1,541 bets, 95% interval -8.7% to +0.1%. **No demonstrated edge**.
- `total_goals`: -0.5% over 1,150 bets, 95% interval -6.0% to +5.0%. **No demonstrated edge**.

## Not measured against real prices

- `hits` has **no price-based measurement**: Not offered in any historical snapshot across 256 probed events spanning two seasons, so it cannot be measured against past prices. It is served live; its evidence must accumulate forward. It has been calibration-checked on 616,730 walk-forward samples, which can rule the model out and can never rule it in. That is not evidence of an edge and is not offered as any.
- `regulation_3_way` has **no price-based measurement**: the provider serves it per-event only, with no bulk history; its evidence accumulates forward once the season starts.

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
