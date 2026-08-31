# Team markets measurement

Moneyline, puck line and totals — calibrated walk-forward, and measured against real prices wherever any have been bought.

- Generated: 2026-08-31T20:37:38+00:00
- 142,662 walk-forward samples across 4 market(s) and 3,658 games; 3 market(s) have any price-based evidence.

## Calibration

| Market | Samples | Brier raw | Brier corrected | Correction |
|:-------|--------:|----------:|----------------:|:-----------|
| `moneyline` (Moneyline) | 7,114 | 0.2423 | 0.2422 | intercept -0.000, slope 0.811 (fitted on 7254 samples) |
| `puck_line` (Puck line (-1.5 / +1.5)) | 68,528 | 0.1554 | 0.1547 | intercept +0.000, slope 0.879 (fitted on 68100 samples) |
| `regulation_3_way` (Regulation result (3-way)) | 10,749 | 0.2142 | 0.2118 | intercept -0.232, slope 0.637 (fitted on 10911 samples) |
| `total_goals` (Total goals) | 46,930 | 0.2177 | 0.2178 | intercept -0.000, slope 0.990 (fitted on 46902 samples) |

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

- Over 68,528 held-out samples the correction improves the Brier score from 0.1554 to 0.1547 (delta +0.00072). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 0%-10% | 9,569 | 4.8% | 5.2% | 4.8% .. 5.6% |
| 10%-20% | 9,517 | 15.1% | 20.0% | 19.2% .. 20.8% |
| 20%-30% | 7,856 | 24.7% | 28.3% | 27.3% .. 29.3% |
| 30%-40% | 4,678 | 34.4% | 36.1% | 34.8% .. 37.5% |
| 40%-50% | 2,644 | 44.6% | 43.2% | 41.3% .. 45.1% |
| 50%-60% | 2,644 | 55.4% | 56.8% | 54.9% .. 58.7% |
| 60%-70% | 4,678 | 65.6% | 63.9% | 62.5% .. 65.2% |
| 70%-80% | 7,856 | 75.3% | 71.7% | 70.7% .. 72.7% |
| 80%-90% | 9,517 | 84.9% | 80.0% | 79.2% .. 80.8% |
| 90%-100% | 9,569 | 95.2% | 94.8% | 94.4% .. 95.2% |

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

- Over 46,930 held-out samples the correction makes no material difference to the Brier score (0.2177 raw, 0.2178 corrected, delta -0.00013). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 10%-20% | 1,580 | 17.9% | 20.3% | 18.3% .. 22.3% |
| 20%-30% | 7,021 | 25.1% | 25.0% | 24.0% .. 26.0% |
| 30%-40% | 5,892 | 35.0% | 33.6% | 32.4% .. 34.8% |
| 40%-50% | 8,972 | 45.3% | 46.6% | 45.6% .. 47.7% |
| 50%-60% | 8,972 | 54.7% | 53.4% | 52.3% .. 54.4% |
| 60%-70% | 5,892 | 65.0% | 66.4% | 65.2% .. 67.6% |
| 70%-80% | 7,021 | 74.9% | 75.0% | 74.0% .. 76.0% |
| 80%-90% | 1,580 | 82.1% | 79.7% | 77.7% .. 81.7% |

## Measured against real prices

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| `moneyline` | 1504 | -36.5u | -2.4% | -8.0% .. +3.1% | -9.5% .. +4.6% | no |
| `puck_line` | 1541 | -66.4u | -4.3% | -8.7% .. +0.1% | -9.9% .. +1.3% | no |
| `total_goals` | 1150 | -5.9u | -0.5% | -6.0% .. +5.0% | -7.5% .. +6.4% | no |

- `moneyline`: -2.4% over 1504 bets, 95% interval -8.0% to +3.1%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: -4.3% over 1541 bets, 95% interval -8.7% to +0.1%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: -0.5% over 1150 bets, 95% interval -6.0% to +5.0%. The interval includes zero, which means **no demonstrated edge**.

### Where every price landed

An unmatched price is one the sample grid could not score — a line the books hang that the grid does not carry, or a warm-up-window game no sample covers. It is counted, because a third of the bought totals once vanished this way with nothing saying so.

- `moneyline`: 8,298 prices seen, 338 unmatched (96% matched), 6,456 below threshold, 1,504 bets.
- `puck_line`: 7,858 prices seen, 342 unmatched (96% matched), 5,975 below threshold, 1,541 bets.
- `total_goals`: 8,136 prices seen, 340 unmatched (96% matched), 6,646 below threshold, 1,150 bets.

### How much data would settle it

| If the true edge were | Bets needed to separate it from zero |
|----------------------:|-------------------------------------:|
| +5% | ~1,537 |
| +8% | ~601 |
| +10% | ~385 |
| +15% | ~171 |

## Standing notes

- Team markets are not the point of this lab. They are measured to the same standard anyway, because a market nobody prices is a market where nobody can find an edge.
- The puck line is the market most likely to expose a modelling error: covering -1.5 depends on the overtime rule rather than on the scoring rate, so a model that has overtime wrong looks fine on moneylines and totals and wrong only here.
- A push is excluded rather than scored as a loss. Scoring pushes as losses would make every whole-number total look worse than it is.
- Calibration can rule this model out; it cannot rule it in. Where historical prices exist the backtest decides, and where they do not this report says so rather than offering a calibration number in their place.
