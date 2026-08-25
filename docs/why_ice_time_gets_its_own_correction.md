# Why ice time gets its own calibration correction

A per-group calibration correction is curve-fitting with extra steps unless
there is a mechanism for why the groups differ. This document is that
mechanism, written before the change was made, so it can be judged on the
argument rather than on the improvement.

## What the measurement showed

Walk-forward calibration of `assists` over 125,048 held-out samples, split by
the player's ice time in the game being priced:

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 18,402 | 8.9% | 5.2% |
| 12-16 min | 35,312 | 11.7% | 11.0% |
| 16-20 min | 40,488 | 15.4% | 16.3% |
| 20 min and up | 30,846 | 18.1% | 20.7% |

The same shape appears on `shots_on_goal`, `points` and `blocked_shots`: the
model runs hot on low-minutes players and cold on high-minutes ones, in every
market, with samples in the tens of thousands per bucket.

A single Platt curve cannot fix this. It applies one monotone transform to
every probability, and here the required correction runs in **opposite
directions** in different buckets. That is why the pooled correction moved the
Brier score by less than 0.001 on three of the four skater markets: it was
being asked to push a curve up and down at the same time.

## The mechanism

The model has ice-time **quantity** and no measure of ice-time **quality**.

A forward playing nine minutes is not a scaled-down version of a forward
playing twenty-two. He plays those nine minutes against the opponent's best
players or in the defensive zone, without power-play time, with linemates who
are also fourth-liners. His per-minute production is genuinely lower, and not
because of anything the per-60 rate can see.

The shrinkage makes it worse in a predictable direction. Every player's rate
is pulled toward his position group's league baseline in proportion to the ice
time behind it — and that baseline is dominated by the players who play the
most minutes, because it is computed per sixty minutes across all of them. So
a low-minutes player, who has the least evidence and gets shrunk hardest, is
shrunk toward a number describing players who get far better minutes than he
does. The model then multiplies that inflated rate by his (correctly low)
expected ice time and still lands too high.

The high-minutes bucket is the same effect with the sign flipped: a
first-liner is shrunk down toward a baseline that includes fourth-liners, and
his power-play time is only crudely represented by the goals-share proxy.

Both directions follow from one missing input. That is a mechanism, not a
pattern found by slicing.

## What the correction does and does not do

It fits a separate Platt curve per ice-time bucket, walk-forward, with the
pooled curve as the fallback for any bucket that lacks its own history. It is
still two parameters per bucket; nothing here is flexible enough to memorise
the sample.

It does **not** fix the model. The right fix is an ice-time-quality input —
line assignment, zone starts, power-play time — and this repository does not
have one, for the reasons in `docs/nhl_data_sources.md`. The correction makes
the model's stated probabilities mean what they say across the range of
workloads it prices; it adds no information the model did not have.

## The rule this does not escape

Better calibration is not a reason to ship. `CLAUDE.md` is explicit: where
historical prices exist, a price-based backtest decides, and a change that
improves calibration but loses the backtest does not ship. This correction
must clear that bar in `data/outputs/player_props_backtest.md` before it
influences a single selection, and until it has, its status in that report is
what governs — not the tables above.
