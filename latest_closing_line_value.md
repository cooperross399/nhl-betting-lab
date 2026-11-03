# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-03T20:45:02+00:00
- Opinions considered: **123489**; matched to a closing price: **116502**; no closing price found: **6987**.
- Within that count, priced before face-off but no close near face-off: **6773** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **204** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5709** opinion(s), 240 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 116502 | 37247 | 35256 | 45.8% [45.2%, 46.4%] | +0.15% [-0.02%, +0.31%] | -4.5% [-4.6%, -4.4%] (76951) | 225 |

6987 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 5311 | 2670 | 1098 | 63.4% [60.9%, 65.8%] | +2.73% [+1.93%, +3.54%] | -1.2% [-2.0%, -0.4%] (4684) | 224 |

312 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 13191 | 4266 | 3744 | 45.2% [43.4%, 46.9%] | -0.72% [-1.32%, -0.11%] | -4.2% [-4.4%, -4.0%] (8241) | 219 |
| `assists` | bets | 597 | 278 | 147 | 61.8% [54.6%, 68.5%] | +1.34% [+0.85%, +1.82%] | -1.5% [-2.0%, -1.0%] (595) | 205 |
| `blocked_shots` | opinions | 520 | 108 | 269 | 43.0% [34.4%, 52.1%] | -0.34% [-0.88%, +0.19%] | -7.9% [-8.5%, -7.3%] (308) | 85 |
| `blocked_shots` | bets | 54 | 11 | 34 | 55.0% [25.4%, 81.4%] | +0.50% [-1.59%, +2.60%] | -7.0% [-8.1%, -5.9%] (52) | 41 |
| `goalie_saves` | opinions | 2000 | 556 | 829 | 47.5% [38.6%, 56.5%] | -0.49% [-1.80%, +0.82%] | -3.6% [-4.2%, -3.0%] (438) | 79 |
| `goalie_saves` | bets | 112 | 62 | 34 | 79.5% [56.4%, 92.1%] | +3.84% [-1.57%, +9.24%] | -1.6% [-3.3%, +0.2%] (53) | 37 |
| `goals` | opinions | 28960 | 7705 | 12592 | 47.1% [45.3%, 48.9%] | +1.15% [+0.71%, +1.59%] | -4.2% [-4.4%, -4.1%] (13820) | 219 |
| `goals` | bets | 175 | 99 | 38 | 72.3% [58.1%, 83.0%] | +2.46% [+1.14%, +3.79%] | -2.3% [-3.4%, -1.1%] (168) | 103 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 440 | 185 | 49 | 47.3% [40.2%, 54.5%] | -0.26% [-0.78%, +0.25%] | -2.2% [-2.7%, -1.7%] (440) | 220 |
| `moneyline` | bets | 70 | 34 | 9 | 55.7% [37.9%, 72.2%] | +0.68% [-0.80%, +2.17%] | -1.2% [-2.7%, +0.2%] (70) | 70 |
| `points` | opinions | 25066 | 7783 | 6310 | 41.5% [40.2%, 42.8%] | -0.84% [-1.43%, -0.25%] | -5.0% [-5.3%, -4.6%] (19040) | 219 |
| `points` | bets | 1164 | 547 | 256 | 60.2% [54.3%, 65.9%] | +4.24% [-0.43%, +8.92%] | +1.4% [-3.2%, +6.0%] (1164) | 215 |
| `puck_line` | opinions | 3957 | 1516 | 1044 | 52.0% [49.4%, 54.7%] | +0.45% [+0.05%, +0.86%] | -2.9% [-3.3%, -2.5%] (3542) | 225 |
| `puck_line` | bets | 236 | 134 | 43 | 69.4% [57.0%, 79.6%] | +1.16% [-0.09%, +2.41%] | -2.2% [-3.3%, -1.1%] (236) | 124 |
| `regulation_3_way` | opinions | 657 | 256 | 143 | 49.8% [43.5%, 56.1%] | -0.06% [-0.49%, +0.37%] | — | 219 |
| `regulation_3_way` | bets | 149 | 71 | 28 | 58.7% [45.7%, 70.6%] | +0.58% [-0.51%, +1.67%] | — | 149 |
| `shots_on_goal` | opinions | 25468 | 9095 | 5812 | 46.3% [44.3%, 48.2%] | +0.51% [+0.09%, +0.93%] | -4.6% [-4.8%, -4.5%] (15115) | 219 |
| `shots_on_goal` | bets | 1836 | 1009 | 319 | 66.5% [61.8%, 70.9%] | +3.67% [+2.74%, +4.60%] | -0.7% [-1.3%, -0.1%] (1428) | 218 |
| `team_total` | opinions | 10309 | 3729 | 2723 | 49.2% [47.5%, 50.8%] | +0.06% [-0.10%, +0.22%] | -4.9% [-5.1%, -4.8%] (10188) | 219 |
| `team_total` | bets | 461 | 222 | 98 | 61.2% [46.2%, 74.3%] | +0.90% [-0.44%, +2.23%] | -4.2% [-5.5%, -2.9%] (461) | 106 |
| `total_goals` | opinions | 5560 | 1914 | 1635 | 48.8% [46.5%, 51.1%] | +0.04% [-0.18%, +0.26%] | -3.6% [-3.7%, -3.4%] (5445) | 225 |
| `total_goals` | bets | 337 | 146 | 58 | 52.3% [37.8%, 66.5%] | +0.59% [-0.73%, +1.90%] | -3.3% [-4.5%, -2.1%] (337) | 76 |

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
