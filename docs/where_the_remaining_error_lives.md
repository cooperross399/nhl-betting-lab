# Where the remaining error lives

The model recovers most of the vig and stops short. Betting every wager it
has an opinion on returns **−2.70%** over 100,805; its own 6% selection
returns **−0.34%** over 26,091. The selection is worth **+2.35 points**. This
document is about the 0.34 that is left, and it is not a mystery any more.

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
