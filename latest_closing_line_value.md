# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-06T18:29:25+00:00
- Opinions considered: **19808**; matched to a closing price: **18897**; no closing price found: **911**.
- Within that count, priced before face-off but no close near face-off: **842** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **59** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **4204** opinion(s), 172 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 18897 | 6291 | 5674 | 47.6% [46.4%, 48.8%] | +1.19% [+0.82%, +1.56%] | -4.3% [-4.6%, -4.0%] (12466) | 42 |

911 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 992 | 540 | 168 | 65.5% [58.0%, 72.4%] | +6.33% [+2.60%, +10.06%] | +2.4% [-1.6%, +6.4%] (874) | 41 |

33 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 2254 | 751 | 658 | 47.1% [43.5%, 50.7%] | +0.25% [-0.66%, +1.15%] | -4.7% [-5.2%, -4.1%] (1294) | 37 |
| `assists` | bets | 112 | 68 | 23 | 76.4% [61.8%, 86.6%] | +2.90% [+1.70%, +4.09%] | -0.4% [-1.7%, +1.0%] (110) | 35 |
| `blocked_shots` | opinions | 16 | 5 | 4 | 41.7% [13.6%, 76.4%] | -0.83% [-3.91%, +2.25%] | -8.3% [-11.0%, -5.6%] (16) | 5 |
| `blocked_shots` | bets | 3 | 2 | 1 | 100.0% [19.9%, 100.0%] | +2.19% [-1.70%, +6.07%] | -5.4% [-7.7%, -3.1%] (3) | 2 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 4819 | 1244 | 2122 | 46.1% [42.1%, 50.2%] | +1.34% [+0.18%, +2.50%] | -4.5% [-5.1%, -4.0%] (2288) | 37 |
| `goals` | bets | 43 | 23 | 8 | 65.7% [35.3%, 87.0%] | +1.92% [-1.04%, +4.88%] | -2.0% [-4.5%, +0.5%] (41) | 23 |
| `moneyline` | opinions | 74 | 32 | 12 | 51.6% [34.5%, 68.4%] | -0.48% [-1.68%, +0.72%] | -2.5% [-3.7%, -1.4%] (74) | 37 |
| `moneyline` | bets | 13 | 6 | 2 | 54.5% [20.2%, 85.1%] | -0.07% [-3.20%, +3.06%] | -2.3% [-5.5%, +0.9%] (13) | 13 |
| `points` | opinions | 4038 | 1293 | 1049 | 43.3% [39.6%, 47.0%] | +1.41% [-0.38%, +3.19%] | -4.1% [-5.9%, -2.3%] (3095) | 37 |
| `points` | bets | 232 | 138 | 29 | 68.0% [54.6%, 79.0%] | +17.71% [-1.14%, +36.55%] | +14.5% [-4.1%, +33.1%] (232) | 36 |
| `puck_line` | opinions | 762 | 254 | 268 | 51.4% [45.1%, 57.7%] | +0.42% [-0.24%, +1.08%] | -2.7% [-3.4%, -2.0%] (697) | 42 |
| `puck_line` | bets | 52 | 24 | 14 | 63.2% [33.5%, 85.4%] | +2.28% [-2.45%, +7.02%] | -1.4% [-5.8%, +3.0%] (52) | 24 |
| `regulation_3_way` | opinions | 111 | 36 | 23 | 40.9% [27.4%, 55.9%] | -0.53% [-1.50%, +0.43%] | — | 37 |
| `regulation_3_way` | bets | 31 | 13 | 5 | 50.0% [25.7%, 74.3%] | +0.24% [-1.82%, +2.29%] | — | 31 |
| `shots_on_goal` | opinions | 4030 | 1701 | 779 | 52.3% [48.1%, 56.5%] | +2.50% [+1.16%, +3.85%] | -4.3% [-4.7%, -3.9%] (2319) | 37 |
| `shots_on_goal` | bets | 304 | 166 | 45 | 64.1% [51.7%, 74.9%] | +3.87% [+1.25%, +6.49%] | -1.1% [-2.9%, +0.7%] (230) | 36 |
| `team_total` | opinions | 1740 | 606 | 482 | 48.2% [44.2%, 52.2%] | -0.02% [-0.39%, +0.35%] | -5.1% [-5.4%, -4.7%] (1716) | 37 |
| `team_total` | bets | 129 | 66 | 22 | 61.7% [31.2%, 85.1%] | +1.39% [-2.22%, +4.99%] | -4.1% [-7.5%, -0.6%] (129) | 23 |
| `total_goals` | opinions | 957 | 340 | 262 | 48.9% [43.6%, 54.3%] | +0.06% [-0.57%, +0.69%] | -3.5% [-4.0%, -3.0%] (937) | 42 |
| `total_goals` | bets | 60 | 23 | 18 | 54.8% [25.5%, 81.0%] | +0.42% [-2.24%, +3.08%] | -3.4% [-5.5%, -1.2%] (60) | 14 |

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
- **Bets**: A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`) and nothing in a hard-gated market (`goalie_saves`), whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
