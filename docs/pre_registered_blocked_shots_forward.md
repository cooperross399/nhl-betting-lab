# Pre-registration: does `blocked_shots` hold forward?

**Registered 2026-09-25, four days before the 2026-27 season opens on
2026-09-29, and before a single forward `blocked_shots` opinion has settled.**
Nothing below may be revised after the first game. This document exists so
that a decision taken later cannot be re-described as a prediction made now.

## The hypothesis

`blocked_shots` is the only market in this repository whose measured return is
positive, excludes zero, and survives correcting for the number of markets
tested. **Registered direction: POSITIVE.** The claim under test is that this
is a real edge that persists on data that did not exist when the model was
built — not a survivor of a multi-market search.

## The evidence it rests on

From `data/outputs/player_props_backtest.md`, generated 2026-09-24, edge
threshold 6.0%:

| Window | Bets | ROI | 95% interval | Corrected for the search | Survives |
|:--|--:|--:|:--|:--|:--|
| `late` (T−4.1h, 7 markets) | 4,286 | **+4.9%** | +1.8% .. +8.1% | +0.6% .. +9.3% | yes |
| `card` (T−9.6h, 8 markets) | 3,026 | **+7.9%** | +4.2% .. +11.7% | +2.7% .. +13.2% | yes |

Both generated 2026-09-24 at a 6.0% edge threshold. **The `card` window is the
one the live card corresponds to**, so it, not `late`, is the prior this
forward test actually runs against.

And per season, from `data/outputs/replication.md`:

| Season | Bets | ROI |
|:--|--:|--:|
| 2024-25 | 2,697 | +4.6% |
| 2025-26 | 1,589 | +5.5% |

Both seasons carry the same sign at a similar magnitude. That is the strongest
thing in this repository and it is still not a finding.

**ROI here is already net of the price paid.** Unlike a points-versus-vig
coefficient, a positive ROI is money. If +4.9% held, it would be an edge in the
only sense that matters. That is precisely why it needs a harder test than the
one that produced it.

## Why it is a hypothesis and not a finding

**It has never replicated.** `data/outputs/replication.md` returns
**untestable** for `blocked_shots` — nothing survived correction on the
discovery window, so there was no result there to replicate. Two positive
seasons that each fail to clear their own bar are not two confirmations.

**It is a survivor of a search.** Seven markets were measured in the `late`
window and eight in the `card` window, on one body of data. The backtest states
the arithmetic itself: *"Under the null, the chance that at least one of 7
independent 95% tests clears is about 30%."* A 30% chance of exactly this
artifact is the prior this test has to beat.

**The measured gap between claimed and realised edge is already known to be
large.** The average selected bet claimed +9.4%; the flat-stake return across
all props was −0.3%. Selection concentrates where the model's own estimation
error concentrates.

**This lab has retracted four findings.** The most recent replicated across
both seasons and was then reproduced by a placebo containing seven constants.
A result that looks robust in this repository has looked robust before.

## The placebo it has to beat

A pass requires beating a **composition-matched control drawn from the same
slates**, not merely beating zero. For every selected `blocked_shots` wager,
one *unselected* `blocked_shots` rung from the same (event, player, book,
snapshot) is drawn and scored identically.

If the selected rungs do not beat the unselected rungs from the same nights,
the "edge" is a property of which players, books and nights carry blocked-shots
markets at all — not of the model's selection. Retention is uneven by
construction: `player_blocked_shots` is measurable in 4,715 of 5,432 events.

## What settles it

**The test is the forward ledger**, frozen before puck drop and settled from
the boxscore, per `src/nhl_betting_lab/forward_evidence.py`. It is not a re-cut
of the two bought seasons.

**Decision date: 2027-04-25**, the date already fixed in
`docs/when_this_ends.md`.

**Sample floor: 1,600 settled forward `blocked_shots` opinions.** This is the
repository's own arithmetic, not a number chosen for this document: the
detection table in `player_props_backtest.md` gives ~1,537 bets to separate a
+5% edge from zero, and the lower of the two measured effects is +4.9%.

The floor is deliberately sized on the **lower** estimate. Sizing on the
`card` window's +7.9% would call for only ~601 bets, and a floor set from the
larger of two numbers produced by the same search is how an underpowered test
gets declared adequate. At the observed rate of ~2,143 `blocked_shots` wagers
per season, one forward season clears 1,600.

**PASSES** — `blocked_shots` is a demonstrated forward edge — only if all three
hold at the decision date:

1. at least **1,600** settled forward `blocked_shots` opinions; **and**
2. forward ROI positive with a 95% interval **clustered by game date**
   excluding zero on the positive side; **and**
3. the selected rungs beat their composition-matched unselected controls, on
   the same nights, by an interval that also excludes zero.

**FAILS** — the measured positive was a search artifact — if the sample floor is met and
either the forward interval spans zero or it excludes zero on the negative
side.

**NEITHER, and the question is carried unresolved** — if fewer than 1,600
opinions settle. That is a finding about the pipeline, not about the model, and
it may not be reported as evidence in either direction.

## What may not be revised after 2026-09-29

The registered direction (POSITIVE), the sample floor (1,600), the decision
date (2027-04-25), the placebo, the clustering unit (game date), and the
three-part pass condition. A threshold moved after the data arrives is not a
threshold.

**No correction factor is applied within this test**, because this is one
hypothesis fixed in advance rather than a search. That is the entire value of
registering it now, and it is also why a pass here licenses a claim about
`blocked_shots` and about nothing else. The other eleven allowlisted markets
are not on trial in this document, and `points` — a *replicated loss* at −4.4%
over 6,194 bets — is not made acceptable by anything that happens here.

## What a pass does not authorize

A pass is evidence, not an instruction. It does not place a bet, size one, or
automate one, and it does not by itself change what the card is allowed to
select. Acting on it would remain Cooper's decision, taken separately and
recorded separately.

Its honest ceiling is also worth stating in advance: one forward season at
n ≈ 1,600 would establish that the effect survived one out-of-sample test at
95%. That is considerably more than this repository has ever had. It is still
one window.
