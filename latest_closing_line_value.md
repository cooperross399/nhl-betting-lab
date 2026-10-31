# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-31T13:02:30+00:00
- Opinions considered: **112898**; matched to a closing price: **107685**; no closing price found: **5213**.
- Within that count, priced before face-off but no close near face-off: **5023** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **180** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5372** opinion(s), 288 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 107685 | 34406 | 32474 | 45.7% [45.1%, 46.4%] | +0.14% [-0.04%, +0.32%] | -4.5% [-4.6%, -4.4%] (71169) | 209 |

5213 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 4880 | 2473 | 999 | 63.7% [61.2%, 66.2%] | +2.87% [+2.00%, +3.74%] | -1.1% [-2.0%, -0.2%] (4321) | 208 |

221 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 12200 | 3937 | 3465 | 45.1% [43.2%, 46.9%] | -0.78% [-1.43%, -0.13%] | -4.3% [-4.5%, -4.0%] (7606) | 203 |
| `assists` | bets | 557 | 264 | 134 | 62.4% [55.1%, 69.2%] | +1.39% [+0.88%, +1.90%] | -1.5% [-2.0%, -1.0%] (555) | 191 |
| `blocked_shots` | opinions | 452 | 91 | 229 | 40.8% [31.7%, 50.6%] | -0.47% [-1.07%, +0.12%] | -8.0% [-8.6%, -7.3%] (276) | 76 |
| `blocked_shots` | bets | 44 | 9 | 29 | 60.0% [24.9%, 87.1%] | +0.75% [-1.72%, +3.23%] | -6.7% [-7.9%, -5.6%] (42) | 34 |
| `goalie_saves` | opinions | 1744 | 467 | 718 | 45.5% [36.5%, 54.9%] | -0.65% [-2.02%, +0.73%] | -3.6% [-4.2%, -3.0%] (385) | 69 |
| `goalie_saves` | bets | 89 | 48 | 30 | 81.4% [57.7%, 93.3%] | +4.59% [-1.90%, +11.08%] | -1.7% [-3.6%, +0.2%] (46) | 32 |
| `goals` | opinions | 26850 | 7140 | 11654 | 47.0% [45.1%, 48.9%] | +1.16% [+0.70%, +1.62%] | -4.2% [-4.4%, -4.0%] (12828) | 203 |
| `goals` | bets | 164 | 95 | 37 | 74.8% [60.4%, 85.3%] | +2.64% [+1.25%, +4.02%] | -2.1% [-3.4%, -0.9%] (157) | 97 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 408 | 172 | 46 | 47.5% [40.1%, 55.0%] | -0.25% [-0.78%, +0.27%] | -2.2% [-2.7%, -1.7%] (408) | 204 |
| `moneyline` | bets | 67 | 33 | 9 | 56.9% [38.6%, 73.5%] | +0.74% [-0.70%, +2.17%] | -1.2% [-2.5%, +0.2%] (67) | 67 |
| `points` | opinions | 23189 | 7211 | 5773 | 41.4% [40.0%, 42.8%] | -0.90% [-1.53%, -0.27%] | -5.0% [-5.4%, -4.7%] (17613) | 203 |
| `points` | bets | 1082 | 518 | 232 | 60.9% [54.8%, 66.8%] | +4.54% [-0.47%, +9.55%] | +1.7% [-3.2%, +6.6%] (1082) | 199 |
| `puck_line` | opinions | 3704 | 1399 | 986 | 51.5% [48.7%, 54.2%] | +0.45% [+0.03%, +0.87%] | -2.8% [-3.3%, -2.4%] (3320) | 209 |
| `puck_line` | bets | 230 | 132 | 41 | 69.8% [57.3%, 80.0%] | +1.16% [-0.12%, +2.43%] | -2.2% [-3.4%, -1.1%] (230) | 121 |
| `regulation_3_way` | opinions | 609 | 234 | 133 | 49.2% [42.7%, 55.7%] | -0.06% [-0.49%, +0.38%] | — | 203 |
| `regulation_3_way` | bets | 136 | 67 | 23 | 59.3% [45.9%, 71.5%] | +0.67% [-0.44%, +1.78%] | — | 136 |
| `shots_on_goal` | opinions | 23417 | 8388 | 5322 | 46.4% [44.3%, 48.4%] | +0.56% [+0.11%, +1.01%] | -4.7% [-4.8%, -4.5%] (13845) | 203 |
| `shots_on_goal` | bets | 1664 | 909 | 288 | 66.1% [61.1%, 70.7%] | +3.77% [+2.76%, +4.77%] | -0.7% [-1.3%, -0.1%] (1295) | 202 |
| `team_total` | opinions | 9577 | 3442 | 2551 | 49.0% [47.3%, 50.7%] | +0.07% [-0.09%, +0.23%] | -4.9% [-5.1%, -4.8%] (9464) | 203 |
| `team_total` | bets | 433 | 213 | 93 | 62.6% [47.0%, 76.0%] | +1.09% [-0.27%, +2.46%] | -4.1% [-5.4%, -2.7%] (433) | 99 |
| `total_goals` | opinions | 5161 | 1791 | 1491 | 48.8% [46.4%, 51.2%] | +0.06% [-0.17%, +0.29%] | -3.5% [-3.7%, -3.3%] (5050) | 209 |
| `total_goals` | bets | 294 | 128 | 49 | 52.2% [37.2%, 66.9%] | +0.61% [-0.82%, +2.04%] | -3.3% [-4.5%, -2.0%] (294) | 67 |

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
