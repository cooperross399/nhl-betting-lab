# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-26T14:09:24+00:00
- Opinions considered: **94676**; matched to a closing price: **89794**; no closing price found: **4882**.
- Within that count, priced before face-off but no close near face-off: **4717** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **155** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1562** opinion(s), 76 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 89794 | 28565 | 27326 | 45.7% [45.0%, 46.4%] | +0.26% [+0.09%, +0.42%] | -4.5% [-4.6%, -4.4%] (59916) | 177 |

4882 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 4048 | 2048 | 845 | 63.9% [61.0%, 66.8%] | +2.99% [+1.96%, +4.02%] | -0.9% [-2.0%, +0.2%] (3584) | 176 |

214 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 10182 | 3262 | 2947 | 45.1% [43.2%, 47.0%] | -0.36% [-0.76%, +0.04%] | -4.4% [-4.7%, -4.2%] (6403) | 171 |
| `assists` | bets | 453 | 215 | 111 | 62.9% [54.9%, 70.2%] | +1.43% [+0.86%, +2.00%] | -1.5% [-2.1%, -0.9%] (451) | 159 |
| `blocked_shots` | opinions | 290 | 69 | 128 | 42.6% [31.5%, 54.5%] | -0.49% [-1.39%, +0.42%] | -8.0% [-8.9%, -7.1%] (186) | 53 |
| `blocked_shots` | bets | 24 | 8 | 14 | 80.0% [36.4%, 96.5%] | +2.08% [-2.09%, +6.24%] | -6.2% [-7.9%, -4.4%] (23) | 21 |
| `goalie_saves` | opinions | 864 | 238 | 345 | 45.9% [33.3%, 58.9%] | -0.86% [-3.12%, +1.40%] | -3.9% [-4.9%, -3.0%] (192) | 37 |
| `goalie_saves` | bets | 65 | 40 | 18 | 85.1% [57.8%, 96.0%] | +5.99% [-2.62%, +14.60%] | -1.7% [-4.6%, +1.1%] (27) | 20 |
| `goals` | opinions | 22620 | 6059 | 9780 | 47.2% [45.1%, 49.3%] | +1.23% [+0.71%, +1.76%] | -4.2% [-4.4%, -4.0%] (10780) | 171 |
| `goals` | bets | 142 | 82 | 32 | 74.5% [58.6%, 85.8%] | +2.59% [+1.07%, +4.10%] | -2.1% [-3.4%, -0.8%] (136) | 81 |
| `hits` | opinions | 340 | 125 | 90 | 50.0% [41.1%, 58.9%] | +0.04% [-0.62%, +0.70%] | -7.9% [-8.5%, -7.3%] (340) | 64 |
| `hits` | bets | 111 | 53 | 31 | 66.2% [45.7%, 82.1%] | +1.07% [-0.38%, +2.52%] | -7.0% [-8.3%, -5.7%] (111) | 56 |
| `moneyline` | opinions | 344 | 146 | 37 | 47.6% [39.6%, 55.7%] | -0.27% [-0.84%, +0.30%] | -2.2% [-2.8%, -1.7%] (344) | 172 |
| `moneyline` | bets | 61 | 30 | 7 | 55.6% [36.8%, 72.9%] | +0.68% [-0.85%, +2.22%] | -1.2% [-2.7%, +0.3%] (61) | 61 |
| `points` | opinions | 19280 | 5998 | 4844 | 41.5% [40.1%, 43.1%] | -0.41% [-0.92%, +0.10%] | -5.0% [-5.5%, -4.6%] (14813) | 171 |
| `points` | bets | 897 | 424 | 195 | 60.4% [53.4%, 67.0%] | +5.24% [-0.74%, +11.22%] | +2.3% [-3.6%, +8.2%] (897) | 167 |
| `puck_line` | opinions | 3203 | 1179 | 913 | 51.5% [48.5%, 54.5%] | +0.49% [+0.03%, +0.95%] | -2.8% [-3.2%, -2.3%] (2883) | 177 |
| `puck_line` | bets | 208 | 114 | 41 | 68.3% [54.8%, 79.2%] | +1.10% [-0.31%, +2.50%] | -2.3% [-3.5%, -1.0%] (208) | 107 |
| `regulation_3_way` | opinions | 513 | 196 | 111 | 48.8% [41.7%, 55.9%] | -0.12% [-0.59%, +0.35%] | — | 171 |
| `regulation_3_way` | bets | 121 | 60 | 22 | 60.6% [46.2%, 73.3%] | +0.79% [-0.37%, +1.95%] | — | 121 |
| `shots_on_goal` | opinions | 19732 | 6912 | 4663 | 45.9% [43.6%, 48.2%] | +0.27% [-0.18%, +0.73%] | -4.7% [-4.9%, -4.5%] (11743) | 171 |
| `shots_on_goal` | bets | 1375 | 734 | 255 | 65.5% [60.1%, 70.6%] | +3.48% [+2.44%, +4.52%] | -0.6% [-1.4%, +0.1%] (1079) | 170 |
| `team_total` | opinions | 8071 | 2866 | 2202 | 48.8% [47.0%, 50.7%] | +0.07% [-0.11%, +0.25%] | -4.9% [-5.1%, -4.7%] (7972) | 171 |
| `team_total` | bets | 379 | 189 | 84 | 64.1% [47.2%, 78.0%] | +1.22% [-0.30%, +2.75%] | -3.9% [-5.4%, -2.4%] (379) | 85 |
| `total_goals` | opinions | 4355 | 1515 | 1266 | 49.0% [46.5%, 51.6%] | +0.07% [-0.19%, +0.32%] | -3.5% [-3.8%, -3.3%] (4260) | 177 |
| `total_goals` | bets | 212 | 99 | 35 | 55.9% [38.0%, 72.4%] | +1.02% [-0.66%, +2.69%] | -2.9% [-4.4%, -1.5%] (212) | 51 |

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
