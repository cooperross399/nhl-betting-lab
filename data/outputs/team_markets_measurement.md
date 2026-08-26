# Team markets measurement

Moneyline, puck line and totals — calibrated walk-forward, and measured against real prices wherever any have been bought.

- Generated: 2026-08-26T02:01:18+00:00
- 62,186 walk-forward samples across 4 market(s) and 3,658 games; 0 market(s) have any price-based evidence.

## Calibration

| Market | Samples | Brier raw | Brier corrected | Correction |
|:-------|--------:|----------:|----------------:|:-----------|
| `moneyline` (Moneyline) | 7,114 | 0.2430 | 0.2429 | intercept -0.000, slope 0.792 (fitted on 7254 samples) |
| `puck_line` (Puck line (-1.5 / +1.5)) | 14,400 | 0.2066 | 0.2057 | intercept -0.000, slope 0.832 (fitted on 14484 samples) |
| `regulation_3_way` (Regulation result (3-way)) | 10,749 | 0.2144 | 0.2121 | intercept -0.234, slope 0.633 (fitted on 10911 samples) |
| `total_goals` (Total goals) | 29,032 | 0.2136 | 0.2137 | intercept -0.000, slope 1.005 (fitted on 29016 samples) |

### `moneyline`

- Over 7,114 held-out samples the correction makes no material difference to the Brier score (0.2430 raw, 0.2429 corrected, delta +0.00016). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 10%-20% | 9 | 18.7% | 0.0% | 0.0% .. 29.9% |
| 20%-30% | 212 | 26.6% | 32.1% | 26.2% .. 38.6% |
| 30%-40% | 1,023 | 36.1% | 37.6% | 34.7% .. 40.6% |
| 40%-50% | 2,313 | 45.4% | 47.5% | 45.4% .. 49.5% |
| 50%-60% | 2,313 | 54.6% | 52.5% | 50.5% .. 54.6% |
| 60%-70% | 1,023 | 63.9% | 62.4% | 59.4% .. 65.3% |
| 70%-80% | 212 | 73.4% | 67.9% | 61.4% .. 73.8% |
| 80%-90% | 9 | 81.3% | 100.0% | 70.1% .. 100.0% |

### `puck_line`

- Over 14,400 held-out samples the correction improves the Brier score from 0.2066 to 0.2057 (delta +0.00091). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 0%-10% | 94 | 8.5% | 8.5% | 4.4% .. 15.9% |
| 10%-20% | 1,397 | 16.3% | 21.5% | 19.4% .. 23.7% |
| 20%-30% | 3,098 | 25.0% | 29.1% | 27.6% .. 30.8% |
| 30%-40% | 1,935 | 34.2% | 34.0% | 31.9% .. 36.1% |
| 40%-50% | 676 | 44.0% | 46.3% | 42.6% .. 50.1% |
| 50%-60% | 676 | 56.0% | 53.7% | 49.9% .. 57.4% |
| 60%-70% | 1,935 | 65.8% | 66.0% | 63.9% .. 68.1% |
| 70%-80% | 3,098 | 75.0% | 70.9% | 69.2% .. 72.4% |
| 80%-90% | 1,397 | 83.7% | 78.5% | 76.3% .. 80.6% |
| 90%-100% | 94 | 91.5% | 91.5% | 84.1% .. 95.6% |

### `regulation_3_way`

- Over 10,749 held-out samples the correction improves the Brier score from 0.2144 to 0.2121 (delta +0.00233). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 10%-20% | 3,691 | 15.9% | 22.0% | 20.7% .. 23.3% |
| 20%-30% | 833 | 26.4% | 25.7% | 22.8% .. 28.8% |
| 30%-40% | 2,187 | 35.6% | 35.4% | 33.5% .. 37.5% |
| 40%-50% | 2,452 | 44.8% | 40.9% | 38.9% .. 42.8% |
| 50%-60% | 1,246 | 54.3% | 48.2% | 45.5% .. 51.0% |
| 60%-70% | 295 | 63.9% | 51.2% | 45.5% .. 56.8% |
| 70%-80% | 45 | 72.5% | 64.4% | 49.8% .. 76.8% |

### `total_goals`

- Over 29,032 held-out samples the correction makes no material difference to the Brier score (0.2136 raw, 0.2137 corrected, delta -0.00010). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

| Bucket | Samples | Predicted | Observed | 95% on observed |
|:-------|--------:|----------:|---------:|:----------------|
| 10%-20% | 1,368 | 17.8% | 20.3% | 18.3% .. 22.5% |
| 20%-30% | 4,595 | 24.7% | 23.3% | 22.1% .. 24.5% |
| 30%-40% | 2,999 | 35.3% | 35.3% | 33.6% .. 37.0% |
| 40%-50% | 5,554 | 45.3% | 46.6% | 45.3% .. 47.9% |
| 50%-60% | 5,554 | 54.7% | 53.4% | 52.1% .. 54.7% |
| 60%-70% | 2,999 | 64.7% | 64.7% | 63.0% .. 66.4% |
| 70%-80% | 4,595 | 75.3% | 76.7% | 75.5% .. 77.9% |
| 80%-90% | 1,368 | 82.2% | 79.7% | 77.5% .. 81.7% |

## Measured against real prices

**No price-based measurement.** 0 historical team price(s) are on disk, and no market has enough matched, above-threshold outcomes to measure. This means **no demonstrated edge** — and equally, no demonstrated absence of one.

The calibration numbers above are **not** a substitute. They say the model's probabilities are internally sensible; they say nothing about whether the market disagrees with them profitably.

## Standing notes

- Team markets are not the point of this lab. They are measured to the same standard anyway, because a market nobody prices is a market where nobody can find an edge.
- The puck line is the market most likely to expose a modelling error: covering -1.5 depends on the overtime rule rather than on the scoring rate, so a model that has overtime wrong looks fine on moneylines and totals and wrong only here.
- A push is excluded rather than scored as a loss. Scoring pushes as losses would make every whole-number total look worse than it is.
- Calibration can rule this model out; it cannot rule it in. Where historical prices exist the backtest decides, and where they do not this report says so rather than offering a calibration number in their place.
