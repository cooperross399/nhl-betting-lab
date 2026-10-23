# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-23T20:47:25+00:00
- Opinions considered: **84058**; matched to a closing price: **79774**; no closing price found: **4284**.
- Within that count, priced before face-off but no close near face-off: **4129** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **145** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1095** opinion(s), 35 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 79774 | 25403 | 24096 | 45.6% [44.9%, 46.4%] | +0.25% [+0.07%, +0.42%] | -4.5% [-4.6%, -4.4%] (53369) | 159 |

4284 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 3560 | 1790 | 722 | 63.1% [59.9%, 66.1%] | +3.12% [+1.95%, +4.28%] | -0.8% [-2.0%, +0.5%] (3167) | 158 |

156 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 9081 | 2898 | 2656 | 45.1% [43.1%, 47.1%] | -0.38% [-0.81%, +0.05%] | -4.5% [-4.7%, -4.2%] (5708) | 153 |
| `assists` | bets | 404 | 195 | 98 | 63.7% [55.2%, 71.5%] | +1.50% [+0.90%, +2.11%] | -1.5% [-2.1%, -0.8%] (402) | 141 |
| `blocked_shots` | opinions | 162 | 44 | 62 | 44.0% [30.8%, 58.1%] | -0.78% [-1.74%, +0.17%] | -8.1% [-9.2%, -7.0%] (118) | 37 |
| `blocked_shots` | bets | 11 | 3 | 6 | 60.0% [14.7%, 92.9%] | +0.06% [-2.17%, +2.28%] | -6.6% [-8.5%, -4.7%] (11) | 10 |
| `goalie_saves` | opinions | 465 | 142 | 168 | 47.8% [31.3%, 64.8%] | -0.84% [-4.43%, +2.75%] | -4.0% [-5.0%, -2.9%] (110) | 21 |
| `goalie_saves` | bets | 42 | 27 | 9 | 81.8% [46.2%, 95.9%] | +7.73% [-4.75%, +20.21%] | -3.0% [-5.9%, -0.1%] (16) | 12 |
| `goals` | opinions | 20224 | 5393 | 8712 | 46.8% [44.6%, 49.1%] | +1.15% [+0.59%, +1.70%] | -4.3% [-4.5%, -4.0%] (9627) | 153 |
| `goals` | bets | 135 | 76 | 31 | 73.1% [56.5%, 85.0%] | +2.47% [+0.92%, +4.03%] | -2.2% [-3.5%, -0.8%] (129) | 75 |
| `hits` | opinions | 260 | 95 | 70 | 50.0% [39.8%, 60.2%] | +0.06% [-0.64%, +0.76%] | -7.9% [-8.5%, -7.3%] (260) | 49 |
| `hits` | bets | 89 | 45 | 26 | 71.4% [51.1%, 85.7%] | +1.50% [+0.12%, +2.88%] | -6.6% [-7.8%, -5.3%] (89) | 45 |
| `moneyline` | opinions | 308 | 129 | 36 | 47.4% [39.0%, 56.0%] | -0.30% [-0.89%, +0.29%] | -2.3% [-2.8%, -1.7%] (308) | 154 |
| `moneyline` | bets | 54 | 25 | 6 | 52.1% [32.7%, 70.9%] | +0.33% [-1.25%, +1.91%] | -1.5% [-3.0%, +0.1%] (54) | 54 |
| `points` | opinions | 17176 | 5340 | 4313 | 41.5% [39.9%, 43.1%] | -0.40% [-0.96%, +0.16%] | -5.0% [-5.5%, -4.6%] (13211) | 153 |
| `points` | bets | 805 | 377 | 177 | 60.0% [52.5%, 67.1%] | +5.70% [-0.92%, +12.32%] | +2.7% [-3.8%, +9.3%] (805) | 149 |
| `puck_line` | opinions | 2913 | 1050 | 862 | 51.2% [48.0%, 54.3%] | +0.52% [+0.04%, +1.01%] | -2.7% [-3.2%, -2.2%] (2630) | 159 |
| `puck_line` | bets | 178 | 92 | 37 | 65.2% [50.6%, 77.5%] | +0.97% [-0.63%, +2.58%] | -2.3% [-3.8%, -0.9%] (178) | 93 |
| `regulation_3_way` | opinions | 459 | 176 | 101 | 49.2% [41.7%, 56.7%] | -0.13% [-0.62%, +0.36%] | — | 153 |
| `regulation_3_way` | bets | 107 | 53 | 19 | 60.2% [45.0%, 73.7%] | +0.67% [-0.54%, +1.87%] | — | 107 |
| `shots_on_goal` | opinions | 17613 | 6234 | 3999 | 45.8% [43.4%, 48.3%] | +0.28% [-0.22%, +0.79%] | -4.7% [-4.9%, -4.5%] (10458) | 153 |
| `shots_on_goal` | bets | 1206 | 647 | 206 | 64.7% [58.8%, 70.1%] | +3.56% [+2.39%, +4.73%] | -0.7% [-1.4%, +0.1%] (954) | 152 |
| `team_total` | opinions | 7221 | 2546 | 2000 | 48.8% [46.8%, 50.7%] | +0.07% [-0.12%, +0.26%] | -4.9% [-5.1%, -4.7%] (7128) | 153 |
| `team_total` | bets | 330 | 158 | 73 | 61.5% [43.3%, 76.9%] | +1.07% [-0.62%, +2.76%] | -4.1% [-5.7%, -2.4%] (330) | 75 |
| `total_goals` | opinions | 3892 | 1356 | 1117 | 48.9% [46.2%, 51.6%] | +0.10% [-0.17%, +0.37%] | -3.5% [-3.7%, -3.3%] (3811) | 159 |
| `total_goals` | bets | 199 | 92 | 34 | 55.8% [37.2%, 72.8%] | +0.98% [-0.75%, +2.72%] | -3.0% [-4.5%, -1.4%] (199) | 46 |

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
