# Schedule states checked against the model, and what was built

The record of what was measured, what shipped, and what was deliberately not
built. This lives in `docs/` and not in `data/outputs/` because the
experiment outputs are regenerated on every run — the first draft of this
record was appended to one and lasted exactly one re-run.

## Back-to-backs: shipped, for teams and for props

The team diagnostic: the model missed away back-to-backs by 8.5 points over
574 games. The adjustment (venue-split, totals-preserving, shrunk) ships on
the price backtest — +19.4u on the corrected joins, under the must-not-lose
bar, explicitly not evidence of an edge.

The props diagnostic, on 749,115 walk-forward samples: on a back-to-back,
scoring production runs about six percent under the model (goals 0.963 vs a
rested 1.017 act/pred, assists 0.982 vs 1.034, points 0.975 vs 1.027); the
opponent-tired mirror runs the same amount *over* (goals 1.060, assists
1.086, points 1.077); the both-tired cell cancels to baseline without being
asked to; and the tired team's goalie makes more saves (1.052) while the
goalie facing tired shooters makes fewer (0.970). Seven independent
settlement columns, every direction fatigue predicts. The adjustment
(per-market own and opponent factors, shrunk, fitted from the training logs
only) ships on the price backtest — +11.4u, same bar, same caveat.

Both verdicts are recorded (`rest_experiment.json`,
`props_rest_experiment.json`) and read through `verdicts.ships` by the card
and the sample generators, so what is in force is auditable against the
measurement that decided it.

## The third game in four nights: checked, and not built

Diagnosed the same way, on 3,658 walk-forward-priced games with the shipped
rest policy in force:

| Schedule state | Games | Predicted home | Actual home | Miss |
|:---------------|------:|---------------:|------------:|-----:|
| both sides rested | 2,191 | 53.5% | 54.0% | +0.6 |
| home 3-in-4, not a B2B | 232 | 53.5% | 46.1% | **−7.4** |
| away 3-in-4, not a B2B | 227 | 52.9% | 50.7% | −2.3 |

The home cell looks like fatigue at about 2.2σ. **The mirror cell points the
wrong way** — a tired away side should push the home number up, and it moves
down. A real venue-symmetric mechanism shows in both cells; one cell at 2.2σ
with a contradicting mirror, found among several looks, is what noise looks
like, and a factor fitted to it would mostly be fitted to that one cell. So
nothing was built. If the shape recurs on 2026-27 data with both cells
agreeing, that is the moment to build it — through the same price-decides
harness everything else used.

## The B2B adjustment closes less than half the team gap, on purpose

With the shipped policy in force, the away-B2B/home-rested miss is +5.3
points over 574 games, down from +8.5 unadjusted. The remainder is shrinkage
doing its job walk-forward: early fit windows hold few back-to-backs, so
their factors sit near 1.0 and grow with evidence. Widening it faster would
be tuning the shrinkage to this diagnostic — and the price backtest approved
the adjustment as it is. The residual is recorded rather than chased.
