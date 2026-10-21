# Goalie saves: priced on tonight's game

Cooper, 2026-10-20: "Re-evaluate and fine-tune the goalie saves portion of
the model. Factor in the team that is favored to win and home ice
advantage." From the card of 2026-10-21 (`saves_context.SAVES_CONTEXT_FROM`)
goalie saves are priced on the game-context model. Every other market is
unchanged.

## What was wrong with the old saves mean

`PlayerPropsModel.expected_saves` is the goalie's own career shots against
per sixty, times the opponent's shot factor, times his save rate. The
career figure follows him across clubs, is never shrunk, and describes the
teams he used to play behind rather than tonight's. Refitted on outcomes,
its own log mean earns a coefficient of 0.45: it moves about twice as much
as saves do. It also ignored who is favoured:

| Starts (out of sample, 2024-25 and 2025-26) | Starts | Actual saves | Old model | New model |
|:--|--:|--:|--:|--:|
| Goalie's team favoured | 1,967 | 23.55 | 24.43 | (see run) |
| Goalie's team the underdog | 2,057 | 25.91 | 25.50 | |
| Heavy favourite (65% or more) | 326 | 22.46 | 23.46 | 22.85 |
| Big underdog (35% or less) | 309 | 27.83 | 25.93 | 27.39 |

(The new model's column is variant `F` in the run's split table, which
carries the market line; the shipped `G` reads the same teams' shot rates
and lands within a few tenths of it on the outcome measures below.)

## The measurement

`scripts/run_saves_model_study.py`, Saves Model Study run 39536283289
(2026-10-21). Walk-forward: the props model refitted every 14 days on
earlier games only; each variant's coefficients fitted only on starts in
earlier windows; 4,024 starts scored. The rule was fixed in the script
before the run: ship only if out-of-sample log-likelihood beats the old
model with a game-clustered 95% interval excluding zero, AND the variant
does not lose units against the old model on the bought saves prices in
either window, at the card's 6% prop bar, one bet per wager.

| Variant | Δ log-likelihood per start [95%] | MAE | `late` prices | `card` prices |
|:--|:--|--:|:--|:--|
| Old model | 0 | 5.266 | -47.3u over 1,703 | -6.3u over 114 |
| Favourite + home (market line) | +0.0380 [+0.0295, +0.0464] | 5.070 | +43.5u over 1,169 | -9.4u over 70 |
| Full context + market line (`F`) | +0.0519 [+0.0424, +0.0614] | 4.991 | +65.2u over 668 | -9.8u over 46 |
| **Shipped: full context (`G`)** | **+0.0510 [+0.0417, +0.0604]** | **4.998** | **+52.0u over 668** | **-4.2u over 44** |

`G` gains in both seasons on its own (2024-25 +0.0547 over 1,538 starts,
2025-26 +0.0488 over 2,486, both intervals excluding zero). Only `G` and
home-only (`C`) passed both tests, and `G` has the better log-likelihood.
The variants carrying the market moneyline lost more units than the old
model on the `card`-window prices, which is 44 to 116 bets and close to
noise, but the rule was set before the run and is kept.

The favourite is in `G`, through the two teams: the side the market
favours is the side that outshoots, so its shots for and against carry most
of what the moneyline knew. With them in, the moneyline's own coefficient
falls from -0.116 to -0.044.

**No edge is claimed.** `+52.0u over 668` in the `late` window is +7.78%
[+0.69%, +14.87%] uncorrected, picked from seven variants on the same
data. What is demonstrated is a better projection of saves out of sample;
whether it beats prices going forward is for the forward ledger.

## The shipped model

`saves_context.SHIPPED`, fitted on all 4,942 starts with a market line:

    log mean = 2.888 + 0.118 log(old mean) - 0.029 home
               + 0.876 log(team shots against) + 0.952 log(opponent shots for)
               + 0.266 log(rink factor) + 0.139 log(start minutes / expected minutes)

Negative binomial, r = 45.2. Team rates are recency-weighted (half-life 20
games) and shrunk toward the league; the rink factor is the arena's total
shots against the same club's road games. All are read from the completed
games on the card's morning.

## The forward ledger

Saves rows frozen before 2026-10-21 were priced on the old mean. They stay
in the ledger and are set aside from the forward report
(`superseded_saves_rows`), as the team markets' goals-priced rows were at the
xG switch. The 2027-04-25 verdict on `goalie_saves` covers the new model
only. The ledger held 192 saves rows over four days when this landed,
because books post saves after the morning freeze.
