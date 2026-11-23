# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-23T13:44:14+00:00
- Opinions considered: **204028**; matched to a closing price: **194989**; no closing price found: **9039**.
- Within that count, priced before face-off but no close near face-off: **8725** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **67** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `goalie_saves` (42), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **247** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **3581** opinion(s), 175 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 194989 | 61093 | 61467 | 45.8% [45.2%, 46.3%] | +0.41% [+0.25%, +0.57%] | -4.5% [-4.5%, -4.4%] (125965) | 365 |

9039 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 8970 | 4382 | 2016 | 63.0% [61.1%, 64.9%] | +2.40% [+1.86%, +2.94%] | -1.6% [-2.2%, -1.1%] (7767) | 364 |

398 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 762 | 445 | 154 | 73.2% [68.3%, 77.5%] | +3.69% [+2.20%, +5.18%] | -0.6% [-1.3%, +0.0%] (702) | 280 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 21443 | 6937 | 6339 | 45.9% [44.5%, 47.4%] | -0.45% [-0.85%, -0.04%] | -4.1% [-4.3%, -4.0%] (13450) | 359 |
| `assists` | bets | 998 | 425 | 279 | 59.1% [53.4%, 64.6%] | +0.93% [+0.57%, +1.29%] | -1.9% [-2.3%, -1.5%] (993) | 340 |
| `assists` | best-bet bar | 59 | 20 | 19 | 50.0% [28.5%, 71.5%] | +0.81% [-0.58%, +2.20%] | -1.7% [-3.3%, -0.1%] (59) | 54 |
| `blocked_shots` | opinions | 1455 | 230 | 890 | 40.7% [34.3%, 47.4%] | -0.32% [-0.61%, -0.02%] | -7.9% [-8.2%, -7.5%] (735) | 183 |
| `blocked_shots` | bets | 138 | 33 | 86 | 63.5% [43.4%, 79.7%] | +0.87% [-0.21%, +1.95%] | -6.7% [-7.5%, -5.9%] (131) | 100 |
| `blocked_shots` | best-bet bar | 27 | 11 | 14 | 84.6% [45.1%, 97.4%] | +1.64% [-0.02%, +3.30%] | -5.7% [-7.1%, -4.2%] (27) | 25 |
| `goalie_saves` | opinions | 6541 | 1797 | 2888 | 49.2% [43.5%, 54.9%] | -0.25% [-0.99%, +0.49%] | -3.3% [-3.7%, -2.8%] (1284) | 215 |
| `goalie_saves` | bets | 389 | 234 | 106 | 82.7% [69.6%, 90.9%] | +5.90% [-0.18%, +11.99%] | +0.5% [-2.8%, +3.7%] (132) | 90 |
| `goalie_saves` | best-bet bar | 45 | 38 | 5 | 95.0% [74.8%, 99.2%] | +17.50% [-12.86%, +47.86%] | +8.8% [-10.1%, +27.6%] (20) | 15 |
| `goals` | opinions | 47699 | 12619 | 21147 | 47.5% [46.1%, 48.9%] | +0.96% [+0.64%, +1.28%] | -3.9% [-4.1%, -3.7%] (22786) | 359 |
| `goals` | bets | 304 | 170 | 72 | 73.3% [63.3%, 81.4%] | +2.91% [+1.79%, +4.04%] | -1.7% [-2.8%, -0.7%] (288) | 179 |
| `goals` | best-bet bar | 8 | 5 | 1 | 71.4% [24.7%, 95.0%] | +2.26% [-2.34%, +6.85%] | -2.5% [-6.3%, +1.3%] (8) | 8 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 720 | 308 | 88 | 48.7% [43.1%, 54.4%] | -0.31% [-0.69%, +0.08%] | -2.2% [-2.5%, -1.8%] (720) | 360 |
| `moneyline` | bets | 103 | 50 | 11 | 54.3% [39.7%, 68.3%] | +0.44% [-0.74%, +1.62%] | -1.5% [-2.6%, -0.3%] (103) | 103 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 41352 | 12882 | 10541 | 41.8% [40.7%, 42.9%] | +0.78% [+0.02%, +1.53%] | -5.2% [-5.4%, -4.9%] (31524) | 359 |
| `points` | bets | 1883 | 857 | 434 | 59.1% [54.5%, 63.6%] | +2.84% [-0.11%, +5.80%] | -0.1% [-3.0%, +2.9%] (1882) | 355 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 6114 | 2395 | 1526 | 52.2% [50.1%, 54.3%] | +0.45% [+0.15%, +0.76%] | -3.0% [-3.2%, -2.7%] (5387) | 365 |
| `puck_line` | bets | 367 | 191 | 73 | 65.0% [54.4%, 74.3%] | +0.85% [-0.06%, +1.76%] | -2.3% [-3.2%, -1.5%] (367) | 199 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 1077 | 406 | 250 | 49.1% [44.1%, 54.1%] | -0.15% [-0.49%, +0.19%] | — | 359 |
| `regulation_3_way` | bets | 231 | 104 | 49 | 57.1% [46.5%, 67.1%] | +0.32% [-0.63%, +1.27%] | — | 231 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 42908 | 14491 | 10525 | 44.7% [43.1%, 46.4%] | +0.22% [-0.12%, +0.56%] | -4.7% [-4.8%, -4.6%] (24784) | 359 |
| `shots_on_goal` | bets | 3111 | 1659 | 592 | 65.9% [62.2%, 69.3%] | +3.35% [+2.63%, +4.06%] | -1.0% [-1.5%, -0.6%] (2425) | 358 |
| `shots_on_goal` | best-bet bar | 403 | 261 | 63 | 76.8% [69.1%, 83.0%] | +4.03% [+2.97%, +5.10%] | +1.2% [+0.2%, +2.2%] (399) | 226 |
| `team_total` | opinions | 16228 | 5780 | 4473 | 49.2% [47.9%, 50.5%] | +0.10% [-0.02%, +0.22%] | -4.8% [-4.9%, -4.7%] (16033) | 359 |
| `team_total` | bets | 713 | 322 | 156 | 57.8% [45.6%, 69.1%] | +0.67% [-0.34%, +1.69%] | -4.4% [-5.4%, -3.5%] (713) | 165 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 9078 | 3114 | 2694 | 48.8% [47.0%, 50.6%] | +0.11% [-0.08%, +0.29%] | -3.5% [-3.6%, -3.3%] (8888) | 365 |
| `total_goals` | bets | 613 | 280 | 124 | 57.3% [45.1%, 68.6%] | +0.82% [-0.13%, +1.78%] | -3.1% [-4.0%, -2.2%] (613) | 126 |
| `total_goals` | best-bet bar | 47 | 13 | 16 | 41.9% [13.5%, 76.9%] | -0.42% [-2.86%, +2.01%] | -4.4% [-6.4%, -2.3%] (47) | 14 |

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
