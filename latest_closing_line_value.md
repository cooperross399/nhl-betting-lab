# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-04T22:44:06+00:00
- Opinions considered: **129243**; matched to a closing price: **122196**; no closing price found: **7047**.
- Within that count, priced before face-off but no close near face-off: **6832** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **205** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2268** opinion(s), 106 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 122196 | 38858 | 36851 | 45.5% [44.9%, 46.2%] | +0.11% [-0.05%, +0.27%] | -4.5% [-4.6%, -4.4%] (80599) | 236 |

7047 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 5556 | 2779 | 1151 | 63.1% [60.7%, 65.4%] | +2.65% [+1.88%, +3.42%] | -1.3% [-2.1%, -0.4%] (4902) | 235 |

312 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 13809 | 4468 | 3895 | 45.1% [43.3%, 46.8%] | -0.69% [-1.27%, -0.11%] | -4.2% [-4.4%, -4.0%] (8639) | 230 |
| `assists` | bets | 616 | 286 | 149 | 61.2% [54.2%, 67.9%] | +1.31% [+0.83%, +1.79%] | -1.6% [-2.1%, -1.1%] (614) | 216 |
| `blocked_shots` | opinions | 617 | 119 | 344 | 43.6% [35.3%, 52.3%] | -0.32% [-0.79%, +0.14%] | -7.9% [-8.5%, -7.4%] (352) | 95 |
| `blocked_shots` | bets | 67 | 14 | 44 | 60.9% [31.3%, 84.1%] | +0.84% [-1.06%, +2.74%] | -6.8% [-7.9%, -5.6%] (65) | 49 |
| `goalie_saves` | opinions | 2295 | 628 | 960 | 47.0% [39.0%, 55.3%] | -0.50% [-1.65%, +0.66%] | -3.6% [-4.1%, -3.0%] (501) | 90 |
| `goalie_saves` | bets | 118 | 67 | 35 | 80.7% [58.6%, 92.5%] | +3.87% [-1.25%, +8.99%] | -1.4% [-3.1%, +0.2%] (59) | 42 |
| `goals` | opinions | 30432 | 8090 | 13150 | 46.8% [45.1%, 48.6%] | +1.08% [+0.66%, +1.51%] | -4.2% [-4.4%, -4.1%] (14537) | 230 |
| `goals` | bets | 190 | 105 | 42 | 70.9% [57.7%, 81.4%] | +2.32% [+1.07%, +3.57%] | -2.4% [-3.5%, -1.3%] (182) | 112 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 462 | 195 | 50 | 47.3% [40.4%, 54.4%] | -0.26% [-0.77%, +0.25%] | -2.2% [-2.7%, -1.7%] (462) | 231 |
| `moneyline` | bets | 72 | 35 | 9 | 55.6% [38.0%, 71.8%] | +0.75% [-0.73%, +2.23%] | -1.1% [-2.6%, +0.3%] (72) | 72 |
| `points` | opinions | 26313 | 8113 | 6574 | 41.1% [39.8%, 42.5%] | -0.86% [-1.42%, -0.30%] | -5.0% [-5.4%, -4.7%] (20042) | 230 |
| `points` | bets | 1213 | 569 | 266 | 60.1% [54.3%, 65.6%] | +4.08% [-0.41%, +8.58%] | +1.3% [-3.2%, +5.7%] (1213) | 226 |
| `puck_line` | opinions | 4125 | 1579 | 1073 | 51.7% [49.1%, 54.3%] | +0.41% [+0.02%, +0.81%] | -2.9% [-3.3%, -2.5%] (3689) | 236 |
| `puck_line` | bets | 247 | 139 | 44 | 68.5% [56.3%, 78.5%] | +1.12% [-0.08%, +2.32%] | -2.2% [-3.3%, -1.2%] (247) | 130 |
| `regulation_3_way` | opinions | 690 | 271 | 148 | 50.0% [43.9%, 56.1%] | -0.04% [-0.47%, +0.38%] | — | 230 |
| `regulation_3_way` | bets | 157 | 76 | 29 | 59.4% [46.7%, 70.9%] | +0.65% [-0.43%, +1.72%] | — | 157 |
| `shots_on_goal` | opinions | 26622 | 9409 | 6052 | 45.7% [43.8%, 47.7%] | +0.42% [+0.01%, +0.84%] | -4.7% [-4.8%, -4.5%] (15791) | 230 |
| `shots_on_goal` | bets | 1929 | 1046 | 337 | 65.7% [61.1%, 70.0%] | +3.52% [+2.62%, +4.42%] | -0.8% [-1.4%, -0.2%] (1503) | 229 |
| `team_total` | opinions | 10628 | 3843 | 2789 | 49.0% [47.4%, 50.6%] | +0.05% [-0.11%, +0.20%] | -4.9% [-5.1%, -4.7%] (10501) | 230 |
| `team_total` | bets | 474 | 232 | 99 | 61.9% [47.2%, 74.7%] | +0.97% [-0.35%, +2.28%] | -4.1% [-5.4%, -2.9%] (474) | 111 |
| `total_goals` | opinions | 5829 | 2009 | 1710 | 48.8% [46.5%, 51.0%] | +0.03% [-0.19%, +0.25%] | -3.6% [-3.7%, -3.4%] (5711) | 236 |
| `total_goals` | bets | 353 | 153 | 63 | 52.8% [38.3%, 66.7%] | +0.60% [-0.66%, +1.85%] | -3.3% [-4.4%, -2.1%] (353) | 79 |

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
