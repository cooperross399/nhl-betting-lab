# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-18T13:38:43+00:00
- Opinions considered: **67030**; matched to a closing price: **62914**; no closing price found: **4116**.
- Within that count, priced before face-off but no close near face-off: **3987** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **119** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1103** opinion(s), 51 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 62914 | 19840 | 19082 | 45.3% [44.4%, 46.1%] | +0.23% [+0.01%, +0.44%] | -4.5% [-4.7%, -4.4%] (42274) | 128 |

4116 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2808 | 1426 | 576 | 63.9% [60.1%, 67.5%] | +3.49% [+2.04%, +4.94%] | -0.4% [-1.9%, +1.1%] (2507) | 127 |

146 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 7192 | 2194 | 2198 | 43.9% [41.8%, 46.1%] | -0.50% [-1.00%, -0.01%] | -4.5% [-4.8%, -4.2%] (4496) | 122 |
| `assists` | bets | 314 | 152 | 81 | 65.2% [55.0%, 74.3%] | +1.72% [+1.01%, +2.44%] | -1.2% [-2.0%, -0.5%] (312) | 111 |
| `blocked_shots` | opinions | 62 | 21 | 9 | 39.6% [23.0%, 59.0%] | -1.75% [-3.69%, +0.18%] | -8.4% [-10.1%, -6.7%] (62) | 25 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 100 | 30 | 16 | 35.7% [14.4%, 64.6%] | -5.34% [-19.66%, +8.98%] | -5.5% [-7.2%, -3.8%] (34) | 9 |
| `goalie_saves` | bets | 15 | 12 | 1 | 85.7% [39.2%, 98.2%] | +16.80% [-5.78%, +39.38%] | -5.1% [-10.8%, +0.5%] (6) | 5 |
| `goals` | opinions | 16159 | 4213 | 6904 | 45.5% [43.1%, 47.9%] | +1.00% [+0.37%, +1.64%] | -4.4% [-4.7%, -4.2%] (7695) | 122 |
| `goals` | bets | 108 | 58 | 29 | 73.4% [53.8%, 86.8%] | +2.26% [+0.59%, +3.93%] | -2.3% [-3.7%, -0.9%] (105) | 59 |
| `hits` | opinions | 90 | 37 | 16 | 50.0% [34.2%, 65.8%] | +0.15% [-0.85%, +1.14%] | -7.8% [-8.7%, -6.9%] (90) | 21 |
| `hits` | bets | 37 | 24 | 8 | 82.8% [55.8%, 94.8%] | +2.27% [+0.74%, +3.80%] | -5.9% [-7.2%, -4.5%] (37) | 20 |
| `moneyline` | opinions | 246 | 109 | 26 | 49.5% [40.1%, 59.0%] | -0.21% [-0.91%, +0.48%] | -2.2% [-2.9%, -1.5%] (246) | 123 |
| `moneyline` | bets | 46 | 23 | 6 | 57.5% [35.8%, 76.7%] | +0.53% [-1.25%, +2.30%] | -1.2% [-3.0%, +0.5%] (46) | 46 |
| `points` | opinions | 13587 | 4184 | 3464 | 41.3% [39.5%, 43.2%] | -0.40% [-1.09%, +0.29%] | -5.1% [-5.7%, -4.5%] (10494) | 122 |
| `points` | bets | 628 | 301 | 134 | 60.9% [52.1%, 69.1%] | +7.07% [-1.24%, +15.38%] | +4.1% [-4.1%, +12.3%] (628) | 119 |
| `puck_line` | opinions | 2419 | 837 | 750 | 50.1% [46.7%, 53.6%] | +0.43% [-0.12%, +0.98%] | -2.6% [-3.2%, -2.0%] (2197) | 128 |
| `puck_line` | bets | 145 | 73 | 31 | 64.0% [47.2%, 78.0%] | +1.13% [-0.82%, +3.08%] | -2.1% [-3.9%, -0.4%] (145) | 74 |
| `regulation_3_way` | opinions | 366 | 136 | 83 | 48.1% [39.7%, 56.5%] | -0.17% [-0.74%, +0.41%] | — | 122 |
| `regulation_3_way` | bets | 91 | 45 | 18 | 61.6% [45.0%, 76.0%] | +0.74% [-0.60%, +2.09%] | — | 91 |
| `shots_on_goal` | opinions | 13822 | 4959 | 3130 | 46.4% [43.5%, 49.2%] | +0.44% [-0.18%, +1.06%] | -4.6% [-4.9%, -4.4%] (8225) | 122 |
| `shots_on_goal` | bets | 946 | 513 | 170 | 66.1% [59.6%, 72.1%] | +3.69% [+2.38%, +5.01%] | -0.7% [-1.6%, +0.2%] (750) | 121 |
| `team_total` | opinions | 5756 | 2046 | 1568 | 48.9% [46.6%, 51.1%] | +0.07% [-0.14%, +0.29%] | -4.9% [-5.1%, -4.7%] (5684) | 122 |
| `team_total` | bets | 295 | 142 | 63 | 61.2% [41.8%, 77.6%] | +1.10% [-0.77%, +2.98%] | -4.1% [-5.9%, -2.2%] (295) | 65 |
| `total_goals` | opinions | 3115 | 1074 | 918 | 48.9% [45.8%, 51.9%] | +0.11% [-0.19%, +0.41%] | -3.5% [-3.7%, -3.3%] (3051) | 128 |
| `total_goals` | bets | 178 | 80 | 33 | 55.2% [36.6%, 72.4%] | +0.88% [-0.86%, +2.62%] | -3.1% [-4.6%, -1.6%] (178) | 41 |

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
