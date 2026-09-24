# Rest experiment: does knowing about back-to-backs make better bets?

The motivating diagnostic: an 8.5-point moneyline miss on away back-to-backs over 574 games. Mechanism and diagnostic are still not the decision — identical policies on identical prices, one knowing the schedule, one ignoring it.

Priced in the `late` window, median 1.5 hours before face-off. 34,196 price row(s) captured at or after face-off and 61,784 from other windows were excluded.

| Market | Variant | Bets | Profit | ROI | 95% interval |
|:-------|:--------|-----:|-------:|----:|:-------------|
| `moneyline` | rest_ignored | 998 | -72.0u | -7.2% | -14.2% .. -0.3% |
| `puck_line` | rest_ignored | 1163 | -45.0u | -3.9% | -8.9% .. +1.2% |
| `regulation_3_way` | rest_ignored | — | — | — | no prices |
| `total_goals` | rest_ignored | 1219 | -47.4u | -3.9% | -9.3% .. +1.5% |
| `moneyline` | rest_known | 954 | -62.9u | -6.6% | -13.6% .. +0.4% |
| `puck_line` | rest_known | 1117 | -47.1u | -4.2% | -9.4% .. +0.9% |
| `regulation_3_way` | rest_known | — | — | — | no prices |
| `total_goals` | rest_known | 1216 | -48.6u | -4.0% | -9.4% .. +1.4% |

## Verdict

The priced sample is close to indifferent: rest-known finishes **+5.8u** ahead across the measured markets, improving 1 of 3. That is the interesting finding — the books already price fatigue, so correcting the model's 8.5-point residual bias mostly moves its probabilities toward numbers the market had all along. The adjustment ships because the rule's bar is *must not lose the backtest* and it does not, while making the stated probabilities honest on a quarter of the schedule. It is not evidence of an edge, and a delta this small would not survive any correction for chance.
