# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-02T14:52:20+00:00
- Opinions considered: **121213**; matched to a closing price: **114252**; no closing price found: **6961**.
- Within that count, priced before face-off but no close near face-off: **6749** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **202** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2125** opinion(s), 94 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 114252 | 36551 | 34483 | 45.8% [45.2%, 46.4%] | +0.14% [-0.02%, +0.31%] | -4.5% [-4.6%, -4.4%] (75526) | 221 |

6961 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 5213 | 2623 | 1065 | 63.2% [60.7%, 65.7%] | +2.75% [+1.93%, +3.57%] | -1.2% [-2.1%, -0.3%] (4607) | 220 |

312 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 12948 | 4177 | 3678 | 45.1% [43.3%, 46.9%] | -0.75% [-1.36%, -0.13%] | -4.2% [-4.4%, -4.0%] (8087) | 215 |
| `assists` | bets | 584 | 275 | 140 | 61.9% [54.7%, 68.7%] | +1.35% [+0.85%, +1.84%] | -1.5% [-2.0%, -1.0%] (582) | 201 |
| `blocked_shots` | opinions | 480 | 103 | 238 | 42.6% [33.7%, 51.9%] | -0.39% [-0.97%, +0.18%] | -7.9% [-8.6%, -7.3%] (290) | 81 |
| `blocked_shots` | bets | 50 | 11 | 31 | 57.9% [26.8%, 83.8%] | +0.70% [-1.52%, +2.91%] | -6.8% [-7.9%, -5.7%] (48) | 38 |
| `goalie_saves` | opinions | 1889 | 525 | 761 | 46.5% [37.6%, 55.7%] | -0.56% [-1.93%, +0.82%] | -3.5% [-4.1%, -2.9%] (416) | 75 |
| `goalie_saves` | bets | 112 | 62 | 34 | 79.5% [56.4%, 92.1%] | +3.84% [-1.57%, +9.24%] | -1.6% [-3.3%, +0.2%] (53) | 37 |
| `goals` | opinions | 28429 | 7566 | 12368 | 47.1% [45.3%, 48.9%] | +1.16% [+0.72%, +1.60%] | -4.2% [-4.4%, -4.0%] (13566) | 215 |
| `goals` | bets | 175 | 99 | 38 | 72.3% [58.1%, 83.0%] | +2.46% [+1.14%, +3.79%] | -2.3% [-3.4%, -1.1%] (168) | 103 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 432 | 182 | 48 | 47.4% [40.2%, 54.7%] | -0.27% [-0.80%, +0.25%] | -2.2% [-2.7%, -1.7%] (432) | 216 |
| `moneyline` | bets | 70 | 34 | 9 | 55.7% [37.9%, 72.2%] | +0.68% [-0.80%, +2.17%] | -1.2% [-2.7%, +0.2%] (70) | 70 |
| `points` | opinions | 24603 | 7641 | 6182 | 41.5% [40.1%, 42.8%] | -0.87% [-1.47%, -0.27%] | -5.0% [-5.3%, -4.6%] (18693) | 215 |
| `points` | bets | 1143 | 536 | 249 | 60.0% [53.9%, 65.7%] | +4.29% [-0.47%, +9.05%] | +1.5% [-3.2%, +6.1%] (1143) | 211 |
| `puck_line` | opinions | 3894 | 1493 | 1019 | 51.9% [49.3%, 54.6%] | +0.44% [+0.03%, +0.85%] | -2.9% [-3.3%, -2.5%] (3487) | 221 |
| `puck_line` | bets | 234 | 134 | 41 | 69.4% [57.0%, 79.6%] | +1.17% [-0.09%, +2.43%] | -2.2% [-3.3%, -1.1%] (234) | 123 |
| `regulation_3_way` | opinions | 645 | 253 | 136 | 49.7% [43.4%, 56.0%] | -0.07% [-0.51%, +0.37%] | — | 215 |
| `regulation_3_way` | bets | 146 | 71 | 25 | 58.7% [45.7%, 70.6%] | +0.59% [-0.52%, +1.71%] | — | 146 |
| `shots_on_goal` | opinions | 24982 | 8935 | 5686 | 46.3% [44.3%, 48.3%] | +0.53% [+0.11%, +0.96%] | -4.6% [-4.8%, -4.5%] (14836) | 215 |
| `shots_on_goal` | bets | 1785 | 980 | 308 | 66.4% [61.6%, 70.8%] | +3.70% [+2.75%, +4.64%] | -0.7% [-1.4%, -0.1%] (1395) | 214 |
| `team_total` | opinions | 10119 | 3652 | 2672 | 49.0% [47.4%, 50.7%] | +0.06% [-0.10%, +0.22%] | -4.9% [-5.1%, -4.8%] (10000) | 215 |
| `team_total` | bets | 458 | 219 | 98 | 60.8% [45.8%, 74.1%] | +0.89% [-0.45%, +2.24%] | -4.2% [-5.5%, -2.9%] (458) | 105 |
| `total_goals` | opinions | 5457 | 1890 | 1589 | 48.9% [46.6%, 51.2%] | +0.05% [-0.18%, +0.27%] | -3.5% [-3.7%, -3.3%] (5345) | 221 |
| `total_goals` | bets | 336 | 145 | 58 | 52.2% [37.6%, 66.4%] | +0.58% [-0.74%, +1.90%] | -3.3% [-4.5%, -2.1%] (336) | 75 |

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
