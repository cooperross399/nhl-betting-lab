# Props rest experiment: does knowing about back-to-backs make better bets?

Two variants of the identical policy on identical prices. The diagnostic (own-side scoring −6%, opponent-side +5%, both-tired cancelling, the tired team's goalie busier) said the model misses fatigue; this decides whether correcting it beats the prices that were actually for sale.

| Market | Rest ignored | Rest known | Delta |
|:-------|-------------:|-----------:|------:|
| `assists` | -40.3u (3611) | -36.2u (3742) | +4.1u |
| `blocked_shots` | +242.4u (3044) | +240.5u (3026) | -1.9u |
| `goalie_saves` | -6.1u (112) | -6.3u (114) | -0.1u |
| `goals` | -16.5u (826) | -23.3u (842) | -6.8u |
| `hits` | -61.8u (5112) | -67.0u (5178) | -5.3u |
| `points` | -243.6u (5927) | -256.8u (6140) | -13.2u |
| `shots_on_goal` | +98.1u (8986) | +140.0u (9245) | +41.9u |
| **Total** | -27.8u | -9.1u | **+18.7u** |

## Verdict

Rest-known finishes **+18.7u** ahead across the measured markets, improving 2 of 7. The adjustment ships because the bar is *must not lose the backtest* and it does not, while making the stated probabilities honest on the quarter of the schedule that is a back-to-back. It is not evidence of an edge, and a delta this size would not survive any correction for chance.

Recorded to `props_rest_experiment.json`. The card and the default sample generation read the verdict rather than assert their own — the configuration stays auditable against the measurement that made it.
