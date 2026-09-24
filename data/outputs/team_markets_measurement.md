# Team markets measurement

Moneyline, puck line and totals — calibrated walk-forward, and measured against real prices wherever any have been bought.

- Generated: 2026-09-24T12:25:31+00:00
- 347,510 walk-forward samples across 4 market(s) and 3,658 games; 3 market(s) have any price-based evidence.

## Calibration

| Market | Samples | Brier raw | Brier corrected | Correction |
|:-------|--------:|----------:|----------------:|:-----------|
| `moneyline` (Moneyline) | 7,114 | 0.2423 | 0.2422 | intercept -0.000, slope 0.811 (fitted on 7254 samples) |
| `puck_line` (Puck line (-1.5 / +1.5)) | 153,186 | 0.0890 | 0.0889 | intercept -0.000, slope 0.968 (fitted on 152220 samples) |
| `regulation_3_way` (Regulation result (3-way)) | 10,749 | 0.2142 | 0.2118 | intercept -0.232, slope 0.637 (fitted on 10911 samples) |
| `total_goals` (Total goals) | 160,446 | 0.1028 | 0.1027 | intercept -0.000, slope 1.082 (fitted on 159436 samples) |

### `moneyline`

- Over 7,114 held-out samples the correction makes no material difference to the Brier score (0.2423 raw, 0.2422 corrected, delta +0.00012). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 10%-20% | 10 | 18.3% | 0.0% | 0.0% .. 27.8% |
| 20%-30% | 229 | 26.5% | 32.3% | 26.6% .. 38.6% |
| 30%-40% | 1,054 | 36.1% | 37.4% | 34.5% .. 40.3% |
| 40%-50% | 2,264 | 45.4% | 47.3% | 45.2% .. 49.3% |
| 50%-60% | 2,264 | 54.6% | 52.7% | 50.7% .. 54.8% |
| 60%-70% | 1,054 | 63.9% | 62.6% | 59.7% .. 65.5% |
| 70%-80% | 229 | 73.5% | 67.7% | 61.4% .. 73.4% |
| 80%-90% | 10 | 81.7% | 100.0% | 72.2% .. 100.0% |

### `puck_line`

- Over 153,186 held-out samples the correction makes no material difference to the Brier score (0.0890 raw, 0.0889 corrected, delta +0.00009). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 0%-10% | 47,099 | 3.3% | 3.2% | 3.0% .. 3.4% |
| 10%-20% | 13,895 | 14.5% | 17.6% | 17.0% .. 18.3% |
| 20%-30% | 8,240 | 24.6% | 27.6% | 26.7% .. 28.6% |
| 30%-40% | 4,714 | 34.4% | 36.1% | 34.7% .. 37.4% |
| 40%-50% | 2,645 | 44.6% | 43.2% | 41.3% .. 45.1% |
| 50%-60% | 2,645 | 55.4% | 56.8% | 54.9% .. 58.7% |
| 60%-70% | 4,714 | 65.6% | 63.9% | 62.6% .. 65.3% |
| 70%-80% | 8,240 | 75.4% | 72.4% | 71.4% .. 73.3% |
| 80%-90% | 13,895 | 85.5% | 82.4% | 81.7% .. 83.0% |
| 90%-100% | 47,099 | 96.7% | 96.8% | 96.6% .. 97.0% |

### `regulation_3_way`

- Over 10,749 held-out samples the correction improves the Brier score from 0.2142 to 0.2118 (delta +0.00232). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 0%-10% | 1 | 9.9% | 100.0% | 20.7% .. 100.0% |
| 10%-20% | 3,697 | 15.9% | 22.0% | 20.7% .. 23.3% |
| 20%-30% | 861 | 26.3% | 25.4% | 22.6% .. 28.4% |
| 30%-40% | 2,150 | 35.5% | 35.5% | 33.5% .. 37.6% |
| 40%-50% | 2,411 | 44.8% | 40.6% | 38.6% .. 42.5% |
| 50%-60% | 1,266 | 54.4% | 48.6% | 45.8% .. 51.3% |
| 60%-70% | 310 | 63.9% | 51.9% | 46.4% .. 57.4% |
| 70%-80% | 53 | 72.6% | 62.3% | 48.8% .. 74.1% |

### `total_goals`

- Over 160,446 held-out samples the correction makes no material difference to the Brier score (0.1028 raw, 0.1027 corrected, delta +0.00009). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 0%-10% | 39,162 | 3.4% | 2.5% | 2.4% .. 2.7% |
| 10%-20% | 14,723 | 14.8% | 13.7% | 13.2% .. 14.3% |
| 20%-30% | 11,181 | 24.5% | 22.8% | 22.0% .. 23.5% |
| 30%-40% | 6,150 | 34.9% | 33.3% | 32.1% .. 34.5% |
| 40%-50% | 9,007 | 45.3% | 46.7% | 45.6% .. 47.7% |
| 50%-60% | 9,007 | 54.7% | 53.3% | 52.3% .. 54.4% |
| 60%-70% | 6,150 | 65.1% | 66.7% | 65.5% .. 67.9% |
| 70%-80% | 11,181 | 75.5% | 77.2% | 76.5% .. 78.0% |
| 80%-90% | 14,723 | 85.2% | 86.3% | 85.7% .. 86.8% |
| 90%-100% | 39,162 | 96.6% | 97.5% | 97.3% .. 97.6% |

## Measured against real prices

Every price below was captured in the `late` window, median **1.5 hours** before face-off, and strictly before the puck dropped. A wager priced in two windows is two questions; this report answers one.

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| `moneyline` | 954 | -62.9u | -6.6% | -13.6% .. +0.4% | -15.5% .. +2.4% | no |
| `puck_line` | 1117 | -47.1u | -4.2% | -9.4% .. +0.9% | -10.8% .. +2.4% | no |
| `total_goals` | 1216 | -48.6u | -4.0% | -9.4% .. +1.4% | -10.9% .. +2.9% | no |

- `moneyline`: -6.6% over 954 bets, 95% interval -13.6% to +0.4%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: -4.2% over 1117 bets, 95% interval -9.4% to +0.9%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: -4.0% over 1216 bets, 95% interval -9.4% to +1.4%. The interval includes zero, which means **no demonstrated edge**.

### Where every price landed

An unmatched price is one the sample grid could not score — a line the books hang that the grid does not carry, or a warm-up-window game no sample covers. It is counted, because a third of the bought totals once vanished this way with nothing saying so.

- `moneyline`: 4,200 prices seen, 156 unmatched (96% matched), 3,090 below threshold, 954 bets.
- `puck_line`: 4,582 prices seen, 188 unmatched (96% matched), 3,277 below threshold, 1,117 bets.
- `total_goals`: 7,926 prices seen, 366 unmatched (95% matched), 6,344 below threshold, 1,216 bets.

### How much data would settle it

| If the true edge were | Bets needed to separate it from zero |
|----------------------:|-------------------------------------:|
| +5% | ~1,537 |
| +8% | ~601 |
| +10% | ~385 |
| +15% | ~171 |

## Standing notes

- Prices measured: 212,964 of 308,944 stored rows, from the `late` window, median 1.5 hours before face-off.
- 34,196 price row(s) captured at or after face-off were excluded. A quote on a team already losing mid-game clears the edge threshold against a pre-game probability and is then usually lost; it is not a price a card can take.
- 61,784 price row(s) from other windows were excluded. The best-price collapse would otherwise take the better of two moments for one wager — a price nobody could have taken.
- Team markets are not the point of this lab. They are measured to the same standard anyway, because a market nobody prices is a market where nobody can find an edge.
- The puck line is the market most likely to expose a modelling error: covering -1.5 depends on the overtime rule rather than on the scoring rate, so a model that has overtime wrong looks fine on moneylines and totals and wrong only here.
- A push is excluded rather than scored as a loss. Scoring pushes as losses would make every whole-number total look worse than it is.
- Calibration can rule this model out; it cannot rule it in. Where historical prices exist the backtest decides, and where they do not this report says so rather than offering a calibration number in their place.
