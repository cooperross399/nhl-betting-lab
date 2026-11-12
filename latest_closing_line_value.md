# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-12T22:42:44+00:00
- Opinions considered: **159880**; matched to a closing price: **151857**; no closing price found: **8023**.
- Within that count, priced before face-off but no close near face-off: **7777** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **221** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5728** opinion(s), 285 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 151857 | 48102 | 46580 | 45.7% [45.1%, 46.3%] | +0.23% [+0.08%, +0.39%] | -4.5% [-4.6%, -4.4%] (99043) | 288 |

8023 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 6835 | 3392 | 1449 | 63.0% [60.8%, 65.1%] | +2.68% [+1.99%, +3.37%] | -1.4% [-2.0%, -0.7%] (5989) | 287 |

349 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 343 | 204 | 66 | 73.6% [66.4%, 79.8%] | +4.73% [+1.58%, +7.88%] | -0.5% [-1.7%, +0.7%] (305) | 164 |

21 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 16920 | 5538 | 4846 | 45.9% [44.2%, 47.5%] | -0.54% [-1.03%, -0.04%] | -4.1% [-4.3%, -4.0%] (10589) | 282 |
| `assists` | bets | 775 | 347 | 199 | 60.2% [53.8%, 66.4%] | +1.12% [+0.70%, +1.55%] | -1.7% [-2.1%, -1.2%] (771) | 265 |
| `assists` | best-bet bar | 22 | 8 | 5 | 47.1% [19.5%, 76.5%] | +0.63% [-1.71%, +2.97%] | -1.8% [-4.4%, +0.7%] (22) | 20 |
| `blocked_shots` | opinions | 944 | 173 | 551 | 44.0% [36.7%, 51.6%] | -0.26% [-0.59%, +0.07%] | -7.9% [-8.3%, -7.5%] (509) | 132 |
| `blocked_shots` | bets | 93 | 20 | 59 | 58.8% [35.3%, 78.9%] | +0.71% [-0.70%, +2.11%] | -6.9% [-7.8%, -6.0%] (90) | 69 |
| `blocked_shots` | best-bet bar | 8 | 3 | 5 | 100.0% [26.8%, 100.0%] | +1.26% [-0.77%, +3.29%] | -6.0% [-8.3%, -3.7%] (8) | 7 |
| `goalie_saves` | opinions | 3783 | 992 | 1687 | 47.3% [40.8%, 53.9%] | -0.31% [-1.24%, +0.61%] | -3.3% [-3.9%, -2.8%] (805) | 140 |
| `goalie_saves` | bets | 196 | 117 | 49 | 79.6% [58.1%, 91.6%] | +8.27% [-3.33%, +19.87%] | +0.6% [-4.3%, +5.5%] (83) | 57 |
| `goalie_saves` | best-bet bar | 15 | 13 | 2 | 100.0% [26.8%, 100.0%] | +41.07% [-30.34%, +112.48%] | +18.3% [-33.8%, +70.3%] (7) | 4 |
| `goals` | opinions | 37380 | 9899 | 16371 | 47.1% [45.6%, 48.7%] | +0.99% [+0.62%, +1.37%] | -4.1% [-4.3%, -4.0%] (17874) | 282 |
| `goals` | bets | 235 | 134 | 52 | 73.2% [61.5%, 82.4%] | +2.73% [+1.49%, +3.96%] | -2.1% [-3.2%, -0.9%] (224) | 139 |
| `goals` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 51 | 30 | 16 | 85.7% [57.2%, 96.4%] | +2.53% [+0.71%, +4.35%] | -5.7% [-7.3%, -4.0%] (51) | 36 |
| `moneyline` | opinions | 566 | 241 | 63 | 47.9% [41.6%, 54.3%] | -0.30% [-0.74%, +0.14%] | -2.2% [-2.7%, -1.8%] (566) | 283 |
| `moneyline` | bets | 85 | 41 | 10 | 54.7% [38.6%, 69.8%] | +0.53% [-0.80%, +1.85%] | -1.4% [-2.7%, -0.1%] (85) | 85 |
| `moneyline` | best-bet bar | 8 | 4 | 1 | 57.1% [16.7%, 89.8%] | +0.36% [-5.46%, +6.17%] | -1.9% [-7.6%, +3.9%] (8) | 8 |
| `points` | opinions | 32416 | 10139 | 8076 | 41.7% [40.5%, 42.8%] | -0.04% [-0.69%, +0.61%] | -5.1% [-5.4%, -4.8%] (24689) | 282 |
| `points` | bets | 1475 | 685 | 323 | 59.5% [54.1%, 64.6%] | +3.51% [-0.22%, +7.24%] | +0.7% [-3.0%, +4.3%] (1474) | 278 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 4939 | 1929 | 1247 | 52.2% [49.9%, 54.6%] | +0.46% [+0.12%, +0.81%] | -3.0% [-3.3%, -2.7%] (4381) | 288 |
| `puck_line` | bets | 297 | 163 | 53 | 66.8% [55.5%, 76.5%] | +1.05% [+0.02%, +2.09%] | -2.3% [-3.3%, -1.4%] (297) | 156 |
| `puck_line` | best-bet bar | 16 | 11 | 2 | 78.6% [39.1%, 95.4%] | +2.17% [-0.84%, +5.19%] | -0.4% [-2.5%, +1.7%] (16) | 13 |
| `regulation_3_way` | opinions | 846 | 329 | 184 | 49.7% [44.2%, 55.2%] | -0.10% [-0.47%, +0.27%] | — | 282 |
| `regulation_3_way` | bets | 187 | 89 | 37 | 59.3% [47.6%, 70.0%] | +0.62% [-0.31%, +1.55%] | — | 187 |
| `regulation_3_way` | best-bet bar | 30 | 16 | 5 | 64.0% [36.4%, 84.7%] | +1.61% [-1.30%, +4.52%] | — | 30 |
| `shots_on_goal` | opinions | 33650 | 11624 | 7905 | 45.2% [43.4%, 46.9%] | +0.20% [-0.19%, +0.59%] | -4.7% [-4.9%, -4.6%] (19521) | 282 |
| `shots_on_goal` | bets | 2395 | 1296 | 431 | 66.0% [62.0%, 69.8%] | +3.58% [+2.75%, +4.40%] | -0.8% [-1.3%, -0.3%] (1868) | 281 |
| `shots_on_goal` | best-bet bar | 140 | 91 | 14 | 72.2% [59.7%, 82.0%] | +4.87% [+3.05%, +6.70%] | +2.2% [+0.5%, +3.9%] (140) | 107 |
| `team_total` | opinions | 12905 | 4656 | 3451 | 49.2% [47.8%, 50.7%] | +0.08% [-0.06%, +0.21%] | -4.9% [-5.0%, -4.7%] (12750) | 282 |
| `team_total` | bets | 553 | 255 | 122 | 59.2% [45.7%, 71.4%] | +0.82% [-0.34%, +1.99%] | -4.3% [-5.4%, -3.2%] (553) | 131 |
| `team_total` | best-bet bar | 35 | 21 | 9 | 80.8% [37.3%, 96.7%] | +2.44% [-1.29%, +6.18%] | -3.1% [-6.5%, +0.3%] (35) | 14 |
| `total_goals` | opinions | 7134 | 2448 | 2093 | 48.6% [46.5%, 50.6%] | +0.06% [-0.14%, +0.26%] | -3.5% [-3.7%, -3.3%] (6985) | 288 |
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
