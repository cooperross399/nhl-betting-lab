# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-14T13:50:30+00:00
- Opinions considered: **166724**; matched to a closing price: **158622**; no closing price found: **8102**.
- Within that count, priced before face-off but no close near face-off: **7850** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **227** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **7332** opinion(s), 373 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 158622 | 50419 | 48660 | 45.9% [45.3%, 46.4%] | +0.31% [+0.15%, +0.46%] | -4.5% [-4.6%, -4.4%] (103284) | 300 |

8102 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 7172 | 3553 | 1519 | 62.9% [60.7%, 64.9%] | +2.64% [+1.98%, +3.30%] | -1.5% [-2.1%, -0.8%] (6277) | 299 |

350 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 360 | 212 | 71 | 73.4% [66.2%, 79.4%] | +4.57% [+1.56%, +7.58%] | -0.6% [-1.8%, +0.5%] (322) | 170 |

21 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 17606 | 5780 | 5046 | 46.0% [44.4%, 47.6%] | -0.51% [-0.99%, -0.03%] | -4.1% [-4.3%, -4.0%] (11025) | 294 |
| `assists` | bets | 800 | 357 | 206 | 60.1% [53.7%, 66.2%] | +1.09% [+0.68%, +1.51%] | -1.7% [-2.1%, -1.3%] (796) | 276 |
| `assists` | best-bet bar | 22 | 8 | 5 | 47.1% [19.5%, 76.5%] | +0.63% [-1.71%, +2.97%] | -1.8% [-4.4%, +0.7%] (22) | 20 |
| `blocked_shots` | opinions | 1036 | 185 | 613 | 43.7% [36.8%, 50.9%] | -0.21% [-0.55%, +0.13%] | -7.9% [-8.3%, -7.5%] (542) | 141 |
| `blocked_shots` | bets | 101 | 22 | 63 | 57.9% [35.6%, 77.3%] | +0.69% [-0.62%, +2.01%] | -6.8% [-7.7%, -6.0%] (96) | 75 |
| `blocked_shots` | best-bet bar | 10 | 5 | 5 | 100.0% [37.9%, 100.0%] | +1.91% [-0.45%, +4.28%] | -5.3% [-7.9%, -2.8%] (10) | 9 |
| `goalie_saves` | opinions | 4227 | 1160 | 1835 | 48.5% [41.9%, 55.2%] | -0.23% [-1.11%, +0.65%] | -3.3% [-3.8%, -2.7%] (884) | 152 |
| `goalie_saves` | bets | 202 | 123 | 49 | 80.4% [59.6%, 91.9%] | +8.14% [-3.12%, +19.40%] | +0.6% [-4.0%, +5.3%] (88) | 61 |
| `goalie_saves` | best-bet bar | 15 | 13 | 2 | 100.0% [26.8%, 100.0%] | +41.07% [-30.34%, +112.48%] | +18.3% [-33.8%, +70.3%] (7) | 4 |
| `goals` | opinions | 39007 | 10356 | 17137 | 47.4% [45.8%, 48.9%] | +0.99% [+0.62%, +1.35%] | -4.1% [-4.3%, -3.9%] (18658) | 294 |
| `goals` | bets | 247 | 141 | 55 | 73.4% [62.1%, 82.3%] | +2.82% [+1.63%, +4.02%] | -2.0% [-3.1%, -0.9%] (235) | 147 |
| `goals` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 51 | 30 | 16 | 85.7% [57.2%, 96.4%] | +2.53% [+0.71%, +4.35%] | -5.7% [-7.3%, -4.0%] (51) | 36 |
| `moneyline` | opinions | 590 | 251 | 66 | 47.9% [41.7%, 54.1%] | -0.28% [-0.72%, +0.16%] | -2.2% [-2.6%, -1.8%] (590) | 295 |
| `moneyline` | bets | 90 | 43 | 10 | 53.8% [38.2%, 68.6%] | +0.50% [-0.79%, +1.79%] | -1.4% [-2.7%, -0.1%] (90) | 90 |
| `moneyline` | best-bet bar | 8 | 4 | 1 | 57.1% [16.7%, 89.8%] | +0.36% [-5.46%, +6.17%] | -1.9% [-7.6%, +3.9%] (8) | 8 |
| `points` | opinions | 33778 | 10624 | 8381 | 41.8% [40.7%, 43.0%] | +0.22% [-0.45%, +0.89%] | -5.1% [-5.4%, -4.9%] (25757) | 294 |
| `points` | bets | 1537 | 718 | 336 | 59.8% [54.6%, 64.8%] | +3.40% [-0.19%, +6.99%] | +0.5% [-3.0%, +4.1%] (1536) | 290 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 5125 | 2014 | 1279 | 52.4% [50.1%, 54.7%] | +0.46% [+0.12%, +0.80%] | -3.0% [-3.3%, -2.7%] (4539) | 300 |
| `puck_line` | bets | 309 | 167 | 55 | 65.7% [54.6%, 75.4%] | +1.01% [+0.00%, +2.01%] | -2.4% [-3.3%, -1.5%] (309) | 164 |
| `puck_line` | best-bet bar | 16 | 11 | 2 | 78.6% [39.1%, 95.4%] | +2.17% [-0.84%, +5.19%] | -0.4% [-2.5%, +1.7%] (16) | 13 |
| `regulation_3_way` | opinions | 882 | 344 | 191 | 49.8% [44.4%, 55.2%] | -0.08% [-0.45%, +0.28%] | — | 294 |
| `regulation_3_way` | bets | 196 | 91 | 38 | 57.6% [46.2%, 68.2%] | +0.52% [-0.38%, +1.42%] | — | 196 |
| `regulation_3_way` | best-bet bar | 30 | 16 | 5 | 64.0% [36.4%, 84.7%] | +1.61% [-1.30%, +4.52%] | — | 30 |
| `shots_on_goal` | opinions | 35090 | 12143 | 8208 | 45.2% [43.4%, 46.9%] | +0.26% [-0.12%, +0.64%] | -4.7% [-4.8%, -4.5%] (20325) | 294 |
| `shots_on_goal` | bets | 2506 | 1349 | 450 | 65.6% [61.7%, 69.3%] | +3.59% [+2.78%, +4.41%] | -0.9% [-1.4%, -0.4%] (1943) | 293 |
| `shots_on_goal` | best-bet bar | 146 | 95 | 14 | 72.0% [59.7%, 81.6%] | +4.75% [+2.97%, +6.53%] | +2.1% [+0.4%, +3.7%] (146) | 111 |
| `team_total` | opinions | 13468 | 4865 | 3617 | 49.4% [47.9%, 50.8%] | +0.09% [-0.05%, +0.22%] | -4.9% [-5.0%, -4.7%] (13307) | 294 |
| `team_total` | bets | 593 | 268 | 132 | 58.1% [45.1%, 70.1%] | +0.76% [-0.34%, +1.86%] | -4.3% [-5.4%, -3.3%] (593) | 139 |
| `team_total` | best-bet bar | 36 | 21 | 10 | 80.8% [37.3%, 96.7%] | +2.38% [-1.26%, +6.01%] | -3.2% [-6.6%, +0.1%] (36) | 15 |
| `total_goals` | opinions | 7439 | 2563 | 2181 | 48.7% [46.8%, 50.7%] | +0.08% [-0.12%, +0.27%] | -3.5% [-3.7%, -3.3%] (7283) | 300 |
| `total_goals` | bets | 471 | 217 | 91 | 57.1% [43.9%, 69.4%] | +0.78% [-0.23%, +1.80%] | -3.1% [-4.1%, -2.2%] (471) | 103 |
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
