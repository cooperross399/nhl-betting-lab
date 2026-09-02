# What the evidence actually supports

This file is written **before** the first measurement, on purpose. In the EPL
lab the equivalent document arrived late, after months of numbers had already
been quoted without their intervals. Writing it first means every number this
project produces lands in a place that already knows how to read it.

## The current position, stated plainly

**No demonstrated edge, and it has now been measured twice, in two windows.**
The props store holds every quote bought for both seasons at two distances
from face-off, and each is measured on its own because a wager priced at two
moments is two questions:

| Window | When | Wagers | ROI | 95% interval | Verdict |
|:-------|:-----|-------:|----:|:-------------|:--------|
| `late` | T−4.07h | 25,009 | −0.2% | −1.5% .. +1.0% | no demonstrated edge |
| `card` | T−9.57h | 27,286 | −0.0% | −1.2% .. +1.2% | no demonstrated edge |

The team markets say the same: moneyline +0.0% over 1,366, puck line −1.3%
over 1,762, totals −2.5% over 2,201, every interval spanning zero. The honest
answer to "does this work" is: *the evidence says no edge has been
demonstrated, on samples large enough to mean it.*

**Those two rows are not a comparison of the windows.** The nine-and-a-half
hour purchase asked a second region and came back with fourteen books where
the four-hour one had eight, it carries `hits` and the earlier buy does not,
and it holds almost no `goalie_saves` because the books have not posted them
that far out. The window question was answered separately, on the wagers
priced in both: +4.41% against +4.18%, a difference of −0.23 points, inside
noise.

**An earlier version of this section read "4,830 prop bets pooled at +1.4%,
95% interval −1.4% to +4.2%".** That sample was thirty times smaller than the
population now bought and the figure was noise; it is recorded here rather
than deleted, because a number this document once published is part of what it
is for.

**Nothing is allowlisted.** Cooper approved all eleven markets on 2026-08-27,
overriding this document's enable-nothing recommendation in his own quoted
words; the approval was withdrawn on 2026-08-29 when the evidence it cited
moved, and `data/manual/staging_provider_policy.json` has allowlisted nothing
since. The superseded receipt is kept as the record of a decision that was
really made. So the card prices every market, recommends nothing, and says
why — and the only way the answer above ever changes is the forward ledger:
out-of-sample, priced, settled, and counted.

## A population is not a result until it exists on disk

On 2026-08-31 a second purchase priced the same 2,710 events at 9.5 hours and
was appended to a store already holding them at 4.0. The append deduplicated
on the quote and not on the window, so **1,126,739 of the 1,259,312 four-hour
rows were overwritten** and 132,573 survived. Nothing raised; the store still
held 2.7 million rows; and `data/outputs/player_props_backtest.md` went on
reporting −0.3% over 25,947 bets at the four-hour window against a store that
could produce 8,007 of them.

It was recovered from the raw cache, which is why the raw cache exists. But
one thing did not survive: **the canonical 25,947 reproduces from nothing that
still exists.** 24,996 of those bets rebuild exactly — same book, same odds,
model probability identical to the last bit — and 951 do not. The reproducible
four-hour population is 25,009 bets at −0.2%.

So this document adds a rule to the ones below:

**A recorded number must name a population that can be rebuilt.** Not one that
was on someone's disk when the report ran. The price CSVs are derived data;
the raw responses are the evidence; and a headline that cannot be reproduced
from the evidence is a claim about a file, not about the market.

Calibration was measured too, and heavily — 2.5 million walk-forward prop
samples. That establishes exactly one thing: the models' probabilities are
internally sensible. It establishes nothing about whether the market
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

**And a probe's absence is only as wide as the probe.** `hits` sat in this
category for weeks on the strength of 256 events in which no book quoted it.
The probe asked one region; both books that quote hits are in the second, and
the purchase that asked for two came back with 16,048 rows over 1,218 events —
5,021 settled wagers at −1.2%, interval −3.9% to +1.5%, no demonstrated edge.
"Not offered in any of 256 events" was true and "cannot be measured" was not.
The backtest now retires an unmeasurable verdict for any market the same run
measures, because a report that prints a market's ROI and calls it
unmeasurable four sections later is the thing this document exists to prevent.

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
