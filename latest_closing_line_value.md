# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-30T22:47:02+00:00
- Opinions considered: **111817**; matched to a closing price: **106609**; no closing price found: **5208**.
- Within that count, priced before face-off but no close near face-off: **5021** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **177** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1081** opinion(s), 64 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 106609 | 34106 | 32068 | 45.8% [45.1%, 46.4%] | +0.15% [-0.03%, +0.32%] | -4.5% [-4.6%, -4.4%] (70460) | 207 |

5208 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 4816 | 2449 | 982 | 63.9% [61.3%, 66.4%] | +2.89% [+2.01%, +3.77%] | -1.1% [-2.0%, -0.2%] (4262) | 206 |

221 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 12078 | 3906 | 3412 | 45.1% [43.3%, 46.9%] | -0.78% [-1.44%, -0.13%] | -4.3% [-4.5%, -4.0%] (7526) | 201 |
| `assists` | bets | 547 | 261 | 131 | 62.7% [55.3%, 69.6%] | +1.40% [+0.89%, +1.92%] | -1.5% [-2.0%, -0.9%] (545) | 189 |
| `blocked_shots` | opinions | 452 | 91 | 229 | 40.8% [31.7%, 50.6%] | -0.47% [-1.07%, +0.12%] | -8.0% [-8.6%, -7.3%] (276) | 76 |
| `blocked_shots` | bets | 44 | 9 | 29 | 60.0% [24.9%, 87.1%] | +0.75% [-1.72%, +3.23%] | -6.7% [-7.9%, -5.6%] (42) | 34 |
| `goalie_saves` | opinions | 1710 | 463 | 708 | 46.2% [37.0%, 55.6%] | -0.50% [-1.85%, +0.84%] | -3.6% [-4.2%, -3.0%] (375) | 67 |
| `goalie_saves` | bets | 89 | 48 | 30 | 81.4% [57.7%, 93.3%] | +4.59% [-1.90%, +11.08%] | -1.7% [-3.6%, +0.2%] (46) | 32 |
| `goals` | opinions | 26582 | 7074 | 11516 | 47.0% [45.1%, 48.9%] | +1.16% [+0.69%, +1.63%] | -4.2% [-4.4%, -4.0%] (12698) | 201 |
| `goals` | bets | 162 | 93 | 37 | 74.4% [59.8%, 85.0%] | +2.49% [+1.15%, +3.83%] | -2.3% [-3.4%, -1.1%] (155) | 95 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 404 | 171 | 45 | 47.6% [40.2%, 55.2%] | -0.25% [-0.78%, +0.28%] | -2.2% [-2.7%, -1.7%] (404) | 202 |
| `moneyline` | bets | 67 | 33 | 9 | 56.9% [38.6%, 73.5%] | +0.74% [-0.70%, +2.17%] | -1.2% [-2.5%, +0.2%] (67) | 67 |
| `points` | opinions | 22949 | 7158 | 5675 | 41.4% [40.0%, 42.9%] | -0.90% [-1.54%, -0.26%] | -5.0% [-5.4%, -4.6%] (17431) | 201 |
| `points` | bets | 1067 | 511 | 227 | 60.8% [54.6%, 66.7%] | +4.59% [-0.49%, +9.66%] | +1.8% [-3.2%, +6.7%] (1067) | 197 |
| `puck_line` | opinions | 3672 | 1385 | 981 | 51.5% [48.7%, 54.2%] | +0.46% [+0.03%, +0.88%] | -2.8% [-3.3%, -2.4%] (3292) | 207 |
| `puck_line` | bets | 229 | 131 | 41 | 69.7% [57.1%, 79.9%] | +1.15% [-0.13%, +2.43%] | -2.2% [-3.4%, -1.1%] (229) | 120 |
| `regulation_3_way` | opinions | 603 | 232 | 131 | 49.2% [42.6%, 55.7%] | -0.06% [-0.50%, +0.38%] | — | 201 |
| `regulation_3_way` | bets | 136 | 67 | 23 | 59.3% [45.9%, 71.5%] | +0.67% [-0.44%, +1.78%] | — | 136 |
| `shots_on_goal` | opinions | 23188 | 8318 | 5270 | 46.4% [44.4%, 48.5%] | +0.58% [+0.13%, +1.03%] | -4.6% [-4.8%, -4.5%] (13708) | 201 |
| `shots_on_goal` | bets | 1644 | 901 | 285 | 66.3% [61.4%, 70.9%] | +3.80% [+2.78%, +4.81%] | -0.7% [-1.3%, -0.0%] (1280) | 200 |
| `team_total` | opinions | 9483 | 3405 | 2519 | 48.9% [47.2%, 50.6%] | +0.06% [-0.10%, +0.23%] | -4.9% [-5.1%, -4.8%] (9372) | 201 |
| `team_total` | bets | 425 | 213 | 90 | 63.6% [47.9%, 76.8%] | +1.14% [-0.25%, +2.52%] | -4.0% [-5.3%, -2.7%] (425) | 98 |
| `total_goals` | opinions | 5114 | 1769 | 1476 | 48.6% [46.3%, 51.0%] | +0.05% [-0.18%, +0.28%] | -3.5% [-3.7%, -3.3%] (5004) | 207 |
| `total_goals` | bets | 286 | 125 | 46 | 52.1% [36.8%, 67.0%] | +0.61% [-0.86%, +2.08%] | -3.3% [-4.6%, -2.0%] (286) | 65 |

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
