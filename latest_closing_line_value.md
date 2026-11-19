# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-19T20:44:12+00:00
- Opinions considered: **186644**; matched to a closing price: **177823**; no closing price found: **8821**.
- Within that count, priced before face-off but no close near face-off: **8562** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **234** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **6780** opinion(s), 314 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 177823 | 56141 | 55044 | 45.7% [45.2%, 46.3%] | +0.31% [+0.17%, +0.46%] | -4.5% [-4.6%, -4.4%] (115241) | 334 |

8821 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 8131 | 4019 | 1750 | 63.0% [60.9%, 65.0%] | +2.50% [+1.91%, +3.09%] | -1.5% [-2.1%, -1.0%] (7097) | 333 |

393 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 692 | 408 | 132 | 72.9% [67.8%, 77.4%] | +3.81% [+2.18%, +5.43%] | -0.5% [-1.2%, +0.2%] (639) | 254 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 19604 | 6373 | 5676 | 45.8% [44.3%, 47.3%] | -0.51% [-0.94%, -0.07%] | -4.1% [-4.3%, -4.0%] (12287) | 328 |
| `assists` | bets | 895 | 391 | 239 | 59.6% [53.5%, 65.4%] | +1.01% [+0.63%, +1.40%] | -1.8% [-2.2%, -1.4%] (891) | 310 |
| `assists` | best-bet bar | 55 | 18 | 18 | 48.6% [26.7%, 71.1%] | +0.80% [-0.68%, +2.29%] | -1.7% [-3.4%, +0.1%] (55) | 50 |
| `blocked_shots` | opinions | 1308 | 215 | 780 | 40.7% [34.1%, 47.7%] | -0.34% [-0.66%, -0.01%] | -7.9% [-8.2%, -7.5%] (666) | 166 |
| `blocked_shots` | bets | 125 | 29 | 78 | 61.7% [40.3%, 79.4%] | +0.82% [-0.37%, +2.00%] | -6.7% [-7.6%, -5.9%] (120) | 90 |
| `blocked_shots` | best-bet bar | 22 | 9 | 11 | 81.8% [39.6%, 96.9%] | +1.48% [-0.39%, +3.35%] | -5.6% [-7.3%, -3.9%] (22) | 21 |
| `goalie_saves` | opinions | 5520 | 1530 | 2397 | 49.0% [43.3%, 54.8%] | -0.06% [-0.79%, +0.67%] | -3.2% [-3.6%, -2.7%] (1119) | 186 |
| `goalie_saves` | bets | 283 | 174 | 68 | 80.9% [65.0%, 90.7%] | +6.74% [-1.48%, +14.95%] | +0.8% [-3.1%, +4.6%] (110) | 74 |
| `goalie_saves` | best-bet bar | 36 | 31 | 3 | 93.9% [70.4%, 99.0%] | +20.59% [-16.00%, +57.17%] | +10.1% [-13.2%, +33.4%] (16) | 12 |
| `goals` | opinions | 43487 | 11624 | 19157 | 47.8% [46.3%, 49.2%] | +1.02% [+0.68%, +1.36%] | -4.0% [-4.2%, -3.8%] (20757) | 328 |
| `goals` | bets | 278 | 161 | 63 | 74.9% [64.4%, 83.1%] | +3.01% [+1.86%, +4.16%] | -1.8% [-2.8%, -0.7%] (264) | 165 |
| `goals` | best-bet bar | 7 | 5 | 0 | 71.4% [24.7%, 95.0%] | +2.58% [-2.62%, +7.78%] | -2.4% [-6.8%, +1.9%] (7) | 7 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 658 | 278 | 78 | 47.9% [42.1%, 53.9%] | -0.29% [-0.70%, +0.11%] | -2.2% [-2.6%, -1.8%] (658) | 329 |
| `moneyline` | bets | 98 | 46 | 10 | 52.3% [37.5%, 66.7%] | +0.37% [-0.86%, +1.60%] | -1.5% [-2.7%, -0.3%] (98) | 98 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 37691 | 11777 | 9404 | 41.6% [40.5%, 42.7%] | +0.29% [-0.33%, +0.91%] | -5.2% [-5.4%, -4.9%] (28737) | 328 |
| `points` | bets | 1709 | 793 | 382 | 59.8% [54.9%, 64.4%] | +3.13% [-0.11%, +6.37%] | +0.2% [-3.0%, +3.4%] (1708) | 324 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 5644 | 2216 | 1389 | 52.1% [49.9%, 54.3%] | +0.43% [+0.11%, +0.75%] | -3.0% [-3.3%, -2.7%] (4980) | 334 |
| `puck_line` | bets | 340 | 177 | 67 | 64.8% [53.8%, 74.5%] | +0.85% [-0.13%, +1.82%] | -2.4% [-3.3%, -1.5%] (340) | 182 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 984 | 377 | 226 | 49.7% [44.6%, 54.9%] | -0.08% [-0.42%, +0.26%] | — | 328 |
| `regulation_3_way` | bets | 217 | 99 | 44 | 57.2% [46.4%, 67.4%] | +0.47% [-0.38%, +1.32%] | — | 217 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 39187 | 13377 | 9284 | 44.7% [43.1%, 46.4%] | +0.18% [-0.18%, +0.53%] | -4.7% [-4.8%, -4.6%] (22649) | 328 |
| `shots_on_goal` | bets | 2811 | 1526 | 505 | 66.2% [62.4%, 69.7%] | +3.49% [+2.74%, +4.23%] | -0.8% [-1.3%, -0.4%] (2191) | 327 |
| `shots_on_goal` | best-bet bar | 357 | 236 | 49 | 76.6% [68.7%, 83.1%] | +4.21% [+3.12%, +5.29%] | +1.5% [+0.4%, +2.5%] (355) | 204 |
| `team_total` | opinions | 15071 | 5407 | 4099 | 49.3% [47.9%, 50.6%] | +0.09% [-0.04%, +0.21%] | -4.9% [-5.0%, -4.7%] (14894) | 328 |
| `team_total` | bets | 690 | 313 | 148 | 57.7% [45.4%, 69.2%] | +0.67% [-0.38%, +1.72%] | -4.4% [-5.4%, -3.4%] (690) | 159 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 8295 | 2833 | 2448 | 48.5% [46.6%, 50.3%] | +0.08% [-0.11%, +0.27%] | -3.5% [-3.7%, -3.3%] (8120) | 334 |
| `total_goals` | bets | 565 | 253 | 112 | 55.8% [43.3%, 67.7%] | +0.72% [-0.28%, +1.72%] | -3.2% [-4.1%, -2.3%] (565) | 117 |
| `total_goals` | best-bet bar | 42 | 12 | 15 | 44.4% [13.4%, 80.6%] | -0.28% [-2.99%, +2.42%] | -4.2% [-6.5%, -1.9%] (42) | 12 |

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
