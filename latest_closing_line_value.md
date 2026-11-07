# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-07T22:43:37+00:00
- Opinions considered: **141378**; matched to a closing price: **133542**; no closing price found: **7836**.
- Within that count, priced before face-off but no close near face-off: **7615** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **211** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5341** opinion(s), 231 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 133542 | 42466 | 40351 | 45.6% [45.0%, 46.2%] | +0.17% [+0.01%, +0.32%] | -4.5% [-4.6%, -4.4%] (87629) | 256 |

7836 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 6019 | 3000 | 1264 | 63.1% [60.8%, 65.4%] | +2.61% [+1.89%, +3.33%] | -1.3% [-2.1%, -0.6%] (5300) | 255 |

343 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 15002 | 4864 | 4255 | 45.3% [43.5%, 47.0%] | -0.63% [-1.17%, -0.08%] | -4.2% [-4.4%, -4.0%] (9387) | 250 |
| `assists` | bets | 684 | 309 | 174 | 60.6% [53.8%, 67.0%] | +1.20% [+0.75%, +1.66%] | -1.6% [-2.1%, -1.2%] (681) | 235 |
| `blocked_shots` | opinions | 711 | 132 | 404 | 43.0% [35.0%, 51.4%] | -0.35% [-0.76%, +0.06%] | -7.9% [-8.4%, -7.4%] (403) | 107 |
| `blocked_shots` | bets | 76 | 16 | 50 | 61.5% [33.4%, 83.6%] | +0.84% [-0.86%, +2.53%] | -6.7% [-7.8%, -5.7%] (73) | 57 |
| `goalie_saves` | opinions | 2842 | 762 | 1236 | 47.4% [39.9%, 55.1%] | -0.61% [-1.65%, +0.42%] | -3.5% [-4.0%, -3.0%] (620) | 109 |
| `goalie_saves` | bets | 144 | 74 | 44 | 74.0% [49.5%, 89.2%] | +3.07% [-1.39%, +7.53%] | -1.5% [-3.1%, +0.1%] (69) | 48 |
| `goals` | opinions | 33092 | 8760 | 14339 | 46.7% [45.1%, 48.4%] | +1.00% [+0.60%, +1.41%] | -4.2% [-4.4%, -4.1%] (15828) | 250 |
| `goals` | bets | 210 | 117 | 47 | 71.8% [59.2%, 81.7%] | +2.36% [+1.19%, +3.52%] | -2.3% [-3.4%, -1.3%] (200) | 124 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 502 | 213 | 55 | 47.7% [41.0%, 54.4%] | -0.29% [-0.77%, +0.19%] | -2.2% [-2.7%, -1.8%] (502) | 251 |
| `moneyline` | bets | 76 | 37 | 9 | 55.2% [38.2%, 71.1%] | +0.63% [-0.81%, +2.07%] | -1.2% [-2.7%, +0.2%] (76) | 76 |
| `points` | opinions | 28646 | 8898 | 7103 | 41.3% [40.0%, 42.6%] | -0.39% [-1.03%, +0.26%] | -5.1% [-5.4%, -4.7%] (21801) | 250 |
| `points` | bets | 1324 | 624 | 291 | 60.4% [55.0%, 65.6%] | +3.83% [-0.30%, +7.97%] | +1.0% [-3.1%, +5.1%] (1324) | 246 |
| `puck_line` | opinions | 4441 | 1715 | 1145 | 52.0% [49.5%, 54.5%] | +0.44% [+0.07%, +0.82%] | -2.9% [-3.3%, -2.6%] (3959) | 256 |
| `puck_line` | bets | 260 | 145 | 49 | 68.7% [56.8%, 78.6%] | +1.09% [-0.05%, +2.24%] | -2.3% [-3.3%, -1.2%] (260) | 138 |
| `regulation_3_way` | opinions | 750 | 293 | 159 | 49.6% [43.7%, 55.4%] | -0.07% [-0.48%, +0.33%] | — | 250 |
| `regulation_3_way` | bets | 165 | 80 | 30 | 59.3% [47.0%, 70.5%] | +0.67% [-0.37%, +1.70%] | — | 165 |
| `shots_on_goal` | opinions | 29341 | 10332 | 6701 | 45.6% [43.8%, 47.5%] | +0.30% [-0.11%, +0.71%] | -4.7% [-4.8%, -4.5%] (17179) | 250 |
| `shots_on_goal` | bets | 2077 | 1131 | 364 | 66.0% [61.7%, 70.1%] | +3.62% [+2.74%, +4.50%] | -0.8% [-1.4%, -0.3%] (1614) | 249 |
| `team_total` | opinions | 11514 | 4179 | 3012 | 49.2% [47.6%, 50.7%] | +0.06% [-0.09%, +0.21%] | -4.9% [-5.0%, -4.7%] (11378) | 250 |
| `team_total` | bets | 497 | 239 | 105 | 61.0% [46.7%, 73.6%] | +0.91% [-0.35%, +2.17%] | -4.2% [-5.4%, -3.0%] (497) | 118 |
| `total_goals` | opinions | 6327 | 2184 | 1836 | 48.6% [46.5%, 50.8%] | +0.05% [-0.16%, +0.27%] | -3.5% [-3.7%, -3.4%] (6198) | 256 |
| `total_goals` | bets | 386 | 171 | 67 | 53.6% [39.5%, 67.1%] | +0.68% [-0.53%, +1.90%] | -3.2% [-4.3%, -2.1%] (386) | 88 |

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
