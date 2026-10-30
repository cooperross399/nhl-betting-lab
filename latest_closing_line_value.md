# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-30T20:47:22+00:00
- Opinions considered: **111261**; matched to a closing price: **106057**; no closing price found: **5204**.
- Within that count, priced before face-off but no close near face-off: **5017** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **177** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1637** opinion(s), 98 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 106057 | 33971 | 31858 | 45.8% [45.1%, 46.4%] | +0.15% [-0.03%, +0.33%] | -4.5% [-4.6%, -4.4%] (70106) | 206 |

5204 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 4782 | 2436 | 972 | 63.9% [61.4%, 66.4%] | +2.91% [+2.02%, +3.79%] | -1.1% [-2.0%, -0.1%] (4236) | 205 |

221 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 12018 | 3888 | 3384 | 45.0% [43.2%, 46.9%] | -0.79% [-1.45%, -0.13%] | -4.3% [-4.5%, -4.0%] (7490) | 200 |
| `assists` | bets | 544 | 258 | 131 | 62.5% [55.1%, 69.3%] | +1.39% [+0.88%, +1.91%] | -1.5% [-2.0%, -0.9%] (542) | 188 |
| `blocked_shots` | opinions | 450 | 91 | 227 | 40.8% [31.7%, 50.6%] | -0.48% [-1.08%, +0.13%] | -8.0% [-8.6%, -7.3%] (274) | 75 |
| `blocked_shots` | bets | 44 | 9 | 29 | 60.0% [24.9%, 87.1%] | +0.75% [-1.72%, +3.23%] | -6.7% [-7.9%, -5.6%] (42) | 34 |
| `goalie_saves` | opinions | 1694 | 462 | 694 | 46.2% [37.0%, 55.6%] | -0.51% [-1.87%, +0.85%] | -3.5% [-4.1%, -2.9%] (371) | 66 |
| `goalie_saves` | bets | 83 | 47 | 25 | 81.0% [57.0%, 93.2%] | +4.92% [-1.93%, +11.77%] | -1.5% [-3.4%, +0.4%] (44) | 31 |
| `goals` | opinions | 26447 | 7051 | 11440 | 47.0% [45.1%, 48.9%] | +1.16% [+0.69%, +1.63%] | -4.2% [-4.4%, -4.0%] (12634) | 200 |
| `goals` | bets | 162 | 93 | 37 | 74.4% [59.8%, 85.0%] | +2.49% [+1.15%, +3.83%] | -2.3% [-3.4%, -1.1%] (155) | 95 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 402 | 170 | 44 | 47.5% [40.1%, 55.0%] | -0.26% [-0.79%, +0.28%] | -2.2% [-2.7%, -1.7%] (402) | 201 |
| `moneyline` | bets | 66 | 33 | 8 | 56.9% [38.6%, 73.5%] | +0.75% [-0.71%, +2.20%] | -1.1% [-2.5%, +0.3%] (66) | 66 |
| `points` | opinions | 22833 | 7131 | 5646 | 41.5% [40.1%, 42.9%] | -0.89% [-1.53%, -0.25%] | -5.0% [-5.4%, -4.6%] (17343) | 200 |
| `points` | bets | 1062 | 510 | 226 | 61.0% [54.8%, 66.9%] | +4.61% [-0.49%, +9.71%] | +1.8% [-3.2%, +6.8%] (1062) | 196 |
| `puck_line` | opinions | 3657 | 1378 | 977 | 51.4% [48.7%, 54.2%] | +0.45% [+0.02%, +0.88%] | -2.8% [-3.3%, -2.4%] (3280) | 206 |
| `puck_line` | bets | 227 | 131 | 41 | 70.4% [57.9%, 80.5%] | +1.17% [-0.12%, +2.46%] | -2.2% [-3.4%, -1.0%] (227) | 119 |
| `regulation_3_way` | opinions | 600 | 232 | 130 | 49.4% [42.8%, 55.9%] | -0.05% [-0.50%, +0.39%] | — | 200 |
| `regulation_3_way` | bets | 135 | 67 | 23 | 59.8% [46.3%, 72.0%] | +0.69% [-0.42%, +1.80%] | — | 135 |
| `shots_on_goal` | opinions | 23062 | 8283 | 5237 | 46.5% [44.4%, 48.6%] | +0.59% [+0.14%, +1.04%] | -4.6% [-4.8%, -4.5%] (13636) | 200 |
| `shots_on_goal` | bets | 1633 | 894 | 283 | 66.2% [61.2%, 70.9%] | +3.80% [+2.78%, +4.82%] | -0.7% [-1.3%, -0.0%] (1272) | 199 |
| `team_total` | opinions | 9433 | 3391 | 2504 | 48.9% [47.2%, 50.7%] | +0.07% [-0.10%, +0.23%] | -4.9% [-5.1%, -4.8%] (9324) | 200 |
| `team_total` | bets | 421 | 213 | 89 | 64.2% [48.4%, 77.3%] | +1.16% [-0.23%, +2.55%] | -4.0% [-5.3%, -2.6%] (421) | 97 |
| `total_goals` | opinions | 5087 | 1760 | 1469 | 48.6% [46.3%, 51.0%] | +0.06% [-0.17%, +0.29%] | -3.5% [-3.7%, -3.3%] (4978) | 206 |
| `total_goals` | bets | 285 | 124 | 46 | 51.9% [36.5%, 66.9%] | +0.61% [-0.87%, +2.08%] | -3.3% [-4.6%, -2.0%] (285) | 64 |

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
