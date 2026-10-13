# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-13T13:43:10+00:00
- Opinions considered: **43304**; matched to a closing price: **40076**; no closing price found: **3228**.
- Within that count, priced before face-off but no close near face-off: **3126** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **92** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **8327** opinion(s), 365 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

A closing price is the last price captured **strictly before** the
listed start, and no more than 150 minutes before it.
An opinion with none is counted here, never dropped:
a selection the books pulled before puck drop is exactly the one
most likely to have been wrong, and silently excluding it would
flatter the model precisely where it deserves scrutiny.

Every interval below is clustered by game. One game brings both
sides of a market, every rung of a ladder and every player, and
they all move with that game's news, so they are not independent
trials. `Games` is the count each interval rests on. No interval
here is narrower than one on the rows would be, and one game
cannot bound an interval at all.

## All opinions

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 40076 | 12874 | 12163 | 46.1% [45.1%, 47.1%] | +0.50% [+0.25%, +0.74%] | -4.4% [-4.6%, -4.2%] (26814) | 84 |

3228 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 1895 | 986 | 372 | 64.7% [59.8%, 69.4%] | +4.20% [+2.11%, +6.28%] | +0.4% [-1.8%, +2.6%] (1694) | 83 |

116 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 4610 | 1441 | 1422 | 45.2% [42.5%, 48.0%] | -0.30% [-0.93%, +0.33%] | -4.5% [-4.8%, -4.1%] (2798) | 78 |
| `assists` | bets | 203 | 101 | 52 | 66.9% [54.5%, 77.3%] | +1.97% [+1.04%, +2.90%] | -1.0% [-2.0%, -0.0%] (201) | 70 |
| `blocked_shots` | opinions | 36 | 10 | 8 | 35.7% [15.9%, 62.0%] | -1.83% [-4.23%, +0.57%] | -8.4% [-10.6%, -6.3%] (36) | 13 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.0%, 65.6%] | -5.55% [-20.54%, +9.44%] | -5.1% [-6.9%, -3.2%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [42.6%, 99.4%] | +19.37% [-2.71%, +41.46%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 10282 | 2630 | 4499 | 45.5% [42.8%, 48.2%] | +1.20% [+0.50%, +1.90%] | -4.6% [-4.9%, -4.2%] (4915) | 78 |
| `goals` | bets | 79 | 45 | 20 | 76.3% [51.8%, 90.6%] | +2.49% [+0.59%, +4.40%] | -2.1% [-3.7%, -0.5%] (76) | 41 |
| `hits` | opinions | 4 | 2 | 0 | 50.0% [2.8%, 97.2%] | -0.19% n too small | -7.8% n too small (4) | 1 |
| `hits` | bets | 1 | 1 | 0 | 100.0% [10.9%, 100.0%] | +2.13% n too small | -5.5% n too small (1) | 1 |
| `moneyline` | opinions | 158 | 71 | 17 | 50.4% [38.6%, 62.1%] | -0.38% [-1.21%, +0.46%] | -2.4% [-3.2%, -1.6%] (158) | 79 |
| `moneyline` | bets | 30 | 16 | 3 | 59.3% [33.3%, 80.9%] | +0.75% [-1.41%, +2.92%] | -1.2% [-3.4%, +1.0%] (30) | 30 |
| `points` | opinions | 8570 | 2681 | 2241 | 42.4% [39.8%, 45.0%] | +0.01% [-0.96%, +0.99%] | -4.7% [-5.6%, -3.8%] (6602) | 78 |
| `points` | bets | 417 | 215 | 85 | 64.8% [54.3%, 74.0%] | +10.37% [-1.55%, +22.28%] | +7.2% [-4.5%, +19.0%] (417) | 76 |
| `puck_line` | opinions | 1578 | 526 | 521 | 49.8% [45.4%, 54.2%] | +0.64% [-0.11%, +1.38%] | -2.4% [-3.2%, -1.6%] (1438) | 84 |
| `puck_line` | bets | 95 | 45 | 22 | 61.6% [40.4%, 79.2%] | +1.38% [-1.46%, +4.21%] | -2.0% [-4.6%, +0.6%] (95) | 49 |
| `regulation_3_way` | opinions | 234 | 85 | 50 | 46.2% [36.1%, 56.7%] | -0.34% [-1.05%, +0.36%] | — | 78 |
| `regulation_3_way` | bets | 64 | 31 | 12 | 59.6% [40.1%, 76.5%] | +0.46% [-1.18%, +2.11%] | — | 64 |
| `shots_on_goal` | opinions | 8849 | 3378 | 1867 | 48.4% [45.0%, 51.8%] | +0.89% [+0.03%, +1.75%] | -4.5% [-4.8%, -4.2%] (5260) | 78 |
| `shots_on_goal` | bets | 625 | 336 | 102 | 64.2% [56.0%, 71.8%] | +3.40% [+1.88%, +4.92%] | -1.0% [-2.1%, +0.1%] (502) | 77 |
| `team_total` | opinions | 3669 | 1312 | 975 | 48.7% [45.9%, 51.5%] | +0.07% [-0.22%, +0.35%] | -4.9% [-5.2%, -4.6%] (3623) | 78 |
| `team_total` | bets | 223 | 114 | 45 | 64.0% [41.3%, 81.9%] | +1.38% [-0.95%, +3.72%] | -3.9% [-6.2%, -1.7%] (223) | 45 |
| `total_goals` | opinions | 1990 | 709 | 548 | 49.2% [45.4%, 52.9%] | +0.20% [-0.22%, +0.62%] | -3.4% [-3.7%, -3.1%] (1950) | 84 |
| `total_goals` | bets | 140 | 68 | 28 | 60.7% [40.8%, 77.6%] | +1.08% [-0.91%, +3.07%] | -2.9% [-4.6%, -1.2%] (140) | 32 |

## How to read this

- **Beat close** counts opinions taken at a longer price than the
  market's last. A rate meaningfully above 50% on a real sample is
  the earliest honest sign a model is finding something.
- **CLV%** is `decimal_taken / decimal_close - 1`, vig included on
  both sides, so it compares across bets and markets.
- **EV at close** de-vigs the closing pair proportionally and asks
  what the bet is worth *if the closing line is right*. It is the
  money figure, and it is the most assumption-laden: it is computed
  only where the opposite side also closed, and the regulation
  three-way is excluded entirely because a three-outcome market
  cannot be de-vigged as a pair.
- **Bets**: A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
