# Rest experiment: does knowing about back-to-backs make better bets?

The motivating diagnostic: an 8.5-point moneyline miss on away back-to-backs over 574 games. Mechanism and diagnostic are still not the decision — identical policies on identical prices, one knowing the schedule, one ignoring it.

| Market | Variant | Bets | Profit | ROI | 95% interval |
|:-------|:--------|-----:|-------:|----:|:-------------|
| `moneyline` | rest_ignored | 1536 | -50.5u | -3.3% | -8.8% .. +2.2% |
| `puck_line` | rest_ignored | 1574 | -75.1u | -4.8% | -9.1% .. -0.4% |
| `regulation_3_way` | rest_ignored | — | — | — | no prices |
| `total_goals` | rest_ignored | 1154 | -2.5u | -0.2% | -5.7% .. +5.2% |
| `moneyline` | rest_known | 1504 | -36.5u | -2.4% | -8.0% .. +3.1% |
| `puck_line` | rest_known | 1541 | -66.4u | -4.3% | -8.7% .. +0.1% |
| `regulation_3_way` | rest_known | — | — | — | no prices |
| `total_goals` | rest_known | 1150 | -5.9u | -0.5% | -6.0% .. +5.0% |

## Verdict

The priced sample is close to indifferent: rest-known finishes **+19.4u** ahead across the measured markets, improving 2 of 3. That is the interesting finding — the books already price fatigue, so correcting the model's 8.5-point residual bias mostly moves its probabilities toward numbers the market had all along. The adjustment ships because the rule's bar is *must not lose the backtest* and it does not, while making the stated probabilities honest on a quarter of the schedule. It is not evidence of an edge, and a delta this small would not survive any correction for chance.
