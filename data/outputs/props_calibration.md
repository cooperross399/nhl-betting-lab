# Player props calibration

When the model says 62%, does it happen 62% of the time? That is the only question this report answers. Whether the model beats a price is a different question, answered in `data/outputs/player_props_backtest.md`.

- Generated: 2026-08-26T11:41:09+00:00
- 2,508,315 walk-forward samples across 7 market(s); 7 have enough samples to say anything about.

## Headline, per market

| Market | Samples | Warm-up dropped | Brier raw | Brier pooled | Brier by ice time | Correction |
|:-------|--------:|----------------:|----------:|-------------:|------------------:|:-----------|
| `assists` (Assists) | 246,692 | 760 | 0.1055 | 0.1055 | 0.1050 | intercept +0.060, slope 1.016 (fitted on 245000 samples) |
| `blocked_shots` (Blocked shots) | 493,384 | 1,520 | 0.1128 | 0.1122 | 0.1120 | intercept +0.172, slope 1.190 (fitted on 490000 samples) |
| `goalie_saves` (Goalie saves) | 33,595 | 200 | 0.1935 | 0.1938 | 0.1917 | intercept +0.012, slope 0.905 (fitted on 33530 samples) |
| `goals` (Goals (incl. anytime scorer)) | 246,692 | 760 | 0.0693 | 0.0693 | 0.0691 | intercept -0.010, slope 0.986 (fitted on 245000 samples) |
| `hits` (Hits) | 616,730 | 1,900 | 0.1234 | 0.1227 | 0.1213 | intercept +0.172, slope 1.193 (fitted on 612500 samples) |
| `points` (Points) | 370,038 | 1,140 | 0.1003 | 0.1003 | 0.0997 | intercept +0.033, slope 0.996 (fitted on 367500 samples) |
| `shots_on_goal` (Shots on goal) | 493,384 | 1,520 | 0.1259 | 0.1252 | 0.1237 | intercept +0.086, slope 1.226 (fitted on 490000 samples) |

## `assists`

- Over 246,692 held-out samples the correction makes no material difference to the Brier score (0.1055 raw, 0.1055 corrected, delta +0.00004). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 116,523 | 3.1% | 3.0% | 3.5% |
| 10%-20% | 58,238 | 15.5% | 15.5% | 14.7% |
| 20%-30% | 42,818 | 24.2% | 24.3% | 25.2% |
| 30%-40% | 19,106 | 34.5% | 34.5% | 36.6% |
| 40%-50% | 7,807 | 44.0% | 44.1% | 45.9% |
| 50%-60% | 1,778 | 53.5% | 53.6% | 57.4% |
| 60%-70% | 396 | 63.5% | 63.9% | 62.1% |
| 70%-80% | 26 | 72.3% | 72.2% | 84.6% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 37,294 | 8.6% | 8.6% | 5.2% | 5.0% .. 5.4% |
| 12-16 min | 69,718 | 11.4% | 11.6% | 11.2% | 10.9% .. 11.4% |
| 16-20 min | 79,430 | 15.4% | 15.6% | 16.6% | 16.4% .. 16.9% |
| 20 min and up | 60,250 | 18.2% | 18.5% | 20.6% | 20.2% .. 20.9% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.1050 against 0.1055 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 37,294 | 5.0% | 5.2% |
| 12-16 min | 69,718 | 10.9% | 11.2% |
| 16-20 min | 79,430 | 16.3% | 16.6% |
| 20 min and up | 60,250 | 20.7% | 20.6% |

## `blocked_shots`

- Over 493,384 held-out samples the correction improves the Brier score from 0.1128 to 0.1122 (delta +0.00065). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 216,852 | 3.4% | 3.0% | 2.5% |
| 10%-20% | 81,185 | 14.1% | 14.1% | 11.8% |
| 20%-30% | 43,753 | 25.3% | 25.2% | 24.4% |
| 30%-40% | 64,485 | 35.1% | 35.2% | 36.0% |
| 40%-50% | 38,703 | 44.1% | 44.5% | 47.8% |
| 50%-60% | 12,798 | 54.7% | 54.0% | 60.2% |
| 60%-70% | 20,453 | 65.5% | 65.5% | 70.9% |
| 70%-80% | 14,763 | 73.7% | 75.2% | 81.8% |
| 80%-90% | 392 | 81.1% | 82.7% | 88.8% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 74,588 | 12.3% | 12.2% | 10.9% | 10.7% .. 11.1% |
| 12-16 min | 139,436 | 16.0% | 16.1% | 15.6% | 15.5% .. 15.8% |
| 16-20 min | 158,860 | 20.7% | 21.3% | 20.8% | 20.6% .. 21.0% |
| 20 min and up | 120,500 | 30.5% | 32.1% | 32.3% | 32.1% .. 32.6% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.1120 against 0.1122 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 74,588 | 11.1% | 10.9% |
| 12-16 min | 139,436 | 16.1% | 15.6% |
| 16-20 min | 158,860 | 21.3% | 20.8% |
| 20 min and up | 120,500 | 32.7% | 32.3% |

## `goalie_saves`

- Over 33,595 held-out samples the correction makes no material difference to the Brier score (0.1935 raw, 0.1938 corrected, delta -0.00026). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 1,783 | 6.8% | 7.1% | 12.1% |
| 10%-20% | 5,146 | 15.4% | 15.7% | 19.4% |
| 20%-30% | 5,953 | 25.0% | 25.1% | 25.3% |
| 30%-40% | 5,071 | 34.8% | 34.9% | 35.2% |
| 40%-50% | 4,001 | 44.8% | 44.8% | 44.6% |
| 50%-60% | 3,062 | 54.7% | 54.7% | 52.4% |
| 60%-70% | 2,482 | 64.8% | 64.8% | 65.5% |
| 70%-80% | 2,638 | 75.3% | 75.1% | 75.5% |
| 80%-90% | 2,864 | 84.7% | 84.5% | 83.9% |
| 90%-100% | 595 | 92.3% | 92.3% | 90.8% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| goalie, pulled or partial (under 50 min) | 830 | 43.9% | 47.5% | 10.4% | 8.5% .. 12.6% |
| goalie, full game (50 min+) | 32,765 | 42.2% | 45.6% | 43.9% | 43.3% .. 44.4% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.1917 against 0.1938 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| goalie, pulled or partial (under 50 min) | 830 | 20.7% | 10.4% |
| goalie, full game (50 min+) | 32,765 | 46.7% | 43.9% |

## `goals`

- Over 246,692 held-out samples the correction makes no material difference to the Brier score (0.0693 raw, 0.0693 corrected, delta -0.00001). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 164,687 | 2.8% | 2.8% | 2.9% |
| 10%-20% | 49,184 | 14.6% | 14.6% | 14.5% |
| 20%-30% | 22,153 | 24.3% | 24.3% | 25.5% |
| 30%-40% | 8,963 | 34.0% | 34.0% | 33.0% |
| 40%-50% | 1,573 | 43.4% | 43.4% | 42.2% |
| 50%-60% | 132 | 52.0% | 52.0% | 50.0% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 37,294 | 6.1% | 6.2% | 3.7% | 3.6% .. 3.9% |
| 12-16 min | 69,718 | 7.9% | 8.0% | 7.9% | 7.7% .. 8.1% |
| 16-20 min | 79,430 | 10.0% | 10.1% | 10.9% | 10.7% .. 11.1% |
| 20 min and up | 60,250 | 8.7% | 8.8% | 9.3% | 9.1% .. 9.5% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.0691 against 0.0693 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 37,294 | 3.6% | 3.7% |
| 12-16 min | 69,718 | 8.0% | 7.9% |
| 16-20 min | 79,430 | 10.8% | 10.9% |
| 20 min and up | 60,250 | 9.4% | 9.3% |

## `hits`

- Over 616,730 held-out samples the correction improves the Brier score from 0.1234 to 0.1227 (delta +0.00065). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 241,438 | 4.4% | 4.0% | 3.0% |
| 10%-20% | 111,749 | 14.5% | 14.5% | 13.0% |
| 20%-30% | 74,325 | 24.7% | 24.8% | 24.4% |
| 30%-40% | 45,428 | 34.6% | 34.5% | 38.2% |
| 40%-50% | 41,096 | 45.2% | 45.1% | 46.3% |
| 50%-60% | 51,712 | 55.1% | 55.3% | 55.3% |
| 60%-70% | 36,967 | 64.5% | 64.6% | 72.7% |
| 70%-80% | 12,888 | 73.7% | 74.3% | 86.7% |
| 80%-90% | 1,123 | 82.4% | 83.1% | 95.9% |
| 90%-100% | 4 | 90.8% | 91.6% | 100.0% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 93,235 | 22.1% | 22.5% | 28.2% | 27.9% .. 28.5% |
| 12-16 min | 174,295 | 22.9% | 23.4% | 25.3% | 25.1% .. 25.5% |
| 16-20 min | 198,575 | 23.4% | 23.9% | 21.8% | 21.6% .. 22.0% |
| 20 min and up | 150,625 | 23.5% | 24.0% | 20.1% | 19.9% .. 20.3% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.1213 against 0.1227 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 93,235 | 28.8% | 28.2% |
| 12-16 min | 174,295 | 25.6% | 25.3% |
| 16-20 min | 198,575 | 22.2% | 21.8% |
| 20 min and up | 150,625 | 20.4% | 20.1% |

## `points`

- Over 370,038 held-out samples the correction makes no material difference to the Brier score (0.1003 raw, 0.1003 corrected, delta +0.00001). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 209,024 | 2.8% | 2.8% | 3.1% |
| 10%-20% | 39,952 | 15.2% | 15.1% | 15.8% |
| 20%-30% | 49,328 | 24.8% | 24.9% | 23.8% |
| 30%-40% | 33,201 | 34.6% | 34.6% | 35.4% |
| 40%-50% | 18,532 | 44.5% | 44.5% | 47.0% |
| 50%-60% | 12,622 | 54.6% | 54.7% | 57.5% |
| 60%-70% | 5,770 | 64.0% | 64.1% | 64.5% |
| 70%-80% | 1,486 | 73.7% | 73.8% | 75.0% |
| 80%-90% | 123 | 81.8% | 81.9% | 82.1% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 55,941 | 9.8% | 10.0% | 6.0% | 5.8% .. 6.2% |
| 12-16 min | 104,577 | 12.9% | 13.2% | 12.8% | 12.6% .. 13.0% |
| 16-20 min | 119,145 | 17.0% | 17.3% | 18.6% | 18.3% .. 18.8% |
| 20 min and up | 90,375 | 18.1% | 18.4% | 20.2% | 20.0% .. 20.5% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.0997 against 0.1003 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 55,941 | 5.8% | 6.0% |
| 12-16 min | 104,577 | 12.6% | 12.8% |
| 16-20 min | 119,145 | 18.2% | 18.6% |
| 20 min and up | 90,375 | 20.5% | 20.2% |

## `shots_on_goal`

- Over 493,384 held-out samples the correction improves the Brier score from 0.1259 to 0.1252 (delta +0.00071). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 166,885 | 4.7% | 3.9% | 2.8% |
| 10%-20% | 103,049 | 14.6% | 14.5% | 11.4% |
| 20%-30% | 71,378 | 24.9% | 24.9% | 22.2% |
| 30%-40% | 58,495 | 34.8% | 34.8% | 32.9% |
| 40%-50% | 41,906 | 44.7% | 44.8% | 44.9% |
| 50%-60% | 29,451 | 54.6% | 54.8% | 57.7% |
| 60%-70% | 16,647 | 64.4% | 64.6% | 70.4% |
| 70%-80% | 5,175 | 73.6% | 74.3% | 81.8% |
| 80%-90% | 398 | 81.9% | 83.3% | 88.7% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 74,588 | 14.5% | 12.9% | 7.7% | 7.5% .. 7.9% |
| 12-16 min | 139,436 | 19.9% | 18.6% | 16.3% | 16.1% .. 16.5% |
| 16-20 min | 158,860 | 25.3% | 24.6% | 25.0% | 24.8% .. 25.2% |
| 20 min and up | 120,500 | 26.6% | 26.1% | 29.6% | 29.3% .. 29.8% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.1237 against 0.1252 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 74,588 | 7.6% | 7.7% |
| 12-16 min | 139,436 | 16.3% | 16.3% |
| 16-20 min | 158,860 | 25.6% | 25.0% |
| 20 min and up | 120,500 | 30.6% | 29.6% |

## Standing notes

- Calibration can rule a model out. It cannot rule one in. Nothing in this report says the model beats a price; that question is answered only by `data/outputs/player_props_backtest.md`.
- Every correction applied here was fitted only on samples from strictly earlier game-days. Warm-up samples are dropped rather than scored uncorrected, and the count is stated per market.
- Ice time is the dominant input to a skater prop, so a correction that straightens the headline curve while leaving a volume bucket bent has not fixed the model.
- These samples are priced at standard lines, not at prices that were actually for sale. A well-calibrated model with no price advantage is a normal and unprofitable thing to have.
- Goalie relief appearances produce no sample: a book posts a total saves line for the expected starter, and nobody can bet a saves prop on a goalie who enters cold in the second period. See `docs/goalie_props_need_a_confirmed_starter.md` — the model still has no way to know who starts, which is a card-level gate rather than something this measurement fixes.
- Both a pooled correction and an ice-time-conditional one are shown for every market, whether or not the conditional one wins. A variant reported only when it wins is a selection, not a measurement.
- **Neither correction is in force on the card.** The card prices props with the raw model. Calibration cannot rule a model in, so a correction ships only when the price-based backtest in `data/outputs/player_props_backtest.md` says it should — and that report currently measures nothing, because no historical prices have been bought.
