# Rest experiment: does knowing about back-to-backs make better bets?

The motivating diagnostic: an 8.5-point moneyline miss on away back-to-backs over 574 games. Mechanism and diagnostic are still not the decision — identical policies on identical prices, one knowing the schedule, one ignoring it.

| Market | Variant | Bets | Profit | ROI | 95% interval |
|:-------|:--------|-----:|-------:|----:|:-------------|
| `moneyline` | rest_ignored | 1536 | -50.5u | -3.3% | -8.8% .. +2.2% |
| `puck_line` | rest_ignored | 1563 | -71.3u | -4.6% | -8.9% .. -0.2% |
| `regulation_3_way` | rest_ignored | — | — | — | no prices |
| `total_goals` | rest_ignored | 823 | -1.2u | -0.1% | -6.7% .. +6.4% |
| `moneyline` | rest_known | 1504 | -36.5u | -2.4% | -8.0% .. +3.1% |
| `puck_line` | rest_known | 1530 | -62.5u | -4.1% | -8.5% .. +0.4% |
| `regulation_3_way` | rest_known | — | — | — | no prices |
| `total_goals` | rest_known | 818 | -5.5u | -0.7% | -7.3% .. +5.9% |

## Verdict

The priced sample is close to indifferent: rest-known finishes **+18.4u** ahead across the measured markets, improving 2 of 3. That is the interesting finding — the books already price fatigue, so correcting the model's 8.5-point residual bias mostly moves its probabilities toward numbers the market had all along. The adjustment ships because the rule's bar is *must not lose the backtest* and it does not, while making the stated probabilities honest on a quarter of the schedule. It is not evidence of an edge, and a delta this small would not survive any correction for chance.
