# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-02T13:38:50+00:00
- Opinions considered: **8782**; matched to a closing price: **8485**; no closing price found: **297**.
- Within that count, priced before face-off but no close near face-off: **240** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **47** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2350** opinion(s), 80 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 8485 | 2881 | 2633 | 49.2% [47.3%, 51.2%] | +1.03% [+0.62%, +1.44%] | -4.4% [-4.7%, -4.2%] (5568) | 16 |

297 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 468 | 257 | 79 | 66.1% [57.0%, 74.1%] | +2.23% [+1.02%, +3.44%] | -2.2% [-3.1%, -1.3%] (406) | 16 |

4 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 1022 | 340 | 330 | 49.1% [43.3%, 55.0%] | +0.40% [-0.92%, +1.71%] | -4.6% [-5.2%, -3.9%] (586) | 16 |
| `assists` | bets | 52 | 33 | 8 | 75.0% [53.7%, 88.6%] | +2.33% [+0.84%, +3.83%] | -0.6% [-2.2%, +1.0%] (51) | 15 |
| `blocked_shots` | opinions | 10 | 4 | 1 | 44.4% [12.8%, 81.3%] | -1.06% [-5.42%, +3.31%] | -8.3% [-12.1%, -4.5%] (10) | 2 |
| `blocked_shots` | bets | 3 | 2 | 1 | 100.0% [19.9%, 100.0%] | +2.19% [-1.70%, +6.07%] | -5.4% [-7.7%, -3.1%] (3) | 2 |
| `goalie_saves` | opinions | 73 | 14 | 11 | 22.6% [9.5%, 44.7%] | -11.12% [-20.36%, -1.89%] | -5.0% [-7.0%, -3.1%] (26) | 6 |
| `goalie_saves` | bets | 5 | 3 | 1 | 75.0% [17.2%, 97.7%] | +5.40% [-5.12%, +15.93%] | -3.6% [-7.6%, +0.4%] (4) | 3 |
| `goals` | opinions | 2131 | 522 | 967 | 44.8% [38.7%, 51.2%] | +0.19% [-1.23%, +1.61%] | -4.5% [-5.5%, -3.5%] (1022) | 16 |
| `goals` | bets | 25 | 14 | 4 | 66.7% [27.5%, 91.3%] | +1.12% [-3.07%, +5.32%] | -2.3% [-5.6%, +1.0%] (23) | 12 |
| `moneyline` | opinions | 22 | 10 | 3 | 52.6% [24.6%, 79.1%] | -0.54% [-2.53%, +1.44%] | -2.6% [-4.5%, -0.7%] (22) | 11 |
| `moneyline` | bets | 4 | 1 | 0 | 25.0% [2.6%, 80.8%] | -1.09% [-3.84%, +1.67%] | -3.4% [-6.0%, -0.8%] (4) | 4 |
| `points` | opinions | 1835 | 591 | 550 | 46.0% [40.8%, 51.3%] | +0.16% [-1.07%, +1.38%] | -5.0% [-5.5%, -4.4%] (1379) | 16 |
| `points` | bets | 87 | 48 | 14 | 65.8% [49.2%, 79.2%] | +0.97% [-0.47%, +2.40%] | -2.4% [-3.9%, -0.9%] (87) | 16 |
| `puck_line` | opinions | 325 | 111 | 121 | 54.4% [44.5%, 64.0%] | +0.36% [-0.64%, +1.35%] | -2.9% [-4.0%, -1.8%] (295) | 16 |
| `puck_line` | bets | 22 | 10 | 8 | 71.4% [33.6%, 92.5%] | +1.43% [-1.13%, +3.99%] | -2.5% [-4.8%, -0.1%] (22) | 10 |
| `regulation_3_way` | opinions | 48 | 17 | 8 | 42.5% [23.5%, 64.0%] | -0.35% [-1.46%, +0.77%] | — | 16 |
| `regulation_3_way` | bets | 15 | 5 | 2 | 38.5% [12.5%, 73.3%] | -0.55% [-2.69%, +1.58%] | — | 15 |
| `shots_on_goal` | opinions | 1858 | 866 | 320 | 56.3% [50.7%, 61.7%] | +4.48% [+2.73%, +6.23%] | -4.0% [-4.6%, -3.3%] (1083) | 16 |
| `shots_on_goal` | bets | 168 | 99 | 25 | 69.2% [49.7%, 83.7%] | +4.09% [+0.38%, +7.80%] | -1.2% [-3.5%, +1.2%] (125) | 16 |
| `team_total` | opinions | 755 | 261 | 210 | 47.9% [41.9%, 53.9%] | +0.03% [-0.59%, +0.64%] | -5.0% [-5.6%, -4.5%] (748) | 16 |
| `team_total` | bets | 57 | 28 | 11 | 60.9% [30.6%, 84.6%] | +0.83% [-1.61%, +3.28%] | -4.7% [-6.8%, -2.6%] (57) | 11 |
| `total_goals` | opinions | 406 | 145 | 112 | 49.3% [41.2%, 57.5%] | +0.14% [-0.95%, +1.23%] | -3.5% [-4.4%, -2.6%] (397) | 16 |
| `total_goals` | bets | 30 | 14 | 5 | 56.0% [20.2%, 86.5%] | +0.78% [-3.90%, +5.45%] | -3.1% [-6.8%, +0.7%] (30) | 6 |

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
