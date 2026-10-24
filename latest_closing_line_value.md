# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-24T13:43:18+00:00
- Opinions considered: **85153**; matched to a closing price: **80864**; no closing price found: **4289**.
- Within that count, priced before face-off but no close near face-off: **4134** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **145** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **6523** opinion(s), 337 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 80864 | 25748 | 24438 | 45.6% [44.9%, 46.4%] | +0.24% [+0.06%, +0.41%] | -4.5% [-4.6%, -4.4%] (54069) | 161 |

4289 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 3595 | 1805 | 733 | 63.1% [59.9%, 66.1%] | +3.11% [+1.96%, +4.27%] | -0.8% [-2.0%, +0.4%] (3196) | 160 |

156 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 9194 | 2930 | 2684 | 45.0% [43.0%, 47.0%] | -0.39% [-0.82%, +0.03%] | -4.5% [-4.7%, -4.2%] (5777) | 155 |
| `assists` | bets | 406 | 195 | 99 | 63.5% [55.0%, 71.3%] | +1.48% [+0.88%, +2.09%] | -1.5% [-2.2%, -0.9%] (404) | 143 |
| `blocked_shots` | opinions | 172 | 46 | 65 | 43.0% [30.3%, 56.7%] | -0.91% [-1.87%, +0.05%] | -8.1% [-9.2%, -7.0%] (128) | 39 |
| `blocked_shots` | bets | 11 | 3 | 6 | 60.0% [14.7%, 92.9%] | +0.06% [-2.17%, +2.28%] | -6.6% [-8.5%, -4.7%] (11) | 10 |
| `goalie_saves` | opinions | 536 | 153 | 203 | 45.9% [30.8%, 61.9%] | -0.83% [-3.94%, +2.28%] | -3.9% [-4.8%, -3.0%] (124) | 23 |
| `goalie_saves` | bets | 43 | 27 | 10 | 81.8% [46.2%, 95.9%] | +7.55% [-4.65%, +19.75%] | -3.0% [-5.7%, -0.3%] (17) | 13 |
| `goals` | opinions | 20494 | 5469 | 8834 | 46.9% [44.7%, 49.1%] | +1.12% [+0.57%, +1.67%] | -4.3% [-4.5%, -4.0%] (9753) | 155 |
| `goals` | bets | 135 | 76 | 31 | 73.1% [56.5%, 85.0%] | +2.47% [+0.92%, +4.03%] | -2.2% [-3.5%, -0.8%] (129) | 75 |
| `hits` | opinions | 268 | 96 | 76 | 50.0% [39.9%, 60.1%] | +0.06% [-0.63%, +0.74%] | -7.9% [-8.5%, -7.3%] (268) | 51 |
| `hits` | bets | 91 | 46 | 27 | 71.9% [51.8%, 85.9%] | +1.55% [+0.18%, +2.91%] | -6.5% [-7.8%, -5.3%] (91) | 47 |
| `moneyline` | opinions | 312 | 131 | 36 | 47.5% [39.0%, 56.0%] | -0.29% [-0.88%, +0.30%] | -2.3% [-2.8%, -1.7%] (312) | 156 |
| `moneyline` | bets | 54 | 25 | 6 | 52.1% [32.7%, 70.9%] | +0.33% [-1.25%, +1.91%] | -1.5% [-3.0%, +0.1%] (54) | 54 |
| `points` | opinions | 17397 | 5409 | 4364 | 41.5% [39.9%, 43.1%] | -0.40% [-0.96%, +0.15%] | -5.0% [-5.5%, -4.6%] (13386) | 155 |
| `points` | bets | 814 | 381 | 179 | 60.0% [52.5%, 67.1%] | +5.64% [-0.91%, +12.19%] | +2.7% [-3.8%, +9.1%] (814) | 151 |
| `puck_line` | opinions | 2945 | 1064 | 864 | 51.1% [48.0%, 54.3%] | +0.53% [+0.04%, +1.01%] | -2.7% [-3.2%, -2.2%] (2658) | 161 |
| `puck_line` | bets | 179 | 92 | 37 | 64.8% [50.2%, 77.1%] | +0.95% [-0.65%, +2.55%] | -2.3% [-3.8%, -0.9%] (179) | 94 |
| `regulation_3_way` | opinions | 465 | 178 | 102 | 49.0% [41.6%, 56.5%] | -0.13% [-0.62%, +0.36%] | — | 155 |
| `regulation_3_way` | bets | 108 | 53 | 19 | 59.6% [44.5%, 73.0%] | +0.59% [-0.62%, +1.80%] | — | 108 |
| `shots_on_goal` | opinions | 17823 | 6314 | 4053 | 45.9% [43.4%, 48.3%] | +0.28% [-0.22%, +0.78%] | -4.7% [-4.9%, -4.5%] (10582) | 155 |
| `shots_on_goal` | bets | 1225 | 657 | 212 | 64.9% [59.1%, 70.2%] | +3.58% [+2.43%, +4.74%] | -0.6% [-1.4%, +0.1%] (968) | 154 |
| `team_total` | opinions | 7316 | 2586 | 2017 | 48.8% [46.8%, 50.8%] | +0.07% [-0.11%, +0.26%] | -4.9% [-5.1%, -4.7%] (7222) | 155 |
| `team_total` | bets | 330 | 158 | 73 | 61.5% [43.3%, 76.9%] | +1.07% [-0.62%, +2.76%] | -4.1% [-5.7%, -2.4%] (330) | 75 |
| `total_goals` | opinions | 3942 | 1372 | 1140 | 49.0% [46.3%, 51.7%] | +0.12% [-0.15%, +0.39%] | -3.5% [-3.7%, -3.3%] (3859) | 161 |
| `total_goals` | bets | 199 | 92 | 34 | 55.8% [37.2%, 72.8%] | +0.98% [-0.75%, +2.72%] | -3.0% [-4.5%, -1.4%] (199) | 46 |

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
