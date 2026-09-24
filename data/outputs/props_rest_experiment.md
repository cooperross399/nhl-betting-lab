# Props rest experiment: does knowing about back-to-backs make better bets?

Two variants of the identical policy on identical prices. The diagnostic (own-side scoring −6%, opponent-side +5%, both-tired cancelling, the tired team's goalie busier) said the model misses fatigue; this decides whether correcting it beats the prices that were actually for sale.

| Market | Rest ignored | Rest known | Delta |
|:-------|-------------:|-----------:|------:|
| `assists` | -35.9u (3486) | -35.2u (3609) | +0.7u |
| `blocked_shots` | +243.8u (2907) | +243.8u (2894) | +0.1u |
| `goalie_saves` | -2.1u (108) | -2.3u (110) | -0.1u |
| `goals` | -13.8u (807) | -21.1u (820) | -7.3u |
| `hits` | -55.2u (4957) | -60.0u (5021) | -4.8u |
| `points` | -246.3u (5732) | -256.2u (5933) | -9.9u |
| `shots_on_goal` | +90.3u (8658) | +130.5u (8899) | +40.2u |
| **Total** | -19.2u | -0.4u | **+18.7u** |

## Verdict

Rest-known finishes **+18.7u** ahead across the measured markets, improving 3 of 7. The adjustment ships because the bar is *must not lose the backtest* and it does not, while making the stated probabilities honest on the quarter of the schedule that is a back-to-back. It is not evidence of an edge, and a delta this size would not survive any correction for chance.

Recorded to `props_rest_experiment.json`. The card and the default sample generation read the verdict rather than assert their own — the configuration stays auditable against the measurement that made it.
