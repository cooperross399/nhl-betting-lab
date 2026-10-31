# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-31T20:50:41+00:00
- Opinions considered: **116183**; matched to a closing price: **109849**; no closing price found: **6334**.
- Within that count, priced before face-off but no close near face-off: **6130** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **194** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2221** opinion(s), 121 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 109849 | 35107 | 33147 | 45.8% [45.1%, 46.4%] | +0.14% [-0.03%, +0.31%] | -4.5% [-4.6%, -4.4%] (72615) | 213 |

6334 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 5001 | 2512 | 1024 | 63.2% [60.6%, 65.7%] | +2.80% [+1.94%, +3.65%] | -1.2% [-2.0%, -0.3%] (4432) | 212 |

284 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 12445 | 3997 | 3554 | 45.0% [43.1%, 46.8%] | -0.78% [-1.41%, -0.14%] | -4.2% [-4.5%, -4.0%] (7760) | 207 |
| `assists` | bets | 566 | 265 | 138 | 61.9% [54.6%, 68.7%] | +1.35% [+0.85%, +1.86%] | -1.5% [-2.0%, -1.0%] (564) | 195 |
| `blocked_shots` | opinions | 452 | 91 | 229 | 40.8% [31.7%, 50.6%] | -0.47% [-1.07%, +0.12%] | -8.0% [-8.6%, -7.3%] (276) | 76 |
| `blocked_shots` | bets | 44 | 9 | 29 | 60.0% [24.9%, 87.1%] | +0.75% [-1.72%, +3.23%] | -6.7% [-7.9%, -5.6%] (42) | 34 |
| `goalie_saves` | opinions | 1744 | 467 | 718 | 45.5% [36.5%, 54.9%] | -0.65% [-2.02%, +0.73%] | -3.6% [-4.2%, -3.0%] (385) | 69 |
| `goalie_saves` | bets | 89 | 48 | 30 | 81.4% [57.7%, 93.3%] | +4.59% [-1.90%, +11.08%] | -1.7% [-3.6%, +0.2%] (46) | 32 |
| `goals` | opinions | 27389 | 7283 | 11896 | 47.0% [45.2%, 48.9%] | +1.16% [+0.71%, +1.62%] | -4.2% [-4.4%, -4.0%] (13076) | 207 |
| `goals` | bets | 173 | 99 | 38 | 73.3% [59.0%, 84.0%] | +2.52% [+1.19%, +3.85%] | -2.2% [-3.4%, -1.0%] (166) | 101 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 416 | 176 | 46 | 47.6% [40.3%, 55.0%] | -0.27% [-0.80%, +0.26%] | -2.2% [-2.7%, -1.7%] (416) | 208 |
| `moneyline` | bets | 69 | 33 | 9 | 55.0% [37.1%, 71.7%] | +0.54% [-0.91%, +1.99%] | -1.4% [-2.8%, +0.0%] (69) | 69 |
| `points` | opinions | 23657 | 7352 | 5926 | 41.5% [40.1%, 42.9%] | -0.88% [-1.50%, -0.26%] | -5.0% [-5.4%, -4.6%] (17964) | 207 |
| `points` | bets | 1105 | 522 | 238 | 60.2% [54.0%, 66.1%] | +4.43% [-0.48%, +9.34%] | +1.6% [-3.2%, +6.4%] (1105) | 203 |
| `puck_line` | opinions | 3765 | 1432 | 989 | 51.6% [48.9%, 54.3%] | +0.45% [+0.03%, +0.87%] | -2.8% [-3.3%, -2.4%] (3373) | 213 |
| `puck_line` | bets | 232 | 132 | 41 | 69.1% [56.6%, 79.4%] | +1.13% [-0.14%, +2.40%] | -2.2% [-3.4%, -1.1%] (232) | 122 |
| `regulation_3_way` | opinions | 621 | 242 | 133 | 49.6% [43.2%, 56.0%] | -0.06% [-0.50%, +0.38%] | — | 207 |
| `regulation_3_way` | bets | 139 | 68 | 23 | 58.6% [45.4%, 70.7%] | +0.52% [-0.61%, +1.65%] | — | 139 |
| `shots_on_goal` | opinions | 23976 | 8583 | 5468 | 46.4% [44.3%, 48.4%] | +0.55% [+0.11%, +0.99%] | -4.6% [-4.8%, -4.5%] (14207) | 207 |
| `shots_on_goal` | bets | 1705 | 931 | 297 | 66.1% [61.3%, 70.6%] | +3.73% [+2.74%, +4.72%] | -0.7% [-1.3%, -0.1%] (1329) | 206 |
| `team_total` | opinions | 9748 | 3520 | 2567 | 49.0% [47.3%, 50.7%] | +0.06% [-0.10%, +0.22%] | -4.9% [-5.1%, -4.8%] (9634) | 207 |
| `team_total` | bets | 442 | 213 | 93 | 61.0% [45.6%, 74.6%] | +0.91% [-0.48%, +2.31%] | -4.2% [-5.6%, -2.9%] (442) | 101 |
| `total_goals` | opinions | 5262 | 1830 | 1515 | 48.8% [46.5%, 51.2%] | +0.06% [-0.17%, +0.29%] | -3.5% [-3.7%, -3.3%] (5150) | 213 |
| `total_goals` | bets | 317 | 135 | 54 | 51.3% [36.3%, 66.1%] | +0.57% [-0.82%, +1.97%] | -3.3% [-4.6%, -2.0%] (317) | 70 |

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
