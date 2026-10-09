# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-09T13:45:07+00:00
- Opinions considered: **30706**; matched to a closing price: **28698**; no closing price found: **2008**.
- Within that count, priced before face-off but no close near face-off: **1933** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **65** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2073** opinion(s), 93 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 28698 | 9395 | 8434 | 46.4% [45.3%, 47.5%] | +0.70% [+0.39%, +1.02%] | -4.3% [-4.6%, -4.1%] (19089) | 62 |

2008 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 1433 | 763 | 260 | 65.0% [59.3%, 70.4%] | +5.03% [+2.34%, +7.71%] | +1.1% [-1.7%, +4.0%] (1274) | 61 |

58 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 3375 | 1100 | 976 | 45.9% [42.7%, 49.1%] | +0.00% [-0.78%, +0.79%] | -4.5% [-5.0%, -4.1%] (2006) | 56 |
| `assists` | bets | 155 | 85 | 33 | 69.7% [56.4%, 80.3%] | +2.43% [+1.35%, +3.52%] | -0.6% [-1.8%, +0.5%] (153) | 52 |
| `blocked_shots` | opinions | 30 | 9 | 6 | 37.5% [16.2%, 65.1%] | -1.77% [-4.52%, +0.98%] | -8.4% [-10.8%, -5.9%] (30) | 11 |
| `blocked_shots` | bets | 4 | 2 | 2 | 100.0% [19.9%, 100.0%] | +1.64% [-1.52%, +4.80%] | -5.4% [-6.9%, -3.9%] (4) | 3 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 7353 | 1885 | 3160 | 45.0% [41.7%, 48.3%] | +1.13% [+0.28%, +1.98%] | -4.6% [-5.0%, -4.2%] (3510) | 56 |
| `goals` | bets | 62 | 34 | 16 | 73.9% [45.5%, 90.6%] | +2.76% [+0.42%, +5.09%] | -1.9% [-3.8%, +0.1%] (59) | 30 |
| `moneyline` | opinions | 114 | 50 | 14 | 50.0% [36.4%, 63.6%] | -0.43% [-1.41%, +0.55%] | -2.4% [-3.4%, -1.5%] (114) | 57 |
| `moneyline` | bets | 23 | 12 | 3 | 60.0% [30.7%, 83.5%] | +0.79% [-1.37%, +2.96%] | -1.2% [-3.4%, +1.0%] (23) | 23 |
| `points` | opinions | 6132 | 1947 | 1561 | 42.6% [39.7%, 45.5%] | +0.54% [-0.73%, +1.81%] | -4.5% [-5.6%, -3.3%] (4724) | 56 |
| `points` | bets | 322 | 173 | 52 | 64.1% [51.7%, 74.8%] | +13.10% [-1.56%, +27.76%] | +9.9% [-4.5%, +24.4%] (322) | 55 |
| `puck_line` | opinions | 1146 | 384 | 372 | 49.6% [44.5%, 54.7%] | +0.73% [-0.17%, +1.64%] | -2.3% [-3.3%, -1.4%] (1043) | 62 |
| `puck_line` | bets | 74 | 35 | 18 | 62.5% [39.3%, 81.1%] | +1.75% [-1.73%, +5.23%] | -1.7% [-4.9%, +1.5%] (74) | 36 |
| `regulation_3_way` | opinions | 168 | 56 | 38 | 43.1% [31.5%, 55.4%] | -0.46% [-1.28%, +0.35%] | — | 56 |
| `regulation_3_way` | bets | 47 | 19 | 10 | 51.4% [30.0%, 72.2%] | +0.37% [-1.35%, +2.10%] | — | 47 |
| `shots_on_goal` | opinions | 6210 | 2498 | 1199 | 49.9% [46.2%, 53.5%] | +1.30% [+0.17%, +2.42%] | -4.4% [-4.7%, -4.1%] (3621) | 56 |
| `shots_on_goal` | bets | 453 | 254 | 68 | 66.0% [55.9%, 74.8%] | +3.72% [+1.74%, +5.70%] | -1.0% [-2.5%, +0.5%] (355) | 55 |
| `team_total` | opinions | 2633 | 918 | 708 | 47.7% [44.5%, 50.9%] | +0.03% [-0.31%, +0.37%] | -5.0% [-5.3%, -4.6%] (2598) | 56 |
| `team_total` | bets | 176 | 90 | 33 | 62.9% [37.3%, 82.9%] | +1.41% [-1.33%, +4.16%] | -4.0% [-6.6%, -1.3%] (176) | 35 |
| `total_goals` | opinions | 1441 | 519 | 385 | 49.1% [44.8%, 53.5%] | +0.16% [-0.36%, +0.68%] | -3.4% [-3.8%, -3.0%] (1413) | 62 |
| `total_goals` | bets | 104 | 48 | 24 | 60.0% [37.6%, 78.9%] | +0.75% [-1.10%, +2.59%] | -3.2% [-4.7%, -1.7%] (104) | 22 |

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
