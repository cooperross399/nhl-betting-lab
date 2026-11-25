# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-25T14:09:05+00:00
- Opinions considered: **208482**; matched to a closing price: **199372**; no closing price found: **9110**.
- Within that count, priced before face-off but no close near face-off: **8793** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **67** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `goalie_saves` (42), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **250** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **7393** opinion(s), 314 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 199372 | 62540 | 62704 | 45.8% [45.2%, 46.3%] | +0.40% [+0.24%, +0.56%] | -4.5% [-4.5%, -4.4%] (128632) | 373 |

9110 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 9180 | 4485 | 2059 | 63.0% [61.1%, 64.9%] | +2.38% [+1.85%, +2.91%] | -1.6% [-2.1%, -1.1%] (7948) | 372 |

403 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 780 | 453 | 155 | 72.5% [67.7%, 76.8%] | +3.59% [+2.13%, +5.04%] | -0.7% [-1.3%, -0.0%] (720) | 288 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 21898 | 7118 | 6434 | 46.0% [44.6%, 47.4%] | -0.43% [-0.82%, -0.03%] | -4.1% [-4.3%, -3.9%] (13733) | 367 |
| `assists` | bets | 1023 | 440 | 282 | 59.4% [53.7%, 64.8%] | +0.93% [+0.57%, +1.29%] | -1.9% [-2.3%, -1.5%] (1018) | 348 |
| `assists` | best-bet bar | 63 | 21 | 20 | 48.8% [28.3%, 69.8%] | +0.75% [-0.57%, +2.08%] | -1.7% [-3.2%, -0.2%] (63) | 58 |
| `blocked_shots` | opinions | 1476 | 232 | 905 | 40.6% [34.3%, 47.3%] | -0.31% [-0.60%, -0.02%] | -7.8% [-8.2%, -7.5%] (747) | 187 |
| `blocked_shots` | bets | 140 | 33 | 87 | 62.3% [42.4%, 78.7%] | +0.85% [-0.22%, +1.92%] | -6.7% [-7.5%, -5.9%] (132) | 102 |
| `blocked_shots` | best-bet bar | 27 | 11 | 14 | 84.6% [45.1%, 97.4%] | +1.64% [-0.02%, +3.30%] | -5.7% [-7.1%, -4.2%] (27) | 25 |
| `goalie_saves` | opinions | 6855 | 1863 | 3029 | 48.7% [43.1%, 54.3%] | -0.26% [-0.99%, +0.46%] | -3.3% [-3.8%, -2.9%] (1332) | 223 |
| `goalie_saves` | bets | 399 | 235 | 111 | 81.6% [68.2%, 90.2%] | +5.72% [-0.24%, +11.68%] | +0.4% [-2.8%, +3.6%] (135) | 92 |
| `goalie_saves` | best-bet bar | 45 | 38 | 5 | 95.0% [74.8%, 99.2%] | +17.50% [-12.86%, +47.86%] | +8.8% [-10.1%, +27.6%] (20) | 15 |
| `goals` | opinions | 48753 | 12942 | 21538 | 47.6% [46.2%, 48.9%] | +0.96% [+0.63%, +1.28%] | -3.9% [-4.0%, -3.7%] (23253) | 367 |
| `goals` | bets | 310 | 173 | 73 | 73.0% [63.1%, 81.0%] | +2.83% [+1.71%, +3.96%] | -1.8% [-2.8%, -0.7%] (294) | 183 |
| `goals` | best-bet bar | 9 | 5 | 1 | 62.5% [21.1%, 91.2%] | -0.13% [-8.08%, +7.82%] | -4.6% [-11.5%, +2.3%] (9) | 9 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 736 | 316 | 91 | 49.0% [43.4%, 54.6%] | -0.30% [-0.67%, +0.08%] | -2.2% [-2.5%, -1.8%] (736) | 368 |
| `moneyline` | bets | 105 | 51 | 12 | 54.8% [40.3%, 68.6%] | +0.43% [-0.72%, +1.59%] | -1.5% [-2.6%, -0.3%] (105) | 105 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 42239 | 13172 | 10715 | 41.8% [40.7%, 42.9%] | +0.73% [-0.01%, +1.47%] | -5.2% [-5.4%, -4.9%] (32206) | 367 |
| `points` | bets | 1929 | 877 | 441 | 58.9% [54.3%, 63.4%] | +2.80% [-0.09%, +5.69%] | -0.1% [-2.9%, +2.7%] (1928) | 363 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 6236 | 2444 | 1555 | 52.2% [50.1%, 54.3%] | +0.46% [+0.16%, +0.76%] | -2.9% [-3.2%, -2.7%] (5492) | 373 |
| `puck_line` | bets | 376 | 197 | 75 | 65.4% [55.0%, 74.6%] | +0.86% [-0.02%, +1.75%] | -2.3% [-3.1%, -1.5%] (376) | 204 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 1101 | 414 | 254 | 48.9% [44.0%, 53.8%] | -0.17% [-0.51%, +0.17%] | — | 367 |
| `regulation_3_way` | bets | 236 | 107 | 49 | 57.2% [46.8%, 67.1%] | +0.35% [-0.59%, +1.29%] | — | 236 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 43820 | 14796 | 10763 | 44.8% [43.2%, 46.4%] | +0.21% [-0.12%, +0.54%] | -4.7% [-4.8%, -4.6%] (25271) | 367 |
| `shots_on_goal` | bets | 3185 | 1694 | 609 | 65.8% [62.2%, 69.2%] | +3.31% [+2.61%, +4.01%] | -1.0% [-1.5%, -0.6%] (2483) | 366 |
| `shots_on_goal` | best-bet bar | 415 | 268 | 63 | 76.1% [68.5%, 82.4%] | +3.94% [+2.89%, +4.99%] | +1.1% [+0.2%, +2.1%] (411) | 231 |
| `team_total` | opinions | 16603 | 5920 | 4573 | 49.2% [47.9%, 50.5%] | +0.10% [-0.02%, +0.22%] | -4.8% [-4.9%, -4.7%] (16403) | 367 |
| `team_total` | bets | 728 | 331 | 161 | 58.4% [46.3%, 69.5%] | +0.70% [-0.30%, +1.69%] | -4.4% [-5.4%, -3.5%] (728) | 168 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 9281 | 3189 | 2741 | 48.8% [47.0%, 50.5%] | +0.11% [-0.07%, +0.30%] | -3.5% [-3.6%, -3.3%] (9085) | 373 |
| `total_goals` | bets | 629 | 290 | 125 | 57.5% [45.6%, 68.7%] | +0.92% [-0.07%, +1.91%] | -3.0% [-3.9%, -2.1%] (629) | 129 |
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
