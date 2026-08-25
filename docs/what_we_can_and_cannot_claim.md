# What the evidence actually supports

This file is written **before** the first measurement, on purpose. In the EPL
lab the equivalent document arrived late, after months of numbers had already
been quoted without their intervals. Writing it first means every number this
project produces lands in a place that already knows how to read it.

## The current position, stated plainly

**Nothing in this repository has a demonstrated edge, because nothing has been
measured against a real price.** No market is allowlisted. No card produces
selections. The honest answer to "does this work" is: *unknown, and it will
stay unknown until historical prices are bought and measured against.*

What *has* been measured is calibration, and a lot of it — 1.9 million
walk-forward prop samples and 51,212 team-market samples across 3,658 games.
That establishes exactly one thing: the models' probabilities are internally
sensible, once corrected. It establishes nothing about whether the market
disagrees with them profitably, and this document will not let the two be
confused.

`data/outputs/what_we_can_claim.md` is the generated counterpart to this file.
It is rebuilt from the measurement outputs every run, so it cannot drift from
them.

## The rules this document enforces

**A number without a sample size is not a result.** Every measured figure in
this repository is written next to the count of bets, games, or player-games
behind it. A report that omits one is a bug.

**An interval that includes zero means "no demonstrated edge".** Those exact
words, not "promising", not "trending positive", not "small but positive". A
+12% ROI over 40 bets and a coin flip are the same claim at that sample size.

**Calibration can rule a model out. It can never rule one in.** A well
calibrated model that has never been priced against a real market has shown
only that its probabilities are internally sensible. Whether the market
disagrees with it profitably is a different question, answered only by prices.

**Where historical prices exist, the price-based backtest decides.** A change
that improves calibration and loses the backtest does not ship.

## How much data would settle it

This arithmetic does not depend on the sport, so it can be written down now.
Separating a true edge from zero at 95% confidence, with flat stakes at roughly
even money, takes about:

| If the true edge were | Bets needed to separate it from zero |
|----------------------:|-------------------------------------:|
| +5%                   | ~1,540 |
| +8%                   | ~600 |
| +10%                  | ~385 |
| +15%                  | ~171 |

The NHL's advantage over the EPL lab is volume: roughly 1,312 regular-season
games a season against 380, with many prop markets per game. A prop programme
that places even five bets a game-day reaches four figures within a season.
That is the reason props are the centre of this lab and not an appendix — not
because prop edges are believed to be larger, but because they are the only
part of the system that can accumulate enough bets to ever be measured.

That advantage is real but it is not free. See the next section.

## What props cost in exchange for that volume

**The lineup is not known when the card is built.** Scratches, line
combinations, power-play units, and — most of all — the confirmed starting
goalie are published close to puck drop, hours after the card exists. Books
reprice on every one of them. This model cannot. That is a structural
information deficit on every prop, and it is why the prop edge threshold in
`config.py` is *higher* than the team-market one, not lower.

**Prop prices are one-sided.** Books quote the Over and the Yes; there is often
no quoted Under to devig against. Implied probability from a single quoted side
overstates the true probability, which **understates** measured model edges. The
measurement is conservative in that one direction, and that is worth stating
whenever a prop edge looks small.

**Not every prop market can be measured historically.** The Odds API retains
some markets per event and not others, and retention differs by market and by
book. Where a market cannot be measured, this repository says so by name rather
than presenting a calibration number as though it settled the question. See
`data/outputs/player_props_backtest.md` for the per-market retention table.

## What cannot be measured at all

To be filled in by the retention probe, market by market, with the reason. An
entry here is a statement that no historical price exists to test against —
not a statement that the market is bad.

Until that probe has run, the honest state is **unknown**: not "all six
markets are retained" and not "none are". `data/outputs/player_props_backtest.md`
says so in those words.

## Two things calibration has already ruled out

Calibration cannot rule a model in, but it has already ruled two things out,
and both changed the code:

**Goalie saves could not be measured the way it was being measured.** Pricing
every goalie in every boxscore put 16,145 relief appearances into the sample,
predicting 42.8% and observing 0.3%. Those are bets no book offers. Excluding
them is not the model improving —
`docs/goalie_props_need_a_confirmed_starter.md` is explicit that nothing about
the model changed.

**The team model is overconfident on favourites.** Its docstring argued the
opposite, from a plausible mechanism about empty-net goals. The measurement
disagreed and the measurement governs; the wrong prediction stays on the
record in `models/team_model.py`.

## The one thing that is certain

Every claim this project will make rests on results already observed. The first
genuinely out-of-sample evidence it will ever have is the 2026-27 season, one
game-day at a time. That is worth more than any further slicing of the seasons
already in the file.
