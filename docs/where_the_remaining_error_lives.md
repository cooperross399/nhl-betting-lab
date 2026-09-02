# Where the remaining error lives

The model recovers most of the vig and stops short.

**Corrected 2026-09-02.** This paragraph used to read "betting every wager it
has an opinion on returns −2.70% over 100,805". That population is every
wager with a **positive** model edge, and it is already 77.6% unders — so the
null quoted here already contained the model's own direction, and "the
selection is worth +2.35 points" credited the model with a gap it had partly
been handed. Betting literally every wager returns **−27.45% over 475,395**.

Against a direction-neutral baseline the honest arithmetic is: both sides of
every two-sided market **−5.74%** → blind unders **−3.90%** → the model's
90.1/9.9 side mix **−4.26%** → the shipped card **−0.29%** over 25,947, 95%
[−1.76%, +1.19%], **no demonstrated edge**. Direction is worth +1.85 points,
side mix −0.37, and **within-side selection +3.97** — which is where the real
skill is, and it survives matching on market × line × price bucket
(+3.34 points [+1.04%, +5.71%], both seasons).

This document is about the third of a point that is left, and it is not a
mystery any more.

## The loss is one cell, and it is four times the size of the whole loss

Split the shipped card by whether a player's near-future ice time is above or
below what the model's trailing-ten-game estimate assumed:

| The player's usage is about to… | ROI | bets |
|:--|--:|--:|
| fall | **+5.82%** / +3.22% | |
| stay stable | −0.13% | |
| **rise by more than two minutes** | **−6.44%** [−8.96, −3.92] | 5,661 |

That last row loses **364.6 units**. The entire card loses 89.6. **One stale
ice-time cell loses four times what the card loses**, and 98% of those bets
are unders.

The mechanism is plain once stated. The model prices a player from the
minutes he used to play. When a role is expanding — an injury above him, a
promotion, a new line — his recent history understates him, the model takes
the under, and the book does not.

## What it would be worth, and why that number is an upper bound

Substituting the player's **next-three-game mean** ice time — which knows
nothing about the specific game being bet — moves the card from −0.35% to
**+4.63%** [+3.38, +5.87] over 25,374 bets. Substituting the *realised* ice
time gives +5.16%, and holds at +4.53% on regulation-only games, so it is not
an overtime-length artefact.

**Neither is achievable.** Both use information from after the card is
built. They are an *oracle*: they prove where the value is, they do not
deliver it. The honest reading is "deployment information is worth about five
points of ROI **to this model**" — not "there is a five-point edge here".

## The information is not in the box score, and that is measured

Every prior-only reshuffle of the same history was tried: trailing three,
five and ten games, exponentially-weighted means, blends. All of them land
between **−0.30% and +0.02%**. Nothing. A pre-game proxy for the coming usage
shift built from box scores has **R² = 0.080**.

So this cannot be fixed by being cleverer with what the lab already has. It
needs a **deployment source** — projected lines, projected ice time, a
confirmed line-combination feed — published before puck drop.

## Two internal defects were found, fixed, and made it worse

Worth recording because it is the strongest confirmation available that
better statistics on the same data is a dead end:

- **Per-player rates are over-shrunk.** Out-of-sample slopes of actual on
  predicted: 1.32 assists, 1.26 shots, 1.21 points, 1.80 hits. Unshrinking
  them is textbook correct. The card went to **−1.27%**.
- **Dispersion is mis-specified** — one league-wide variance-to-mean ratio,
  giving too much upper-tail mass on shots and blocks and too little on
  points. Rescaling it is also textbook correct. The card went to −0.47% to
  −0.93%.

Both fixes make the model statistically better and the card worse, because
**the market already holds the corrected view**. Improving the model's
agreement with reality, where reality is already priced, buys nothing.

## Where the error is not

- **Rate estimation is fine.** On the full sample the means are near
  unbiased: points −2.9%, goals −1.8%, shots +4.7%.
- **The opportunity term** averages under 0.005 of a unit for skaters.
- **Rest works.** Back-to-backs +0.36% against rested −0.50%; the measured
  adjustment does its job.
- **Opponent structure is real but tiny**, 1.1–1.9× noise.

## What this points at, and the caveat that governs it

For **shots, blocked shots and goalie saves**: deployment and ice time.
For **points, goals and assists**: linemate and finishing context — perfect
ice time leaves points at −3.28%, so minutes are not their problem.

Not opponent adjustments. Not rest. Not re-weighting.

**The caveat.** That deployment information is worth five points *to this
model* is shown. That it is **unpriced** is not — books reprice on every
lineup release, and this lab's own documentation says so. The realistic prize
is not beating the close. It is **not making 5,661 bets a year that are pure
error**.

## Two leakage-free attacks on the stale-minutes cell, both dead

Written 2026-08-31, after the error map, because the obvious fixes should be
closed with numbers rather than left as things someone will suggest again.

### Teammate absence

The mechanical cause of a role expanding is that somebody above the player is
out. That is knowable before puck drop from participation history alone: a
teammate who played in games N−8..N−4 and is missing from N−3..N−1 is
probably still missing. No new source, no licence, no leakage.

Predicting a player's ice-time **level** is easy and irrelevant — trailing-10
alone gives R² = 0.8865, because minutes are stable. The money is in the
**shift**, actual minus assumed. On that target:

| | R² on the shift |
|:--|--:|
| own history only | 0.0117 |
| **with teammate absence** | **0.0117** |

The absence coefficient is +0.0005 seconds of own ice time per second of
absent teammate baseline. It flags 175 player-games out of 49,857 and catches
**1.3%** of the 10,680 real rises. High precision (82%) on a rounding error's
worth of coverage.

### Pre-game ice-time volatility

If the *direction* of a shift cannot be predicted, perhaps the *risk* can:
a player whose recent minutes bounce around should carry a wider
distribution, which would thin out exactly the confident unders that lose.
Volatility is a property of the player, known before the card is built — this
is not excluding the losing cell after the fact.

Card ROI by pre-game coefficient of variation of trailing-10 ice time, five
equal bands of ~5,200 bets each: −1.33%, +0.59%, −0.40%, +0.68%, −1.30%.
**Every band spans zero and there is no gradient.** Dropping the two most
volatile bands moves the card from −0.35% to −0.38%.

### What this settles

The usage shift is real, it is expensive, and **nothing knowable before puck
drop from this lab's data predicts it**. Not the player's own history, not
his teammates' absences, not his volatility. The oracle is worth five points
and the information genuinely is not there.

That leaves one path: an external **projected-lineup feed** published before
puck drop. And it carries a cost that has to be stated before anyone starts
building it — **no archive of past projections exists for the bought
seasons**, so its value cannot be measured historically. Under this lab's own
rule that the price backtest decides, it cannot ship on a hope. It would have
to be **collected forward from opening night and measured a season later**,
which is the same shape of wait as the forward ledger and for the same
reason.

## What is being collected instead, from 2026-09-29

Daily Faceoff — the standard source for projected lines and starting goalies
— **blocks automated access**: its own `robots.txt` returns a Cloudflare
challenge. That is an explicit signal and this lab does not scrape past it.

The NHL's own API publishes a usable subset for free, inside the licence the
lab already relies on: `gameInfo.{home,away}Team.scratches` and `headCoach`,
plus `referees` and `linesmen`, on the game-centre right rail.

`scripts/capture_deployment.py` records it **with the instant it was taken**,
in the same workflow run as the price capture, so the two share a timestamp
and can be joined. What is not known today, and what a season of this makes
answerable:

1. **How long before puck drop does the scratch list become public?** If it
   populates an hour out it is far too late for a card built at 09:30 — but
   that is a fact worth having rather than assuming, and it decides whether a
   later card is worth building at all.
2. **Had the market already moved by the time it appeared?** Only a shared
   instant between the deployment capture and the price capture can answer
   that, which is why they are one job rather than two.

This collects. It does not fix anything, it is wired into no card, and it
changes no number. Like forward evidence, it cannot be gathered
retroactively, which is the only reason it starts now rather than when the
question is asked.

## What every measured lever is worth

Recorded so the arithmetic is in one place and nobody has to re-derive it.

| lever | worth | status |
|:--|--:|:--|
| the model's own selection | **+2.35 points** | captured |
| book access, one account to eight | **+0.68 points** | captured, and saturating |
| card timing, 4h against 9.5h | unknown | being bought |
| deployment information (oracle) | ~+5 points | not obtainable pre-game |
| better statistics on the same data | **negative** | measured, dead |
| thirteen external data inputs | **zero** | measured, dead |
| 1,175 structural rules | **zero** | measured, dead |

### Book access, measured

ROI at the 6% bar, one bet per wager, as the number of books you can reach
grows:

| reachable books | ROI |
|:--|--:|
| 1 (DraftKings alone) | −1.02% |
| 2 | −0.81% |
| 3 | −0.59% |
| 5 | −0.40% |
| **8** | **−0.34%** |

Opening accounts is worth **+0.68 points** and the curve is flat by five —
the last three books add 0.06 between them. **More accounts cannot close the
remaining gap.** No single book is positive alone; the best is Bovada at
−0.67%, the worst Caesars at −3.68%.

### The execution caveat that governs the headline

The −0.34% assumes the best of eight books is taken on **every** wager. That
is the most favourable assumption available and it is not how betting works:
prop limits are small, books restrict winners quickly, and the best price is
disproportionately the stale one about to move or be pulled.

So the honest bracket runs from about **−1.6%** (every quote counted, average
price) to **−0.34%** (perfect shopping), and a real-world result sits nearer
the middle than the top. Quoting −0.34% as *the* number overstates what is
reachable, in the same way quoting −1.6% understated it.
