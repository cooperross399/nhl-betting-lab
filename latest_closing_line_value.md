# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-22T20:50:28+00:00
- Opinions considered: **202002**; matched to a closing price: **192971**; no closing price found: **9031**.
- Within that count, priced before face-off but no close near face-off: **8719** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **67** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `goalie_saves` (42), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **245** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2026** opinion(s), 100 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 192971 | 60557 | 60761 | 45.8% [45.3%, 46.3%] | +0.42% [+0.26%, +0.59%] | -4.5% [-4.5%, -4.4%] (124668) | 361 |

9031 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 8870 | 4343 | 1991 | 63.1% [61.2%, 65.1%] | +2.42% [+1.88%, +2.97%] | -1.6% [-2.2%, -1.1%] (7683) | 360 |

398 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 757 | 443 | 152 | 73.2% [68.4%, 77.6%] | +3.72% [+2.22%, +5.21%] | -0.6% [-1.3%, +0.0%] (698) | 277 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 21219 | 6876 | 6271 | 46.0% [44.6%, 47.4%] | -0.44% [-0.85%, -0.03%] | -4.1% [-4.3%, -4.0%] (13306) | 355 |
| `assists` | bets | 984 | 420 | 275 | 59.2% [53.4%, 64.8%] | +0.96% [+0.59%, +1.32%] | -1.9% [-2.3%, -1.5%] (979) | 336 |
| `assists` | best-bet bar | 58 | 19 | 19 | 48.7% [27.3%, 70.6%] | +0.80% [-0.61%, +2.21%] | -1.7% [-3.4%, -0.1%] (58) | 53 |
| `blocked_shots` | opinions | 1451 | 230 | 886 | 40.7% [34.3%, 47.4%] | -0.32% [-0.61%, -0.02%] | -7.9% [-8.2%, -7.5%] (731) | 182 |
| `blocked_shots` | bets | 137 | 33 | 85 | 63.5% [43.4%, 79.7%] | +0.88% [-0.22%, +1.97%] | -6.7% [-7.5%, -5.9%] (130) | 99 |
| `blocked_shots` | best-bet bar | 26 | 11 | 13 | 84.6% [45.1%, 97.4%] | +1.70% [-0.01%, +3.42%] | -5.6% [-7.1%, -4.0%] (26) | 24 |
| `goalie_saves` | opinions | 6451 | 1783 | 2879 | 49.9% [44.2%, 55.6%] | -0.10% [-0.79%, +0.59%] | -3.2% [-3.6%, -2.7%] (1270) | 211 |
| `goalie_saves` | bets | 387 | 232 | 106 | 82.6% [69.4%, 90.8%] | +5.89% [-0.23%, +12.01%] | +0.5% [-2.8%, +3.7%] (132) | 89 |
| `goalie_saves` | best-bet bar | 45 | 38 | 5 | 95.0% [74.8%, 99.2%] | +17.50% [-12.86%, +47.86%] | +8.8% [-10.1%, +27.6%] (20) | 15 |
| `goals` | opinions | 47158 | 12500 | 20869 | 47.5% [46.1%, 49.0%] | +0.97% [+0.65%, +1.30%] | -3.9% [-4.1%, -3.7%] (22526) | 355 |
| `goals` | bets | 303 | 170 | 72 | 73.6% [63.5%, 81.7%] | +2.95% [+1.82%, +4.08%] | -1.7% [-2.8%, -0.7%] (287) | 178 |
| `goals` | best-bet bar | 8 | 5 | 1 | 71.4% [24.7%, 95.0%] | +2.26% [-2.34%, +6.85%] | -2.5% [-6.3%, +1.3%] (8) | 8 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 712 | 304 | 88 | 48.7% [43.0%, 54.4%] | -0.30% [-0.69%, +0.08%] | -2.2% [-2.5%, -1.8%] (712) | 356 |
| `moneyline` | bets | 102 | 49 | 11 | 53.8% [39.2%, 67.9%] | +0.39% [-0.79%, +1.58%] | -1.5% [-2.7%, -0.3%] (102) | 102 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 40907 | 12777 | 10400 | 41.9% [40.8%, 43.0%] | +0.79% [+0.03%, +1.55%] | -5.2% [-5.4%, -4.9%] (31172) | 355 |
| `points` | bets | 1857 | 851 | 426 | 59.5% [54.8%, 64.0%] | +2.89% [-0.10%, +5.89%] | -0.0% [-3.0%, +2.9%] (1856) | 351 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 6053 | 2373 | 1506 | 52.2% [50.1%, 54.3%] | +0.45% [+0.15%, +0.76%] | -3.0% [-3.2%, -2.7%] (5335) | 361 |
| `puck_line` | bets | 366 | 190 | 73 | 64.8% [54.2%, 74.2%] | +0.85% [-0.07%, +1.76%] | -2.4% [-3.2%, -1.5%] (366) | 198 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 1065 | 401 | 247 | 49.0% [44.0%, 54.0%] | -0.14% [-0.48%, +0.20%] | — | 355 |
| `regulation_3_way` | bets | 229 | 102 | 49 | 56.7% [46.0%, 66.7%] | +0.29% [-0.66%, +1.25%] | — | 229 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 42495 | 14375 | 10399 | 44.8% [43.2%, 46.4%] | +0.22% [-0.12%, +0.57%] | -4.7% [-4.8%, -4.6%] (24538) | 355 |
| `shots_on_goal` | bets | 3066 | 1639 | 584 | 66.0% [62.4%, 69.5%] | +3.38% [+2.65%, +4.10%] | -1.0% [-1.5%, -0.6%] (2392) | 354 |
| `shots_on_goal` | best-bet bar | 400 | 260 | 62 | 76.9% [69.2%, 83.2%] | +4.07% [+3.00%, +5.14%] | +1.2% [+0.2%, +2.2%] (397) | 223 |
| `team_total` | opinions | 16111 | 5733 | 4448 | 49.2% [47.8%, 50.5%] | +0.09% [-0.03%, +0.22%] | -4.8% [-5.0%, -4.7%] (15917) | 355 |
| `team_total` | bets | 713 | 322 | 156 | 57.8% [45.6%, 69.1%] | +0.67% [-0.34%, +1.69%] | -4.4% [-5.4%, -3.5%] (713) | 165 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 8975 | 3071 | 2662 | 48.6% [46.8%, 50.4%] | +0.10% [-0.09%, +0.28%] | -3.5% [-3.6%, -3.3%] (8787) | 361 |
| `total_goals` | bets | 606 | 278 | 120 | 57.2% [44.9%, 68.6%] | +0.83% [-0.14%, +1.80%] | -3.1% [-4.0%, -2.2%] (606) | 125 |
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
