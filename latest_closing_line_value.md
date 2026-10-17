# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-17T13:45:41+00:00
- Opinions considered: **59559**; matched to a closing price: **56150**; no closing price found: **3409**.
- Within that count, priced before face-off but no close near face-off: **3290** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **109** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **7471** opinion(s), 284 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 56150 | 17711 | 16877 | 45.1% [44.2%, 46.0%] | +0.23% [-0.00%, +0.46%] | -4.5% [-4.7%, -4.4%] (37673) | 115 |

3409 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2546 | 1305 | 505 | 63.9% [60.0%, 67.7%] | +3.64% [+2.05%, +5.24%] | -0.2% [-1.9%, +1.4%] (2276) | 114 |

124 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 6429 | 1948 | 1972 | 43.7% [41.3%, 46.1%] | -0.54% [-1.08%, -0.00%] | -4.6% [-4.9%, -4.2%] (3996) | 109 |
| `assists` | bets | 283 | 138 | 74 | 66.0% [55.6%, 75.1%] | +1.76% [+1.00%, +2.51%] | -1.2% [-2.0%, -0.4%] (281) | 100 |
| `blocked_shots` | opinions | 62 | 21 | 9 | 39.6% [23.0%, 59.0%] | -1.75% [-3.69%, +0.18%] | -8.4% [-10.1%, -6.7%] (62) | 25 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 100 | 30 | 16 | 35.7% [14.4%, 64.6%] | -5.34% [-19.66%, +8.98%] | -5.5% [-7.2%, -3.8%] (34) | 9 |
| `goalie_saves` | bets | 15 | 12 | 1 | 85.7% [39.2%, 98.2%] | +16.80% [-5.78%, +39.38%] | -5.1% [-10.8%, +0.5%] (6) | 5 |
| `goals` | opinions | 14403 | 3756 | 6092 | 45.2% [42.7%, 47.7%] | +1.00% [+0.31%, +1.69%] | -4.4% [-4.7%, -4.2%] (6865) | 109 |
| `goals` | bets | 97 | 55 | 24 | 75.3% [54.3%, 88.7%] | +2.51% [+0.70%, +4.31%] | -2.1% [-3.7%, -0.6%] (94) | 53 |
| `hits` | opinions | 80 | 32 | 16 | 50.0% [33.1%, 66.9%] | +0.17% [-0.84%, +1.17%] | -7.8% [-8.8%, -6.9%] (80) | 18 |
| `hits` | bets | 32 | 20 | 8 | 83.3% [51.5%, 95.9%] | +2.21% [+0.61%, +3.81%] | -5.9% [-7.4%, -4.5%] (32) | 17 |
| `moneyline` | opinions | 220 | 98 | 23 | 49.7% [39.8%, 59.8%] | -0.23% [-0.98%, +0.51%] | -2.2% [-2.9%, -1.5%] (220) | 110 |
| `moneyline` | bets | 42 | 21 | 5 | 56.8% [34.4%, 76.7%] | +0.42% [-1.46%, +2.30%] | -1.4% [-3.2%, +0.5%] (42) | 42 |
| `points` | opinions | 12091 | 3716 | 3097 | 41.3% [39.2%, 43.4%] | -0.40% [-1.15%, +0.36%] | -5.0% [-5.7%, -4.4%] (9331) | 109 |
| `points` | bets | 566 | 280 | 118 | 62.5% [53.7%, 70.5%] | +7.77% [-1.36%, +16.90%] | +4.8% [-4.2%, +13.8%] (566) | 106 |
| `puck_line` | opinions | 2196 | 753 | 688 | 49.9% [46.3%, 53.6%] | +0.49% [-0.11%, +1.08%] | -2.5% [-3.2%, -1.9%] (2000) | 115 |
| `puck_line` | bets | 129 | 65 | 28 | 64.4% [46.3%, 79.1%] | +1.25% [-0.92%, +3.41%] | -2.1% [-4.1%, -0.1%] (129) | 65 |
| `regulation_3_way` | opinions | 327 | 120 | 72 | 47.1% [38.3%, 56.0%] | -0.21% [-0.82%, +0.41%] | — | 109 |
| `regulation_3_way` | bets | 84 | 41 | 16 | 60.3% [43.1%, 75.3%] | +0.63% [-0.80%, +2.06%] | — | 84 |
| `shots_on_goal` | opinions | 12314 | 4446 | 2699 | 46.2% [43.3%, 49.2%] | +0.47% [-0.21%, +1.14%] | -4.6% [-4.9%, -4.4%] (7282) | 109 |
| `shots_on_goal` | bets | 844 | 458 | 141 | 65.1% [58.2%, 71.5%] | +3.70% [+2.24%, +5.15%] | -0.7% [-1.7%, +0.3%] (672) | 108 |
| `team_total` | opinions | 5145 | 1828 | 1395 | 48.7% [46.4%, 51.1%] | +0.07% [-0.16%, +0.31%] | -4.9% [-5.2%, -4.7%] (5077) | 109 |
| `team_total` | bets | 275 | 132 | 57 | 60.6% [40.2%, 77.8%] | +1.07% [-0.94%, +3.07%] | -4.1% [-6.1%, -2.2%] (275) | 59 |
| `total_goals` | opinions | 2783 | 963 | 798 | 48.5% [45.3%, 51.7%] | +0.10% [-0.23%, +0.43%] | -3.5% [-3.8%, -3.2%] (2726) | 115 |
| `total_goals` | bets | 174 | 80 | 31 | 55.9% [37.1%, 73.2%] | +0.92% [-0.85%, +2.69%] | -3.0% [-4.6%, -1.5%] (174) | 40 |

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
