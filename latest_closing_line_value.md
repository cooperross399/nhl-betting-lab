# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-01T13:40:59+00:00
- Opinions considered: **4333**; matched to a closing price: **4244**; no closing price found: **89**.
- Within that count, priced before face-off but no close near face-off: **32** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **47** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **4449** opinion(s), 256 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 4244 | 1414 | 1435 | 50.3% [47.8%, 52.8%] | +1.06% [+0.45%, +1.67%] | -4.4% [-4.6%, -4.1%] (2775) | 8 |

89 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 214 | 118 | 37 | 66.7% [55.7%, 76.1%] | +2.17% [+0.36%, +3.98%] | -2.6% [-4.1%, -1.0%] (182) | 8 |

2 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 504 | 174 | 161 | 50.7% [43.1%, 58.3%] | +0.98% [-0.40%, +2.36%] | -4.5% [-5.4%, -3.6%] (302) | 8 |
| `assists` | bets | 17 | 9 | 5 | 75.0% [34.9%, 94.4%] | +2.54% [-0.80%, +5.89%] | -1.4% [-3.7%, +0.9%] (16) | 7 |
| `blocked_shots` | opinions | 4 | 2 | 0 | 50.0% [2.8%, 97.2%] | +0.32% n too small | -8.3% n too small (4) | 1 |
| `blocked_shots` | bets | 1 | 1 | 0 | 100.0% [11.0%, 100.0%] | +1.85% n too small | -6.6% n too small (1) | 1 |
| `goalie_saves` | opinions | 71 | 14 | 11 | 23.3% [9.8%, 45.9%] | -11.34% [-20.95%, -1.72%] | -4.9% [-7.0%, -2.8%] (24) | 5 |
| `goalie_saves` | bets | 5 | 3 | 1 | 75.0% [17.2%, 97.7%] | +5.40% [-5.12%, +15.93%] | -3.6% [-7.6%, +0.4%] (4) | 3 |
| `goals` | opinions | 1044 | 266 | 497 | 48.6% [42.1%, 55.2%] | +0.62% [-0.98%, +2.21%] | -4.5% [-5.2%, -3.8%] (497) | 8 |
| `goals` | bets | 11 | 7 | 2 | 77.8% [33.2%, 96.1%] | +0.72% [-2.71%, +4.15%] | -2.7% [-5.0%, -0.4%] (10) | 6 |
| `moneyline` | opinions | 6 | 3 | 0 | 50.0% [12.2%, 87.8%] | -0.48% [-5.28%, +4.32%] | -2.5% [-7.3%, +2.2%] (6) | 3 |
| `moneyline` | bets | 1 | 0 | 0 | 0.0% [0.0%, 89.0%] | -1.77% n too small | -4.2% n too small (1) | 1 |
| `points` | opinions | 919 | 302 | 296 | 48.5% [41.2%, 55.8%] | +0.61% [-1.34%, +2.56%] | -4.5% [-5.3%, -3.8%] (676) | 8 |
| `points` | bets | 38 | 20 | 8 | 66.7% [41.2%, 85.1%] | +0.92% [-1.70%, +3.55%] | -2.9% [-5.3%, -0.5%] (38) | 8 |
| `puck_line` | opinions | 161 | 51 | 66 | 53.7% [39.5%, 67.3%] | +0.33% [-0.94%, +1.60%] | -3.0% [-4.5%, -1.5%] (146) | 8 |
| `puck_line` | bets | 11 | 7 | 2 | 77.8% [33.2%, 96.1%] | +2.08% [-2.15%, +6.30%] | -2.1% [-6.1%, +1.9%] (11) | 5 |
| `regulation_3_way` | opinions | 24 | 10 | 3 | 47.6% [22.0%, 74.6%] | -0.08% [-1.66%, +1.50%] | — | 8 |
| `regulation_3_way` | bets | 8 | 3 | 0 | 37.5% [8.9%, 78.6%] | -0.13% [-2.84%, +2.57%] | — | 8 |
| `shots_on_goal` | opinions | 929 | 405 | 195 | 55.2% [47.3%, 62.8%] | +3.75% [+1.09%, +6.41%] | -4.1% [-5.1%, -3.0%] (546) | 8 |
| `shots_on_goal` | bets | 74 | 41 | 8 | 62.1% [38.6%, 81.1%] | +3.22% [-0.82%, +7.26%] | -2.1% [-6.1%, +1.9%] (53) | 8 |
| `team_total` | opinions | 381 | 115 | 145 | 48.7% [39.7%, 57.8%] | +0.02% [-0.84%, +0.88%] | -5.1% [-5.8%, -4.4%] (377) | 8 |
| `team_total` | bets | 31 | 16 | 9 | 72.7% [28.0%, 94.8%] | +1.60% [-2.49%, +5.70%] | -3.8% [-7.2%, -0.5%] (31) | 6 |
| `total_goals` | opinions | 201 | 72 | 61 | 51.4% [39.0%, 63.7%] | +0.24% [-1.31%, +1.80%] | -3.5% [-4.8%, -2.2%] (197) | 8 |
| `total_goals` | bets | 17 | 11 | 2 | 73.3% [33.6%, 93.7%] | +2.39% [-3.85%, +8.63%] | -1.8% [-7.1%, +3.5%] (17) | 3 |

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
- **Bets**: A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`) and nothing in a hard-gated market (`goalie_saves`), whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
