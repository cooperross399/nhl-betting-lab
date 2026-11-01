# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-01T13:45:48+00:00
- Opinions considered: **118404**; matched to a closing price: **112035**; no closing price found: **6369**.
- Within that count, priced before face-off but no close near face-off: **6159** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **200** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2752** opinion(s), 108 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 112035 | 35879 | 33726 | 45.8% [45.2%, 46.4%] | +0.15% [-0.02%, +0.32%] | -4.5% [-4.6%, -4.4%] (74044) | 217 |

6369 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 5120 | 2576 | 1048 | 63.3% [60.7%, 65.7%] | +2.77% [+1.93%, +3.60%] | -1.2% [-2.0%, -0.3%] (4529) | 216 |

286 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 12695 | 4097 | 3598 | 45.0% [43.2%, 46.9%] | -0.76% [-1.38%, -0.13%] | -4.2% [-4.4%, -4.0%] (7929) | 211 |
| `assists` | bets | 577 | 273 | 139 | 62.3% [55.0%, 69.1%] | +1.37% [+0.87%, +1.87%] | -1.5% [-2.0%, -1.0%] (575) | 198 |
| `blocked_shots` | opinions | 476 | 101 | 238 | 42.4% [33.4%, 52.0%] | -0.40% [-0.98%, +0.18%] | -8.0% [-8.6%, -7.3%] (286) | 79 |
| `blocked_shots` | bets | 49 | 10 | 31 | 55.6% [24.5%, 82.8%] | +0.60% [-1.63%, +2.84%] | -6.9% [-7.9%, -5.8%] (47) | 37 |
| `goalie_saves` | opinions | 1836 | 500 | 740 | 45.6% [36.6%, 54.9%] | -0.69% [-2.07%, +0.70%] | -3.7% [-4.3%, -3.0%] (403) | 73 |
| `goalie_saves` | bets | 101 | 55 | 30 | 77.5% [53.4%, 91.1%] | +4.03% [-1.93%, +9.99%] | -1.5% [-3.3%, +0.3%] (49) | 35 |
| `goals` | opinions | 27915 | 7440 | 12123 | 47.1% [45.3%, 49.0%] | +1.18% [+0.73%, +1.63%] | -4.2% [-4.4%, -4.0%] (13324) | 211 |
| `goals` | bets | 175 | 99 | 38 | 72.3% [58.1%, 83.0%] | +2.46% [+1.14%, +3.79%] | -2.3% [-3.4%, -1.1%] (168) | 103 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 424 | 179 | 47 | 47.5% [40.2%, 54.8%] | -0.26% [-0.80%, +0.27%] | -2.2% [-2.7%, -1.7%] (424) | 212 |
| `moneyline` | bets | 70 | 34 | 9 | 55.7% [37.9%, 72.2%] | +0.68% [-0.80%, +2.17%] | -1.2% [-2.7%, +0.2%] (70) | 70 |
| `points` | opinions | 24123 | 7517 | 6021 | 41.5% [40.2%, 42.9%] | -0.87% [-1.48%, -0.26%] | -5.0% [-5.4%, -4.6%] (18324) | 211 |
| `points` | bets | 1129 | 531 | 245 | 60.1% [54.0%, 65.9%] | +4.35% [-0.47%, +9.16%] | +1.5% [-3.2%, +6.3%] (1129) | 207 |
| `puck_line` | opinions | 3829 | 1468 | 997 | 51.8% [49.1%, 54.5%] | +0.46% [+0.04%, +0.87%] | -2.8% [-3.2%, -2.4%] (3432) | 217 |
| `puck_line` | bets | 234 | 134 | 41 | 69.4% [57.0%, 79.6%] | +1.17% [-0.09%, +2.43%] | -2.2% [-3.3%, -1.1%] (234) | 123 |
| `regulation_3_way` | opinions | 633 | 248 | 135 | 49.8% [43.4%, 56.2%] | -0.03% [-0.48%, +0.41%] | — | 211 |
| `regulation_3_way` | bets | 143 | 70 | 24 | 58.8% [45.7%, 70.8%] | +0.62% [-0.51%, +1.76%] | — | 143 |
| `shots_on_goal` | opinions | 24438 | 8744 | 5559 | 46.3% [44.3%, 48.3%] | +0.54% [+0.10%, +0.97%] | -4.6% [-4.8%, -4.5%] (14485) | 211 |
| `shots_on_goal` | bets | 1745 | 958 | 305 | 66.5% [61.7%, 71.0%] | +3.71% [+2.75%, +4.68%] | -0.7% [-1.3%, -0.1%] (1360) | 210 |
| `team_total` | opinions | 9931 | 3600 | 2601 | 49.1% [47.4%, 50.8%] | +0.06% [-0.10%, +0.23%] | -4.9% [-5.1%, -4.8%] (9814) | 211 |
| `team_total` | bets | 450 | 218 | 95 | 61.4% [46.2%, 74.7%] | +0.92% [-0.45%, +2.29%] | -4.2% [-5.5%, -2.9%] (450) | 103 |
| `total_goals` | opinions | 5361 | 1851 | 1561 | 48.7% [46.4%, 51.0%] | +0.05% [-0.18%, +0.28%] | -3.5% [-3.7%, -3.3%] (5249) | 217 |
| `total_goals` | bets | 327 | 137 | 57 | 50.7% [36.1%, 65.3%] | +0.54% [-0.81%, +1.89%] | -3.3% [-4.5%, -2.1%] (327) | 73 |

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
