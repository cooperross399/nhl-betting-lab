# Pre-registration: drop the over side

**Registered 2026-09-02, before the season opens on 2026-09-29.**
Nothing below may be revised after the first game. This document exists so
that a decision taken later cannot be re-described as a prediction made now.

## The hypothesis

The card's over-side selections are a measured drag and should be removed.

## The evidence it rests on

From the diagnostics of 2026-09-02, on the canonical 25,947-wager population:

| Side | Bets | ROI |
|:--|--:|--:|
| Unders | 23,375 | **+0.17%** [−1.12%, +1.40%] |
| Overs | 2,572 | **−4.48%** [−8.92%, −0.10%] |

The over side's interval excludes zero on the losing side. In the honest
decomposition of the card's −0.29%, side mix contributes **−0.37 points**: the
model's 9.9% overs actively dilute its unders.

This is consistent with the mechanism already documented in
`docs/where_the_remaining_error_lives.md` — the model prices players on the
minutes they used to play, and the resulting error is asymmetric.

## Why it is a hypothesis and not a finding

**It was not pre-registered before it was measured.** It came out of a
diagnostic that examined roughly seven cuts of the same data, and no
family-wise correction was applied to the side split. A −4.48% cell with an
upper bound of −0.10% is one ordinary revision away from spanning zero.

This lab has retracted four findings. The most recent, a +11-point result,
replicated across both seasons and was reproduced by a placebo containing
seven constants. A cell that merely looks bad is not evidence that removing
it helps.

## What would settle it, and what would not

**The test is the forward ledger, not a re-cut of the same two seasons.**
Opinions are frozen before puck drop and settled day-as-unit; the over side
is scored separately from the under side from opening night.

**Passes** — the over side is dropped — if, at the pre-registered decision
date of **2027-04-25** (`docs/when_this_ends.md`):

1. forward over-side ROI is negative with a 95% interval excluding zero,
   clustered by game date; **and**
2. forward under-side ROI is at least as good with the overs removed as with
   them included, on the same nights; **and**
3. there are at least 500 forward over-side wagers, so the cell is not being
   judged on a sample smaller than the noise that produced it.

**Fails** — the over side stays — if the forward over-side interval spans
zero, which is the outcome to expect if the −4.48% was a subgroup artifact.

**Neither** — and the question is simply carried, unresolved, rather than
resolved in the direction the point estimate happens to point — if fewer than
500 over-side wagers accrue.

## What is explicitly NOT being done now

The card is **not** being changed. No gate is being weakened, no market
withdrawn, no policy edited. Both sides continue to be priced and frozen,
because dropping the side now would destroy the only sample that could test
this, and a rule that removes its own evidence can never be wrong.
