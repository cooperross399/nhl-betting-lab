# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-11T14:54:53+00:00
- Opinions considered: **155830**; matched to a closing price: **147838**; no closing price found: **7992**.
- Within that count, priced before face-off but no close near face-off: **7748** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **219** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **3184** opinion(s), 123 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 147838 | 46828 | 45112 | 45.6% [45.0%, 46.2%] | +0.17% [+0.02%, +0.33%] | -4.5% [-4.6%, -4.4%] (96472) | 281 |

7992 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 6654 | 3303 | 1404 | 62.9% [60.7%, 65.1%] | +2.67% [+1.96%, +3.37%] | -1.4% [-2.0%, -0.7%] (5842) | 280 |

349 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 333 | 197 | 65 | 73.5% [66.1%, 79.8%] | +4.80% [+1.56%, +8.04%] | -0.5% [-1.7%, +0.8%] (295) | 158 |

21 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 16495 | 5407 | 4705 | 45.9% [44.2%, 47.5%] | -0.53% [-1.04%, -0.03%] | -4.1% [-4.3%, -4.0%] (10321) | 275 |
| `assists` | bets | 752 | 338 | 194 | 60.6% [54.0%, 66.8%] | +1.17% [+0.74%, +1.60%] | -1.6% [-2.1%, -1.2%] (748) | 258 |
| `assists` | best-bet bar | 22 | 8 | 5 | 47.1% [19.5%, 76.5%] | +0.63% [-1.71%, +2.97%] | -1.8% [-4.4%, +0.7%] (22) | 20 |
| `blocked_shots` | opinions | 907 | 170 | 527 | 44.7% [37.5%, 52.2%] | -0.25% [-0.60%, +0.09%] | -7.9% [-8.4%, -7.5%] (491) | 127 |
| `blocked_shots` | bets | 90 | 19 | 58 | 59.4% [34.9%, 79.9%] | +0.73% [-0.72%, +2.18%] | -6.8% [-7.8%, -5.9%] (87) | 67 |
| `blocked_shots` | best-bet bar | 8 | 3 | 5 | 100.0% [26.8%, 100.0%] | +1.26% [-0.77%, +3.29%] | -6.0% [-8.3%, -3.7%] (8) | 7 |
| `goalie_saves` | opinions | 3531 | 921 | 1551 | 46.5% [39.9%, 53.2%] | -0.44% [-1.41%, +0.52%] | -3.4% [-4.0%, -2.8%] (759) | 133 |
| `goalie_saves` | bets | 178 | 99 | 49 | 76.7% [55.3%, 89.8%] | +7.75% [-4.96%, +20.46%] | +0.3% [-4.7%, +5.2%] (81) | 56 |
| `goalie_saves` | best-bet bar | 15 | 13 | 2 | 100.0% [26.8%, 100.0%] | +41.07% [-30.34%, +112.48%] | +18.3% [-33.8%, +70.3%] (7) | 4 |
| `goals` | opinions | 36438 | 9643 | 15883 | 46.9% [45.3%, 48.5%] | +0.96% [+0.57%, +1.34%] | -4.2% [-4.3%, -4.0%] (17417) | 275 |
| `goals` | bets | 230 | 131 | 51 | 73.2% [61.2%, 82.5%] | +2.53% [+1.40%, +3.66%] | -2.3% [-3.3%, -1.3%] (219) | 135 |
| `goals` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 51 | 30 | 16 | 85.7% [57.2%, 96.4%] | +2.53% [+0.71%, +4.35%] | -5.7% [-7.3%, -4.0%] (51) | 36 |
| `moneyline` | opinions | 552 | 236 | 62 | 48.2% [41.8%, 54.6%] | -0.29% [-0.74%, +0.16%] | -2.2% [-2.7%, -1.8%] (552) | 276 |
| `moneyline` | bets | 84 | 40 | 10 | 54.1% [37.9%, 69.4%] | +0.52% [-0.82%, +1.86%] | -1.4% [-2.7%, -0.1%] (84) | 84 |
| `moneyline` | best-bet bar | 8 | 4 | 1 | 57.1% [16.7%, 89.8%] | +0.36% [-5.46%, +6.17%] | -1.9% [-7.6%, +3.9%] (8) | 8 |
| `points` | opinions | 31582 | 9867 | 7867 | 41.6% [40.4%, 42.8%] | -0.22% [-0.84%, +0.41%] | -5.1% [-5.4%, -4.8%] (24038) | 275 |
| `points` | bets | 1440 | 676 | 313 | 60.0% [54.6%, 65.1%] | +3.61% [-0.21%, +7.42%] | +0.8% [-3.0%, +4.5%] (1439) | 271 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 4828 | 1882 | 1224 | 52.2% [49.8%, 54.6%] | +0.45% [+0.10%, +0.80%] | -3.0% [-3.3%, -2.6%] (4285) | 281 |
| `puck_line` | bets | 293 | 159 | 53 | 66.2% [54.8%, 76.1%] | +1.01% [-0.04%, +2.06%] | -2.4% [-3.3%, -1.4%] (293) | 154 |
| `puck_line` | best-bet bar | 14 | 9 | 2 | 75.0% [33.8%, 94.6%] | +1.76% [-1.48%, +5.01%] | -0.6% [-2.9%, +1.8%] (14) | 12 |
| `regulation_3_way` | opinions | 825 | 323 | 180 | 50.1% [44.5%, 55.7%] | -0.07% [-0.45%, +0.31%] | — | 275 |
| `regulation_3_way` | bets | 182 | 88 | 34 | 59.5% [47.7%, 70.2%] | +0.64% [-0.32%, +1.59%] | — | 182 |
| `regulation_3_way` | best-bet bar | 30 | 16 | 5 | 64.0% [36.4%, 84.7%] | +1.61% [-1.30%, +4.52%] | — | 30 |
| `shots_on_goal` | opinions | 32780 | 11310 | 7646 | 45.0% [43.2%, 46.8%] | +0.15% [-0.24%, +0.55%] | -4.7% [-4.9%, -4.6%] (19004) | 275 |
| `shots_on_goal` | bets | 2317 | 1257 | 410 | 65.9% [61.8%, 69.8%] | +3.59% [+2.74%, +4.43%] | -0.8% [-1.3%, -0.3%] (1803) | 274 |
| `shots_on_goal` | best-bet bar | 132 | 86 | 13 | 72.3% [59.3%, 82.3%] | +5.06% [+3.14%, +6.98%] | +2.4% [+0.6%, +4.1%] (132) | 101 |
| `team_total` | opinions | 12569 | 4546 | 3327 | 49.2% [47.7%, 50.7%] | +0.07% [-0.07%, +0.21%] | -4.9% [-5.0%, -4.7%] (12419) | 275 |
| `team_total` | bets | 544 | 251 | 118 | 58.9% [45.4%, 71.2%] | +0.82% [-0.37%, +2.00%] | -4.3% [-5.4%, -3.1%] (544) | 129 |
| `team_total` | best-bet bar | 35 | 21 | 9 | 80.8% [37.3%, 96.7%] | +2.44% [-1.29%, +6.18%] | -3.1% [-6.5%, +0.3%] (35) | 14 |
| `total_goals` | opinions | 6957 | 2389 | 2034 | 48.5% [46.5%, 50.6%] | +0.05% [-0.15%, +0.26%] | -3.5% [-3.7%, -3.3%] (6812) | 281 |
| `total_goals` | bets | 424 | 188 | 80 | 54.7% [41.1%, 67.5%] | +0.70% [-0.41%, +1.81%] | -3.2% [-4.2%, -2.2%] (424) | 95 |
| `total_goals` | best-bet bar | 18 | 7 | 7 | 63.6% [15.5%, 94.3%] | +0.02% [-2.24%, +2.28%] | -4.0% [-6.2%, -1.7%] (18) | 6 |

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
