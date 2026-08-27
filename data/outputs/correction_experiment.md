# Correction experiment: does better calibration make better bets?

The rule: where historical prices exist, the price-based backtest decides. Both corrections straighten every reliability bucket; this is the question that actually governs.

| Window | Variant | Bets | Profit | ROI | 95% interval |
|:-------|:--------|-----:|-------:|----:|:-------------|
| 2024-25 | raw | 3450 | +106.6u | +3.1% | -0.3% .. +6.5% |
| 2024-25 | pooled | 2719 | +8.1u | +0.3% | -3.4% .. +4.0% |
| 2024-25 | by_toi | 2724 | +47.7u | +1.8% | -1.9% .. +5.4% |
| 2025-26 | raw | 1327 | -50.3u | -3.8% | -9.0% .. +1.4% |
| 2025-26 | pooled | 1160 | -48.8u | -4.2% | -9.7% .. +1.2% |
| 2025-26 | by_toi | 1225 | -29.0u | -2.4% | -7.7% .. +3.0% |

## Verdict

- **pooled** loses the backtest (-97.0u against raw) despite improving calibration. Exactly the EPL lesson: it does not ship, and the calibration tables do not overrule this.
- **by_toi** loses the backtest (-37.6u against raw) despite improving calibration. Exactly the EPL lesson: it does not ship, and the calibration tables do not overrule this.

Every correction applied to a bet was fitted only on samples from strictly earlier dates, on the same cadence the sample generator uses. The three variants saw identical prices and used the identical selection rule; only the stated probability differed.
