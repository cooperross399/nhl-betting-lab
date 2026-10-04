# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-04T13:41:52+00:00
- Opinions considered: **15151**; matched to a closing price: **14812**; no closing price found: **339**.
- Within that count, priced before face-off but no close near face-off: **280** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **49** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2590** opinion(s), 137 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 14812 | 4959 | 4469 | 47.9% [46.5%, 49.4%] | +1.20% [+0.77%, +1.63%] | -4.6% [-4.8%, -4.3%] (9749) | 34 |

339 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 708 | 396 | 113 | 66.6% [59.2%, 73.2%] | +2.58% [+1.46%, +3.69%] | -1.9% [-2.7%, -1.1%] (616) | 33 |

4 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 1760 | 592 | 521 | 47.8% [43.6%, 52.0%] | +0.29% [-0.73%, +1.30%] | -4.8% [-5.4%, -4.2%] (1012) | 29 |
| `assists` | bets | 85 | 54 | 15 | 77.1% [60.6%, 88.1%] | +2.64% [+1.46%, +3.83%] | -0.6% [-1.9%, +0.7%] (84) | 27 |
| `blocked_shots` | opinions | 14 | 4 | 4 | 40.0% [11.4%, 77.5%] | -0.89% [-3.99%, +2.20%] | -8.3% [-11.0%, -5.7%] (14) | 4 |
| `blocked_shots` | bets | 3 | 2 | 1 | 100.0% [19.9%, 100.0%] | +2.19% [-1.70%, +6.07%] | -5.4% [-7.7%, -3.1%] (3) | 2 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 3772 | 946 | 1663 | 44.9% [40.3%, 49.5%] | +1.18% [-0.21%, +2.56%] | -4.5% [-5.2%, -3.9%] (1795) | 29 |
| `goals` | bets | 37 | 18 | 7 | 60.0% [28.9%, 84.7%] | +1.32% [-1.92%, +4.55%] | -2.4% [-5.2%, +0.4%] (35) | 19 |
| `moneyline` | opinions | 58 | 26 | 9 | 53.1% [33.9%, 71.4%] | -0.40% [-1.68%, +0.88%] | -2.4% [-3.7%, -1.2%] (58) | 29 |
| `moneyline` | bets | 9 | 4 | 1 | 50.0% [14.6%, 85.4%] | +0.40% [-2.35%, +3.15%] | -1.9% [-4.8%, +0.9%] (9) | 9 |
| `points` | opinions | 3143 | 1002 | 848 | 43.7% [39.5%, 47.9%] | +0.99% [-0.83%, +2.81%] | -5.3% [-5.8%, -4.8%] (2393) | 29 |
| `points` | bets | 143 | 77 | 21 | 63.1% [50.1%, 74.4%] | +0.95% [-0.21%, +2.12%] | -2.2% [-3.5%, -0.9%] (143) | 28 |
| `puck_line` | opinions | 604 | 207 | 217 | 53.5% [46.3%, 60.5%] | +0.49% [-0.27%, +1.26%] | -2.7% [-3.5%, -1.9%] (553) | 34 |
| `puck_line` | bets | 36 | 16 | 11 | 64.0% [36.1%, 84.9%] | +1.14% [-0.89%, +3.18%] | -2.6% [-4.5%, -0.7%] (36) | 18 |
| `regulation_3_way` | opinions | 87 | 29 | 16 | 40.8% [26.1%, 57.5%] | -0.49% [-1.53%, +0.54%] | — | 29 |
| `regulation_3_way` | bets | 24 | 10 | 3 | 47.6% [22.0%, 74.6%] | +0.42% [-1.63%, +2.47%] | — | 24 |
| `shots_on_goal` | opinions | 3149 | 1384 | 568 | 53.6% [49.0%, 58.2%] | +3.17% [+1.66%, +4.67%] | -4.2% [-4.7%, -3.7%] (1801) | 29 |
| `shots_on_goal` | bets | 234 | 140 | 30 | 68.6% [54.3%, 80.1%] | +4.02% [+0.92%, +7.11%] | -0.7% [-3.0%, +1.6%] (178) | 28 |
| `team_total` | opinions | 1369 | 465 | 404 | 48.2% [43.7%, 52.7%] | +0.01% [-0.43%, +0.46%] | -5.0% [-5.4%, -4.6%] (1350) | 29 |
| `team_total` | bets | 77 | 42 | 12 | 64.6% [36.3%, 85.4%] | +1.56% [-1.46%, +4.58%] | -4.0% [-6.8%, -1.2%] (77) | 16 |
| `total_goals` | opinions | 760 | 275 | 204 | 49.5% [43.5%, 55.4%] | +0.04% [-0.72%, +0.80%] | -3.5% [-4.1%, -2.8%] (743) | 34 |
| `total_goals` | bets | 47 | 22 | 11 | 61.1% [28.3%, 86.2%] | +0.85% [-2.32%, +4.03%] | -3.0% [-5.5%, -0.4%] (47) | 11 |

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
