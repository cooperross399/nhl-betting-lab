# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-28T14:58:14+00:00
- Opinions considered: **225099**; matched to a closing price: **215805**; no closing price found: **9294**.
- Within that count, priced before face-off but no close near face-off: **8972** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **67** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `goalie_saves` (42), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **255** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **7474** opinion(s), 361 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 215805 | 67351 | 68517 | 45.7% [45.2%, 46.2%] | +0.38% [+0.23%, +0.53%] | -4.4% [-4.5%, -4.4%] (139030) | 402 |

9294 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 9892 | 4793 | 2282 | 63.0% [61.2%, 64.8%] | +2.31% [+1.82%, +2.80%] | -1.7% [-2.2%, -1.2%] (8558) | 401 |

408 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 10% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 818 | 476 | 161 | 72.5% [67.8%, 76.6%] | +3.51% [+2.12%, +4.90%] | -0.7% [-1.3%, -0.1%] (756) | 309 |

32 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 23621 | 7641 | 6985 | 45.9% [44.6%, 47.3%] | -0.41% [-0.79%, -0.03%] | -4.1% [-4.3%, -3.9%] (14811) | 396 |
| `assists` | bets | 1116 | 480 | 308 | 59.4% [54.1%, 64.5%] | +0.90% [+0.57%, +1.24%] | -1.9% [-2.3%, -1.6%] (1111) | 377 |
| `assists` | best-bet bar | 70 | 26 | 21 | 53.1% [33.0%, 72.2%] | +0.73% [-0.48%, +1.94%] | -1.7% [-3.1%, -0.3%] (70) | 65 |
| `blocked_shots` | opinions | 1536 | 244 | 940 | 40.9% [34.7%, 47.5%] | -0.30% [-0.58%, -0.02%] | -7.8% [-8.2%, -7.5%] (775) | 195 |
| `blocked_shots` | bets | 147 | 34 | 92 | 61.8% [42.4%, 78.1%] | +0.83% [-0.19%, +1.86%] | -6.7% [-7.5%, -6.0%] (138) | 106 |
| `blocked_shots` | best-bet bar | 28 | 12 | 14 | 85.7% [47.5%, 97.6%] | +1.80% [+0.14%, +3.46%] | -5.5% [-7.0%, -4.1%] (28) | 26 |
| `goalie_saves` | opinions | 7681 | 2078 | 3388 | 48.4% [43.1%, 53.8%] | -0.27% [-0.94%, +0.40%] | -3.4% [-3.8%, -3.0%] (1464) | 246 |
| `goalie_saves` | bets | 429 | 243 | 129 | 81.0% [67.9%, 89.6%] | +5.38% [-0.20%, +10.96%] | +0.1% [-2.8%, +3.1%] (146) | 99 |
| `goalie_saves` | best-bet bar | 45 | 38 | 5 | 95.0% [74.8%, 99.2%] | +17.50% [-12.86%, +47.86%] | +8.8% [-10.1%, +27.6%] (20) | 15 |
| `goals` | opinions | 52726 | 13856 | 23419 | 47.3% [45.9%, 48.6%] | +0.86% [+0.54%, +1.17%] | -3.8% [-4.0%, -3.7%] (25180) | 396 |
| `goals` | bets | 339 | 188 | 83 | 73.4% [64.0%, 81.2%] | +2.70% [+1.65%, +3.75%] | -1.8% [-2.8%, -0.8%] (322) | 201 |
| `goals` | best-bet bar | 9 | 5 | 1 | 62.5% [21.1%, 91.2%] | -0.13% [-8.08%, +7.82%] | -4.6% [-11.5%, +2.3%] (9) | 9 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 68 | 38 | 18 | 76.0% [52.1%, 90.2%] | +2.27% [+0.59%, +3.94%] | -5.9% [-7.4%, -4.4%] (68) | 42 |
| `moneyline` | opinions | 794 | 343 | 101 | 49.5% [44.1%, 54.9%] | -0.27% [-0.63%, +0.09%] | -2.1% [-2.5%, -1.8%] (794) | 397 |
| `moneyline` | bets | 110 | 55 | 13 | 56.7% [42.3%, 70.0%] | +0.47% [-0.64%, +1.58%] | -1.4% [-2.5%, -0.3%] (110) | 110 |
| `moneyline` | best-bet bar | 10 | 4 | 2 | 50.0% [14.4%, 85.6%] | -0.30% [-5.21%, +4.61%] | -2.5% [-7.4%, +2.3%] (10) | 10 |
| `points` | opinions | 45607 | 14115 | 11750 | 41.7% [40.6%, 42.7%] | +0.65% [-0.05%, +1.34%] | -5.2% [-5.4%, -5.0%] (34758) | 396 |
| `points` | bets | 2099 | 951 | 487 | 59.0% [54.6%, 63.2%] | +2.65% [-0.01%, +5.30%] | -0.3% [-2.9%, +2.4%] (2098) | 392 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 6679 | 2610 | 1676 | 52.2% [50.1%, 54.2%] | +0.44% [+0.15%, +0.72%] | -2.9% [-3.2%, -2.6%] (5865) | 402 |
| `puck_line` | bets | 404 | 208 | 88 | 65.8% [55.7%, 74.7%] | +0.85% [+0.02%, +1.68%] | -2.3% [-3.0%, -1.5%] (403) | 220 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 1188 | 442 | 280 | 48.7% [44.0%, 53.4%] | -0.16% [-0.48%, +0.16%] | — | 396 |
| `regulation_3_way` | bets | 259 | 117 | 57 | 57.9% [47.9%, 67.4%] | +0.41% [-0.46%, +1.28%] | — | 259 |
| `regulation_3_way` | best-bet bar | 32 | 16 | 5 | 59.3% [33.3%, 80.9%] | +1.23% [-1.66%, +4.11%] | — | 32 |
| `shots_on_goal` | opinions | 47672 | 16049 | 11998 | 45.0% [43.4%, 46.5%] | +0.28% [-0.04%, +0.60%] | -4.6% [-4.8%, -4.5%] (27509) | 396 |
| `shots_on_goal` | bets | 3449 | 1817 | 690 | 65.9% [62.4%, 69.2%] | +3.26% [+2.59%, +3.93%] | -1.1% [-1.5%, -0.6%] (2690) | 395 |
| `shots_on_goal` | best-bet bar | 442 | 285 | 67 | 76.0% [68.7%, 82.0%] | +3.85% [+2.85%, +4.85%] | +1.1% [+0.1%, +2.0%] (437) | 251 |
| `team_total` | opinions | 17964 | 6411 | 4943 | 49.2% [48.0%, 50.5%] | +0.10% [-0.01%, +0.21%] | -4.8% [-4.9%, -4.7%] (17750) | 396 |
| `team_total` | bets | 763 | 347 | 172 | 58.7% [47.0%, 69.5%] | +0.70% [-0.26%, +1.65%] | -4.4% [-5.3%, -3.5%] (763) | 178 |
| `team_total` | best-bet bar | 48 | 26 | 10 | 68.4% [32.8%, 90.6%] | +1.58% [-1.74%, +4.90%] | -4.1% [-7.1%, -1.0%] (48) | 21 |
| `total_goals` | opinions | 9963 | 3428 | 2931 | 48.7% [47.0%, 50.5%] | +0.14% [-0.03%, +0.32%] | -3.4% [-3.6%, -3.3%] (9750) | 402 |
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
