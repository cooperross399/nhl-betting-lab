# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-20T20:37:49+00:00
- Opinions considered: **70286**; matched to a closing price: **66151**; no closing price found: **4135**.
- Within that count, priced before face-off but no close near face-off: **4004** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **121** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5822** opinion(s), 250 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 66151 | 20969 | 20019 | 45.5% [44.6%, 46.3%] | +0.25% [+0.04%, +0.46%] | -4.5% [-4.7%, -4.4%] (44397) | 134 |

4135 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2942 | 1488 | 607 | 63.7% [60.1%, 67.2%] | +3.40% [+2.01%, +4.79%] | -0.5% [-1.9%, +1.0%] (2621) | 133 |

147 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 7572 | 2326 | 2313 | 44.2% [42.1%, 46.4%] | -0.45% [-0.93%, +0.03%] | -4.5% [-4.8%, -4.2%] (4741) | 128 |
| `assists` | bets | 330 | 160 | 84 | 65.0% [55.0%, 73.9%] | +1.66% [+0.96%, +2.36%] | -1.3% [-2.0%, -0.5%] (328) | 117 |
| `blocked_shots` | opinions | 62 | 21 | 9 | 39.6% [23.0%, 59.0%] | -1.75% [-3.69%, +0.18%] | -8.4% [-10.1%, -6.7%] (62) | 25 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 100 | 30 | 16 | 35.7% [14.4%, 64.6%] | -5.34% [-19.66%, +8.98%] | -5.5% [-7.2%, -3.8%] (34) | 9 |
| `goalie_saves` | bets | 15 | 12 | 1 | 85.7% [39.2%, 98.2%] | +16.80% [-5.78%, +39.38%] | -5.1% [-10.8%, +0.5%] (6) | 5 |
| `goals` | opinions | 16944 | 4469 | 7248 | 46.1% [43.7%, 48.5%] | +1.07% [+0.45%, +1.69%] | -4.4% [-4.6%, -4.1%] (8046) | 128 |
| `goals` | bets | 113 | 61 | 29 | 72.6% [54.2%, 85.6%] | +2.27% [+0.67%, +3.87%] | -2.3% [-3.7%, -1.0%] (108) | 61 |
| `hits` | opinions | 108 | 42 | 24 | 50.0% [35.1%, 64.9%] | +0.12% [-0.82%, +1.05%] | -7.8% [-8.7%, -7.0%] (108) | 26 |
| `hits` | bets | 45 | 28 | 12 | 84.8% [60.3%, 95.4%] | +2.27% [+0.84%, +3.71%] | -5.9% [-7.2%, -4.6%] (45) | 25 |
| `moneyline` | opinions | 258 | 112 | 28 | 48.7% [39.5%, 58.0%] | -0.24% [-0.90%, +0.43%] | -2.2% [-2.9%, -1.6%] (258) | 129 |
| `moneyline` | bets | 48 | 23 | 6 | 54.8% [33.8%, 74.1%] | +0.45% [-1.25%, +2.16%] | -1.3% [-3.0%, +0.4%] (48) | 48 |
| `points` | opinions | 14310 | 4408 | 3644 | 41.3% [39.5%, 43.1%] | -0.39% [-1.05%, +0.27%] | -5.0% [-5.6%, -4.5%] (11034) | 128 |
| `points` | bets | 665 | 315 | 148 | 60.9% [52.3%, 68.9%] | +6.73% [-1.16%, +14.63%] | +3.8% [-4.0%, +11.5%] (665) | 125 |
| `puck_line` | opinions | 2518 | 882 | 762 | 50.2% [46.8%, 53.6%] | +0.43% [-0.10%, +0.97%] | -2.6% [-3.2%, -2.1%] (2286) | 134 |
| `puck_line` | bets | 151 | 76 | 32 | 63.9% [47.7%, 77.4%] | +1.10% [-0.78%, +2.97%] | -2.1% [-3.8%, -0.4%] (151) | 77 |
| `regulation_3_way` | opinions | 384 | 142 | 84 | 47.3% [39.3%, 55.6%] | -0.20% [-0.76%, +0.35%] | — | 128 |
| `regulation_3_way` | bets | 94 | 45 | 18 | 59.2% [42.9%, 73.7%] | +0.63% [-0.69%, +1.95%] | — | 94 |
| `shots_on_goal` | opinions | 14591 | 5266 | 3294 | 46.6% [43.9%, 49.4%] | +0.43% [-0.16%, +1.02%] | -4.6% [-4.9%, -4.4%] (8664) | 128 |
| `shots_on_goal` | bets | 992 | 539 | 175 | 66.0% [59.5%, 71.9%] | +3.66% [+2.34%, +4.97%] | -0.7% [-1.6%, +0.2%] (781) | 127 |
| `team_total` | opinions | 6034 | 2142 | 1650 | 48.9% [46.7%, 51.0%] | +0.08% [-0.13%, +0.29%] | -4.9% [-5.1%, -4.7%] (5960) | 128 |
| `team_total` | bets | 305 | 146 | 66 | 61.1% [42.1%, 77.2%] | +1.08% [-0.73%, +2.90%] | -4.1% [-5.8%, -2.3%] (305) | 68 |
| `total_goals` | opinions | 3270 | 1129 | 947 | 48.6% [45.6%, 51.6%] | +0.10% [-0.19%, +0.38%] | -3.5% [-3.7%, -3.3%] (3204) | 134 |
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
