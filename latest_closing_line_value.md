# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-07T13:50:21+00:00
- Opinions considered: **139567**; matched to a closing price: **132386**; no closing price found: **7181**.
- Within that count, priced before face-off but no close near face-off: **6963** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **208** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **6753** opinion(s), 269 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 132386 | 42169 | 39878 | 45.6% [45.0%, 46.2%] | +0.17% [+0.02%, +0.33%] | -4.5% [-4.6%, -4.4%] (86927) | 254 |

7181 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 5989 | 2991 | 1252 | 63.1% [60.8%, 65.4%] | +2.62% [+1.89%, +3.34%] | -1.3% [-2.1%, -0.6%] (5273) | 253 |

314 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 14882 | 4834 | 4209 | 45.3% [43.6%, 47.0%] | -0.62% [-1.17%, -0.07%] | -4.2% [-4.4%, -4.0%] (9311) | 248 |
| `assists` | bets | 682 | 309 | 173 | 60.7% [53.9%, 67.1%] | +1.21% [+0.75%, +1.66%] | -1.6% [-2.1%, -1.2%] (679) | 234 |
| `blocked_shots` | opinions | 694 | 132 | 387 | 43.0% [35.0%, 51.4%] | -0.36% [-0.78%, +0.06%] | -7.9% [-8.4%, -7.4%] (395) | 106 |
| `blocked_shots` | bets | 75 | 16 | 49 | 61.5% [33.4%, 83.6%] | +0.85% [-0.87%, +2.56%] | -6.7% [-7.8%, -5.7%] (72) | 56 |
| `goalie_saves` | opinions | 2822 | 760 | 1219 | 47.4% [39.9%, 55.1%] | -0.62% [-1.66%, +0.43%] | -3.5% [-4.0%, -3.0%] (616) | 108 |
| `goalie_saves` | bets | 143 | 74 | 43 | 74.0% [49.5%, 89.2%] | +3.09% [-1.40%, +7.59%] | -1.5% [-3.1%, +0.1%] (68) | 47 |
| `goals` | opinions | 32833 | 8716 | 14208 | 46.8% [45.1%, 48.5%] | +1.02% [+0.61%, +1.43%] | -4.2% [-4.4%, -4.1%] (15700) | 248 |
| `goals` | bets | 209 | 117 | 46 | 71.8% [59.2%, 81.7%] | +2.37% [+1.20%, +3.53%] | -2.3% [-3.4%, -1.3%] (199) | 123 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 498 | 210 | 55 | 47.4% [40.7%, 54.2%] | -0.30% [-0.78%, +0.19%] | -2.2% [-2.7%, -1.8%] (498) | 249 |
| `moneyline` | bets | 76 | 37 | 9 | 55.2% [38.2%, 71.1%] | +0.63% [-0.81%, +2.07%] | -1.2% [-2.7%, +0.2%] (76) | 76 |
| `points` | opinions | 28420 | 8842 | 7030 | 41.3% [40.1%, 42.6%] | -0.39% [-1.04%, +0.26%] | -5.1% [-5.4%, -4.7%] (21637) | 248 |
| `points` | bets | 1319 | 623 | 289 | 60.5% [55.0%, 65.7%] | +3.85% [-0.30%, +8.00%] | +1.0% [-3.1%, +5.1%] (1319) | 244 |
| `puck_line` | opinions | 4412 | 1699 | 1139 | 51.9% [49.4%, 54.4%] | +0.44% [+0.06%, +0.82%] | -2.9% [-3.3%, -2.6%] (3935) | 254 |
| `puck_line` | bets | 259 | 144 | 49 | 68.6% [56.6%, 78.5%] | +1.09% [-0.06%, +2.24%] | -2.3% [-3.3%, -1.2%] (259) | 137 |
| `regulation_3_way` | opinions | 744 | 291 | 158 | 49.7% [43.8%, 55.5%] | -0.07% [-0.48%, +0.34%] | — | 248 |
| `regulation_3_way` | bets | 165 | 80 | 30 | 59.3% [47.0%, 70.5%] | +0.67% [-0.37%, +1.70%] | — | 165 |
| `shots_on_goal` | opinions | 29009 | 10240 | 6556 | 45.6% [43.7%, 47.5%] | +0.31% [-0.10%, +0.72%] | -4.7% [-4.9%, -4.5%] (17025) | 248 |
| `shots_on_goal` | bets | 2064 | 1125 | 360 | 66.0% [61.6%, 70.1%] | +3.63% [+2.74%, +4.52%] | -0.8% [-1.4%, -0.3%] (1604) | 247 |
| `team_total` | opinions | 11419 | 4142 | 2985 | 49.1% [47.6%, 50.7%] | +0.06% [-0.09%, +0.21%] | -4.9% [-5.0%, -4.7%] (11284) | 248 |
| `team_total` | bets | 495 | 239 | 104 | 61.1% [46.8%, 73.7%] | +0.92% [-0.35%, +2.19%] | -4.2% [-5.4%, -2.9%] (495) | 117 |
| `total_goals` | opinions | 6279 | 2169 | 1826 | 48.7% [46.6%, 50.9%] | +0.06% [-0.16%, +0.27%] | -3.5% [-3.7%, -3.4%] (6152) | 254 |
| `total_goals` | bets | 382 | 170 | 66 | 53.8% [39.6%, 67.4%] | +0.70% [-0.53%, +1.93%] | -3.2% [-4.3%, -2.1%] (382) | 87 |

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
