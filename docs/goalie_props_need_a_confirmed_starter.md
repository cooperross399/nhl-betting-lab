# Goalie props need a confirmed starter

## The finding

The first walk-forward calibration run priced every goalie who appeared in
every boxscore. Split by ice time, the goalie saves market looked like this:

| Ice time | Samples | Predicted | Observed |
|:---------|--------:|----------:|---------:|
| under 12 min | 16,145 | 42.8% | 0.3% |
| 45 min and up | 16,460 | 44.3% | 47.6% |

The second row is a model that is roughly right. The first is a model being
scored on bets that were never offered.

## What was actually happening

A goalie who comes in cold in the second period makes a handful of saves, so
he goes under every line. The model priced him as though he were playing a
full game, because his expected ice time is a rolling mean over recent
appearances and it has no way to know that tonight he is the backup.

Pooled together, those two rows dragged the whole market's raw Brier score to
0.2191 and made the fitted correction look enormous (slope 0.566). The
correction was not fixing a miscalibrated model. It was averaging a working
model with a category of bet that does not exist.

## The two responses, and why both are needed

**In the measurement:** a goalie appearance under forty minutes produces no
sample. A book posts a total saves line for the expected starter, and nobody
can bet a saves prop on a goalie who enters in relief. Measuring against bets
that exist is not a convenience — measuring against bets that do not exist is
simply a wrong measurement.

**On the card:** excluding relief appearances from the measurement does
nothing about the real problem, which is that **the model has no way to know
who starts**. Starting goalies are confirmed close to puck drop, hours after
the card is built. If the card prices a saves prop for a goalie who turns out
to be the backup, the measurement's clean numbers are irrelevant — the bet is
dead the moment the lineup is posted.

So `goalie_saves` carries a card-level gate of its own: it cannot produce a
selection without a confirmed starter for that game. This lab has no
confirmed-starter source, so the practical consequence is that **goalie saves
props do not reach the card**, and the card says so by name with this reason
rather than listing the market as a pass or an avoid.

## Why not just guess the starter

The obvious heuristic — whoever started the last game, or whoever has started
most — is right most of the time and wrong exactly when it matters. Back-to-back
nights, injuries, and a starter pulled the game before are all situations where
the heuristic fails, and all three are situations where a book has already
moved the line. A gate that is usually right is a gate that fails on the games
where the model most needs one.

If a confirmed-starter feed is added later, the gate opens on that feed and
the change is judged by the backtest, not by whether it feels more complete.

## What this does not claim

Excluding relief appearances improved the measured calibration of
`goalie_saves` dramatically. That improvement is **not** evidence the model
got better. Nothing about the model changed; a wrongly-included category of
sample was removed. The corrected number describes what the model always did
on real starts, and the old number described something that was never a
question anyone could bet on.


## A claim I made here and had to withdraw

This section previously said the provider does not retain goalie saves
historically, and that the market therefore could never be measured against
real prices.

That was wrong, and the way it was wrong is worth keeping.

A retention probe on 2026-01-10 requested all six prop markets and got five
back, missing `player_total_saves`. I recorded it as unmeasurable. The
purchase that followed found it priced on **54 of 58 events, across six
books** — BetMGM, BetOnline.ag, Bovada, DraftKings, FanDuel and Fanatics. The
market was there all along. One event was not a sample of retention; it was
one night's book coverage.

This repository carries `docs/nhl_data_sources.md` and a rule in `CLAUDE.md`
about exactly this: the EPL lab wrote off `total_2_5` for a season after
checking coverage in one place. I then made the same mistake from a sample of
one, in a repository built to stop it.

The code changed rather than only the wording. `MINIMUM_PROBES_FOR_ABSENCE`
now governs: below it, a market that did not appear is reported as *not seen
in N events*, which is a claim about the probe, rather than *cannot be
measured*, which is a claim about the provider. `retention_table` and
`unmeasurable_markets` both refuse to write the second sentence from too
little evidence, and the probe samples spread across the window by default
instead of taking one night.

## So goalie saves is measurable, and still cannot reach the card

The gate above is unaffected and remains the operative one. Saves can be
measured, and it did produce fourteen bets in the first purchase — far too few
to mean anything, and the report says so. But it still cannot produce a
selection, because nothing here knows who starts, and that is a question about
lineups rather than about data retention.
