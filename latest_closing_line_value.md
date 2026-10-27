# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-27T20:49:43+00:00
- Opinions considered: **96330**; matched to a closing price: **91432**; no closing price found: **4898**.
- Within that count, priced before face-off but no close near face-off: **4733** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **155** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **6602** opinion(s), 281 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 91432 | 29098 | 27800 | 45.7% [45.0%, 46.4%] | +0.27% [+0.10%, +0.43%] | -4.5% [-4.6%, -4.4%] (60964) | 180 |

4898 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 4129 | 2093 | 861 | 64.0% [61.2%, 66.8%] | +2.97% [+1.96%, +3.99%] | -0.9% [-2.0%, +0.1%] (3658) | 179 |

215 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 10360 | 3313 | 2992 | 45.0% [43.1%, 46.9%] | -0.36% [-0.76%, +0.03%] | -4.4% [-4.6%, -4.2%] (6512) | 174 |
| `assists` | bets | 464 | 220 | 115 | 63.0% [55.2%, 70.3%] | +1.42% [+0.86%, +1.98%] | -1.5% [-2.1%, -0.9%] (462) | 162 |
| `blocked_shots` | opinions | 300 | 72 | 129 | 42.1% [31.5%, 53.5%] | -0.57% [-1.46%, +0.32%] | -8.0% [-8.9%, -7.2%] (196) | 56 |
| `blocked_shots` | bets | 25 | 8 | 14 | 72.7% [32.3%, 93.7%] | +1.73% [-2.38%, +5.85%] | -6.3% [-7.9%, -4.6%] (24) | 22 |
| `goalie_saves` | opinions | 944 | 253 | 394 | 46.0% [34.1%, 58.4%] | -0.67% [-2.77%, +1.44%] | -3.9% [-4.7%, -3.0%] (210) | 40 |
| `goalie_saves` | bets | 67 | 41 | 19 | 85.4% [58.7%, 96.0%] | +5.84% [-2.52%, +14.21%] | -1.7% [-4.3%, +1.0%] (29) | 21 |
| `goals` | opinions | 23003 | 6173 | 9927 | 47.2% [45.1%, 49.3%] | +1.25% [+0.73%, +1.77%] | -4.2% [-4.4%, -4.0%] (10960) | 174 |
| `goals` | bets | 143 | 83 | 32 | 74.8% [58.9%, 86.0%] | +2.60% [+1.10%, +4.11%] | -2.1% [-3.4%, -0.8%] (137) | 82 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 350 | 149 | 37 | 47.6% [39.7%, 55.6%] | -0.26% [-0.83%, +0.31%] | -2.2% [-2.8%, -1.7%] (350) | 175 |
| `moneyline` | bets | 62 | 30 | 7 | 54.5% [36.0%, 71.9%] | +0.63% [-0.89%, +2.15%] | -1.2% [-2.7%, +0.3%] (62) | 62 |
| `points` | opinions | 19606 | 6109 | 4922 | 41.6% [40.1%, 43.1%] | -0.41% [-0.91%, +0.08%] | -5.0% [-5.5%, -4.6%] (15058) | 174 |
| `points` | bets | 912 | 432 | 199 | 60.6% [53.7%, 67.1%] | +5.18% [-0.71%, +11.06%] | +2.3% [-3.5%, +8.1%] (912) | 170 |
| `puck_line` | opinions | 3251 | 1207 | 917 | 51.7% [48.7%, 54.7%] | +0.50% [+0.04%, +0.96%] | -2.8% [-3.2%, -2.3%] (2923) | 180 |
| `puck_line` | bets | 212 | 118 | 41 | 69.0% [55.7%, 79.7%] | +1.13% [-0.25%, +2.51%] | -2.2% [-3.5%, -1.0%] (212) | 109 |
| `regulation_3_way` | opinions | 522 | 200 | 113 | 48.9% [41.9%, 55.9%] | -0.12% [-0.58%, +0.35%] | — | 174 |
| `regulation_3_way` | bets | 122 | 60 | 22 | 60.0% [45.7%, 72.8%] | +0.75% [-0.41%, +1.90%] | — | 122 |
| `shots_on_goal` | opinions | 20081 | 7014 | 4759 | 45.8% [43.5%, 48.1%] | +0.29% [-0.16%, +0.74%] | -4.7% [-4.9%, -4.5%] (11935) | 174 |
| `shots_on_goal` | bets | 1404 | 753 | 259 | 65.8% [60.4%, 70.7%] | +3.51% [+2.48%, +4.53%] | -0.7% [-1.4%, +0.0%] (1102) | 173 |
| `team_total` | opinions | 8211 | 2930 | 2219 | 48.9% [47.1%, 50.7%] | +0.07% [-0.10%, +0.25%] | -4.9% [-5.1%, -4.7%] (8112) | 174 |
| `team_total` | bets | 382 | 192 | 84 | 64.4% [47.7%, 78.3%] | +1.24% [-0.28%, +2.75%] | -3.9% [-5.4%, -2.4%] (382) | 86 |
| `total_goals` | opinions | 4430 | 1544 | 1285 | 49.1% [46.5%, 51.6%] | +0.09% [-0.16%, +0.35%] | -3.5% [-3.7%, -3.3%] (4334) | 180 |
| `total_goals` | bets | 216 | 99 | 35 | 54.7% [37.0%, 71.3%] | +0.94% [-0.71%, +2.60%] | -3.0% [-4.4%, -1.5%] (216) | 52 |

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
