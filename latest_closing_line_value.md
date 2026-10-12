# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-12T13:38:53+00:00
- Opinions considered: **41691**; matched to a closing price: **39060**; no closing price found: **2631**.
- Within that count, priced before face-off but no close near face-off: **2538** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **83** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1613** opinion(s), 47 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 39060 | 12541 | 11910 | 46.2% [45.2%, 47.2%] | +0.49% [+0.24%, +0.75%] | -4.4% [-4.6%, -4.2%] (26107) | 82 |

2631 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 1880 | 972 | 372 | 64.5% [59.5%, 69.1%] | +4.20% [+2.10%, +6.30%] | +0.4% [-1.8%, +2.6%] (1681) | 81 |

84 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 4504 | 1410 | 1401 | 45.4% [42.8%, 48.2%] | -0.24% [-0.87%, +0.39%] | -4.5% [-4.8%, -4.1%] (2728) | 76 |
| `assists` | bets | 203 | 101 | 52 | 66.9% [54.6%, 77.2%] | +1.97% [+1.04%, +2.89%] | -1.0% [-2.0%, -0.1%] (201) | 70 |
| `blocked_shots` | opinions | 36 | 10 | 8 | 35.7% [16.0%, 61.8%] | -1.83% [-4.20%, +0.55%] | -8.4% [-10.6%, -6.3%] (36) | 13 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [27.1%, 100.0%] | +1.68% [-0.77%, +4.13%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 10020 | 2554 | 4392 | 45.4% [42.6%, 48.1%] | +1.11% [+0.43%, +1.78%] | -4.6% [-4.9%, -4.2%] (4787) | 76 |
| `goals` | bets | 78 | 44 | 20 | 75.9% [51.4%, 90.3%] | +2.48% [+0.57%, +4.40%] | -2.1% [-3.7%, -0.6%] (75) | 40 |
| `moneyline` | opinions | 154 | 69 | 17 | 50.4% [38.6%, 62.1%] | -0.40% [-1.24%, +0.43%] | -2.4% [-3.2%, -1.6%] (154) | 77 |
| `moneyline` | bets | 29 | 15 | 3 | 57.7% [31.8%, 80.0%] | +0.52% [-1.59%, +2.64%] | -1.4% [-3.6%, +0.7%] (29) | 29 |
| `points` | opinions | 8368 | 2624 | 2205 | 42.6% [40.0%, 45.2%] | +0.06% [-0.92%, +1.05%] | -4.7% [-5.6%, -3.8%] (6441) | 76 |
| `points` | bets | 416 | 214 | 85 | 64.7% [54.2%, 73.8%] | +10.39% [-1.44%, +22.22%] | +7.3% [-4.4%, +18.9%] (416) | 75 |
| `puck_line` | opinions | 1538 | 512 | 508 | 49.7% [45.3%, 54.1%] | +0.66% [-0.09%, +1.41%] | -2.4% [-3.1%, -1.6%] (1402) | 82 |
| `puck_line` | bets | 93 | 43 | 22 | 60.6% [39.2%, 78.5%] | +1.33% [-1.54%, +4.21%] | -2.0% [-4.6%, +0.6%] (93) | 48 |
| `regulation_3_way` | opinions | 228 | 81 | 50 | 45.5% [35.3%, 56.1%] | -0.39% [-1.10%, +0.31%] | — | 76 |
| `regulation_3_way` | bets | 62 | 29 | 12 | 58.0% [38.5%, 75.3%] | +0.28% [-1.36%, +1.91%] | — | 62 |
| `shots_on_goal` | opinions | 8604 | 3280 | 1829 | 48.4% [44.9%, 51.9%] | +0.92% [+0.04%, +1.79%] | -4.5% [-4.8%, -4.2%] (5102) | 76 |
| `shots_on_goal` | bets | 623 | 335 | 102 | 64.3% [56.1%, 71.8%] | +3.41% [+1.90%, +4.92%] | -1.0% [-2.1%, +0.1%] (500) | 75 |
| `team_total` | opinions | 3574 | 1275 | 958 | 48.7% [46.0%, 51.5%] | +0.06% [-0.22%, +0.35%] | -4.9% [-5.2%, -4.6%] (3529) | 76 |
| `team_total` | bets | 218 | 109 | 45 | 63.0% [40.2%, 81.2%] | +1.32% [-1.04%, +3.68%] | -4.0% [-6.3%, -1.7%] (218) | 44 |
| `total_goals` | opinions | 1938 | 697 | 527 | 49.4% [45.6%, 53.2%] | +0.22% [-0.21%, +0.64%] | -3.4% [-3.7%, -3.0%] (1898) | 82 |
| `total_goals` | bets | 140 | 68 | 28 | 60.7% [41.0%, 77.5%] | +1.08% [-0.89%, +3.05%] | -2.9% [-4.6%, -1.2%] (140) | 32 |

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
- **Bets**: A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), nothing in a hard-gated market (`goalie_saves`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
