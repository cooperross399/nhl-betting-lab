# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-05T14:56:11+00:00
- Opinions considered: **131511**; matched to a closing price: **124436**; no closing price found: **7075**.
- Within that count, priced before face-off but no close near face-off: **6859** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **206** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5951** opinion(s), 262 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 124436 | 39617 | 37552 | 45.6% [45.0%, 46.2%] | +0.11% [-0.05%, +0.27%] | -4.5% [-4.6%, -4.4%] (82027) | 240 |

7075 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 5660 | 2827 | 1178 | 63.1% [60.7%, 65.4%] | +2.62% [+1.86%, +3.38%] | -1.3% [-2.1%, -0.5%] (4991) | 239 |

314 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 14046 | 4551 | 3964 | 45.1% [43.4%, 46.9%] | -0.67% [-1.24%, -0.09%] | -4.2% [-4.4%, -4.0%] (8791) | 234 |
| `assists` | bets | 633 | 296 | 155 | 61.9% [54.9%, 68.4%] | +1.31% [+0.84%, +1.78%] | -1.6% [-2.0%, -1.1%] (631) | 220 |
| `blocked_shots` | opinions | 639 | 122 | 359 | 43.6% [35.4%, 52.1%] | -0.32% [-0.76%, +0.13%] | -7.9% [-8.5%, -7.4%] (368) | 99 |
| `blocked_shots` | bets | 69 | 14 | 46 | 60.9% [31.3%, 84.1%] | +0.82% [-1.03%, +2.66%] | -6.8% [-7.9%, -5.7%] (67) | 51 |
| `goalie_saves` | opinions | 2436 | 670 | 1026 | 47.5% [39.8%, 55.4%] | -0.50% [-1.60%, +0.61%] | -3.5% [-4.0%, -3.0%] (527) | 94 |
| `goalie_saves` | bets | 123 | 69 | 37 | 80.2% [59.1%, 91.9%] | +3.75% [-1.18%, +8.68%] | -1.6% [-3.2%, +0.0%] (62) | 43 |
| `goals` | opinions | 30957 | 8258 | 13341 | 46.9% [45.2%, 48.6%] | +1.09% [+0.67%, +1.51%] | -4.2% [-4.4%, -4.1%] (14787) | 234 |
| `goals` | bets | 192 | 107 | 42 | 71.3% [58.2%, 81.7%] | +2.35% [+1.11%, +3.59%] | -2.3% [-3.4%, -1.2%] (183) | 113 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 470 | 198 | 52 | 47.4% [40.5%, 54.3%] | -0.26% [-0.76%, +0.24%] | -2.2% [-2.7%, -1.7%] (470) | 235 |
| `moneyline` | bets | 73 | 35 | 9 | 54.7% [37.4%, 70.9%] | +0.73% [-0.73%, +2.19%] | -1.2% [-2.6%, +0.3%] (73) | 73 |
| `points` | opinions | 26788 | 8263 | 6689 | 41.1% [39.8%, 42.4%] | -0.85% [-1.41%, -0.30%] | -5.0% [-5.4%, -4.7%] (20406) | 234 |
| `points` | bets | 1234 | 582 | 270 | 60.4% [54.7%, 65.8%] | +4.04% [-0.38%, +8.46%] | +1.2% [-3.1%, +5.6%] (1234) | 230 |
| `puck_line` | opinions | 4190 | 1606 | 1092 | 51.8% [49.3%, 54.4%] | +0.43% [+0.04%, +0.83%] | -2.9% [-3.3%, -2.5%] (3747) | 240 |
| `puck_line` | bets | 251 | 140 | 47 | 68.6% [56.5%, 78.6%] | +1.11% [-0.07%, +2.29%] | -2.3% [-3.3%, -1.2%] (251) | 133 |
| `regulation_3_way` | opinions | 702 | 275 | 151 | 49.9% [43.9%, 56.0%] | -0.05% [-0.47%, +0.37%] | — | 234 |
| `regulation_3_way` | bets | 160 | 78 | 29 | 59.5% [47.0%, 70.9%] | +0.67% [-0.39%, +1.73%] | — | 160 |
| `shots_on_goal` | opinions | 27092 | 9593 | 6178 | 45.9% [43.9%, 47.8%] | +0.42% [+0.01%, +0.83%] | -4.7% [-4.8%, -4.5%] (16062) | 234 |
| `shots_on_goal` | bets | 1958 | 1063 | 342 | 65.8% [61.2%, 70.0%] | +3.49% [+2.60%, +4.38%] | -0.8% [-1.4%, -0.2%] (1523) | 233 |
| `team_total` | opinions | 10815 | 3907 | 2851 | 49.1% [47.5%, 50.7%] | +0.05% [-0.10%, +0.20%] | -4.9% [-5.0%, -4.7%] (10687) | 234 |
| `team_total` | bets | 484 | 233 | 102 | 61.0% [46.4%, 73.8%] | +0.93% [-0.37%, +2.22%] | -4.2% [-5.4%, -2.9%] (484) | 113 |
| `total_goals` | opinions | 5927 | 2040 | 1743 | 48.8% [46.5%, 51.0%] | +0.04% [-0.18%, +0.25%] | -3.6% [-3.7%, -3.4%] (5808) | 240 |
| `total_goals` | bets | 363 | 153 | 65 | 51.3% [37.0%, 65.5%] | +0.51% [-0.73%, +1.75%] | -3.4% [-4.5%, -2.2%] (363) | 82 |

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
