# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-19T13:45:27+00:00
- Opinions considered: **68133**; matched to a closing price: **64014**; no closing price found: **4119**.
- Within that count, priced before face-off but no close near face-off: **3990** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **119** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2153** opinion(s), 84 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 64014 | 20207 | 19451 | 45.3% [44.5%, 46.2%] | +0.23% [+0.02%, +0.44%] | -4.5% [-4.7%, -4.4%] (43003) | 130 |

4119 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2859 | 1448 | 590 | 63.8% [60.1%, 67.4%] | +3.47% [+2.04%, +4.90%] | -0.4% [-1.9%, +1.1%] (2553) | 129 |

146 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 7317 | 2235 | 2239 | 44.0% [41.8%, 46.2%] | -0.48% [-0.97%, +0.01%] | -4.5% [-4.8%, -4.2%] (4576) | 124 |
| `assists` | bets | 321 | 155 | 82 | 64.9% [54.7%, 73.8%] | +1.70% [+0.99%, +2.40%] | -1.2% [-2.0%, -0.5%] (319) | 113 |
| `blocked_shots` | opinions | 62 | 21 | 9 | 39.6% [23.0%, 59.0%] | -1.75% [-3.69%, +0.18%] | -8.4% [-10.1%, -6.7%] (62) | 25 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 100 | 30 | 16 | 35.7% [14.4%, 64.6%] | -5.34% [-19.66%, +8.98%] | -5.5% [-7.2%, -3.8%] (34) | 9 |
| `goalie_saves` | bets | 15 | 12 | 1 | 85.7% [39.2%, 98.2%] | +16.80% [-5.78%, +39.38%] | -5.1% [-10.8%, +0.5%] (6) | 5 |
| `goals` | opinions | 16420 | 4290 | 7031 | 45.7% [43.3%, 48.1%] | +0.99% [+0.36%, +1.62%] | -4.4% [-4.7%, -4.2%] (7820) | 124 |
| `goals` | bets | 110 | 59 | 29 | 72.8% [53.7%, 86.1%] | +2.22% [+0.58%, +3.87%] | -2.3% [-3.7%, -1.0%] (107) | 60 |
| `hits` | opinions | 98 | 38 | 22 | 50.0% [34.4%, 65.6%] | +0.11% [-0.81%, +1.04%] | -7.9% [-8.7%, -7.0%] (98) | 23 |
| `hits` | bets | 41 | 25 | 11 | 83.3% [57.1%, 94.9%] | +2.10% [+0.66%, +3.55%] | -6.0% [-7.3%, -4.7%] (41) | 22 |
| `moneyline` | opinions | 250 | 110 | 26 | 49.1% [39.7%, 58.5%] | -0.23% [-0.91%, +0.46%] | -2.2% [-2.9%, -1.5%] (250) | 125 |
| `moneyline` | bets | 46 | 23 | 6 | 57.5% [35.8%, 76.7%] | +0.53% [-1.25%, +2.30%] | -1.2% [-3.0%, +0.5%] (46) | 46 |
| `points` | opinions | 13833 | 4254 | 3531 | 41.3% [39.4%, 43.2%] | -0.41% [-1.09%, +0.27%] | -5.1% [-5.6%, -4.5%] (10675) | 124 |
| `points` | bets | 646 | 307 | 141 | 60.8% [52.1%, 68.9%] | +6.87% [-1.24%, +14.98%] | +3.9% [-4.1%, +11.9%] (646) | 121 |
| `puck_line` | opinions | 2452 | 852 | 756 | 50.2% [46.8%, 53.7%] | +0.41% [-0.14%, +0.95%] | -2.6% [-3.2%, -2.0%] (2227) | 130 |
| `puck_line` | bets | 147 | 74 | 31 | 63.8% [47.3%, 77.6%] | +1.13% [-0.79%, +3.05%] | -2.1% [-3.9%, -0.4%] (147) | 75 |
| `regulation_3_way` | opinions | 372 | 138 | 83 | 47.8% [39.5%, 56.1%] | -0.17% [-0.73%, +0.39%] | — | 124 |
| `regulation_3_way` | bets | 92 | 45 | 18 | 60.8% [44.3%, 75.2%] | +0.71% [-0.63%, +2.05%] | — | 92 |
| `shots_on_goal` | opinions | 14096 | 5090 | 3189 | 46.7% [43.8%, 49.5%] | +0.46% [-0.14%, +1.07%] | -4.6% [-4.9%, -4.4%] (8384) | 124 |
| `shots_on_goal` | bets | 959 | 523 | 171 | 66.4% [59.9%, 72.3%] | +3.76% [+2.45%, +5.07%] | -0.7% [-1.6%, +0.3%] (759) | 123 |
| `team_total` | opinions | 5848 | 2065 | 1614 | 48.8% [46.6%, 51.0%] | +0.07% [-0.14%, +0.28%] | -4.9% [-5.1%, -4.7%] (5776) | 124 |
| `team_total` | bets | 298 | 142 | 64 | 60.7% [41.4%, 77.1%] | +1.08% [-0.78%, +2.94%] | -4.1% [-5.9%, -2.3%] (298) | 66 |
| `total_goals` | opinions | 3166 | 1084 | 935 | 48.6% [45.6%, 51.6%] | +0.10% [-0.20%, +0.39%] | -3.5% [-3.8%, -3.3%] (3101) | 130 |
| `total_goals` | bets | 179 | 80 | 34 | 55.2% [36.6%, 72.4%] | +0.87% [-0.85%, +2.60%] | -3.1% [-4.6%, -1.6%] (179) | 42 |

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
