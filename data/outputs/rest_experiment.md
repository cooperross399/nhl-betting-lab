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

## Postscript: the states beyond a strict back-to-back, checked and not built

The natural next feature was the third game in four nights. Diagnosed the same
way the back-to-back was, on 3,658 walk-forward-priced games with the shipped
rest policy in force:

| Schedule state | Games | Predicted home | Actual home | Miss |
|:---------------|------:|---------------:|------------:|-----:|
| both sides rested | 2,191 | 53.5% | 54.0% | +0.6 |
| home 3-in-4, not a B2B | 232 | 53.5% | 46.1% | **−7.4** |
| away 3-in-4, not a B2B | 227 | 52.9% | 50.7% | −2.3 |

The home cell looks like fatigue at about 2.2σ. **The mirror cell points the
wrong way.** A tired away side should push the home number *up*, and it moves
down instead. A real venue-symmetric mechanism shows in both cells; one cell
at 2.2σ with a contradicting mirror, found among several looks, is what noise
looks like — and a factor fitted to it would mostly be fitted to that one
cell. So nothing was built, and this table is the record of why. If the shape
recurs on 2026-27 data with both cells agreeing, that is the moment to build
it — through the same price-decides harness the back-to-back used.

## Postscript: the adjustment closes less than half the gap, on purpose

With the shipped policy in force, the away-B2B/home-rested miss is **+5.3
points over 574 games**, down from the +8.5 the unadjusted model showed. The
remainder is shrinkage doing its job walk-forward: early fit windows hold few
back-to-backs, so their factors sit close to 1.0 and the adjustment grows as
evidence accumulates. Widening it faster would be tuning the shrinkage to
this diagnostic — and the price backtest already approved the adjustment as
it is. The residual is recorded rather than chased.
