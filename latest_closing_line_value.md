# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-05T13:37:15+00:00
- Opinions considered: **17741**; matched to a closing price: **16869**; no closing price found: **872**.
- Within that count, priced before face-off but no close near face-off: **807** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **55** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2067** opinion(s), 176 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 16869 | 5628 | 5075 | 47.7% [46.4%, 49.0%] | +1.09% [+0.69%, +1.48%] | -4.6% [-4.8%, -4.4%] (11118) | 38 |

872 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 817 | 427 | 135 | 62.6% [54.8%, 69.8%] | +2.29% [+1.22%, +3.35%] | -2.0% [-2.9%, -1.2%] (710) | 37 |

32 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 2010 | 683 | 585 | 47.9% [44.2%, 51.7%] | +0.36% [-0.58%, +1.31%] | -4.7% [-5.3%, -4.2%] (1154) | 33 |
| `assists` | bets | 98 | 61 | 18 | 76.2% [60.8%, 86.9%] | +2.82% [+1.62%, +4.02%] | -0.2% [-1.6%, +1.2%] (97) | 31 |
| `blocked_shots` | opinions | 16 | 5 | 4 | 41.7% [13.6%, 76.4%] | -0.83% [-3.91%, +2.25%] | -8.3% [-11.0%, -5.6%] (16) | 5 |
| `blocked_shots` | bets | 3 | 2 | 1 | 100.0% [19.9%, 100.0%] | +2.19% [-1.70%, +6.07%] | -5.4% [-7.7%, -3.1%] (3) | 2 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 4292 | 1092 | 1892 | 45.5% [41.2%, 49.8%] | +1.25% [+0.00%, +2.49%] | -4.5% [-5.1%, -3.9%] (2046) | 33 |
| `goals` | bets | 40 | 21 | 7 | 63.6% [32.8%, 86.2%] | +1.89% [-1.30%, +5.09%] | -2.0% [-4.7%, +0.7%] (38) | 21 |
| `moneyline` | opinions | 66 | 29 | 10 | 51.8% [33.8%, 69.3%] | -0.45% [-1.70%, +0.81%] | -2.5% [-3.7%, -1.3%] (66) | 33 |
| `moneyline` | bets | 10 | 4 | 1 | 44.4% [12.8%, 81.3%] | -0.64% [-4.48%, +3.20%] | -3.0% [-6.8%, +0.9%] (10) | 10 |
| `points` | opinions | 3605 | 1137 | 952 | 42.9% [39.0%, 46.8%] | +0.68% [-0.95%, +2.32%] | -5.4% [-5.8%, -4.9%] (2753) | 33 |
| `points` | bets | 164 | 82 | 26 | 59.4% [46.7%, 71.0%] | +0.92% [-0.13%, +1.97%] | -2.0% [-3.3%, -0.8%] (164) | 32 |
| `puck_line` | opinions | 685 | 230 | 242 | 51.9% [45.2%, 58.6%] | +0.42% [-0.29%, +1.13%] | -2.7% [-3.5%, -2.0%] (626) | 38 |
| `puck_line` | bets | 41 | 16 | 11 | 53.3% [26.3%, 78.5%] | +0.58% [-1.65%, +2.80%] | -3.0% [-4.9%, -1.2%] (41) | 21 |
| `regulation_3_way` | opinions | 99 | 33 | 18 | 40.7% [26.8%, 56.4%] | -0.55% [-1.58%, +0.48%] | — | 33 |
| `regulation_3_way` | bets | 27 | 10 | 4 | 43.5% [19.9%, 70.5%] | -0.15% [-2.40%, +2.10%] | — | 27 |
| `shots_on_goal` | opinions | 3585 | 1541 | 678 | 53.0% [48.7%, 57.3%] | +2.79% [+1.38%, +4.21%] | -4.2% [-4.6%, -3.8%] (2053) | 33 |
| `shots_on_goal` | bets | 277 | 155 | 40 | 65.4% [52.2%, 76.6%] | +3.67% [+0.99%, +6.34%] | -1.0% [-3.0%, +1.0%] (209) | 32 |
| `team_total` | opinions | 1557 | 535 | 449 | 48.3% [44.1%, 52.5%] | -0.00% [-0.41%, +0.41%] | -5.1% [-5.4%, -4.7%] (1534) | 33 |
| `team_total` | bets | 95 | 43 | 14 | 53.1% [24.2%, 80.0%] | +0.40% [-3.27%, +4.07%] | -5.1% [-8.5%, -1.7%] (95) | 19 |
| `total_goals` | opinions | 858 | 314 | 230 | 50.0% [44.4%, 55.6%] | +0.12% [-0.58%, +0.81%] | -3.4% [-4.0%, -2.9%] (840) | 38 |
| `total_goals` | bets | 49 | 22 | 12 | 59.5% [27.6%, 84.9%] | +0.81% [-2.23%, +3.85%] | -3.0% [-5.4%, -0.6%] (49) | 12 |

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
