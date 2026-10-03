# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-03T13:38:54+00:00
- Opinions considered: **11132**; matched to a closing price: **10822**; no closing price found: **310**.
- Within that count, priced before face-off but no close near face-off: **253** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **47** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **4019** opinion(s), 160 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 10822 | 3664 | 3324 | 48.9% [47.0%, 50.7%] | +1.49% [+0.99%, +1.99%] | -4.5% [-4.8%, -4.2%] (7096) | 21 |

310 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 548 | 302 | 91 | 66.1% [57.7%, 73.6%] | +2.44% [+1.17%, +3.72%] | -2.2% [-3.0%, -1.5%] (473) | 21 |

4 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 1301 | 425 | 415 | 48.0% [43.0%, 53.0%] | +0.19% [-1.05%, +1.43%] | -4.7% [-5.3%, -4.0%] (742) | 21 |
| `assists` | bets | 63 | 39 | 12 | 76.5% [56.8%, 88.9%] | +2.21% [+0.91%, +3.51%] | -0.9% [-2.2%, +0.5%] (62) | 20 |
| `blocked_shots` | opinions | 14 | 4 | 4 | 40.0% [11.4%, 77.5%] | -0.89% [-3.99%, +2.20%] | -8.3% [-11.0%, -5.7%] (14) | 4 |
| `blocked_shots` | bets | 3 | 2 | 1 | 100.0% [19.9%, 100.0%] | +2.19% [-1.70%, +6.07%] | -5.4% [-7.7%, -3.1%] (3) | 2 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 2724 | 674 | 1201 | 44.3% [38.7%, 50.0%] | +0.83% [-0.61%, +2.28%] | -4.6% [-5.4%, -3.8%] (1314) | 21 |
| `goals` | bets | 27 | 14 | 6 | 66.7% [27.5%, 91.3%] | +1.04% [-2.83%, +4.91%] | -2.5% [-5.5%, +0.5%] (25) | 14 |
| `moneyline` | opinions | 32 | 13 | 5 | 48.1% [24.6%, 72.5%] | -0.69% [-2.21%, +0.83%] | -2.5% [-4.0%, -1.1%] (32) | 16 |
| `moneyline` | bets | 5 | 1 | 0 | 20.0% [2.0%, 75.0%] | -1.26% [-3.45%, +0.93%] | -3.6% [-5.6%, -1.5%] (5) | 5 |
| `points` | opinions | 2282 | 744 | 662 | 45.9% [41.2%, 50.7%] | +1.74% [-0.60%, +4.08%] | -5.1% [-5.7%, -4.5%] (1716) | 21 |
| `points` | bets | 107 | 56 | 17 | 62.2% [47.3%, 75.1%] | +0.74% [-0.50%, +1.97%] | -2.6% [-3.8%, -1.3%] (107) | 21 |
| `puck_line` | opinions | 426 | 144 | 158 | 53.7% [45.1%, 62.1%] | +0.52% [-0.46%, +1.50%] | -2.7% [-3.8%, -1.7%] (387) | 21 |
| `puck_line` | bets | 24 | 11 | 8 | 68.8% [34.6%, 90.1%] | +1.30% [-1.06%, +3.66%] | -2.6% [-4.8%, -0.5%] (24) | 11 |
| `regulation_3_way` | opinions | 63 | 23 | 9 | 42.6% [25.7%, 61.4%] | -0.45% [-1.48%, +0.58%] | — | 21 |
| `regulation_3_way` | bets | 19 | 8 | 2 | 47.1% [19.7%, 76.3%] | -0.08% [-2.02%, +1.86%] | — | 19 |
| `shots_on_goal` | opinions | 2363 | 1092 | 397 | 55.5% [50.6%, 60.4%] | +4.21% [+2.69%, +5.74%] | -4.1% [-4.7%, -3.5%] (1365) | 21 |
| `shots_on_goal` | bets | 193 | 116 | 25 | 69.0% [52.1%, 82.0%] | +3.81% [+0.54%, +7.08%] | -1.1% [-3.1%, +0.9%] (149) | 21 |
| `team_total` | opinions | 988 | 327 | 306 | 47.9% [42.6%, 53.4%] | +0.02% [-0.52%, +0.56%] | -5.0% [-5.5%, -4.6%] (976) | 21 |
| `team_total` | bets | 62 | 30 | 12 | 60.0% [31.6%, 83.0%] | +0.84% [-1.40%, +3.07%] | -4.7% [-6.6%, -2.8%] (62) | 13 |
| `total_goals` | opinions | 533 | 189 | 152 | 49.6% [42.4%, 56.8%] | +0.09% [-0.85%, +1.03%] | -3.5% [-4.3%, -2.7%] (520) | 21 |
| `total_goals` | bets | 32 | 14 | 7 | 56.0% [20.2%, 86.5%] | +0.73% [-3.60%, +5.06%] | -3.2% [-6.7%, +0.4%] (32) | 7 |

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
