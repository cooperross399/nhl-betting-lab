# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-27T14:55:23+00:00
- Opinions considered: **216467**; matched to a closing price: **207277**; no closing price found: **9190**.
- Within that count, priced before face-off but no close near face-off: **8871** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **67** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `goalie_saves` (42), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **252** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **8391** opinion(s), 366 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 207277 | 64796 | 65602 | 45.7% [45.2%, 46.3%] | +0.38% [+0.22%, +0.53%] | -4.4% [-4.5%, -4.4%] (133544) | 387 |

9190 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 9508 | 4630 | 2174 | 63.1% [61.3%, 65.0%] | +2.34% [+1.83%, +2.85%] | -1.6% [-2.1%, -1.1%] (8230) | 386 |

405 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 797 | 464 | 158 | 72.6% [67.9%, 76.9%] | +3.56% [+2.13%, +4.98%] | -0.7% [-1.3%, -0.1%] (737) | 298 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 22727 | 7374 | 6692 | 46.0% [44.6%, 47.4%] | -0.42% [-0.80%, -0.03%] | -4.1% [-4.3%, -3.9%] (14245) | 381 |
| `assists` | bets | 1064 | 456 | 294 | 59.2% [53.7%, 64.5%] | +0.92% [+0.57%, +1.26%] | -1.9% [-2.3%, -1.6%] (1059) | 362 |
| `assists` | best-bet bar | 67 | 23 | 21 | 50.0% [29.8%, 70.2%] | +0.68% [-0.58%, +1.94%] | -1.8% [-3.2%, -0.3%] (67) | 62 |
| `blocked_shots` | opinions | 1530 | 244 | 938 | 41.2% [35.0%, 47.7%] | -0.29% [-0.57%, -0.01%] | -7.8% [-8.2%, -7.5%] (773) | 194 |
| `blocked_shots` | bets | 147 | 34 | 92 | 61.8% [42.4%, 78.1%] | +0.83% [-0.19%, +1.86%] | -6.7% [-7.5%, -6.0%] (138) | 106 |
| `blocked_shots` | best-bet bar | 28 | 12 | 14 | 85.7% [47.5%, 97.6%] | +1.80% [+0.14%, +3.46%] | -5.5% [-7.0%, -4.1%] (28) | 26 |
| `goalie_saves` | opinions | 7387 | 2019 | 3278 | 49.1% [43.7%, 54.6%] | -0.20% [-0.90%, +0.49%] | -3.3% [-3.8%, -2.9%] (1415) | 237 |
| `goalie_saves` | bets | 408 | 241 | 114 | 82.0% [68.8%, 90.3%] | +5.67% [-0.16%, +11.50%] | +0.3% [-2.8%, +3.3%] (141) | 96 |
| `goalie_saves` | best-bet bar | 45 | 38 | 5 | 95.0% [74.8%, 99.2%] | +17.50% [-12.86%, +47.86%] | +8.8% [-10.1%, +27.6%] (20) | 15 |
| `goals` | opinions | 50656 | 13396 | 22435 | 47.5% [46.1%, 48.8%] | +0.89% [+0.57%, +1.22%] | -3.9% [-4.0%, -3.7%] (24186) | 381 |
| `goals` | bets | 325 | 182 | 77 | 73.4% [63.7%, 81.2%] | +2.73% [+1.65%, +3.81%] | -1.8% [-2.8%, -0.8%] (309) | 193 |
| `goals` | best-bet bar | 9 | 5 | 1 | 62.5% [21.1%, 91.2%] | -0.13% [-8.08%, +7.82%] | -4.6% [-11.5%, +2.3%] (9) | 9 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 764 | 329 | 97 | 49.3% [43.8%, 54.8%] | -0.28% [-0.65%, +0.08%] | -2.1% [-2.5%, -1.8%] (764) | 382 |
| `moneyline` | bets | 108 | 54 | 12 | 56.2% [41.8%, 69.7%] | +0.46% [-0.67%, +1.59%] | -1.4% [-2.5%, -0.3%] (108) | 108 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 43878 | 13639 | 11186 | 41.7% [40.7%, 42.8%] | +0.68% [-0.04%, +1.40%] | -5.2% [-5.4%, -5.0%] (33453) | 381 |
| `points` | bets | 2011 | 911 | 467 | 59.0% [54.5%, 63.4%] | +2.72% [-0.05%, +5.49%] | -0.2% [-2.9%, +2.6%] (2010) | 377 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 6450 | 2518 | 1624 | 52.2% [50.1%, 54.2%] | +0.46% [+0.17%, +0.75%] | -2.9% [-3.2%, -2.6%] (5673) | 387 |
| `puck_line` | bets | 389 | 202 | 82 | 65.8% [55.5%, 74.8%] | +0.86% [+0.00%, +1.72%] | -2.3% [-3.1%, -1.5%] (389) | 212 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 1143 | 429 | 268 | 49.0% [44.2%, 53.9%] | -0.16% [-0.49%, +0.17%] | — | 381 |
| `regulation_3_way` | bets | 247 | 113 | 53 | 58.2% [48.0%, 67.9%] | +0.42% [-0.49%, +1.32%] | — | 247 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 45533 | 15268 | 11401 | 44.7% [43.2%, 46.3%] | +0.19% [-0.14%, +0.51%] | -4.7% [-4.8%, -4.6%] (26239) | 381 |
| `shots_on_goal` | bets | 3306 | 1745 | 657 | 65.9% [62.4%, 69.2%] | +3.25% [+2.58%, +3.93%] | -1.0% [-1.5%, -0.6%] (2573) | 380 |
| `shots_on_goal` | best-bet bar | 427 | 276 | 65 | 76.2% [68.8%, 82.4%] | +3.91% [+2.88%, +4.93%] | +1.1% [+0.2%, +2.1%] (423) | 241 |
| `team_total` | opinions | 17253 | 6160 | 4741 | 49.2% [48.0%, 50.5%] | +0.10% [-0.01%, +0.22%] | -4.8% [-4.9%, -4.7%] (17046) | 381 |
| `team_total` | bets | 746 | 342 | 165 | 58.9% [47.0%, 69.7%] | +0.70% [-0.27%, +1.68%] | -4.4% [-5.3%, -3.5%] (746) | 174 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 9582 | 3286 | 2836 | 48.7% [47.0%, 50.5%] | +0.13% [-0.05%, +0.31%] | -3.4% [-3.6%, -3.3%] (9376) | 387 |
| `total_goals` | bets | 637 | 293 | 127 | 57.5% [45.6%, 68.5%] | +0.91% [-0.07%, +1.89%] | -3.0% [-3.9%, -2.1%] (637) | 131 |
| `total_goals` | best-bet bar | 48 | 13 | 16 | 40.6% [13.3%, 75.4%] | -0.50% [-2.86%, +1.87%] | -4.5% [-6.5%, -2.5%] (48) | 15 |

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
- **Bets**: A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 10% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.
- **Best-bet bar**: The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
