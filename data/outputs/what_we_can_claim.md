# What the evidence actually supports

Generated from the measurement outputs, so it cannot drift from them. The hand-written rules live in `docs/what_we_can_and_cannot_claim.md`.

- Generated: 2026-09-24T13:51:45+00:00

**No demonstrated edge in any market.** 10 market(s) have been measured against real prices. Nothing survives correcting for the number of markets tested and then holds on a window it was not found on.

## Across every measured prop market

-0.2% over 25,009 bets in the `late` window, 4.1 hours before face-off. The interval includes zero: **no demonstrated edge**.

## Measured against real prices

Unless a line names another window, prop figures come from the `late` window, 4.1 hours before face-off, and team figures come from the `late` window, 1.5 hours before face-off.

- `shots_on_goal`: +1.4% over 9,043 bets, 95% interval -0.8% to +3.5%. **No demonstrated edge**.
- `points`: -4.5% over 5,984 bets, 95% interval -7.0% to -1.9%. The interval excludes zero even after correcting for the 7 markets measured on the same data — which is not the same as a loss that will persist, and means nothing until it replicates on a window it was not found on.
- `goals`: -6.6% over 546 bets, 95% interval -17.2% to +4.1%. **No demonstrated edge**.
- `assists`: -1.3% over 3,630 bets, 95% interval -4.1% to +1.5%. **No demonstrated edge**.
- `goalie_saves`: -2.3% over 1,680 bets, 95% interval -6.9% to +2.2%. **No demonstrated edge**.
- `blocked_shots`: +5.2% over 4,126 bets, 95% interval +1.9% to +8.4%. The interval excludes zero even after correcting for the 7 markets measured on the same data — which is not the same as an edge that will persist, and means nothing until it replicates on a window it was not found on.
- `hits`: -1.2% over 5,021 bets, 95% interval -3.9% to +1.5%, measured only in the `card` window, 9.6 hours before face-off. **No demonstrated edge**.
- `moneyline`: -6.6% over 954 bets, 95% interval -13.6% to +0.4%. **No demonstrated edge**.
- `puck_line`: -4.2% over 1,117 bets, 95% interval -9.4% to +0.9%. **No demonstrated edge**.
- `total_goals`: -4.0% over 1,216 bets, 95% interval -9.4% to +1.4%. **No demonstrated edge**.

## Not measured against real prices

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
- Allowlisted markets: **assists, blocked_shots, goalie_saves, goals, hits, moneyline, points, puck_line, regulation_3_way, shots_on_goal, team_total, total_goals**

## Standing notes

- An interval that includes zero means **no demonstrated edge**. Not 'promising', not 'trending positive', not 'small but positive'.
- Calibration can rule a model out. It can never rule one in. A market with only a calibration number has no price-based evidence, and this document will not present one as though it did.
- Prop prices are one-sided at most books, so every measured prop edge here is understated rather than overstated.
- The first genuinely out-of-sample evidence this project will ever have is the season being played, one game-day at a time. That is worth more than any further slicing of the seasons already in the file.
- No market reaches the card without a reviewed human approval, whatever the numbers above say.
- A result has to clear three things before it counts: enough bets, an interval that survives correcting for how many markets were tested, and then holding on a window it was not found on. Clearing the first two and failing the third is the ordinary outcome, not a surprise.
