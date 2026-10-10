# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-10T13:45:00+00:00
- Opinions considered: **32779**; matched to a closing price: **30760**; no closing price found: **2019**.
- Within that count, priced before face-off but no close near face-off: **1942** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **67** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **7223** opinion(s), 315 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 30760 | 10060 | 9061 | 46.4% [45.3%, 47.5%] | +0.65% [+0.35%, +0.95%] | -4.4% [-4.6%, -4.1%] (20479) | 66 |

2019 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 1526 | 814 | 283 | 65.5% [60.0%, 70.6%] | +4.88% [+2.35%, +7.41%] | +1.0% [-1.7%, +3.6%] (1363) | 65 |

58 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 11 markets that
share the table (Bonferroni: z = 2.838 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 11 markets] | Mean CLV% [95% family-wise, 11 markets] | EV at close [95% family-wise, 11 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 3602 | 1163 | 1053 | 45.6% [42.6%, 48.7%] | -0.10% [-0.86%, +0.65%] | -4.5% [-5.0%, -4.1%] (2149) | 60 |
| `assists` | bets | 168 | 91 | 36 | 68.9% [56.5%, 79.2%] | +2.27% [+1.22%, +3.31%] | -0.8% [-2.0%, +0.3%] (166) | 56 |
| `blocked_shots` | opinions | 30 | 9 | 6 | 37.5% [16.2%, 65.1%] | -1.77% [-4.52%, +0.98%] | -8.4% [-10.8%, -5.9%] (30) | 11 |
| `blocked_shots` | bets | 4 | 2 | 2 | 100.0% [19.9%, 100.0%] | +1.64% [-1.52%, +4.80%] | -5.4% [-6.9%, -3.9%] (4) | 3 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.2%, 65.3%] | -5.55% [-20.40%, +9.30%] | -5.1% [-6.9%, -3.3%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [43.0%, 99.4%] | +19.37% [-2.50%, +41.25%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 7869 | 2031 | 3386 | 45.3% [42.0%, 48.6%] | +1.20% [+0.39%, +2.00%] | -4.5% [-4.9%, -4.1%] (3758) | 60 |
| `goals` | bets | 68 | 38 | 18 | 76.0% [48.5%, 91.4%] | +2.64% [+0.50%, +4.78%] | -2.1% [-3.8%, -0.3%] (65) | 33 |
| `moneyline` | opinions | 122 | 54 | 15 | 50.5% [37.2%, 63.7%] | -0.43% [-1.36%, +0.50%] | -2.4% [-3.3%, -1.5%] (122) | 61 |
| `moneyline` | bets | 23 | 12 | 3 | 60.0% [30.7%, 83.5%] | +0.79% [-1.37%, +2.96%] | -1.2% [-3.4%, +1.0%] (23) | 23 |
| `points` | opinions | 6576 | 2075 | 1673 | 42.3% [39.5%, 45.2%] | +0.37% [-0.84%, +1.58%] | -4.5% [-5.6%, -3.4%] (5059) | 60 |
| `points` | bets | 346 | 188 | 57 | 65.1% [53.4%, 75.2%] | +12.31% [-1.53%, +26.14%] | +9.1% [-4.6%, +22.8%] (346) | 59 |
| `puck_line` | opinions | 1227 | 414 | 399 | 50.0% [45.1%, 54.9%] | +0.74% [-0.13%, +1.61%] | -2.3% [-3.2%, -1.4%] (1116) | 66 |
| `puck_line` | bets | 76 | 35 | 20 | 62.5% [39.3%, 81.1%] | +1.70% [-1.69%, +5.10%] | -1.7% [-4.8%, +1.4%] (76) | 38 |
| `regulation_3_way` | opinions | 180 | 61 | 39 | 43.3% [32.1%, 55.1%] | -0.44% [-1.22%, +0.34%] | — | 60 |
| `regulation_3_way` | bets | 49 | 21 | 10 | 53.8% [32.6%, 73.8%] | +0.47% [-1.20%, +2.13%] | — | 49 |
| `shots_on_goal` | opinions | 6692 | 2663 | 1322 | 49.6% [46.0%, 53.1%] | +1.19% [+0.12%, +2.25%] | -4.4% [-4.7%, -4.1%] (3917) | 60 |
| `shots_on_goal` | bets | 483 | 266 | 77 | 65.5% [55.7%, 74.2%] | +3.66% [+1.79%, +5.53%] | -1.0% [-2.4%, +0.4%] (383) | 59 |
| `team_total` | opinions | 2825 | 1001 | 745 | 48.1% [45.0%, 51.2%] | +0.06% [-0.27%, +0.39%] | -4.9% [-5.3%, -4.6%] (2788) | 60 |
| `team_total` | bets | 183 | 95 | 35 | 64.2% [38.9%, 83.5%] | +1.58% [-1.10%, +4.25%] | -3.8% [-6.4%, -1.2%] (183) | 37 |
| `total_goals` | opinions | 1541 | 560 | 408 | 49.4% [45.2%, 53.6%] | +0.20% [-0.29%, +0.70%] | -3.4% [-3.8%, -3.0%] (1510) | 66 |
| `total_goals` | bets | 113 | 55 | 24 | 61.8% [39.8%, 79.8%] | +1.30% [-1.06%, +3.66%] | -2.7% [-4.8%, -0.6%] (113) | 24 |

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
