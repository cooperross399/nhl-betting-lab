# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-28T20:47:30+00:00
- Opinions considered: **102932**; matched to a closing price: **97976**; no closing price found: **4956**.
- Within that count, priced before face-off but no close near face-off: **4789** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **157** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2436** opinion(s), 98 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 97976 | 31182 | 29629 | 45.6% [45.0%, 46.3%] | +0.11% [-0.08%, +0.30%] | -4.5% [-4.6%, -4.4%] (64915) | 191 |

4956 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 4408 | 2241 | 913 | 64.1% [61.4%, 66.8%] | +2.92% [+1.97%, +3.88%] | -1.0% [-2.0%, +0.0%] (3906) | 190 |

217 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 11159 | 3555 | 3181 | 44.6% [42.8%, 46.4%] | -0.84% [-1.53%, -0.14%] | -4.3% [-4.6%, -4.1%] (6946) | 185 |
| `assists` | bets | 499 | 235 | 123 | 62.5% [54.8%, 69.6%] | +1.38% [+0.84%, +1.91%] | -1.5% [-2.1%, -0.9%] (497) | 173 |
| `blocked_shots` | opinions | 379 | 76 | 193 | 40.9% [30.9%, 51.7%] | -0.49% [-1.20%, +0.22%] | -8.0% [-8.7%, -7.2%] (232) | 66 |
| `blocked_shots` | bets | 34 | 9 | 22 | 75.0% [35.4%, 94.3%] | +1.34% [-1.69%, +4.37%] | -6.5% [-7.8%, -5.1%] (33) | 28 |
| `goalie_saves` | opinions | 1276 | 351 | 528 | 46.9% [36.3%, 57.9%] | -0.53% [-2.15%, +1.09%] | -3.5% [-4.2%, -2.8%] (288) | 51 |
| `goalie_saves` | bets | 77 | 47 | 20 | 82.5% [58.6%, 94.0%] | +5.32% [-2.00%, +12.65%] | -1.3% [-3.4%, +0.7%] (39) | 27 |
| `goals` | opinions | 24463 | 6560 | 10550 | 47.2% [45.1%, 49.2%] | +1.23% [+0.73%, +1.73%] | -4.2% [-4.4%, -4.0%] (11670) | 185 |
| `goals` | bets | 150 | 88 | 33 | 75.2% [60.0%, 86.0%] | +2.59% [+1.15%, +4.02%] | -2.1% [-3.4%, -0.8%] (144) | 88 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 372 | 158 | 39 | 47.4% [39.8%, 55.3%] | -0.26% [-0.81%, +0.29%] | -2.2% [-2.8%, -1.7%] (372) | 186 |
| `moneyline` | bets | 64 | 31 | 8 | 55.4% [36.9%, 72.5%] | +0.66% [-0.82%, +2.13%] | -1.2% [-2.6%, +0.2%] (64) | 64 |
| `points` | opinions | 21138 | 6521 | 5279 | 41.1% [39.7%, 42.6%] | -0.96% [-1.65%, -0.28%] | -5.0% [-5.4%, -4.6%] (16043) | 185 |
| `points` | bets | 976 | 468 | 210 | 61.1% [54.5%, 67.3%] | +4.92% [-0.60%, +10.44%] | +2.1% [-3.4%, +7.5%] (976) | 181 |
| `puck_line` | opinions | 3421 | 1280 | 945 | 51.7% [48.8%, 54.6%] | +0.49% [+0.05%, +0.93%] | -2.8% [-3.2%, -2.4%] (3069) | 191 |
| `puck_line` | bets | 220 | 125 | 41 | 69.8% [57.0%, 80.2%] | +1.15% [-0.18%, +2.48%] | -2.2% [-3.4%, -1.0%] (220) | 114 |
| `regulation_3_way` | opinions | 555 | 214 | 120 | 49.2% [42.4%, 56.0%] | -0.11% [-0.57%, +0.34%] | — | 185 |
| `regulation_3_way` | bets | 127 | 62 | 23 | 59.6% [45.6%, 72.2%] | +0.68% [-0.45%, +1.82%] | — | 127 |
| `shots_on_goal` | opinions | 21403 | 7563 | 5012 | 46.1% [44.0%, 48.3%] | +0.40% [-0.05%, +0.86%] | -4.7% [-4.8%, -4.5%] (12689) | 185 |
| `shots_on_goal` | bets | 1497 | 798 | 273 | 65.2% [60.0%, 70.1%] | +3.54% [+2.48%, +4.59%] | -0.7% [-1.4%, -0.0%] (1169) | 184 |
| `team_total` | opinions | 8730 | 3130 | 2321 | 48.8% [47.1%, 50.6%] | +0.07% [-0.10%, +0.24%] | -4.9% [-5.1%, -4.7%] (8629) | 185 |
| `team_total` | bets | 405 | 207 | 87 | 65.1% [48.9%, 78.4%] | +1.21% [-0.22%, +2.65%] | -3.9% [-5.3%, -2.5%] (405) | 91 |
| `total_goals` | opinions | 4706 | 1640 | 1355 | 48.9% [46.5%, 51.4%] | +0.08% [-0.17%, +0.32%] | -3.5% [-3.7%, -3.3%] (4603) | 191 |
| `total_goals` | bets | 239 | 114 | 39 | 57.0% [39.9%, 72.6%] | +1.08% [-0.48%, +2.65%] | -2.8% [-4.2%, -1.4%] (239) | 55 |

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
