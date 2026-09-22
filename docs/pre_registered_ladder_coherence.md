# Pre-registration: books that contradict their own ladders

**Registered 2026-09-22, seven days before the season opens on 2026-09-29 and
before a single forward rung has been captured.** Nothing below may be revised
after the first game. The point of the date is that at the moment of writing
there was no forward data to look at, so none of these numbers can have been
chosen by looking at what they returned.

## Why there is anything left to register

Everything the model can compute has been measured and comes back null. The
model's disagreement with the price carries a regression coefficient of
**0.032** [−0.037, +0.102] where the market carries 0.97, and a bigger claimed
edge is reliably *worse* (`docs/why_the_model_has_no_edge.md`). Three routes
out were tested on 2026-08-29 and two are closed:

- **Line shopping** — of 161,891 quotes, only 1,557 (under one percent) were
  positive-EV against the other books' de-vigged consensus. Every interval
  spans zero.
- **Confirmed starters and lineup latency** — not testable without a feed the
  lab does not have.
- **Alternate-ladder staleness** — recorded as *"not yet"*, not *"no"*.

This registers the third one, and it is registered rather than merely tried
because it is the last one, and a last idea searched for after everything else
failed is exactly the idea most likely to be a false positive.

## The hypothesis

**A book that contradicts its own ladder is mispricing the rung it left
behind, and taking that rung returns more than zero.**

The arithmetic is containment and nothing else. For lines `i < j`, the event
`S > j` is inside `S > i`, so `P(S > i) >= P(S > j)` for every player on every
night. A book quoting `over j` at a higher probability than `over i` has
contradicted itself, and no view about hockey is needed to see it.

The bet is the over at the lower line. Its edge is a **lower bound**:

    edge  =  p_j (de-vigged fair price of the higher rung)
           −  q_i (vig-inclusive price the lower rung is sold at)

conservative twice over — a de-vigged probability against a price that still
carries margin, and the higher rung assumed exactly fair when the violation
means at least one of the two is not.

**Only one book, one moment, two rungs.** Two books is the line-shopping
hypothesis and it is dead. Two moments is a book changing its mind, which is
not a contradiction. The detector is `src/nhl_betting_lab/ladder_coherence.py`
and it never compares across either.

## What the historical data can and cannot say

It cannot test this. `scripts/buy_historical_props.py` requested the seven
standard prop keys and **never the alternate ladders**, so the ladders this
hypothesis is about are absent from the two-season store. That is the same
mistake the EPL lab made with `total_2_5` — a market written off after
checking only the bulk endpoint — and it is why the answer here is "not yet"
rather than "no".

Running the detector over the store anyway says how little is there. Of
2,004,796 ladders, 284,544 carry two or more distinct lines — but the
detector needs the *higher* rung quoted on both sides, because a one-sided
rung cannot be de-vigged and the whole edge arithmetic rests on that
de-vigged number. That leaves **83 comparable rung pairs in two full
seasons**, holding one violation: Fliff, blocked shots, 1.5 against 2.5, 5.5
points, Tier B. Eighty-two duplicate rows were collapsed along the way.

**One in eighty-three is not a rate.** It is not evidence that books are
coherent and it is not evidence that they are not; it is a sample too small
to carry either reading, and quoting 1.2% from it would be the kind of number
this repository exists to not publish. The store is silent on this question,
which is the same thing "not yet" said in August, now with a denominator.

**The discouraging part is the mechanism, not the data**, and it is written
down here rather than discovered later: a book's alternate ladder is generated from one
fitted distribution for that player, which makes it coherent by construction
and moves the whole ladder atomically when the main line moves. If that is
how books actually work, this route is closed and the season will say so.

## One test, not three

The route was first sketched as three separate detectors — an instantaneous
contradiction, a rung left behind after the main line moved, and a rung out
of step with the book's fitted distribution. Three detectors is three
hypotheses against one season, which needs a family correction and gets a
third of the power.

They collapse into one. A book that moves its main line and leaves a rung
behind has, at that moment, quoted a harder threshold as likelier than an
easier one — which is exactly what the single containment test catches.
Staleness is not a separate mechanism; it is the most likely *cause* of the
one contradiction the detector looks for. So there is one test, and it is
stronger for it.

## The bands

Declared now, by **magnitude**, anchored to a mechanism, and never re-cut.
The mechanism is the vig: a two-way prop carries roughly four to eight per
cent of margin, so two to four points sit on each side and two rungs can
differ by that much through nothing more interesting than one being priced
wider than the other.

| Band | Minimum edge | Why that number | Stake if ever licensed |
|:--|--:|:--|--:|
| **wide** | 8 pts | Larger than any plausible margin artifact | 0.5u |
| **clear** | 4 pts | Clears a typical one-sided vig share outright | 0.25u |
| **marginal** | 2 pts | Detection floor — the smallest gap not comfortably a vig asymmetry | 0.1u |

Below 2 points nothing is flagged. A unit is $25, so a marginal is $2.50.

They are called bands, not tiers, and are not A/B/C, because
`reports.gameday_card` already grades edge against the best-bet bar and
calls *that* A/B/C with a byte-identical stake map. Two A/B/C scales
measuring different quantities in one repository is how `home` came to mean
the provider in one table and ESPN in another, and 36% of a November's
neutral-site bets graded for the opponent.
`tests/test_ladder_route_cannot_reach_the_ledger.py` holds the two
vocabularies apart.

**The bands order and size the card. They are not the test.** The registered
test is **pooled across all three and flat-staked**, one bet per wager, which
is the convention every other measurement here uses. Two reasons, and the
second is the one that matters:

1. Weighting a return by a staking rule this lab invented would measure the
   staking rule and the violation together, and only one of those is the
   hypothesis.
2. Splitting one test into three costs most of its power: the standard
   error rises by sqrt(3) = 1.73 and a Bonferroni correction for three looks
   raises the coefficient from 2.80 to 3.24, so a per-band MDE is almost
   exactly **twice** the pooled one. The **cbb** lab has already paid that
   bill — pooled 6.96 became 12.02 per tier on a window sized for the pooled
   test — and that number is cited here as a sibling lab's, because it is.
   It does not appear anywhere in this repository and this lab has no
   equivalent of its own: the 3,000-opinion floor in
   `docs/when_this_ends.md` is a sample floor with no power derivation
   behind it. Per-band numbers will be *reported*, with their intervals and
   their sample sizes, and they decide nothing.

## The placebo it has to beat

A finding must beat a **composition-matched random rung from the same
ladder**, not merely beat zero. For every flagged wager, one unflagged rung
from the same (event, market, player, book, snapshot) is drawn and scored
identically. If the flagged rung does not beat its own ladder's unflagged
rungs, the "edge" is a property of which players, markets and nights have deep
ladders — not of the contradiction.

This is not optional caution. The last apparently-robust finding in this
repository replicated across both seasons and was then reproduced by a placebo
containing seven constants.

## Settlement is deferred, and that loses nothing

`scripts/run_ladder_coherence.py` counts violations. It does not settle them,
and no ladder ledger is built until the December checkpoint is passed. That
looks like the mistake this lab keeps warning about — "a night not captured
is gone" — and here it is not, for a reason worth stating rather than
assuming.

A frozen model opinion cannot be reconstructed, because it depends on the
state of the model at that moment and the model moves. A flagged ladder wager
depends on nothing but the capture: the detector is deterministic given
`data/processed/line_movement/{day}.csv`, which already holds the book, the
rung, the price and the instant. Re-running it in December over October's
captures produces exactly the rows October would have produced, and the
boxscore settles them the same way the forward ledger settles everything
else.

So the thing that cannot be recovered is the **capture**, and the capture is
already running five times a day. Building a second ledger now would be
building it for a route that may be dead by December.

**The one thing this does cost** is that a settlement bug found in April
applies to the whole season at once, with no earlier run to catch it. So the
ladder ledger, when it is built, reuses `forward_evidence`'s settlement
functions rather than growing a second copy — a second copy of a settlement
rule is how every join bug in this repository started.

## The arithmetic says this is already closed

Registered honestly means registering the projection too, and the projection
is that this fails. It is written here, before the season, so that a null in
April is a confirmation rather than a discovery.

**What a test would need.** Pooled ROI, standard deviation of a unit payoff
taken as 1.0, `n` = independent (book, event, snapshot) clusters. At α=.05
and 80% power the MDE is 2.80/√n; Bonferroni across three live registrations
makes it 3.24/√n; requiring each half-season to be independently informative
makes it 4.58/√n. Inverting:

| True ROI per exploited rung | Independent clusters needed |
|:--|--:|
| +15% (generous — a genuinely stale rung should be worth a lot) | **931** |
| +10% | 2,094 |
| +8% | 3,272 |

And sd=1.0 is itself generous. Alternate rungs price at +200 to +500, where
the sd of a unit payoff runs 1.41 to 2.24 — roughly tripling every figure.

**What the season can supply.** Forward cells are 1,312 games × 5 captures a
day × ~9 books = **59,040**, already 2.6× denser than the historical board.
At the measured violating-cell rate of 4.27e-05 that is **2.5 instants a
season**. Grant the strongest pro-route assumption available — real alternate
ladders five rungs deep against the proxy's measured 0.145 pairs per ladder,
a 27× multiplier, when historical ladders max out at three rungs — and it is
**68**.

**Sixty-eight against a floor of 931.** Fourteen times short of the least
demanding bar and about 1,300× short of the realistic one. Closing the gap at
+15% would need a 368× multiplier, which at 0.145 pairs per ladder means
ladders roughly **54 rungs deep**. No NHL prop market has that. The
requirement is not merely unmet; it is unreachable by any depth assumption.

**And the one book that ever misbehaved is gone.** Every non-atomic ladder
observation in the store is Bovada's points ladder, which has 6,974 / 6,881 /
5,994 rows across its three rungs in 2024-25 and **zero in 2025-26** —
while Bovada itself is still present in both seasons on other markets. The
single source of every encouraging observation had already disappeared a
season before this was written.

## The checkpoint: 2026-10-15, on depth

The first draft of this document put the checkpoint at 2026-12-01 and read
the violation count. That is the wrong quantity, two months too late.

**Depth is the binding constraint, and it is readable in week one at zero
marginal credits**, because the alternate keys are already in the fetched
market list. History gives **1.145 rungs per over ladder** and 57 two-sided
multi-rung ladders across two full seasons, against 1,508,769 ladders
carrying exactly one two-sided rung. No violation rate can rescue a
population that does not exist, so counting violations before knowing
whether ladders arrived is measuring the derived quantity while the upstream
one decides everything.

**On 2026-10-15**, `scripts/run_ladder_coherence.py` is run and
`data/outputs/ladder_coherence.json` is read. **It reads depth and
denominators only — never a return.** That is what keeps it a feasibility
gate rather than an interim analysis: counting whether a phenomenon can
occur is not testing whether it pays, so it cannot inflate the
false-positive rate of a test it never looks at.

**The route is closed on 2026-10-15** — a closing note is written and no
further attention is spent — **unless `ladders_with_two_rungs` has risen by
three orders of magnitude over the historical rate.** Concretely: at least
**2,000 ladders carrying two or more de-viggable rungs** in the first
seventeen days. Two seasons produced 57.

That threshold is not a hurdle invented to be cleared. It is the smallest
depth at which the 931-cluster floor is reachable at all, and if the real
market looks anything like the historical one it will be missed by a factor
of hundreds — which is the expected outcome and a perfectly good result.

**Collection continues either way.** The capture costs a cron job and runs
for the deployment and line-movement data regardless, so closing this route
stops the attention, not the tap.

## The failure mode that would fake a closure

A 422 from the provider drops all ten alternate keys and falls back to the
nine core markets. That fallback is deliberate and correct — losing the
ladders is a bounded, stated loss where losing every prop on every event
would not be — and it emits a warning. But **the job stays green, and
nothing asserts that a rung ever arrived.** The same 422 once read as an
off-season for two rounds of debugging.

If it fires on opening night it fires for every event of every run, the
season's ladder collection is zero, every workflow is green, and the CSV
keeps growing from the core markets. That is this lab's recorded *a green
step can be one that never ran*.

So the 2026-10-15 check is also the detector for that, and it must be read
as: **a depth of zero means the capture failed, not that books are
coherent.** The two are indistinguishable in the output and must never be
reported as the same finding.

## What passing does not buy

Nothing automatic. A pass produces **evidence for a receipt, not a receipt**.
`data/manual/staging_provider_policy.json` allowlists nothing, the card
therefore produces no picks, and only Cooper can change that by reading the
evidence and signing. Claude may prepare all six steps of
`docs/provider_allowlist_approval.md` and may never take the sixth.

The detector writes to `data/outputs/` and is read by no part of the card.
Nothing in `ladder_coherence.py` consults the allowlist, because nothing in it
may produce a selection.

## What may and may not change before 2027-04-25

**May**: defect fixes in the detector or the capture, each recorded in
`CLAUDE.md` with the date and what it changed.

**May not**: the tier thresholds, the detection floor, the placebo, the
depth floor of 2,000, the sample floor of 600, the cluster floor of 40,
the correction, or the decision date. Not in December because November looked thin. Not in March
because February looked good.

If a mid-season result looks strong, the correct action is **nothing**.
