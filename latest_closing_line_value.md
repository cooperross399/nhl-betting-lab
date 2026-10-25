# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-25T13:46:46+00:00
- Opinions considered: **91980**; matched to a closing price: **87125**; no closing price found: **4855**.
- Within that count, priced before face-off but no close near face-off: **4694** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **151** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2576** opinion(s), 141 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 87125 | 27743 | 26398 | 45.7% [45.0%, 46.4%] | +0.27% [+0.10%, +0.44%] | -4.5% [-4.6%, -4.4%] (58135) | 172 |

4855 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 3892 | 1962 | 799 | 63.4% [60.5%, 66.3%] | +3.04% [+1.97%, +4.11%] | -0.8% [-2.0%, +0.3%] (3458) | 171 |

212 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 9898 | 3168 | 2862 | 45.0% [43.1%, 47.0%] | -0.34% [-0.75%, +0.07%] | -4.4% [-4.7%, -4.2%] (6218) | 166 |
| `assists` | bets | 436 | 205 | 109 | 62.7% [54.4%, 70.3%] | +1.44% [+0.85%, +2.02%] | -1.5% [-2.1%, -0.9%] (434) | 154 |
| `blocked_shots` | opinions | 254 | 58 | 121 | 43.6% [32.0%, 55.9%] | -0.42% [-1.33%, +0.48%] | -8.0% [-8.9%, -7.1%] (164) | 49 |
| `blocked_shots` | bets | 20 | 7 | 11 | 77.8% [32.9%, 96.2%] | +2.07% [-2.83%, +6.97%] | -6.5% [-7.9%, -5.1%] (19) | 19 |
| `goalie_saves` | opinions | 774 | 213 | 296 | 44.6% [31.8%, 58.0%] | -1.03% [-3.51%, +1.46%] | -4.0% [-5.0%, -3.0%] (176) | 33 |
| `goalie_saves` | bets | 53 | 34 | 12 | 82.9% [52.6%, 95.5%] | +7.03% [-2.98%, +17.03%] | -1.7% [-4.9%, +1.4%] (24) | 18 |
| `goals` | opinions | 21949 | 5902 | 9464 | 47.3% [45.1%, 49.5%] | +1.23% [+0.69%, +1.77%] | -4.2% [-4.5%, -4.0%] (10454) | 166 |
| `goals` | bets | 140 | 81 | 31 | 74.3% [58.2%, 85.7%] | +2.59% [+1.06%, +4.12%] | -2.1% [-3.4%, -0.7%] (134) | 79 |
| `hits` | opinions | 312 | 114 | 84 | 50.0% [40.7%, 59.3%] | +0.04% [-0.65%, +0.73%] | -7.9% [-8.6%, -7.3%] (312) | 59 |
| `hits` | bets | 104 | 48 | 29 | 64.0% [43.0%, 80.7%] | +0.95% [-0.55%, +2.45%] | -7.1% [-8.5%, -5.7%] (104) | 53 |
| `moneyline` | opinions | 334 | 141 | 37 | 47.5% [39.4%, 55.7%] | -0.29% [-0.88%, +0.30%] | -2.2% [-2.8%, -1.7%] (334) | 167 |
| `moneyline` | bets | 58 | 28 | 7 | 54.9% [35.7%, 72.8%] | +0.65% [-0.96%, +2.26%] | -1.2% [-2.7%, +0.4%] (58) | 58 |
| `points` | opinions | 18741 | 5849 | 4678 | 41.6% [40.1%, 43.1%] | -0.38% [-0.90%, +0.14%] | -5.0% [-5.5%, -4.6%] (14390) | 166 |
| `points` | bets | 872 | 412 | 189 | 60.3% [53.1%, 67.1%] | +5.38% [-0.76%, +11.52%] | +2.5% [-3.6%, +8.5%] (872) | 162 |
| `puck_line` | opinions | 3123 | 1146 | 894 | 51.4% [48.4%, 54.4%] | +0.50% [+0.03%, +0.97%] | -2.7% [-3.2%, -2.3%] (2812) | 172 |
| `puck_line` | bets | 196 | 105 | 39 | 66.9% [52.9%, 78.4%] | +1.07% [-0.43%, +2.56%] | -2.3% [-3.6%, -0.9%] (196) | 102 |
| `regulation_3_way` | opinions | 498 | 189 | 108 | 48.5% [41.3%, 55.7%] | -0.13% [-0.61%, +0.35%] | — | 166 |
| `regulation_3_way` | bets | 116 | 57 | 20 | 59.4% [44.8%, 72.4%] | +0.74% [-0.47%, +1.94%] | — | 116 |
| `shots_on_goal` | opinions | 19173 | 6715 | 4477 | 45.7% [43.4%, 48.0%] | +0.28% [-0.19%, +0.75%] | -4.7% [-4.9%, -4.5%] (11395) | 166 |
| `shots_on_goal` | bets | 1327 | 709 | 238 | 65.1% [59.6%, 70.2%] | +3.51% [+2.44%, +4.58%] | -0.6% [-1.4%, +0.1%] (1047) | 165 |
| `team_total` | opinions | 7838 | 2776 | 2146 | 48.8% [46.9%, 50.7%] | +0.07% [-0.11%, +0.25%] | -4.9% [-5.1%, -4.7%] (7740) | 166 |
| `team_total` | bets | 359 | 178 | 79 | 63.6% [45.9%, 78.2%] | +1.22% [-0.38%, +2.83%] | -3.9% [-5.5%, -2.4%] (359) | 82 |
| `total_goals` | opinions | 4231 | 1472 | 1231 | 49.1% [46.5%, 51.7%] | +0.09% [-0.17%, +0.34%] | -3.5% [-3.7%, -3.3%] (4140) | 172 |
| `total_goals` | bets | 211 | 98 | 35 | 55.7% [37.7%, 72.3%] | +1.01% [-0.67%, +2.69%] | -2.9% [-4.4%, -1.5%] (211) | 50 |

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
