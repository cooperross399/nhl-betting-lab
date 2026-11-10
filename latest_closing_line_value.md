# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-10T14:55:11+00:00
- Opinions considered: **151849**; matched to a closing price: **143910**; no closing price found: **7939**.
- Within that count, priced before face-off but no close near face-off: **7699** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **215** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **3658** opinion(s), 181 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 143910 | 45432 | 43984 | 45.5% [44.9%, 46.0%] | +0.11% [-0.03%, +0.26%] | -4.5% [-4.6%, -4.4%] (94026) | 274 |

7939 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 6467 | 3211 | 1372 | 63.0% [60.8%, 65.2%] | +2.66% [+1.93%, +3.38%] | -1.3% [-2.0%, -0.6%] (5678) | 273 |

348 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 311 | 186 | 59 | 73.8% [66.0%, 80.4%] | +4.94% [+1.50%, +8.39%] | -0.5% [-1.8%, +0.8%] (276) | 153 |

21 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 16096 | 5241 | 4598 | 45.6% [43.9%, 47.2%] | -0.58% [-1.09%, -0.06%] | -4.2% [-4.4%, -4.0%] (10073) | 268 |
| `assists` | bets | 740 | 332 | 193 | 60.7% [54.0%, 67.0%] | +1.18% [+0.75%, +1.61%] | -1.6% [-2.1%, -1.2%] (736) | 252 |
| `assists` | best-bet bar | 21 | 8 | 5 | 50.0% [20.9%, 79.1%] | +0.92% [-1.38%, +3.22%] | -1.6% [-4.1%, +0.9%] (21) | 19 |
| `blocked_shots` | opinions | 846 | 157 | 495 | 44.7% [37.1%, 52.6%] | -0.25% [-0.61%, +0.12%] | -7.9% [-8.4%, -7.5%] (459) | 120 |
| `blocked_shots` | bets | 86 | 18 | 56 | 60.0% [34.7%, 80.9%] | +0.76% [-0.75%, +2.26%] | -6.8% [-7.8%, -5.9%] (83) | 64 |
| `blocked_shots` | best-bet bar | 7 | 2 | 5 | 100.0% [19.6%, 100.0%] | +0.77% [-0.79%, +2.32%] | -6.3% [-8.7%, -3.8%] (7) | 6 |
| `goalie_saves` | opinions | 3272 | 868 | 1435 | 47.3% [40.3%, 54.3%] | -0.37% [-1.39%, +0.65%] | -3.4% [-4.0%, -2.7%] (712) | 126 |
| `goalie_saves` | bets | 174 | 97 | 47 | 76.4% [54.6%, 89.7%] | +7.85% [-5.15%, +20.85%] | +0.3% [-4.9%, +5.5%] (77) | 53 |
| `goalie_saves` | best-bet bar | 15 | 13 | 2 | 100.0% [26.8%, 100.0%] | +41.07% [-30.34%, +112.48%] | +18.3% [-33.8%, +70.3%] (7) | 4 |
| `goals` | opinions | 35489 | 9350 | 15473 | 46.7% [45.1%, 48.3%] | +0.93% [+0.55%, +1.32%] | -4.2% [-4.4%, -4.0%] (16962) | 268 |
| `goals` | bets | 223 | 124 | 51 | 72.1% [59.9%, 81.7%] | +2.36% [+1.23%, +3.48%] | -2.4% [-3.4%, -1.4%] (212) | 131 |
| `goals` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 51 | 30 | 16 | 85.7% [57.2%, 96.4%] | +2.53% [+0.71%, +4.35%] | -5.7% [-7.3%, -4.0%] (51) | 36 |
| `moneyline` | opinions | 538 | 228 | 62 | 47.9% [41.4%, 54.4%] | -0.30% [-0.75%, +0.15%] | -2.2% [-2.7%, -1.8%] (538) | 269 |
| `moneyline` | bets | 80 | 38 | 10 | 54.3% [37.7%, 70.0%] | +0.55% [-0.84%, +1.94%] | -1.3% [-2.7%, +0.0%] (80) | 80 |
| `moneyline` | best-bet bar | 8 | 4 | 1 | 57.1% [16.7%, 89.8%] | +0.36% [-5.46%, +6.17%] | -1.9% [-7.6%, +3.9%] (8) | 8 |
| `points` | opinions | 30798 | 9549 | 7729 | 41.4% [40.2%, 42.6%] | -0.41% [-1.01%, +0.19%] | -5.1% [-5.4%, -4.8%] (23431) | 268 |
| `points` | bets | 1412 | 663 | 311 | 60.2% [54.8%, 65.4%] | +3.65% [-0.24%, +7.54%] | +0.8% [-3.0%, +4.7%] (1411) | 264 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 4722 | 1836 | 1211 | 52.3% [49.9%, 54.7%] | +0.46% [+0.11%, +0.82%] | -3.0% [-3.3%, -2.6%] (4197) | 274 |
| `puck_line` | bets | 283 | 156 | 52 | 67.5% [56.1%, 77.2%] | +1.08% [+0.00%, +2.15%] | -2.3% [-3.3%, -1.3%] (283) | 150 |
| `puck_line` | best-bet bar | 14 | 9 | 2 | 75.0% [33.8%, 94.6%] | +1.76% [-1.48%, +5.01%] | -0.6% [-2.9%, +1.8%] (14) | 12 |
| `regulation_3_way` | opinions | 804 | 313 | 176 | 49.8% [44.2%, 55.5%] | -0.10% [-0.48%, +0.29%] | — | 268 |
| `regulation_3_way` | bets | 176 | 85 | 33 | 59.4% [47.5%, 70.4%] | +0.62% [-0.36%, +1.60%] | — | 176 |
| `regulation_3_way` | best-bet bar | 27 | 15 | 5 | 68.2% [38.5%, 88.0%] | +1.81% [-1.40%, +5.01%] | — | 27 |
| `shots_on_goal` | opinions | 31932 | 11015 | 7460 | 45.0% [43.2%, 46.9%] | +0.12% [-0.28%, +0.52%] | -4.7% [-4.9%, -4.6%] (18530) | 268 |
| `shots_on_goal` | bets | 2244 | 1217 | 399 | 66.0% [61.8%, 69.9%] | +3.52% [+2.67%, +4.37%] | -0.8% [-1.3%, -0.3%] (1747) | 267 |
| `shots_on_goal` | best-bet bar | 126 | 81 | 12 | 71.1% [57.8%, 81.5%] | +4.84% [+2.87%, +6.81%] | +2.1% [+0.3%, +3.9%] (126) | 96 |
| `team_total` | opinions | 12257 | 4421 | 3250 | 49.1% [47.6%, 50.6%] | +0.06% [-0.08%, +0.20%] | -4.9% [-5.0%, -4.7%] (12110) | 268 |
| `team_total` | bets | 521 | 243 | 111 | 59.3% [45.4%, 71.8%] | +0.85% [-0.36%, +2.07%] | -4.2% [-5.4%, -3.1%] (521) | 125 |
| `team_total` | best-bet bar | 30 | 20 | 7 | 87.0% [36.7%, 98.7%] | +2.86% [-1.24%, +6.97%] | -2.8% [-6.5%, +1.0%] (30) | 13 |
| `total_goals` | opinions | 6782 | 2320 | 1989 | 48.4% [46.3%, 50.5%] | +0.03% [-0.17%, +0.24%] | -3.5% [-3.7%, -3.4%] (6640) | 274 |
| `total_goals` | bets | 408 | 181 | 75 | 54.4% [40.7%, 67.4%] | +0.70% [-0.45%, +1.85%] | -3.2% [-4.2%, -2.1%] (408) | 93 |
| `total_goals` | best-bet bar | 12 | 4 | 4 | 50.0% [9.0%, 91.0%] | -0.36% [-3.22%, +2.50%] | -4.5% [-6.9%, -2.2%] (12) | 5 |

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
