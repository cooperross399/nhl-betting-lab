# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-21T22:50:15+00:00
- Opinions considered: **194559**; matched to a closing price: **185678**; no closing price found: **8881**.
- Within that count, priced before face-off but no close near face-off: **8616** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **240** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **6917** opinion(s), 332 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 185678 | 58574 | 57947 | 45.9% [45.3%, 46.4%] | +0.44% [+0.27%, +0.60%] | -4.5% [-4.5%, -4.4%] (120094) | 348 |

8881 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 8512 | 4193 | 1866 | 63.1% [61.1%, 65.0%] | +2.46% [+1.89%, +3.03%] | -1.6% [-2.1%, -1.0%] (7397) | 347 |

393 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 736 | 432 | 145 | 73.1% [68.1%, 77.5%] | +3.74% [+2.20%, +5.28%] | -0.6% [-1.3%, +0.1%] (677) | 266 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 20458 | 6653 | 5994 | 46.0% [44.5%, 47.5%] | -0.47% [-0.89%, -0.05%] | -4.1% [-4.3%, -4.0%] (12831) | 342 |
| `assists` | bets | 940 | 408 | 256 | 59.6% [53.7%, 65.3%] | +1.00% [+0.63%, +1.37%] | -1.8% [-2.2%, -1.4%] (936) | 324 |
| `assists` | best-bet bar | 56 | 18 | 19 | 48.6% [26.7%, 71.1%] | +0.79% [-0.67%, +2.25%] | -1.7% [-3.4%, -0.0%] (56) | 51 |
| `blocked_shots` | opinions | 1360 | 222 | 814 | 40.7% [34.1%, 47.6%] | -0.33% [-0.64%, -0.02%] | -7.9% [-8.2%, -7.5%] (691) | 173 |
| `blocked_shots` | bets | 130 | 32 | 80 | 64.0% [43.1%, 80.6%] | +0.90% [-0.25%, +2.05%] | -6.7% [-7.5%, -5.8%] (125) | 93 |
| `blocked_shots` | best-bet bar | 25 | 11 | 12 | 84.6% [45.1%, 97.4%] | +1.77% [-0.00%, +3.54%] | -5.5% [-7.1%, -3.9%] (25) | 23 |
| `goalie_saves` | opinions | 6033 | 1670 | 2695 | 50.0% [44.4%, 55.6%] | -0.01% [-0.68%, +0.66%] | -3.1% [-3.6%, -2.7%] (1204) | 199 |
| `goalie_saves` | bets | 345 | 205 | 94 | 81.7% [67.6%, 90.5%] | +6.05% [-0.77%, +12.87%] | +0.5% [-3.0%, +4.0%] (121) | 82 |
| `goalie_saves` | best-bet bar | 44 | 37 | 5 | 94.9% [74.1%, 99.2%] | +17.57% [-13.55%, +48.68%] | +8.4% [-11.5%, +28.3%] (19) | 14 |
| `goals` | opinions | 45384 | 12062 | 20084 | 47.7% [46.3%, 49.1%] | +1.02% [+0.69%, +1.35%] | -3.9% [-4.1%, -3.8%] (21667) | 342 |
| `goals` | bets | 289 | 166 | 66 | 74.4% [64.3%, 82.5%] | +2.96% [+1.84%, +4.08%] | -1.8% [-2.8%, -0.8%] (274) | 170 |
| `goals` | best-bet bar | 7 | 5 | 0 | 71.4% [24.7%, 95.0%] | +2.58% [-2.62%, +7.78%] | -2.4% [-6.8%, +1.9%] (7) | 7 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 686 | 290 | 85 | 48.3% [42.5%, 54.1%] | -0.30% [-0.69%, +0.10%] | -2.2% [-2.6%, -1.8%] (686) | 343 |
| `moneyline` | bets | 99 | 46 | 11 | 52.3% [37.5%, 66.7%] | +0.37% [-0.85%, +1.59%] | -1.5% [-2.7%, -0.3%] (99) | 99 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 39380 | 12372 | 9888 | 42.0% [40.8%, 43.1%] | +0.79% [+0.00%, +1.57%] | -5.2% [-5.4%, -4.9%] (30018) | 342 |
| `points` | bets | 1788 | 829 | 403 | 59.9% [55.1%, 64.4%] | +3.00% [-0.10%, +6.10%] | +0.1% [-2.9%, +3.2%] (1787) | 338 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 5857 | 2293 | 1451 | 52.0% [49.9%, 54.2%] | +0.44% [+0.13%, +0.75%] | -3.0% [-3.3%, -2.7%] (5165) | 348 |
| `puck_line` | bets | 353 | 185 | 69 | 65.1% [54.3%, 74.6%] | +0.85% [-0.10%, +1.79%] | -2.4% [-3.2%, -1.5%] (353) | 190 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 1026 | 389 | 235 | 49.2% [44.1%, 54.3%] | -0.10% [-0.43%, +0.23%] | — | 342 |
| `regulation_3_way` | bets | 223 | 101 | 47 | 57.4% [46.6%, 67.5%] | +0.48% [-0.35%, +1.31%] | — | 223 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 40961 | 13983 | 9808 | 44.9% [43.2%, 46.5%] | +0.24% [-0.11%, +0.59%] | -4.7% [-4.8%, -4.6%] (23663) | 342 |
| `shots_on_goal` | bets | 2944 | 1586 | 542 | 66.0% [62.3%, 69.5%] | +3.43% [+2.69%, +4.18%] | -1.0% [-1.4%, -0.5%] (2301) | 341 |
| `shots_on_goal` | best-bet bar | 385 | 252 | 57 | 76.8% [69.0%, 83.2%] | +4.13% [+3.03%, +5.22%] | +1.3% [+0.3%, +2.3%] (382) | 214 |
| `team_total` | opinions | 15515 | 5544 | 4238 | 49.2% [47.8%, 50.5%] | +0.09% [-0.03%, +0.22%] | -4.8% [-5.0%, -4.7%] (15331) | 342 |
| `team_total` | bets | 699 | 315 | 150 | 57.4% [45.1%, 68.8%] | +0.66% [-0.37%, +1.70%] | -4.4% [-5.4%, -3.4%] (699) | 161 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 8644 | 2962 | 2549 | 48.6% [46.8%, 50.4%] | +0.09% [-0.10%, +0.28%] | -3.5% [-3.6%, -3.3%] (8464) | 348 |
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
