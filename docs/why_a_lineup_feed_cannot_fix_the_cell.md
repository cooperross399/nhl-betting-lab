# Why a lineup feed cannot fix the stale-ice-time cell

**Measured 2026-09-02, before any Daily Faceoff data existed.** This document
exists so that the collection now running is understood as a cheap option and
not as an investment thesis, and so nobody re-derives the hope in six months.

## The question

The card's loss localises to one cell: it bets unders on players whose ice
time is about to rise. Substituting future ice time — an oracle — takes the
card from −0.29% to about +4.6%. So the prize looked like roughly five ROI
points, and the plan was to buy it with a pre-game lineup feed.

The question this settles is the only one that mattered: **how accurate would
that feed have to be?** Cooper needed the specification before spending a
season collecting, not after.

## The answer: there is no specification, because the target is wrong

A detector is characterised by sensitivity `s` (it flags a true role change)
and specificity `t` (it does not flag a false one). Sweeping an 11×11 grid
from 0.50 to 1.00 on the target a feed can actually see — a role change that
**persists past tonight** — every one of the 121 cells has a 95% interval
containing zero.

Including the corner. A **perfect** detector, `s = 1.00, t = 1.00`, leaves the
card at **+0.26%, 95% [−1.45%, +1.86%]** over 20,855 bets — **no demonstrated
edge**. If the perfect detector fails, no achievable one passes.

## Why: the cell is three groups, and a feed sees the wrong two

Split the losing cell by whether the ice-time rise persists beyond tonight:

| Group | ROI | Bets | Can a feed see it? |
|:--|--:|--:|:--|
| Rise **persists** — a real promotion | −9.98% | 2,662 | **Yes** |
| Rise is a **one-off big night** | −7.22% | 5,160 | **No** |
| Role **is** expanding, but quiet tonight | **+5.57%** | 2,430 | Yes — and it would say abstain |

Two thirds of the cell's lost units — **372.6 of 638** — sit in the one-off
group. That is tonight's game variance, not a deployment fact, and no lineup
feed in existence can see it.

Worse, the group a feed *can* see is heterogeneous: a −9.98% losing group
sitting beside a **+5.57% winning group of almost the same size**. A feed that
correctly flags "this player's role is expanding" tells you to abstain from
both. It destroys as much value as it saves, which is precisely why the
perfect-detector corner nets nothing.

## The apparent ceiling was an outcome filter

The oracle ceiling is real arithmetic and reproduces exactly — abstaining
above a 2-minute realised rise gives +3.11% [+1.39%, +4.80%], and a placebo
removing the same number of *random* bets reaches only −0.30% (z = 8.3, and a
placebo matched on market × selection × price behaves identically). The cell
is genuinely special.

It is also **circular**. Realised ice time in tonight's game is mechanically
correlated with tonight's counting stats — +0.175 on shots, +0.163 on blocks —
so "abstain when tonight's minutes were high" is substantially "abstain when
the under was going to lose." The ceiling is same-game leakage.

Two independent checks confirm it is not a line-label result at all:

- A **one-bit placebo** carrying only the *sign* of the realised ice-time move
  — no band, no rank, no minutes, no line content whatever — reproduces
  +3.05% against the oracle band's +3.12%. The difference is **+0.07 points,
  95% [−1.04, +1.31]**, spanning zero.
- Two oracles with *no* line structure **beat** the band. Eight league-wide
  quantile bins of realised ice time return +4.89%, a difference of
  −1.77 points [−2.65, −0.80] *against* the band.

And the ceiling does not replicate: **+5.23% in 2024-25, +0.76% [−1.76%,
+3.17%] in 2025-26** — no demonstrated edge in the second season. Under this
lab's own replication rule that is a second, independent reason to stop.

## The feasible version is worth nothing

Re-pricing the card with the best label inferable from a player's own history
(his band in his most recent game) returns **−0.02 points, 95% [−0.84,
+0.81]** against the incumbent trailing-10 estimate. That is not surprising in
hindsight: any label derived from a player's history is a *coarsening* of that
history, so it cannot add to it.

At predicting the rise, the band prior scores **AUC 0.568** against 0.560 for
a plain trailing read. A perfect label scores 0.839 — so the honest bracket
for a real feed is that whole span, and it is unmeasurable until real labels
exist. But **47.5% of >2-minute rises happen with no band change at all**, so
even a perfect label is blind to about half the event.

At predicting minutes, trailing-10 beats the band prior outright: MAE 1.984
versus 2.551 minutes. The fitted blend puts 0.86 on the player's own trailing
minutes and 0.14 on the band.

## No free rule captures it either

A walk-forward pre-game score reaches AUC 0.665 and 64.8% top-decile
precision, yet every free abstention rule leaves the card spanning zero. The
best — abstain on unstable within-team ice-time rank — gives +0.57% [−1.22%,
+2.32%]. So the feed is not *redundant*; it is simply that neither route pays.

## What this changes, and what it does not

**Do not buy a projections feed for this purpose.** RotoWire and RotoGrinders
sell projected ice time; the measurement above says the target they would
improve is not the target that loses the money. That decision is Cooper's, but
the evidence points one way.

**Keep collecting Daily Faceoff anyway.** It is free, already built, already
wired beside the price capture, and it **cannot be backfilled** — the source
keeps no archive, so a night not captured is gone. Collection is a cheap
option on a question this measurement could not close: every number here uses
*realised ice-time rank* as a stand-in for a line label, because no real label
exists for these two seasons. A posted line is different in kind — it states
intent before the game and therefore carries no same-game leakage.

That is a reason to keep the option open. It is **not** a reason to expect it
to pay, and the leakage decomposition above is structural rather than an
artifact of the proxy: the persist/one-off/quiet split is about persistence,
which is exactly what a feed reports.

## Pre-registered forward test

Registered **2026-09-02**, before the season opens on 2026-09-29 and before
any real line label has been collected. Nothing below may be revised
afterwards.

**Primary test.** On forward game days with captured Daily Faceoff labels,
compare the card's ROI under an abstention rule keyed on a **posted line or
power-play unit change** against the same card without abstention, on the same
nights, paired.

**It passes** — the rule ships — only if all four hold at the pre-registered
decision date of 2027-04-25 (`docs/when_this_ends.md`):

1. the paired difference is positive with a 95% date-clustered interval
   excluding zero;
2. it survives a Bonferroni correction over every threshold and rule variant
   examined, counted honestly;
3. it holds in **both** halves of the season, split by date in advance; and
4. at least **400** wagers were abstained from, so the rule is not judged on
   a sample smaller than the noise that produced it.

**It fails** on any of: the interval spanning zero, appearing in one half
only, or the one-bit placebo above reproducing it — which is the test that
already killed the retrospective version.

**Explicitly not a pass:** any rule discovered by sweeping the forward data
after the fact. The rule above is a single pre-specified comparison. If
something else is found in the forward data, it is a hypothesis for the season
after, not a finding for this one.
