# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-11T13:44:44+00:00
- Opinions considered: **40002**; matched to a closing price: **37389**; no closing price found: **2613**.
- Within that count, priced before face-off but no close near face-off: **2521** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **82** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1689** opinion(s), 65 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 37389 | 12027 | 11394 | 46.3% [45.2%, 47.3%] | +0.52% [+0.26%, +0.78%] | -4.4% [-4.6%, -4.2%] (24985) | 79 |

2613 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 1817 | 948 | 359 | 65.0% [60.0%, 69.7%] | +4.34% [+2.18%, +6.50%] | +0.5% [-1.8%, +2.8%] (1620) | 78 |

82 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 4317 | 1352 | 1340 | 45.4% [42.6%, 48.2%] | -0.21% [-0.86%, +0.44%] | -4.5% [-4.8%, -4.1%] (2605) | 73 |
| `assists` | bets | 198 | 99 | 50 | 66.9% [54.4%, 77.4%] | +1.98% [+1.04%, +2.93%] | -1.0% [-2.1%, -0.0%] (196) | 67 |
| `blocked_shots` | opinions | 36 | 10 | 8 | 35.7% [16.0%, 61.8%] | -1.83% [-4.20%, +0.55%] | -8.4% [-10.6%, -6.3%] (36) | 13 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [27.1%, 100.0%] | +1.68% [-0.77%, +4.13%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 9611 | 2450 | 4216 | 45.4% [42.6%, 48.3%] | +1.13% [+0.43%, +1.84%] | -4.6% [-4.9%, -4.2%] (4595) | 73 |
| `goals` | bets | 78 | 44 | 20 | 75.9% [51.4%, 90.3%] | +2.48% [+0.57%, +4.40%] | -2.1% [-3.7%, -0.6%] (75) | 40 |
| `moneyline` | opinions | 148 | 66 | 16 | 50.0% [38.0%, 62.0%] | -0.40% [-1.24%, +0.43%] | -2.4% [-3.2%, -1.6%] (148) | 74 |
| `moneyline` | bets | 28 | 14 | 3 | 56.0% [30.0%, 79.1%] | +0.49% [-1.70%, +2.68%] | -1.5% [-3.7%, +0.8%] (28) | 28 |
| `points` | opinions | 7969 | 2492 | 2105 | 42.5% [39.8%, 45.2%] | +0.10% [-0.93%, +1.12%] | -4.6% [-5.6%, -3.7%] (6145) | 73 |
| `points` | bets | 405 | 208 | 84 | 64.8% [54.1%, 74.2%] | +10.64% [-1.47%, +22.75%] | +7.5% [-4.4%, +19.5%] (405) | 72 |
| `puck_line` | opinions | 1481 | 496 | 485 | 49.8% [45.3%, 54.3%] | +0.63% [-0.14%, +1.40%] | -2.4% [-3.2%, -1.6%] (1348) | 79 |
| `puck_line` | bets | 89 | 42 | 20 | 60.9% [39.1%, 79.0%] | +1.43% [-1.55%, +4.41%] | -2.0% [-4.7%, +0.7%] (89) | 45 |
| `regulation_3_way` | opinions | 219 | 78 | 46 | 45.1% [34.8%, 55.8%] | -0.37% [-1.07%, +0.32%] | — | 73 |
| `regulation_3_way` | bets | 60 | 29 | 11 | 59.2% [39.4%, 76.4%] | +0.53% [-1.00%, +2.06%] | — | 60 |
| `shots_on_goal` | opinions | 8209 | 3145 | 1743 | 48.6% [45.1%, 52.2%] | +0.96% [+0.05%, +1.87%] | -4.5% [-4.7%, -4.2%] (4857) | 73 |
| `shots_on_goal` | bets | 598 | 325 | 99 | 65.1% [56.6%, 72.8%] | +3.50% [+1.93%, +5.06%] | -0.9% [-2.1%, +0.2%] (475) | 72 |
| `team_total` | opinions | 3439 | 1231 | 915 | 48.8% [46.0%, 51.6%] | +0.08% [-0.21%, +0.37%] | -4.9% [-5.2%, -4.6%] (3395) | 73 |
| `team_total` | bets | 208 | 105 | 42 | 63.3% [39.8%, 81.7%] | +1.46% [-0.98%, +3.90%] | -3.9% [-6.2%, -1.5%] (208) | 42 |
| `total_goals` | opinions | 1864 | 678 | 505 | 49.9% [46.1%, 53.7%] | +0.24% [-0.20%, +0.68%] | -3.4% [-3.7%, -3.0%] (1826) | 79 |
| `total_goals` | bets | 135 | 68 | 27 | 63.0% [43.2%, 79.2%] | +1.19% [-0.83%, +3.21%] | -2.8% [-4.6%, -1.1%] (135) | 31 |

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
- **Bets**: A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), nothing in a hard-gated market (`goalie_saves`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
