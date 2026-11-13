# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-13T20:46:39+00:00
- Opinions considered: **165608**; matched to a closing price: **157513**; no closing price found: **8095**.
- Within that count, priced before face-off but no close near face-off: **7845** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **225** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1107** opinion(s), 52 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 157513 | 50056 | 48266 | 45.8% [45.3%, 46.4%] | +0.31% [+0.15%, +0.47%] | -4.5% [-4.6%, -4.4%] (102579) | 298 |

8095 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 7119 | 3524 | 1508 | 62.8% [60.7%, 64.9%] | +2.65% [+1.99%, +3.32%] | -1.4% [-2.1%, -0.8%] (6232) | 297 |

350 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 357 | 209 | 71 | 73.1% [65.9%, 79.2%] | +4.57% [+1.54%, +7.60%] | -0.6% [-1.8%, +0.6%] (319) | 168 |

21 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 17490 | 5738 | 5007 | 46.0% [44.4%, 47.6%] | -0.52% [-1.00%, -0.04%] | -4.1% [-4.3%, -4.0%] (10951) | 292 |
| `assists` | bets | 794 | 354 | 204 | 60.0% [53.6%, 66.1%] | +1.10% [+0.68%, +1.52%] | -1.7% [-2.1%, -1.3%] (790) | 274 |
| `assists` | best-bet bar | 22 | 8 | 5 | 47.1% [19.5%, 76.5%] | +0.63% [-1.71%, +2.97%] | -1.8% [-4.4%, +0.7%] (22) | 20 |
| `blocked_shots` | opinions | 1021 | 183 | 606 | 44.1% [37.1%, 51.3%] | -0.19% [-0.53%, +0.15%] | -7.9% [-8.3%, -7.5%] (532) | 139 |
| `blocked_shots` | bets | 99 | 20 | 63 | 55.6% [33.1%, 76.0%] | +0.62% [-0.71%, +1.94%] | -6.9% [-7.8%, -6.1%] (94) | 73 |
| `blocked_shots` | best-bet bar | 8 | 3 | 5 | 100.0% [26.8%, 100.0%] | +1.26% [-0.77%, +3.29%] | -6.0% [-8.3%, -3.7%] (8) | 7 |
| `goalie_saves` | opinions | 4142 | 1140 | 1804 | 48.8% [42.0%, 55.5%] | -0.21% [-1.11%, +0.68%] | -3.3% [-3.8%, -2.7%] (868) | 150 |
| `goalie_saves` | bets | 200 | 121 | 49 | 80.1% [59.1%, 91.8%] | +8.20% [-3.17%, +19.57%] | +0.7% [-4.1%, +5.4%] (86) | 59 |
| `goalie_saves` | best-bet bar | 15 | 13 | 2 | 100.0% [26.8%, 100.0%] | +41.07% [-30.34%, +112.48%] | +18.3% [-33.8%, +70.3%] (7) | 4 |
| `goals` | opinions | 38750 | 10292 | 16998 | 47.3% [45.8%, 48.9%] | +0.99% [+0.63%, +1.36%] | -4.1% [-4.3%, -3.9%] (18533) | 292 |
| `goals` | bets | 246 | 141 | 55 | 73.8% [62.5%, 82.7%] | +2.84% [+1.64%, +4.04%] | -2.0% [-3.1%, -0.9%] (234) | 146 |
| `goals` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 51 | 30 | 16 | 85.7% [57.2%, 96.4%] | +2.53% [+0.71%, +4.35%] | -5.7% [-7.3%, -4.0%] (51) | 36 |
| `moneyline` | opinions | 586 | 249 | 66 | 47.9% [41.7%, 54.1%] | -0.28% [-0.72%, +0.16%] | -2.2% [-2.7%, -1.8%] (586) | 293 |
| `moneyline` | bets | 90 | 43 | 10 | 53.8% [38.2%, 68.6%] | +0.50% [-0.79%, +1.79%] | -1.4% [-2.7%, -0.1%] (90) | 90 |
| `moneyline` | best-bet bar | 8 | 4 | 1 | 57.1% [16.7%, 89.8%] | +0.36% [-5.46%, +6.17%] | -1.9% [-7.6%, +3.9%] (8) | 8 |
| `points` | opinions | 33549 | 10530 | 8323 | 41.7% [40.6%, 42.9%] | +0.22% [-0.45%, +0.89%] | -5.1% [-5.4%, -4.9%] (25581) | 292 |
| `points` | bets | 1522 | 707 | 334 | 59.5% [54.3%, 64.5%] | +3.42% [-0.20%, +7.04%] | +0.6% [-3.0%, +4.1%] (1521) | 288 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 5093 | 2003 | 1270 | 52.4% [50.1%, 54.7%] | +0.46% [+0.12%, +0.80%] | -3.0% [-3.3%, -2.7%] (4511) | 298 |
| `puck_line` | bets | 308 | 166 | 55 | 65.6% [54.4%, 75.3%] | +1.01% [-0.00%, +2.01%] | -2.4% [-3.3%, -1.5%] (308) | 163 |
| `puck_line` | best-bet bar | 16 | 11 | 2 | 78.6% [39.1%, 95.4%] | +2.17% [-0.84%, +5.19%] | -0.4% [-2.5%, +1.7%] (16) | 13 |
| `regulation_3_way` | opinions | 876 | 340 | 190 | 49.6% [44.1%, 55.0%] | -0.10% [-0.47%, +0.27%] | — | 292 |
| `regulation_3_way` | bets | 195 | 91 | 38 | 58.0% [46.6%, 68.6%] | +0.54% [-0.37%, +1.44%] | — | 195 |
| `regulation_3_way` | best-bet bar | 30 | 16 | 5 | 64.0% [36.4%, 84.7%] | +1.61% [-1.30%, +4.52%] | — | 30 |
| `shots_on_goal` | opinions | 34869 | 12071 | 8149 | 45.2% [43.4%, 46.9%] | +0.26% [-0.12%, +0.65%] | -4.7% [-4.8%, -4.6%] (20195) | 292 |
| `shots_on_goal` | bets | 2486 | 1341 | 444 | 65.7% [61.7%, 69.4%] | +3.62% [+2.80%, +4.44%] | -0.9% [-1.4%, -0.4%] (1930) | 291 |
| `shots_on_goal` | best-bet bar | 145 | 94 | 14 | 71.8% [59.4%, 81.5%] | +4.74% [+2.95%, +6.53%] | +2.1% [+0.4%, +3.7%] (145) | 110 |
| `team_total` | opinions | 13376 | 4835 | 3586 | 49.4% [47.9%, 50.8%] | +0.08% [-0.05%, +0.22%] | -4.9% [-5.0%, -4.7%] (13215) | 292 |
| `team_total` | bets | 592 | 267 | 132 | 58.0% [45.0%, 70.0%] | +0.76% [-0.34%, +1.86%] | -4.3% [-5.4%, -3.3%] (592) | 138 |
| `team_total` | best-bet bar | 36 | 21 | 10 | 80.8% [37.3%, 96.7%] | +2.38% [-1.26%, +6.01%] | -3.2% [-6.6%, +0.1%] (36) | 15 |
| `total_goals` | opinions | 7387 | 2541 | 2161 | 48.6% [46.6%, 50.6%] | +0.07% [-0.12%, +0.27%] | -3.5% [-3.7%, -3.3%] (7233) | 298 |
| `total_goals` | bets | 467 | 216 | 90 | 57.3% [44.0%, 69.6%] | +0.80% [-0.23%, +1.82%] | -3.1% [-4.1%, -2.2%] (467) | 102 |
| `total_goals` | best-bet bar | 26 | 9 | 11 | 60.0% [17.7%, 91.3%] | +0.12% [-1.53%, +1.77%] | -3.9% [-5.5%, -2.3%] (26) | 8 |

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
- **Bets**: A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.
- **Best-bet bar**: The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
