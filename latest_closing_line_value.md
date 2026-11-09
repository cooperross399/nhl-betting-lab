# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-09T14:58:58+00:00
- Opinions considered: **150143**; matched to a closing price: **142215**; no closing price found: **7928**.
- Within that count, priced before face-off but no close near face-off: **7689** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **214** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1613** opinion(s), 53 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 142215 | 44928 | 43472 | 45.5% [44.9%, 46.1%] | +0.12% [-0.03%, +0.27%] | -4.5% [-4.6%, -4.4%] (92952) | 271 |

7928 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 6413 | 3181 | 1361 | 63.0% [60.7%, 65.2%] | +2.66% [+1.93%, +3.39%] | -1.3% [-2.1%, -0.6%] (5628) | 270 |

348 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 15915 | 5166 | 4562 | 45.5% [43.8%, 47.2%] | -0.58% [-1.10%, -0.06%] | -4.2% [-4.3%, -4.0%] (9955) | 265 |
| `assists` | bets | 732 | 326 | 192 | 60.4% [53.7%, 66.7%] | +1.15% [+0.72%, +1.59%] | -1.6% [-2.1%, -1.2%] (728) | 249 |
| `blocked_shots` | opinions | 825 | 152 | 482 | 44.3% [36.8%, 52.1%] | -0.27% [-0.64%, +0.10%] | -7.9% [-8.4%, -7.5%] (447) | 117 |
| `blocked_shots` | bets | 85 | 18 | 55 | 60.0% [34.7%, 80.9%] | +0.77% [-0.75%, +2.29%] | -6.8% [-7.8%, -5.9%] (82) | 63 |
| `goalie_saves` | opinions | 3182 | 857 | 1378 | 47.5% [40.5%, 54.6%] | -0.44% [-1.46%, +0.57%] | -3.4% [-4.0%, -2.7%] (692) | 123 |
| `goalie_saves` | bets | 174 | 97 | 47 | 76.4% [54.6%, 89.7%] | +7.85% [-5.15%, +20.85%] | +0.3% [-4.9%, +5.5%] (77) | 53 |
| `goals` | opinions | 35089 | 9240 | 15308 | 46.7% [45.1%, 48.3%] | +0.94% [+0.54%, +1.33%] | -4.2% [-4.4%, -4.0%] (16768) | 265 |
| `goals` | bets | 223 | 124 | 51 | 72.1% [59.9%, 81.7%] | +2.36% [+1.23%, +3.48%] | -2.4% [-3.4%, -1.4%] (212) | 131 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 532 | 226 | 61 | 48.0% [41.5%, 54.6%] | -0.30% [-0.76%, +0.16%] | -2.2% [-2.7%, -1.8%] (532) | 266 |
| `moneyline` | bets | 80 | 38 | 10 | 54.3% [37.7%, 70.0%] | +0.55% [-0.84%, +1.94%] | -1.3% [-2.7%, +0.0%] (80) | 80 |
| `points` | opinions | 30447 | 9435 | 7646 | 41.4% [40.2%, 42.6%] | -0.41% [-1.02%, +0.20%] | -5.1% [-5.4%, -4.8%] (23167) | 265 |
| `points` | bets | 1398 | 654 | 308 | 60.0% [54.6%, 65.2%] | +3.67% [-0.25%, +7.60%] | +0.9% [-3.0%, +4.7%] (1397) | 261 |
| `puck_line` | opinions | 4675 | 1819 | 1196 | 52.3% [49.9%, 54.7%] | +0.46% [+0.10%, +0.82%] | -3.0% [-3.3%, -2.6%] (4156) | 271 |
| `puck_line` | bets | 283 | 156 | 52 | 67.5% [56.1%, 77.2%] | +1.08% [+0.00%, +2.15%] | -2.3% [-3.3%, -1.3%] (283) | 150 |
| `regulation_3_way` | opinions | 795 | 309 | 175 | 49.8% [44.1%, 55.6%] | -0.09% [-0.48%, +0.29%] | — | 265 |
| `regulation_3_way` | bets | 176 | 85 | 33 | 59.4% [47.5%, 70.4%] | +0.62% [-0.36%, +1.60%] | — | 176 |
| `shots_on_goal` | opinions | 31557 | 10919 | 7396 | 45.2% [43.4%, 47.0%] | +0.15% [-0.25%, +0.56%] | -4.7% [-4.9%, -4.6%] (18322) | 265 |
| `shots_on_goal` | bets | 2213 | 1202 | 393 | 66.0% [61.8%, 70.0%] | +3.53% [+2.66%, +4.39%] | -0.8% [-1.4%, -0.3%] (1720) | 264 |
| `team_total` | opinions | 12117 | 4371 | 3203 | 49.0% [47.5%, 50.6%] | +0.06% [-0.08%, +0.20%] | -4.9% [-5.0%, -4.7%] (11971) | 265 |
| `team_total` | bets | 521 | 243 | 111 | 59.3% [45.4%, 71.8%] | +0.85% [-0.36%, +2.07%] | -4.2% [-5.4%, -3.1%] (521) | 125 |
| `total_goals` | opinions | 6707 | 2300 | 1959 | 48.4% [46.4%, 50.5%] | +0.04% [-0.16%, +0.25%] | -3.5% [-3.7%, -3.4%] (6568) | 271 |
| `total_goals` | bets | 408 | 181 | 75 | 54.4% [40.7%, 67.4%] | +0.70% [-0.45%, +1.85%] | -3.2% [-4.2%, -2.1%] (408) | 93 |

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
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
