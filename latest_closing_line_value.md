# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-24T13:44:48+00:00
- Opinions considered: **207892**; matched to a closing price: **198803**; no closing price found: **9089**.
- Within that count, priced before face-off but no close near face-off: **8772** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **67** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `goalie_saves` (42), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **250** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **536** opinion(s), 27 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 198803 | 62318 | 62562 | 45.7% [45.2%, 46.3%] | +0.40% [+0.24%, +0.56%] | -4.5% [-4.5%, -4.4%] (128337) | 372 |

9089 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 9143 | 4466 | 2047 | 62.9% [61.0%, 64.8%] | +2.38% [+1.85%, +2.91%] | -1.6% [-2.2%, -1.1%] (7926) | 371 |

403 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 778 | 451 | 155 | 72.4% [67.6%, 76.7%] | +3.58% [+2.12%, +5.04%] | -0.7% [-1.3%, -0.0%] (718) | 287 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 21836 | 7088 | 6428 | 46.0% [44.6%, 47.4%] | -0.43% [-0.83%, -0.03%] | -4.1% [-4.3%, -3.9%] (13694) | 366 |
| `assists` | bets | 1021 | 438 | 282 | 59.3% [53.6%, 64.7%] | +0.92% [+0.56%, +1.28%] | -1.9% [-2.3%, -1.5%] (1016) | 347 |
| `assists` | best-bet bar | 63 | 21 | 20 | 48.8% [28.3%, 69.8%] | +0.75% [-0.57%, +2.08%] | -1.7% [-3.2%, -0.2%] (63) | 58 |
| `blocked_shots` | opinions | 1466 | 231 | 897 | 40.6% [34.3%, 47.2%] | -0.31% [-0.61%, -0.02%] | -7.9% [-8.2%, -7.5%] (743) | 186 |
| `blocked_shots` | bets | 139 | 33 | 86 | 62.3% [42.4%, 78.7%] | +0.85% [-0.22%, +1.93%] | -6.7% [-7.5%, -5.9%] (132) | 101 |
| `blocked_shots` | best-bet bar | 27 | 11 | 14 | 84.6% [45.1%, 97.4%] | +1.64% [-0.02%, +3.30%] | -5.7% [-7.1%, -4.2%] (27) | 25 |
| `goalie_saves` | opinions | 6811 | 1859 | 3011 | 48.9% [43.3%, 54.5%] | -0.24% [-0.96%, +0.49%] | -3.3% [-3.7%, -2.8%] (1327) | 222 |
| `goalie_saves` | bets | 390 | 234 | 107 | 82.7% [69.6%, 90.9%] | +5.89% [-0.18%, +11.96%] | +0.5% [-2.8%, +3.7%] (133) | 91 |
| `goalie_saves` | best-bet bar | 45 | 38 | 5 | 95.0% [74.8%, 99.2%] | +17.50% [-12.86%, +47.86%] | +8.8% [-10.1%, +27.6%] (20) | 15 |
| `goals` | opinions | 48631 | 12886 | 21496 | 47.5% [46.1%, 48.9%] | +0.94% [+0.62%, +1.26%] | -3.9% [-4.0%, -3.7%] (23227) | 366 |
| `goals` | bets | 310 | 173 | 73 | 73.0% [63.1%, 81.0%] | +2.83% [+1.71%, +3.96%] | -1.8% [-2.8%, -0.7%] (294) | 183 |
| `goals` | best-bet bar | 9 | 5 | 1 | 62.5% [21.1%, 91.2%] | -0.13% [-8.08%, +7.82%] | -4.6% [-11.5%, +2.3%] (9) | 9 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 734 | 314 | 91 | 48.8% [43.2%, 54.5%] | -0.30% [-0.68%, +0.08%] | -2.2% [-2.5%, -1.8%] (734) | 367 |
| `moneyline` | bets | 105 | 51 | 12 | 54.8% [40.3%, 68.6%] | +0.43% [-0.72%, +1.59%] | -1.5% [-2.6%, -0.3%] (105) | 105 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 42125 | 13129 | 10693 | 41.8% [40.7%, 42.9%] | +0.73% [-0.02%, +1.47%] | -5.2% [-5.4%, -4.9%] (32118) | 366 |
| `points` | bets | 1927 | 877 | 440 | 59.0% [54.4%, 63.4%] | +2.81% [-0.08%, +5.69%] | -0.1% [-2.9%, +2.8%] (1926) | 362 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 6221 | 2438 | 1553 | 52.2% [50.1%, 54.3%] | +0.45% [+0.15%, +0.75%] | -2.9% [-3.2%, -2.7%] (5480) | 372 |
| `puck_line` | bets | 376 | 197 | 75 | 65.4% [55.0%, 74.6%] | +0.86% [-0.02%, +1.75%] | -2.3% [-3.1%, -1.5%] (376) | 204 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 1098 | 414 | 254 | 49.1% [44.2%, 54.0%] | -0.17% [-0.50%, +0.17%] | — | 366 |
| `regulation_3_way` | bets | 235 | 107 | 49 | 57.5% [47.0%, 67.4%] | +0.36% [-0.58%, +1.30%] | — | 235 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 43698 | 14755 | 10719 | 44.7% [43.1%, 46.3%] | +0.21% [-0.13%, +0.54%] | -4.7% [-4.8%, -4.6%] (25226) | 366 |
| `shots_on_goal` | bets | 3171 | 1686 | 603 | 65.7% [62.1%, 69.1%] | +3.32% [+2.62%, +4.02%] | -1.0% [-1.5%, -0.6%] (2475) | 365 |
| `shots_on_goal` | best-bet bar | 413 | 266 | 63 | 76.0% [68.3%, 82.3%] | +3.93% [+2.87%, +4.98%] | +1.1% [+0.2%, +2.1%] (409) | 230 |
| `team_total` | opinions | 16553 | 5894 | 4573 | 49.2% [47.9%, 50.5%] | +0.09% [-0.03%, +0.21%] | -4.8% [-4.9%, -4.7%] (16354) | 366 |
| `team_total` | bets | 726 | 329 | 161 | 58.2% [46.1%, 69.4%] | +0.68% [-0.32%, +1.68%] | -4.4% [-5.4%, -3.5%] (726) | 167 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 9256 | 3176 | 2741 | 48.7% [47.0%, 50.5%] | +0.10% [-0.08%, +0.28%] | -3.5% [-3.6%, -3.3%] (9060) | 372 |
| `total_goals` | bets | 623 | 284 | 125 | 57.0% [45.0%, 68.2%] | +0.80% [-0.14%, +1.75%] | -3.1% [-4.0%, -2.2%] (623) | 128 |
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
