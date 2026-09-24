# Correction experiment: does better calibration make better bets?

The rule: where historical prices exist, the price-based backtest decides. Both corrections straighten every reliability bucket; this is the question that actually governs.

| Window | Variant | Bets | Profit | ROI | 95% interval |
|:-------|:--------|-----:|-------:|----:|:-------------|
| 2024-25 | raw | 10903 | +250.1u | +2.3% | +0.4% .. +4.2% |
| 2024-25 | pooled | 8753 | +47.6u | +0.5% | -1.5% .. +2.6% |
| 2024-25 | by_toi | 8791 | +56.6u | +0.6% | -1.5% .. +2.8% |
| 2025-26 | raw | 16383 | -250.5u | -1.5% | -3.0% .. -0.0% |
| 2025-26 | pooled | 14197 | -212.9u | -1.5% | -3.1% .. +0.1% |
| 2025-26 | by_toi | 13626 | -136.8u | -1.0% | -2.7% .. +0.7% |

## Verdict

- **pooled** loses the backtest (-164.9u against raw) despite improving calibration. Exactly the EPL lesson: it does not ship, and the calibration tables do not overrule this.
- **by_toi** loses the backtest (-79.8u against raw) despite improving calibration. Exactly the EPL lesson: it does not ship, and the calibration tables do not overrule this.

Every correction applied to a bet was fitted only on samples from strictly earlier dates, on the same cadence the sample generator uses. The three variants saw identical prices and used the identical selection rule; only the stated probability differed.
