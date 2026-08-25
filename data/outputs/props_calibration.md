# Player props calibration

When the model says 62%, does it happen 62% of the time? That is the only question this report answers. Whether the model beats a price is a different question, answered in `data/outputs/player_props_backtest.md`.

- Generated: 2026-08-25T20:00:45+00:00
- 960,550 walk-forward samples across 6 market(s); 6 have enough samples to say anything about.

## Headline, per market

| Market | Samples | Warm-up dropped | Brier raw | Brier pooled | Brier by ice time | Correction |
|:-------|--------:|----------------:|----------:|-------------:|------------------:|:-----------|
| `assists` (Assists) | 125,048 | 760 | 0.1053 | 0.1053 | 0.1048 | intercept +0.060, slope 1.031 (fitted on 124026 samples) |
| `blocked_shots` (Blocked shots) | 250,096 | 1,520 | 0.1154 | 0.1146 | 0.1144 | intercept +0.215, slope 1.189 (fitted on 248052 samples) |
| `goalie_saves` (Goalie saves) | 16,790 | 200 | 0.1975 | 0.1975 | 0.1963 | intercept +0.101, slope 0.900 (fitted on 16820 samples) |
| `goals` (Goals (incl. anytime scorer)) | 125,048 | 760 | 0.0691 | 0.0691 | 0.0689 | intercept -0.013, slope 0.991 (fitted on 124026 samples) |
| `points` (Points) | 187,572 | 1,140 | 0.1003 | 0.1003 | 0.0996 | intercept +0.022, slope 1.003 (fitted on 186039 samples) |
| `shots_on_goal` (Shots on goal) | 250,096 | 1,520 | 0.1296 | 0.1288 | 0.1270 | intercept +0.114, slope 1.236 (fitted on 248052 samples) |

## `assists`

- Over 125,048 held-out samples the correction makes no material difference to the Brier score (0.1053 raw, 0.1053 corrected, delta +0.00003). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 59,085 | 3.2% | 3.1% | 3.5% |
| 10%-20% | 27,981 | 15.7% | 15.7% | 14.5% |
| 20%-30% | 23,026 | 24.2% | 24.3% | 24.6% |
| 30%-40% | 10,337 | 34.4% | 34.5% | 36.3% |
| 40%-50% | 3,751 | 43.9% | 44.0% | 46.3% |
| 50%-60% | 737 | 53.3% | 53.5% | 59.6% |
| 60%-70% | 128 | 62.9% | 63.6% | 64.1% |
| 70%-80% | 3 | 71.4% | 71.5% | 66.7% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 18,402 | 8.9% | 8.9% | 5.2% | 4.9% .. 5.5% |
| 12-16 min | 35,312 | 11.7% | 11.8% | 11.0% | 10.6% .. 11.3% |
| 16-20 min | 40,488 | 15.4% | 15.6% | 16.3% | 15.9% .. 16.6% |
| 20 min and up | 30,846 | 18.1% | 18.4% | 20.7% | 20.3% .. 21.2% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.1048 against 0.1053 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 18,402 | 5.1% | 5.2% |
| 12-16 min | 35,312 | 11.0% | 11.0% |
| 16-20 min | 40,488 | 16.2% | 16.3% |
| 20 min and up | 30,846 | 20.8% | 20.7% |

## `blocked_shots`

- Over 250,096 held-out samples the correction improves the Brier score from 0.1154 to 0.1146 (delta +0.00085). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 107,958 | 3.3% | 3.0% | 2.6% |
| 10%-20% | 41,799 | 14.1% | 14.0% | 12.2% |
| 20%-30% | 22,097 | 25.2% | 25.1% | 25.0% |
| 30%-40% | 33,844 | 35.1% | 35.2% | 36.7% |
| 40%-50% | 19,887 | 44.0% | 44.4% | 49.2% |
| 50%-60% | 6,025 | 54.5% | 54.0% | 60.9% |
| 60%-70% | 10,431 | 65.7% | 65.5% | 72.2% |
| 70%-80% | 7,914 | 73.6% | 75.4% | 82.6% |
| 80%-90% | 141 | 80.8% | 82.6% | 90.1% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 36,804 | 12.1% | 12.0% | 10.7% | 10.4% .. 11.0% |
| 12-16 min | 70,624 | 16.1% | 16.3% | 16.2% | 15.9% .. 16.4% |
| 16-20 min | 80,976 | 20.9% | 21.6% | 21.6% | 21.4% .. 21.9% |
| 20 min and up | 61,692 | 30.9% | 32.7% | 33.4% | 33.1% .. 33.8% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.1144 against 0.1146 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 36,804 | 11.0% | 10.7% |
| 12-16 min | 70,624 | 16.3% | 16.2% |
| 16-20 min | 80,976 | 21.6% | 21.6% |
| 20 min and up | 61,692 | 33.2% | 33.4% |

## `goalie_saves`

- Over 16,790 held-out samples the correction makes no material difference to the Brier score (0.1975 raw, 0.1975 corrected, delta +0.00008). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 772 | 6.8% | 7.1% | 14.4% |
| 10%-20% | 2,191 | 15.5% | 15.7% | 21.4% |
| 20%-30% | 2,828 | 25.1% | 25.3% | 27.2% |
| 30%-40% | 2,579 | 34.9% | 35.0% | 37.3% |
| 40%-50% | 2,090 | 44.8% | 44.9% | 47.1% |
| 50%-60% | 1,682 | 54.7% | 54.8% | 55.1% |
| 60%-70% | 1,353 | 64.8% | 64.8% | 65.8% |
| 70%-80% | 1,252 | 75.3% | 75.1% | 78.4% |
| 80%-90% | 1,604 | 84.9% | 84.8% | 85.3% |
| 90%-100% | 439 | 92.5% | 92.4% | 92.3% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| goalie, pulled or partial (under 50 min) | 430 | 47.1% | 52.5% | 13.7% | 10.8% .. 17.3% |
| goalie, full game (50 min+) | 16,360 | 44.3% | 49.3% | 47.7% | 46.9% .. 48.5% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.1963 against 0.1975 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| goalie, pulled or partial (under 50 min) | 430 | 31.3% | 13.7% |
| goalie, full game (50 min+) | 16,360 | 50.6% | 47.7% |

## `goals`

- Over 125,048 held-out samples the correction makes no material difference to the Brier score (0.0691 raw, 0.0691 corrected, delta -0.00002). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 82,613 | 2.7% | 2.8% | 2.8% |
| 10%-20% | 25,431 | 14.7% | 14.7% | 14.2% |
| 20%-30% | 11,879 | 24.4% | 24.3% | 25.3% |
| 30%-40% | 4,336 | 33.8% | 33.8% | 32.7% |
| 40%-50% | 726 | 43.3% | 43.3% | 44.8% |
| 50%-60% | 63 | 51.9% | 52.0% | 54.0% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 18,402 | 6.3% | 6.5% | 3.7% | 3.4% .. 4.0% |
| 12-16 min | 35,312 | 8.0% | 8.1% | 8.0% | 7.7% .. 8.3% |
| 16-20 min | 40,488 | 10.0% | 10.2% | 10.8% | 10.5% .. 11.1% |
| 20 min and up | 30,846 | 8.6% | 8.7% | 9.2% | 8.9% .. 9.5% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.0689 against 0.0691 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 18,402 | 3.7% | 3.7% |
| 12-16 min | 35,312 | 8.2% | 8.0% |
| 16-20 min | 40,488 | 10.8% | 10.8% |
| 20 min and up | 30,846 | 9.4% | 9.2% |

## `points`

- Over 187,572 held-out samples the correction makes no material difference to the Brier score (0.1003 raw, 0.1003 corrected, delta -0.00003). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 105,660 | 2.9% | 2.9% | 3.0% |
| 10%-20% | 19,558 | 15.1% | 15.0% | 15.8% |
| 20%-30% | 24,874 | 24.9% | 24.9% | 23.2% |
| 30%-40% | 17,512 | 34.6% | 34.6% | 34.9% |
| 40%-50% | 9,957 | 44.6% | 44.6% | 46.0% |
| 50%-60% | 6,717 | 54.6% | 54.6% | 57.5% |
| 60%-70% | 2,645 | 64.0% | 64.0% | 64.9% |
| 70%-80% | 627 | 73.5% | 73.5% | 77.8% |
| 80%-90% | 22 | 81.2% | 81.3% | 95.5% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 27,603 | 10.2% | 10.4% | 5.9% | 5.6% .. 6.2% |
| 12-16 min | 52,968 | 13.2% | 13.5% | 12.7% | 12.4% .. 13.0% |
| 16-20 min | 60,732 | 17.1% | 17.4% | 18.2% | 17.9% .. 18.5% |
| 20 min and up | 46,269 | 18.0% | 18.3% | 20.3% | 19.9% .. 20.7% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.0996 against 0.1003 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 27,603 | 5.9% | 5.9% |
| 12-16 min | 52,968 | 12.9% | 12.7% |
| 16-20 min | 60,732 | 18.2% | 18.2% |
| 20 min and up | 46,269 | 20.5% | 20.3% |

## `shots_on_goal`

- Over 250,096 held-out samples the correction improves the Brier score from 0.1296 to 0.1288 (delta +0.00073). Calibration can rule this model out; it cannot rule it in. Whether the market disagrees with it profitably is a separate question, answered only by prices.

### Reliability, before and after the correction

| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |
|:-------|--------:|----------------:|----------------------:|---------:|
| 0%-10% | 80,450 | 4.9% | 4.0% | 2.9% |
| 10%-20% | 53,320 | 14.6% | 14.5% | 11.6% |
| 20%-30% | 36,277 | 24.9% | 24.9% | 22.8% |
| 30%-40% | 30,061 | 34.8% | 34.8% | 33.1% |
| 40%-50% | 22,351 | 44.8% | 44.8% | 45.7% |
| 50%-60% | 15,805 | 54.6% | 54.8% | 58.0% |
| 60%-70% | 9,109 | 64.4% | 64.7% | 71.5% |
| 70%-80% | 2,557 | 73.6% | 74.3% | 82.9% |
| 80%-90% | 166 | 81.8% | 83.3% | 91.0% |

### By ice time — where a count model's defects actually live

| Ice time | Samples | Predicted (raw) | Predicted (corrected) | Observed | 95% on observed |
|:---------|--------:|----------------:|----------------------:|---------:|:----------------|
| under 12 min | 36,804 | 15.4% | 14.0% | 8.0% | 7.7% .. 8.3% |
| 12-16 min | 70,624 | 20.6% | 19.7% | 16.8% | 16.5% .. 17.1% |
| 16-20 min | 80,976 | 25.9% | 25.6% | 26.1% | 25.8% .. 26.4% |
| 20 min and up | 61,692 | 26.9% | 26.7% | 30.7% | 30.4% .. 31.1% |

⚠ marks a bucket below 100 samples. Its numbers are printed with their count and should be read as noise, not as a finding.

### The same buckets, corrected per ice-time bucket

Brier 0.1270 against 0.1288 pooled, so the ice-time-conditional correction beats the pooled curve here. The mechanism is in `docs/why_ice_time_gets_its_own_correction.md`; the decision to use it belongs to the price-based backtest, not to this table.

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 36,804 | 8.1% | 8.0% |
| 12-16 min | 70,624 | 17.2% | 16.8% |
| 16-20 min | 80,976 | 26.7% | 26.1% |
| 20 min and up | 61,692 | 31.6% | 30.7% |

## Standing notes

- Calibration can rule a model out. It cannot rule one in. Nothing in this report says the model beats a price; that question is answered only by `data/outputs/player_props_backtest.md`.
- Every correction applied here was fitted only on samples from strictly earlier game-days. Warm-up samples are dropped rather than scored uncorrected, and the count is stated per market.
- Ice time is the dominant input to a skater prop, so a correction that straightens the headline curve while leaving a volume bucket bent has not fixed the model.
- These samples are priced at standard lines, not at prices that were actually for sale. A well-calibrated model with no price advantage is a normal and unprofitable thing to have.
- Goalie relief appearances produce no sample: a book posts a total saves line for the expected starter, and nobody can bet a saves prop on a goalie who enters cold in the second period. See `docs/goalie_props_need_a_confirmed_starter.md` — the model still has no way to know who starts, which is a card-level gate rather than something this measurement fixes.
- Both a pooled correction and an ice-time-conditional one are shown for every market, whether or not the conditional one wins. A variant reported only when it wins is a selection, not a measurement.
