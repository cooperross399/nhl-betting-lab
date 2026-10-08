# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-08T13:39:11+00:00
- Opinions considered: **25545**; matched to a closing price: **23576**; no closing price found: **1969**.
- Within that count, priced before face-off but no close near face-off: **1899** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **60** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5161** opinion(s), 193 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 23576 | 7726 | 7142 | 47.0% [46.0%, 48.1%] | +0.92% [+0.58%, +1.26%] | -4.3% [-4.6%, -4.1%] (15640) | 52 |

1969 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 1240 | 659 | 225 | 64.9% [58.4%, 70.9%] | +5.44% [+2.38%, +8.51%] | +1.5% [-1.8%, +4.8%] (1101) | 51 |

58 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 2805 | 901 | 828 | 45.6% [42.2%, 49.0%] | +0.05% [-0.77%, +0.87%] | -4.7% [-5.1%, -4.2%] (1636) | 46 |
| `assists` | bets | 138 | 78 | 30 | 72.2% [58.4%, 82.8%] | +2.63% [+1.47%, +3.80%] | -0.5% [-1.8%, +0.8%] (136) | 43 |
| `blocked_shots` | opinions | 28 | 8 | 6 | 36.4% [14.9%, 65.2%] | -1.76% [-4.37%, +0.85%] | -8.4% [-10.7%, -6.1%] (28) | 10 |
| `blocked_shots` | bets | 4 | 2 | 2 | 100.0% [19.9%, 100.0%] | +1.64% [-1.52%, +4.80%] | -5.4% [-6.9%, -3.9%] (4) | 3 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 6018 | 1540 | 2656 | 45.8% [42.2%, 49.5%] | +1.18% [+0.20%, +2.17%] | -4.4% [-4.9%, -4.0%] (2863) | 46 |
| `goals` | bets | 55 | 30 | 13 | 71.4% [42.0%, 89.6%] | +2.54% [-0.01%, +5.09%] | -1.9% [-4.0%, +0.2%] (52) | 27 |
| `moneyline` | opinions | 94 | 42 | 13 | 51.9% [36.7%, 66.7%] | -0.41% [-1.47%, +0.65%] | -2.5% [-3.5%, -1.4%] (94) | 47 |
| `moneyline` | bets | 18 | 10 | 2 | 62.5% [30.0%, 86.6%] | +0.38% [-2.05%, +2.82%] | -1.8% [-4.3%, +0.8%] (18) | 18 |
| `points` | opinions | 5000 | 1581 | 1299 | 42.7% [39.5%, 46.0%] | +0.90% [-0.60%, +2.40%] | -4.4% [-5.8%, -2.9%] (3854) | 46 |
| `points` | bets | 283 | 153 | 44 | 64.0% [50.3%, 75.8%] | +14.70% [-1.60%, +30.99%] | +11.5% [-4.5%, +27.6%] (283) | 45 |
| `puck_line` | opinions | 950 | 310 | 338 | 50.7% [44.9%, 56.3%] | +0.34% [-0.24%, +0.92%] | -2.8% [-3.4%, -2.2%] (865) | 52 |
| `puck_line` | bets | 63 | 31 | 15 | 64.6% [39.1%, 83.8%] | +1.94% [-2.07%, +5.94%] | -1.7% [-5.4%, +2.0%] (63) | 30 |
| `regulation_3_way` | opinions | 138 | 44 | 34 | 42.3% [29.6%, 56.1%] | -0.38% [-1.23%, +0.46%] | — | 46 |
| `regulation_3_way` | bets | 39 | 15 | 9 | 50.0% [27.0%, 73.0%] | +0.35% [-1.38%, +2.08%] | — | 39 |
| `shots_on_goal` | opinions | 5088 | 2098 | 1020 | 51.6% [47.8%, 55.3%] | +1.98% [+0.82%, +3.14%] | -4.4% [-4.7%, -4.0%] (2964) | 46 |
| `shots_on_goal` | bets | 389 | 219 | 56 | 65.8% [54.9%, 75.2%] | +3.78% [+1.60%, +5.96%] | -1.1% [-2.8%, +0.5%] (303) | 45 |
| `team_total` | opinions | 2172 | 749 | 606 | 47.8% [44.3%, 51.4%] | +0.02% [-0.31%, +0.36%] | -5.0% [-5.4%, -4.7%] (2142) | 46 |
| `team_total` | bets | 154 | 76 | 32 | 62.3% [34.3%, 84.0%] | +1.25% [-1.79%, +4.29%] | -4.2% [-7.1%, -1.3%] (154) | 29 |
| `total_goals` | opinions | 1187 | 424 | 327 | 49.3% [44.5%, 54.1%] | +0.16% [-0.41%, +0.73%] | -3.4% [-3.8%, -2.9%] (1164) | 52 |
| `total_goals` | bets | 84 | 34 | 21 | 54.0% [30.5%, 75.8%] | +0.28% [-1.75%, +2.30%] | -3.5% [-5.2%, -1.9%] (84) | 18 |

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
- **Bets**: A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`) and nothing in a hard-gated market (`goalie_saves`), whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
