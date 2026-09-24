# Correction experiment: does better calibration make better bets?

The rule: where historical prices exist, the price-based backtest decides. Both corrections straighten every reliability bucket; this is the question that actually governs.

| Window | Variant | Bets | Profit | ROI | 95% interval |
|:-------|:--------|-----:|-------:|----:|:-------------|
| 2024-25 | raw | 11362 | +239.4u | +2.1% | +0.2% .. +4.0% |
| 2024-25 | pooled | 9108 | +48.5u | +0.5% | -1.5% .. +2.6% |
| 2024-25 | by_toi | 9141 | +44.6u | +0.5% | -1.6% .. +2.6% |
| 2025-26 | raw | 16925 | -248.5u | -1.5% | -3.0% .. +0.0% |
| 2025-26 | pooled | 14625 | -226.1u | -1.5% | -3.1% .. +0.0% |
| 2025-26 | by_toi | 14029 | -149.6u | -1.1% | -2.7% .. +0.6% |

## Verdict

- **pooled** loses the backtest (-168.5u against raw) despite improving calibration. Exactly the EPL lesson: it does not ship, and the calibration tables do not overrule this.
- **by_toi** loses the backtest (-95.9u against raw) despite improving calibration. Exactly the EPL lesson: it does not ship, and the calibration tables do not overrule this.

Every correction applied to a bet was fitted only on samples from strictly earlier dates, on the same cadence the sample generator uses. The three variants saw identical prices and used the identical selection rule; only the stated probability differed.
