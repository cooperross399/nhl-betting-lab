# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-16T20:41:58+00:00
- Opinions considered: **58551**; matched to a closing price: **55147**; no closing price found: **3404**.
- Within that count, priced before face-off but no close near face-off: **3286** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **108** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1008** opinion(s), 38 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 55147 | 17387 | 16569 | 45.1% [44.1%, 46.0%] | +0.22% [-0.01%, +0.46%] | -4.5% [-4.7%, -4.4%] (36992) | 113 |

3404 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2508 | 1281 | 499 | 63.8% [59.7%, 67.6%] | +3.66% [+2.05%, +5.28%] | -0.2% [-1.9%, +1.5%] (2244) | 112 |

124 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 6310 | 1910 | 1941 | 43.7% [41.3%, 46.1%] | -0.57% [-1.11%, -0.03%] | -4.6% [-4.9%, -4.2%] (3918) | 107 |
| `assists` | bets | 279 | 137 | 73 | 66.5% [56.0%, 75.6%] | +1.78% [+1.01%, +2.55%] | -1.1% [-1.9%, -0.3%] (277) | 98 |
| `blocked_shots` | opinions | 62 | 21 | 9 | 39.6% [23.0%, 59.0%] | -1.75% [-3.69%, +0.18%] | -8.4% [-10.1%, -6.7%] (62) | 25 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 100 | 30 | 16 | 35.7% [14.4%, 64.6%] | -5.34% [-19.66%, +8.98%] | -5.5% [-7.2%, -3.8%] (34) | 9 |
| `goalie_saves` | bets | 15 | 12 | 1 | 85.7% [39.2%, 98.2%] | +16.80% [-5.78%, +39.38%] | -5.1% [-10.8%, +0.5%] (6) | 5 |
| `goals` | opinions | 14147 | 3673 | 5975 | 44.9% [42.5%, 47.5%] | +0.98% [+0.29%, +1.68%] | -4.5% [-4.8%, -4.2%] (6740) | 107 |
| `goals` | bets | 97 | 55 | 24 | 75.3% [54.3%, 88.7%] | +2.51% [+0.70%, +4.31%] | -2.1% [-3.7%, -0.6%] (94) | 53 |
| `hits` | opinions | 80 | 32 | 16 | 50.0% [33.1%, 66.9%] | +0.17% [-0.84%, +1.17%] | -7.8% [-8.8%, -6.9%] (80) | 18 |
| `hits` | bets | 32 | 20 | 8 | 83.3% [51.5%, 95.9%] | +2.21% [+0.61%, +3.81%] | -5.9% [-7.4%, -4.5%] (32) | 17 |
| `moneyline` | opinions | 216 | 97 | 22 | 50.0% [39.9%, 60.1%] | -0.23% [-0.99%, +0.53%] | -2.2% [-3.0%, -1.5%] (216) | 108 |
| `moneyline` | bets | 41 | 21 | 4 | 56.8% [34.4%, 76.7%] | +0.43% [-1.50%, +2.36%] | -1.5% [-3.3%, +0.4%] (41) | 41 |
| `points` | opinions | 11882 | 3660 | 3035 | 41.4% [39.3%, 43.5%] | -0.40% [-1.17%, +0.36%] | -5.0% [-5.7%, -4.4%] (9171) | 107 |
| `points` | bets | 560 | 279 | 117 | 63.0% [54.2%, 70.9%] | +7.88% [-1.34%, +17.09%] | +4.9% [-4.2%, +14.0%] (560) | 104 |
| `puck_line` | opinions | 2155 | 738 | 677 | 49.9% [46.2%, 53.6%] | +0.48% [-0.12%, +1.08%] | -2.5% [-3.2%, -1.9%] (1963) | 113 |
| `puck_line` | bets | 127 | 63 | 28 | 63.6% [45.4%, 78.7%] | +1.25% [-0.95%, +3.45%] | -2.1% [-4.1%, -0.1%] (127) | 64 |
| `regulation_3_way` | opinions | 321 | 117 | 71 | 46.8% [38.0%, 55.8%] | -0.22% [-0.85%, +0.40%] | — | 107 |
| `regulation_3_way` | bets | 82 | 39 | 16 | 59.1% [41.7%, 74.5%] | +0.56% [-0.89%, +2.02%] | — | 82 |
| `shots_on_goal` | opinions | 12092 | 4376 | 2645 | 46.3% [43.4%, 49.3%] | +0.49% [-0.20%, +1.18%] | -4.6% [-4.8%, -4.4%] (7149) | 107 |
| `shots_on_goal` | bets | 832 | 451 | 138 | 65.0% [58.0%, 71.4%] | +3.72% [+2.25%, +5.19%] | -0.7% [-1.7%, +0.3%] (664) | 106 |
| `team_total` | opinions | 5050 | 1791 | 1372 | 48.7% [46.3%, 51.1%] | +0.06% [-0.18%, +0.30%] | -4.9% [-5.2%, -4.7%] (4983) | 107 |
| `team_total` | bets | 270 | 127 | 57 | 59.6% [39.1%, 77.3%] | +1.01% [-1.03%, +3.05%] | -4.2% [-6.2%, -2.2%] (270) | 57 |
| `total_goals` | opinions | 2732 | 942 | 790 | 48.5% [45.3%, 51.8%] | +0.10% [-0.23%, +0.43%] | -3.5% [-3.8%, -3.2%] (2676) | 113 |
| `total_goals` | bets | 168 | 74 | 31 | 54.0% [35.4%, 71.5%] | +0.71% [-1.02%, +2.45%] | -3.2% [-4.7%, -1.7%] (168) | 39 |

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
