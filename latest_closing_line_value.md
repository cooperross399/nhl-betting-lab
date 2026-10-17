# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-17T19:52:00+00:00
- Opinions considered: **60699**; matched to a closing price: **56674**; no closing price found: **4025**.
- Within that count, priced before face-off but no close near face-off: **3905** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **110** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **6331** opinion(s), 226 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 56674 | 17876 | 17107 | 45.2% [44.3%, 46.1%] | +0.23% [+0.00%, +0.46%] | -4.5% [-4.7%, -4.4%] (38047) | 116 |

4025 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2584 | 1313 | 520 | 63.6% [59.6%, 67.4%] | +3.59% [+2.01%, +5.16%] | -0.3% [-1.9%, +1.4%] (2313) | 115 |

144 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 6478 | 1966 | 1987 | 43.8% [41.4%, 46.2%] | -0.53% [-1.07%, +0.00%] | -4.6% [-4.9%, -4.2%] (4026) | 110 |
| `assists` | bets | 290 | 140 | 75 | 65.1% [54.7%, 74.3%] | +1.70% [+0.95%, +2.46%] | -1.2% [-2.1%, -0.4%] (288) | 101 |
| `blocked_shots` | opinions | 62 | 21 | 9 | 39.6% [23.0%, 59.0%] | -1.75% [-3.69%, +0.18%] | -8.4% [-10.1%, -6.7%] (62) | 25 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 100 | 30 | 16 | 35.7% [14.4%, 64.6%] | -5.34% [-19.66%, +8.98%] | -5.5% [-7.2%, -3.8%] (34) | 9 |
| `goalie_saves` | bets | 15 | 12 | 1 | 85.7% [39.2%, 98.2%] | +16.80% [-5.78%, +39.38%] | -5.1% [-10.8%, +0.5%] (6) | 5 |
| `goals` | opinions | 14539 | 3787 | 6177 | 45.3% [42.8%, 47.8%] | +0.99% [+0.31%, +1.68%] | -4.4% [-4.7%, -4.2%] (6933) | 110 |
| `goals` | bets | 101 | 55 | 27 | 74.3% [53.5%, 87.9%] | +2.40% [+0.64%, +4.16%] | -2.2% [-3.6%, -0.7%] (98) | 54 |
| `hits` | opinions | 80 | 32 | 16 | 50.0% [33.1%, 66.9%] | +0.17% [-0.84%, +1.17%] | -7.8% [-8.8%, -6.9%] (80) | 18 |
| `hits` | bets | 32 | 20 | 8 | 83.3% [51.5%, 95.9%] | +2.21% [+0.61%, +3.81%] | -5.9% [-7.4%, -4.5%] (32) | 17 |
| `moneyline` | opinions | 222 | 99 | 24 | 50.0% [40.0%, 60.0%] | -0.22% [-0.96%, +0.52%] | -2.2% [-2.9%, -1.5%] (222) | 111 |
| `moneyline` | bets | 42 | 21 | 5 | 56.8% [34.4%, 76.7%] | +0.42% [-1.46%, +2.30%] | -1.4% [-3.2%, +0.5%] (42) | 42 |
| `points` | opinions | 12201 | 3748 | 3133 | 41.3% [39.3%, 43.4%] | -0.40% [-1.15%, +0.35%] | -5.0% [-5.7%, -4.4%] (9423) | 110 |
| `points` | bets | 577 | 280 | 121 | 61.4% [52.1%, 69.9%] | +7.61% [-1.38%, +16.59%] | +4.6% [-4.2%, +13.5%] (577) | 107 |
| `puck_line` | opinions | 2215 | 760 | 697 | 50.1% [46.4%, 53.7%] | +0.48% [-0.10%, +1.07%] | -2.5% [-3.1%, -1.9%] (2018) | 116 |
| `puck_line` | bets | 131 | 67 | 28 | 65.0% [47.2%, 79.5%] | +1.27% [-0.86%, +3.39%] | -2.1% [-4.0%, -0.1%] (131) | 66 |
| `regulation_3_way` | opinions | 330 | 121 | 74 | 47.3% [38.5%, 56.2%] | -0.20% [-0.81%, +0.41%] | — | 110 |
| `regulation_3_way` | bets | 85 | 41 | 17 | 60.3% [43.1%, 75.3%] | +0.62% [-0.79%, +2.04%] | — | 85 |
| `shots_on_goal` | opinions | 12446 | 4495 | 2752 | 46.4% [43.5%, 49.3%] | +0.47% [-0.21%, +1.14%] | -4.6% [-4.9%, -4.4%] (7374) | 110 |
| `shots_on_goal` | bets | 855 | 461 | 147 | 65.1% [58.2%, 71.4%] | +3.65% [+2.21%, +5.09%] | -0.7% [-1.7%, +0.3%] (683) | 109 |
| `team_total` | opinions | 5191 | 1846 | 1411 | 48.8% [46.5%, 51.2%] | +0.08% [-0.15%, +0.31%] | -4.9% [-5.2%, -4.7%] (5123) | 110 |
| `team_total` | bets | 277 | 133 | 58 | 60.7% [40.5%, 77.9%] | +1.06% [-0.92%, +3.05%] | -4.1% [-6.1%, -2.2%] (277) | 60 |
| `total_goals` | opinions | 2810 | 971 | 811 | 48.6% [45.4%, 51.8%] | +0.10% [-0.22%, +0.43%] | -3.5% [-3.8%, -3.2%] (2752) | 116 |
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
