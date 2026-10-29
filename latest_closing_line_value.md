# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-29T12:56:01+00:00
- Opinions considered: **105368**; matched to a closing price: **100262**; no closing price found: **5106**.
- Within that count, priced before face-off but no close near face-off: **4935** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **161** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5553** opinion(s), 274 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 100262 | 32074 | 30176 | 45.8% [45.1%, 46.4%] | +0.13% [-0.06%, +0.31%] | -4.5% [-4.6%, -4.4%] (66372) | 195 |

5106 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 4505 | 2282 | 935 | 63.9% [61.2%, 66.5%] | +2.88% [+1.95%, +3.82%] | -1.0% [-2.0%, -0.1%] (3989) | 194 |

218 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 11410 | 3670 | 3237 | 44.9% [43.1%, 46.8%] | -0.80% [-1.48%, -0.11%] | -4.3% [-4.6%, -4.1%] (7108) | 189 |
| `assists` | bets | 510 | 242 | 125 | 62.9% [55.1%, 70.0%] | +1.37% [+0.84%, +1.90%] | -1.5% [-2.1%, -0.9%] (508) | 177 |
| `blocked_shots` | opinions | 421 | 85 | 213 | 40.9% [31.6%, 50.8%] | -0.50% [-1.14%, +0.14%] | -8.0% [-8.6%, -7.3%] (258) | 70 |
| `blocked_shots` | bets | 42 | 9 | 27 | 60.0% [24.9%, 87.1%] | +0.79% [-1.81%, +3.39%] | -6.7% [-7.9%, -5.5%] (40) | 32 |
| `goalie_saves` | opinions | 1386 | 399 | 559 | 48.2% [37.9%, 58.8%] | -0.47% [-2.09%, +1.15%] | -3.6% [-4.2%, -2.9%] (307) | 55 |
| `goalie_saves` | bets | 79 | 47 | 22 | 82.5% [58.6%, 94.0%] | +5.19% [-1.97%, +12.35%] | -1.4% [-3.4%, +0.6%] (41) | 28 |
| `goals` | opinions | 24979 | 6703 | 10754 | 47.1% [45.1%, 49.1%] | +1.18% [+0.69%, +1.68%] | -4.2% [-4.4%, -4.0%] (11924) | 189 |
| `goals` | bets | 153 | 90 | 34 | 75.6% [60.6%, 86.2%] | +2.59% [+1.18%, +4.00%] | -2.1% [-3.4%, -0.9%] (146) | 90 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 380 | 162 | 39 | 47.5% [39.9%, 55.2%] | -0.25% [-0.81%, +0.30%] | -2.2% [-2.8%, -1.7%] (380) | 190 |
| `moneyline` | bets | 64 | 31 | 8 | 55.4% [36.9%, 72.5%] | +0.66% [-0.82%, +2.13%] | -1.2% [-2.6%, +0.2%] (64) | 64 |
| `points` | opinions | 21626 | 6717 | 5383 | 41.4% [39.9%, 42.8%] | -0.91% [-1.59%, -0.24%] | -5.0% [-5.4%, -4.6%] (16404) | 189 |
| `points` | bets | 993 | 477 | 215 | 61.3% [54.8%, 67.4%] | +4.85% [-0.58%, +10.29%] | +2.0% [-3.3%, +7.3%] (993) | 185 |
| `puck_line` | opinions | 3486 | 1310 | 949 | 51.6% [48.8%, 54.5%] | +0.48% [+0.04%, +0.93%] | -2.8% [-3.2%, -2.4%] (3128) | 195 |
| `puck_line` | bets | 220 | 125 | 41 | 69.8% [57.0%, 80.2%] | +1.15% [-0.18%, +2.48%] | -2.2% [-3.4%, -1.0%] (220) | 114 |
| `regulation_3_way` | opinions | 567 | 219 | 122 | 49.2% [42.5%, 56.0%] | -0.09% [-0.55%, +0.36%] | — | 189 |
| `regulation_3_way` | bets | 130 | 63 | 23 | 58.9% [45.1%, 71.4%] | +0.62% [-0.50%, +1.74%] | — | 130 |
| `shots_on_goal` | opinions | 21908 | 7787 | 5092 | 46.3% [44.1%, 48.5%] | +0.47% [+0.00%, +0.93%] | -4.7% [-4.8%, -4.5%] (12971) | 189 |
| `shots_on_goal` | bets | 1536 | 819 | 278 | 65.1% [60.0%, 69.9%] | +3.54% [+2.51%, +4.58%] | -0.8% [-1.4%, -0.1%] (1199) | 188 |
| `team_total` | opinions | 8916 | 3216 | 2334 | 48.9% [47.1%, 50.6%] | +0.07% [-0.10%, +0.24%] | -4.9% [-5.1%, -4.7%] (8813) | 189 |
| `team_total` | bets | 407 | 207 | 87 | 64.7% [48.6%, 78.0%] | +1.18% [-0.25%, +2.62%] | -4.0% [-5.4%, -2.6%] (407) | 92 |
| `total_goals` | opinions | 4809 | 1672 | 1388 | 48.9% [46.4%, 51.3%] | +0.07% [-0.17%, +0.31%] | -3.5% [-3.7%, -3.3%] (4705) | 195 |
| `total_goals` | bets | 251 | 115 | 41 | 54.8% [38.0%, 70.6%] | +0.79% [-0.87%, +2.44%] | -3.1% [-4.6%, -1.6%] (251) | 57 |

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
