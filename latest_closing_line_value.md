# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-27T22:43:50+00:00
- Opinions considered: **223377**; matched to a closing price: **214114**; no closing price found: **9263**.
- Within that count, priced before face-off but no close near face-off: **8941** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **67** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `goalie_saves` (42), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **255** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1722** opinion(s), 63 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 214114 | 66766 | 68041 | 45.7% [45.2%, 46.2%] | +0.37% [+0.22%, +0.52%] | -4.4% [-4.5%, -4.4%] (137988) | 399 |

9263 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 9830 | 4762 | 2275 | 63.0% [61.2%, 64.8%] | +2.32% [+1.83%, +2.82%] | -1.7% [-2.1%, -1.2%] (8501) | 398 |

407 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 813 | 474 | 160 | 72.6% [67.9%, 76.8%] | +3.54% [+2.14%, +4.94%] | -0.7% [-1.3%, -0.1%] (751) | 306 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 23451 | 7572 | 6944 | 45.9% [44.5%, 47.3%] | -0.43% [-0.80%, -0.05%] | -4.1% [-4.3%, -4.0%] (14699) | 393 |
| `assists` | bets | 1106 | 473 | 308 | 59.3% [53.9%, 64.5%] | +0.90% [+0.56%, +1.23%] | -1.9% [-2.3%, -1.6%] (1101) | 374 |
| `assists` | best-bet bar | 69 | 25 | 21 | 52.1% [32.0%, 71.5%] | +0.71% [-0.52%, +1.94%] | -1.7% [-3.1%, -0.3%] (69) | 64 |
| `blocked_shots` | opinions | 1536 | 244 | 940 | 40.9% [34.7%, 47.5%] | -0.30% [-0.58%, -0.02%] | -7.8% [-8.2%, -7.5%] (775) | 195 |
| `blocked_shots` | bets | 147 | 34 | 92 | 61.8% [42.4%, 78.1%] | +0.83% [-0.19%, +1.86%] | -6.7% [-7.5%, -6.0%] (138) | 106 |
| `blocked_shots` | best-bet bar | 28 | 12 | 14 | 85.7% [47.5%, 97.6%] | +1.80% [+0.14%, +3.46%] | -5.5% [-7.0%, -4.1%] (28) | 26 |
| `goalie_saves` | opinions | 7538 | 2042 | 3318 | 48.4% [43.0%, 53.8%] | -0.26% [-0.94%, +0.42%] | -3.4% [-3.8%, -2.9%] (1439) | 243 |
| `goalie_saves` | bets | 429 | 243 | 129 | 81.0% [67.9%, 89.6%] | +5.38% [-0.20%, +10.96%] | +0.1% [-2.8%, +3.1%] (146) | 99 |
| `goalie_saves` | best-bet bar | 45 | 38 | 5 | 95.0% [74.8%, 99.2%] | +17.50% [-12.86%, +47.86%] | +8.8% [-10.1%, +27.6%] (20) | 15 |
| `goals` | opinions | 52306 | 13737 | 23240 | 47.3% [45.9%, 48.6%] | +0.86% [+0.54%, +1.17%] | -3.8% [-4.0%, -3.7%] (24980) | 393 |
| `goals` | bets | 337 | 186 | 83 | 73.2% [63.7%, 81.0%] | +2.67% [+1.62%, +3.72%] | -1.8% [-2.8%, -0.9%] (320) | 200 |
| `goals` | best-bet bar | 9 | 5 | 1 | 62.5% [21.1%, 91.2%] | -0.13% [-8.08%, +7.82%] | -4.6% [-11.5%, +2.3%] (9) | 9 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 788 | 340 | 101 | 49.5% [44.1%, 54.9%] | -0.27% [-0.63%, +0.09%] | -2.1% [-2.5%, -1.8%] (788) | 394 |
| `moneyline` | bets | 110 | 55 | 13 | 56.7% [42.3%, 70.0%] | +0.47% [-0.64%, +1.58%] | -1.4% [-2.5%, -0.3%] (110) | 110 |
| `moneyline` | best-bet bar | 10 | 4 | 2 | 50.0% [14.4%, 85.6%] | -0.30% [-5.21%, +4.61%] | -2.5% [-7.4%, +2.3%] (10) | 10 |
| `points` | opinions | 45276 | 14009 | 11680 | 41.7% [40.6%, 42.8%] | +0.66% [-0.04%, +1.36%] | -5.2% [-5.4%, -5.0%] (34498) | 393 |
| `points` | bets | 2074 | 937 | 484 | 58.9% [54.5%, 63.2%] | +2.67% [-0.02%, +5.36%] | -0.2% [-2.9%, +2.4%] (2073) | 389 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 6634 | 2591 | 1671 | 52.2% [50.2%, 54.2%] | +0.45% [+0.16%, +0.73%] | -2.9% [-3.2%, -2.6%] (5827) | 399 |
| `puck_line` | bets | 403 | 207 | 88 | 65.7% [55.6%, 74.6%] | +0.85% [+0.02%, +1.68%] | -2.3% [-3.0%, -1.5%] (402) | 219 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 1179 | 439 | 279 | 48.8% [44.0%, 53.5%] | -0.16% [-0.48%, +0.16%] | — | 393 |
| `regulation_3_way` | bets | 257 | 116 | 57 | 58.0% [47.9%, 67.5%] | +0.41% [-0.46%, +1.28%] | — | 257 |
| `regulation_3_way` | best-bet bar | 32 | 16 | 5 | 59.3% [33.3%, 80.9%] | +1.23% [-1.66%, +4.11%] | — | 32 |
| `shots_on_goal` | opinions | 47324 | 15908 | 11936 | 45.0% [43.4%, 46.5%] | +0.26% [-0.06%, +0.57%] | -4.7% [-4.8%, -4.5%] (27325) | 393 |
| `shots_on_goal` | bets | 3427 | 1811 | 686 | 66.1% [62.6%, 69.4%] | +3.29% [+2.61%, +3.96%] | -1.0% [-1.5%, -0.6%] (2671) | 392 |
| `shots_on_goal` | best-bet bar | 438 | 284 | 66 | 76.3% [69.0%, 82.4%] | +3.90% [+2.89%, +4.90%] | +1.1% [+0.2%, +2.0%] (433) | 248 |
| `team_total` | opinions | 17821 | 6354 | 4914 | 49.2% [48.0%, 50.5%] | +0.10% [-0.02%, +0.21%] | -4.8% [-4.9%, -4.7%] (17608) | 393 |
| `team_total` | bets | 763 | 347 | 172 | 58.7% [47.0%, 69.5%] | +0.70% [-0.26%, +1.65%] | -4.4% [-5.3%, -3.5%] (763) | 178 |
| `team_total` | best-bet bar | 48 | 26 | 10 | 68.4% [32.8%, 90.6%] | +1.58% [-1.74%, +4.90%] | -4.1% [-7.1%, -1.0%] (48) | 21 |
| `total_goals` | opinions | 9887 | 3396 | 2912 | 48.7% [47.0%, 50.4%] | +0.13% [-0.05%, +0.31%] | -3.4% [-3.6%, -3.3%] (9675) | 399 |
| `total_goals` | bets | 657 | 296 | 129 | 56.1% [44.5%, 67.0%] | +0.85% [-0.11%, +1.80%] | -3.0% [-3.9%, -2.1%] (657) | 136 |
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
