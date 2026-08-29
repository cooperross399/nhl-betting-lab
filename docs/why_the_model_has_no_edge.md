# Why the model has no edge

Recorded 2026-08-29, on the full two-season population: 2,710 events,
1,261,440 prices, **284,493 priced opinions** and 73,918 bets at the shipped
6% bar. This is the answer to "why does it lose", and it is a cleaner answer
than the loss itself.

## The finding

**Once the market's price is known, the model's disagreement with it carries
no information.**

Fitting the model's bias on the 2024-25 opinions and testing on the 145,751
opinions of 2025-26 it had never seen:

| | mean error on the unseen window |
|:--|--:|
| model, raw | −6.34% |
| model, bias-corrected | −0.63% |
| market implied price | −2.11% |

So the model *can* be made calibrated — the correction removes almost all of
its bias. Then the question that decides everything:

```
outcome ~ market_implied + (corrected_model − market_implied)
coefficient on the disagreement: +0.032   95% interval [−0.037, +0.102]
```

A coefficient of 1.0 would mean the model's disagreement is fully
informative. A coefficient of 0.0 means it adds nothing the price already
has. The interval sits on zero.

## The same fact, three other ways

**The model's error grows with its disagreement; the market's does not.**

| model − market | opinions | model error | market error |
|:--|--:|--:|--:|
| ±3% | 130,003 | −3.6% | −2.2% |
| +3 to +8% | 112,069 | −6.6% | −1.5% |
| +8 to +15% | 37,736 | −11.2% | −0.8% |
| +15%+ | 4,685 | **−19.5%** | **−0.7%** |

The market's error stays flat and near zero however loudly the model
disagrees. The model's error grows in almost exact proportion to the
disagreement. Every unit of claimed edge is a unit of its own error.

**A bigger claimed edge is worse, not better.** Realised ROI by claimed edge,
on the bets actually taken: −1.3% at 6–8%, −4.8% at 8–10%, −4.8% at 10–15%,
−18.1% at 20–30%. If the edge signal were real this table would slope the
other way. It slopes down.

**The overconfidence is everywhere, not only where it bets.** Across all
284,493 opinions the model overestimates by 3 to 8 points at every
probability level — 55% is really 49%, 74% is really 67%.

## What this rules out

It rules out every fix that is a re-weighting of the same signal:

- **A higher edge threshold** cannot work, because higher claimed edge is
  where the model is *more* wrong.
- **Shrinking toward the market** is arithmetically the same as raising the
  threshold — `w·p_model + (1−w)·p_implied` moves the edge to `w · edge`, so
  it re-ranks by exactly the same quantity.
- **Recalibration** fixes the bias and leaves the disagreement uninformative,
  which is the regression above.
- **Picking a market** does not survive: `blocked_shots` was the only
  positive result and failed replication on the unseen window.

## What it does not rule out

It says this *information set* is already in the price — historical rates,
opponent, venue, rest. It says nothing about information the market lacks or
prices slowly. If there is a way forward it is there, not in tuning:

- **Confirmed starting goalies.** `goalie_saves` is gated for exactly this
  reason. The market prices the confirmed starter; the model does not know
  who it is.
- **Lineup news before the price moves** — scratches, line and power-play
  unit changes. That is a latency race, not a modelling problem, and it needs
  a feed the lab does not have.
- **Stale rungs on alternate ladders**, where a book moves the main line and
  leaves the ladder behind.

Each is a different project with a different failure mode, and each would
have to clear the same bar this one did not: walk-forward, measured against
real prices, corrected for the search, and replicated on a window it was not
found on.

## Why this is worth having

The lab was built to answer this honestly, and it did — on 284,493 opinions
rather than the 4,830 that had previously said "no demonstrated edge" while
pointing mildly upward. The wrong version of this project ships that +1.4%
and finds out with real money over a season.
