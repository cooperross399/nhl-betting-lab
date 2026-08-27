# Why the by-TOI correction does not ship

## The sequence, kept in order because the order is the lesson

The calibration measurement found every skater market bent by ice time, with
a mechanism (`why_ice_time_gets_its_own_correction.md`). A per-bucket Platt
correction straightened every reliability table. The house rule said that was
not enough — the price backtest decides — so the correction was tested
walk-forward against 4,777 real bets across two seasons.

**Bucketed on the player's actual ice time in the game, it won everywhere:**
+162.8u over the raw model, better on both windows, improving nine of twelve
market-windows. It cleared the written bar for shipping to the card.

One check remained before wiring it in: a live card does not know actual ice
time. It knows *expected* ice time. So the samples were regenerated to carry
the model's own pre-game TOI expectation, and the identical experiment was
re-run bucketed on that instead.

**It lost: −37.6u against raw.** Same fits, same prices, same selection rule,
same leak-free fitting cadence. The only change was which number indexed the
bucket.

## What was actually happening

The correction's *fitting* was walk-forward-clean all along — every curve saw
only strictly earlier dates. The leak was in the **indexing**. A player's
actual ice time in a game is not an input; it is partly an outcome. It rises
in overtime, falls when his team is blown out, collapses when he is injured
mid-game, and for a goalie it encodes whether he was pulled. Bucketing a
probability by actual TOI quietly conditions the correction on how the game
went — hindsight, laundered through a lookup key.

The reliability tables could not see this, because calibration diagnostics
group by the same key and inherit the same hindsight. The backtest could not
see it either until the index was switched to information the card can
actually possess. **A leak can live in an index as easily as in a fit, and
only a deployment-fidelity check finds that kind.**

## Where this leaves things

- **No correction is in force on the card.** The pooled Platt lost the
  backtest outright (−97.0u, the EPL lesson to the letter); the by-TOI
  correction loses once honestly indexed. The card's gate reads the recorded
  verdict from `data/outputs/correction_experiment.json`, which says
  `ships: []`, so this is enforced by data rather than by memory.
- The calibration finding is still true — the model is bent by ice time — and
  still unfixed at the source. The honest fix remains an ice-time-quality
  input the data does not currently offer, not a correction indexed on
  hindsight.
- The machinery for applying a correction live (`models/toi_corrections.py`,
  expected-TOI bucketing, the experiment gate) stays. It is tested and inert,
  and whichever future variant wins an honestly-indexed experiment can ship
  through it without new plumbing.

## The general rule this adds

Every earlier leak here was in what a fit could see. This one was in what a
lookup could see. So the standard for any conditioned quantity — a correction,
a factor, a bucket, a feature — is now stated as: **conditioned on what,
known when?** If the answer is not "before puck drop", it does not matter how
clean the fitting cadence is.
