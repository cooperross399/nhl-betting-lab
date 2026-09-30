# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-09-30T13:40:23+00:00
- Opinions considered: **2799**; matched to a closing price: **2735**; no closing price found: **64**.
- Within that count, priced before face-off but no close near face-off: **12** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — it does not ask for it, or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **42** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1534** opinion(s), 71 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 2735 | 890 | 997 | 51.2% [48.8%, 53.6%] | +1.36% [+0.58%, +2.15%] | -4.2% [-4.5%, -4.0%] (1770) | 5 |

64 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 143 | 79 | 24 | 66.4% [51.4%, 78.6%] | +2.22% [-0.59%, +5.02%] | -2.6% [-5.0%, -0.2%] (122) | 5 |

2 bet(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 9 markets that
share the table (Bonferroni: z = 2.773 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 9 markets] | Mean CLV% [95% family-wise, 9 markets] | EV at close [95% family-wise, 9 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 327 | 105 | 105 | 47.3% [38.3%, 56.5%] | +0.37% [-1.00%, +1.74%] | -4.7% [-5.7%, -3.7%] (202) | 5 |
| `assists` | bets | 12 | 7 | 3 | 77.8% [30.7%, 96.5%] | +3.25% [-0.78%, +7.28%] | -1.0% [-4.2%, +2.1%] (11) | 4 |
| `goalie_saves` | opinions | 71 | 14 | 11 | 23.3% [10.0%, 45.4%] | -11.34% [-20.73%, -1.94%] | -4.9% [-7.0%, -2.8%] (24) | 5 |
| `goalie_saves` | bets | 5 | 3 | 1 | 75.0% [17.8%, 97.7%] | +5.40% [-4.88%, +15.69%] | -3.6% [-7.5%, +0.3%] (4) | 3 |
| `goals` | opinions | 661 | 165 | 345 | 52.2% [44.5%, 59.9%] | +1.47% [-0.23%, +3.18%] | -4.6% [-5.3%, -3.9%] (313) | 5 |
| `goals` | bets | 8 | 5 | 1 | 71.4% [24.9%, 95.0%] | +0.05% [-4.73%, +4.83%] | -2.9% [-5.7%, -0.1%] (7) | 4 |
| `points` | opinions | 610 | 190 | 220 | 48.7% [41.8%, 55.7%] | +0.47% [-1.97%, +2.92%] | -4.3% [-5.2%, -3.5%] (438) | 5 |
| `points` | bets | 30 | 16 | 6 | 66.7% [39.1%, 86.2%] | +0.74% [-2.53%, +4.01%] | -3.0% [-6.1%, +0.0%] (30) | 5 |
| `puck_line` | opinions | 101 | 33 | 44 | 57.9% [39.9%, 74.0%] | +0.54% [-1.43%, +2.50%] | -2.9% [-5.2%, -0.6%] (92) | 5 |
| `puck_line` | bets | 7 | 6 | 0 | 85.7% [35.5%, 98.5%] | +3.32% [-2.92%, +9.56%] | -1.4% [-7.5%, +4.6%] (7) | 3 |
| `regulation_3_way` | opinions | 15 | 6 | 2 | 46.2% [17.2%, 78.0%] | -0.13% [-1.86%, +1.59%] | — | 5 |
| `regulation_3_way` | bets | 5 | 2 | 0 | 40.0% [7.4%, 84.7%] | -0.52% [-3.58%, +2.53%] | — | 5 |
| `shots_on_goal` | opinions | 588 | 261 | 125 | 56.4% [45.5%, 66.7%] | +5.00% [+2.07%, +7.93%] | -3.8% [-5.5%, -2.1%] (345) | 5 |
| `shots_on_goal` | bets | 49 | 24 | 5 | 54.5% [29.7%, 77.4%] | +2.56% [-3.35%, +8.47%] | -2.8% [-8.2%, +2.7%] (36) | 5 |
| `team_total` | opinions | 240 | 69 | 106 | 51.5% [39.8%, 63.1%] | +0.22% [-1.02%, +1.47%] | -5.0% [-6.0%, -4.0%] (237) | 5 |
| `team_total` | bets | 20 | 10 | 7 | 76.9% [17.3%, 98.2%] | +2.03% [-4.60%, +8.66%] | -3.7% [-9.2%, +1.8%] (20) | 3 |
| `total_goals` | opinions | 122 | 47 | 39 | 56.6% [41.6%, 70.5%] | +0.89% [-1.11%, +2.90%] | -3.0% [-4.8%, -1.2%] (119) | 5 |
| `total_goals` | bets | 7 | 6 | 1 | 100.0% [11.5%, 100.0%] | +5.94% n too small | +1.2% n too small (7) | 1 |

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
