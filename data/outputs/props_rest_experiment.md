# Props rest experiment: does knowing about back-to-backs make better bets?

Two variants of the identical policy on identical prices. The diagnostic (own-side scoring −6%, opponent-side +5%, both-tired cancelling, the tired team's goalie busier) said the model misses fatigue; this decides whether correcting it beats the prices that were actually for sale.

| Market | Rest ignored | Rest known | Delta |
|:-------|-------------:|-----------:|------:|
| `assists` | -24.3u (384) | -18.0u (403) | +6.4u |
| `blocked_shots` | +65.7u (555) | +65.2u (548) | -0.4u |
| `goalie_saves` | -10.3u (410) | -6.8u (397) | +3.4u |
| `goals` | +4.2u (37) | +2.6u (35) | -1.6u |
| `points` | -43.9u (910) | -51.8u (940) | -7.9u |
| `shots_on_goal` | +64.9u (2471) | +76.5u (2508) | +11.5u |
| **Total** | +56.3u | +67.7u | **+11.4u** |

## Verdict

Rest-known finishes **+11.4u** ahead across the measured markets, improving 3 of 6. The adjustment ships because the bar is *must not lose the backtest* and it does not, while making the stated probabilities honest on the quarter of the schedule that is a back-to-back. It is not evidence of an edge, and a delta this size would not survive any correction for chance.

Recorded to `props_rest_experiment.json`. The card and the default sample generation read the verdict rather than assert their own — the configuration stays auditable against the measurement that made it.
