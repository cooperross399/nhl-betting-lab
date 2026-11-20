# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-20T22:40:26+00:00
- Opinions considered: **193426**; matched to a closing price: **184550**; no closing price found: **8876**.
- Within that count, priced before face-off but no close near face-off: **8612** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **239** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.

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
| 184550 | 58379 | 57255 | 45.9% [45.3%, 46.4%] | +0.45% [+0.28%, +0.61%] | -4.5% [-4.5%, -4.4%] (119327) | 346 |

8876 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 8445 | 4177 | 1820 | 63.0% [61.0%, 65.0%] | +2.48% [+1.91%, +3.05%] | -1.6% [-2.1%, -1.0%] (7337) | 345 |

393 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 726 | 428 | 139 | 72.9% [67.9%, 77.4%] | +3.77% [+2.22%, +5.33%] | -0.6% [-1.3%, +0.1%] (667) | 264 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 20333 | 6634 | 5914 | 46.0% [44.5%, 47.5%] | -0.48% [-0.90%, -0.05%] | -4.1% [-4.3%, -4.0%] (12751) | 340 |
| `assists` | bets | 934 | 406 | 252 | 59.5% [53.6%, 65.2%] | +1.00% [+0.62%, +1.37%] | -1.8% [-2.2%, -1.4%] (930) | 322 |
| `assists` | best-bet bar | 56 | 18 | 19 | 48.6% [26.7%, 71.1%] | +0.79% [-0.67%, +2.25%] | -1.7% [-3.4%, -0.0%] (56) | 51 |
| `blocked_shots` | opinions | 1360 | 222 | 814 | 40.7% [34.1%, 47.6%] | -0.33% [-0.64%, -0.02%] | -7.9% [-8.2%, -7.5%] (691) | 173 |
| `blocked_shots` | bets | 130 | 32 | 80 | 64.0% [43.1%, 80.6%] | +0.90% [-0.25%, +2.05%] | -6.7% [-7.5%, -5.8%] (125) | 93 |
| `blocked_shots` | best-bet bar | 25 | 11 | 12 | 84.6% [45.1%, 97.4%] | +1.77% [-0.00%, +3.54%] | -5.5% [-7.1%, -3.9%] (25) | 23 |
| `goalie_saves` | opinions | 6017 | 1670 | 2684 | 50.1% [44.5%, 55.7%] | -0.00% [-0.68%, +0.67%] | -3.1% [-3.6%, -2.7%] (1201) | 198 |
| `goalie_saves` | bets | 337 | 205 | 88 | 82.3% [68.3%, 91.0%] | +6.21% [-0.75%, +13.17%] | +0.6% [-2.9%, +4.1%] (119) | 81 |
| `goalie_saves` | best-bet bar | 44 | 37 | 5 | 94.9% [74.1%, 99.2%] | +17.57% [-13.55%, +48.68%] | +8.4% [-11.5%, +28.3%] (19) | 14 |
| `goals` | opinions | 45107 | 12027 | 19900 | 47.7% [46.3%, 49.1%] | +1.02% [+0.69%, +1.36%] | -3.9% [-4.1%, -3.8%] (21529) | 340 |
| `goals` | bets | 286 | 166 | 63 | 74.4% [64.3%, 82.5%] | +2.99% [+1.86%, +4.12%] | -1.8% [-2.8%, -0.7%] (271) | 169 |
| `goals` | best-bet bar | 7 | 5 | 0 | 71.4% [24.7%, 95.0%] | +2.58% [-2.62%, +7.78%] | -2.4% [-6.8%, +1.9%] (7) | 7 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 682 | 288 | 84 | 48.2% [42.4%, 54.0%] | -0.29% [-0.69%, +0.10%] | -2.2% [-2.6%, -1.8%] (682) | 341 |
| `moneyline` | bets | 99 | 46 | 11 | 52.3% [37.5%, 66.7%] | +0.37% [-0.85%, +1.59%] | -1.5% [-2.7%, -0.3%] (99) | 99 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 39138 | 12344 | 9726 | 42.0% [40.8%, 43.1%] | +0.81% [+0.02%, +1.60%] | -5.2% [-5.4%, -4.9%] (29830) | 340 |
| `points` | bets | 1770 | 823 | 391 | 59.7% [54.9%, 64.3%] | +3.02% [-0.11%, +6.16%] | +0.1% [-3.0%, +3.2%] (1769) | 336 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 5826 | 2281 | 1441 | 52.0% [49.9%, 54.2%] | +0.44% [+0.12%, +0.75%] | -3.0% [-3.3%, -2.7%] (5137) | 346 |
| `puck_line` | bets | 351 | 184 | 68 | 65.0% [54.2%, 74.5%] | +0.85% [-0.10%, +1.80%] | -2.4% [-3.3%, -1.5%] (351) | 189 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 1020 | 388 | 234 | 49.4% [44.3%, 54.5%] | -0.09% [-0.43%, +0.24%] | — | 340 |
| `regulation_3_way` | bets | 223 | 101 | 47 | 57.4% [46.6%, 67.5%] | +0.48% [-0.35%, +1.31%] | — | 223 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 40675 | 13930 | 9617 | 44.9% [43.2%, 46.5%] | +0.24% [-0.11%, +0.60%] | -4.7% [-4.8%, -4.6%] (23477) | 340 |
| `shots_on_goal` | bets | 2914 | 1579 | 522 | 66.0% [62.3%, 69.5%] | +3.46% [+2.71%, +4.21%] | -0.9% [-1.4%, -0.4%] (2272) | 339 |
| `shots_on_goal` | best-bet bar | 375 | 248 | 51 | 76.5% [68.6%, 82.9%] | +4.20% [+3.08%, +5.32%] | +1.4% [+0.3%, +2.4%] (372) | 212 |
| `team_total` | opinions | 15423 | 5516 | 4204 | 49.2% [47.8%, 50.5%] | +0.09% [-0.03%, +0.22%] | -4.8% [-5.0%, -4.7%] (15239) | 340 |
| `team_total` | bets | 699 | 315 | 150 | 57.4% [45.1%, 68.8%] | +0.66% [-0.37%, +1.70%] | -4.4% [-5.4%, -3.4%] (699) | 161 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 8595 | 2945 | 2531 | 48.6% [46.7%, 50.4%] | +0.09% [-0.10%, +0.28%] | -3.5% [-3.6%, -3.3%] (8416) | 346 |
| `total_goals` | bets | 582 | 263 | 114 | 56.2% [43.8%, 67.9%] | +0.77% [-0.23%, +1.76%] | -3.1% [-4.1%, -2.2%] (582) | 121 |
| `total_goals` | best-bet bar | 46 | 12 | 16 | 40.0% [12.2%, 76.1%] | -0.48% [-2.95%, +2.00%] | -4.4% [-6.5%, -2.3%] (46) | 13 |

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
