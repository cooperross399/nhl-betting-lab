# What the evidence actually supports

This file is written **before** the first measurement, on purpose. In the EPL
lab the equivalent document arrived late, after months of numbers had already
been quoted without their intervals. Writing it first means every number this
project produces lands in a place that already knows how to read it.

## The current position, stated plainly

**Nothing in this repository has a demonstrated edge, because nothing has been
measured yet.** No market is allowlisted. No card produces selections. Every
number below is a bound on what measurement *could* show, not a result.

When a result exists, it replaces the relevant section here and carries its
sample size and its interval. Until then, the honest answer to "does this work"
is: *unknown, and it will stay unknown for a while.*

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

To be filled in by measurement, market by market, with the reason. An entry
here is a statement that no historical price exists to test against — not a
statement that the market is bad.

## The one thing that is certain

Every claim this project will make rests on results already observed. The first
genuinely out-of-sample evidence it will ever have is the 2026-27 season, one
game-day at a time. That is worth more than any further slicing of the seasons
already in the file.
