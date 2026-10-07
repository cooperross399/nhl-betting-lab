# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-07T13:40:50+00:00
- Opinions considered: **24012**; matched to a closing price: **22047**; no closing price found: **1965**.
- Within that count, priced before face-off but no close near face-off: **1895** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **60** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1533** opinion(s), 101 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 22047 | 7271 | 6618 | 47.1% [46.0%, 48.2%] | +0.99% [+0.64%, +1.34%] | -4.3% [-4.6%, -4.1%] (14600) | 49 |

1965 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 1139 | 617 | 198 | 65.6% [58.7%, 71.8%] | +5.73% [+2.42%, +9.03%] | +1.8% [-1.8%, +5.3%] (1005) | 48 |

58 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 2624 | 861 | 757 | 46.1% [42.8%, 49.5%] | +0.08% [-0.78%, +0.95%] | -4.7% [-5.2%, -4.3%] (1518) | 43 |
| `assists` | bets | 123 | 74 | 25 | 75.5% [61.6%, 85.6%] | +2.82% [+1.68%, +3.97%] | -0.4% [-1.7%, +0.9%] (121) | 40 |
| `blocked_shots` | opinions | 22 | 6 | 5 | 35.3% [12.5%, 67.5%] | -1.52% [-4.11%, +1.08%] | -8.3% [-10.6%, -6.1%] (22) | 8 |
| `blocked_shots` | bets | 4 | 2 | 2 | 100.0% [19.9%, 100.0%] | +1.64% [-1.52%, +4.80%] | -5.4% [-6.9%, -3.9%] (4) | 3 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 5621 | 1444 | 2504 | 46.3% [42.6%, 50.1%] | +1.27% [+0.25%, +2.30%] | -4.4% [-4.9%, -3.9%] (2672) | 43 |
| `goals` | bets | 50 | 28 | 10 | 70.0% [39.9%, 89.1%] | +2.55% [-0.24%, +5.34%] | -1.9% [-4.3%, +0.4%] (47) | 25 |
| `moneyline` | opinions | 88 | 38 | 13 | 50.7% [35.0%, 66.2%] | -0.44% [-1.57%, +0.68%] | -2.5% [-3.5%, -1.4%] (88) | 44 |
| `moneyline` | bets | 17 | 9 | 2 | 60.0% [27.3%, 85.7%] | +0.38% [-2.20%, +2.96%] | -1.7% [-4.4%, +0.9%] (17) | 17 |
| `points` | opinions | 4682 | 1484 | 1202 | 42.6% [39.3%, 46.1%] | +1.00% [-0.60%, +2.59%] | -4.3% [-5.9%, -2.8%] (3609) | 43 |
| `points` | bets | 258 | 146 | 38 | 66.4% [53.3%, 77.3%] | +15.98% [-1.46%, +33.42%] | +12.8% [-4.4%, +30.0%] (258) | 42 |
| `puck_line` | opinions | 888 | 293 | 313 | 51.0% [45.1%, 56.8%] | +0.38% [-0.22%, +0.98%] | -2.8% [-3.4%, -2.1%] (809) | 49 |
| `puck_line` | bets | 60 | 30 | 15 | 66.7% [40.2%, 85.6%] | +2.08% [-2.07%, +6.23%] | -1.6% [-5.4%, +2.3%] (60) | 29 |
| `regulation_3_way` | opinions | 129 | 42 | 28 | 41.6% [28.8%, 55.6%] | -0.43% [-1.33%, +0.46%] | — | 43 |
| `regulation_3_way` | bets | 36 | 15 | 7 | 51.7% [28.1%, 74.6%] | +0.45% [-1.41%, +2.31%] | — | 36 |
| `shots_on_goal` | opinions | 4752 | 1963 | 927 | 51.3% [47.4%, 55.2%] | +2.06% [+0.82%, +3.30%] | -4.4% [-4.7%, -4.0%] (2759) | 43 |
| `shots_on_goal` | bets | 361 | 199 | 53 | 64.6% [53.4%, 74.4%] | +3.62% [+1.35%, +5.88%] | -1.4% [-2.9%, +0.2%] (277) | 42 |
| `team_total` | opinions | 2030 | 716 | 544 | 48.2% [44.5%, 51.9%] | +0.05% [-0.31%, +0.40%] | -5.0% [-5.4%, -4.7%] (2000) | 43 |
| `team_total` | bets | 145 | 75 | 26 | 63.0% [34.3%, 84.8%] | +1.34% [-1.88%, +4.56%] | -4.1% [-7.2%, -1.0%] (145) | 27 |
| `total_goals` | opinions | 1115 | 395 | 310 | 49.1% [44.1%, 54.1%] | +0.19% [-0.39%, +0.76%] | -3.4% [-3.8%, -2.9%] (1093) | 49 |
| `total_goals` | bets | 72 | 28 | 19 | 52.8% [26.5%, 77.7%] | +0.23% [-2.13%, +2.60%] | -3.5% [-5.5%, -1.6%] (72) | 16 |

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
