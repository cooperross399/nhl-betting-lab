# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-17T13:43:19+00:00
- Opinions considered: **178665**; matched to a closing price: **169921**; no closing price found: **8744**.
- Within that count, priced before face-off but no close near face-off: **8488** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **231** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5783** opinion(s), 287 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 169921 | 53664 | 52506 | 45.7% [45.2%, 46.3%] | +0.30% [+0.15%, +0.44%] | -4.5% [-4.6%, -4.4%] (110304) | 320 |

8744 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 7770 | 3826 | 1672 | 62.7% [60.7%, 64.8%] | +2.51% [+1.89%, +3.13%] | -1.6% [-2.2%, -1.0%] (6772) | 319 |

389 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 414 | 240 | 77 | 71.2% [63.7%, 77.7%] | +4.09% [+1.43%, +6.75%] | -0.9% [-2.0%, +0.2%] (373) | 185 |

23 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 18795 | 6114 | 5440 | 45.8% [44.3%, 47.3%] | -0.51% [-0.96%, -0.07%] | -4.1% [-4.3%, -4.0%] (11783) | 314 |
| `assists` | bets | 852 | 381 | 222 | 60.5% [54.3%, 66.3%] | +1.08% [+0.69%, +1.48%] | -1.7% [-2.1%, -1.3%] (848) | 296 |
| `assists` | best-bet bar | 24 | 9 | 5 | 47.4% [20.7%, 75.6%] | +0.62% [-1.61%, +2.85%] | -1.9% [-4.3%, +0.5%] (24) | 22 |
| `blocked_shots` | opinions | 1201 | 207 | 701 | 41.4% [34.6%, 48.6%] | -0.31% [-0.64%, +0.02%] | -7.9% [-8.3%, -7.5%] (616) | 154 |
| `blocked_shots` | bets | 115 | 26 | 72 | 60.5% [38.5%, 78.9%] | +0.76% [-0.47%, +1.99%] | -6.8% [-7.6%, -5.9%] (110) | 83 |
| `blocked_shots` | best-bet bar | 10 | 5 | 5 | 100.0% [37.9%, 100.0%] | +1.91% [-0.45%, +4.28%] | -5.3% [-7.9%, -2.8%] (10) | 9 |
| `goalie_saves` | opinions | 5015 | 1400 | 2191 | 49.6% [43.4%, 55.7%] | -0.11% [-0.89%, +0.67%] | -3.2% [-3.7%, -2.7%] (1031) | 172 |
| `goalie_saves` | bets | 277 | 174 | 63 | 81.3% [65.3%, 91.0%] | +6.89% [-1.49%, +15.27%] | +0.8% [-3.1%, +4.7%] (107) | 72 |
| `goalie_saves` | best-bet bar | 19 | 17 | 2 | 100.0% [32.8%, 100.0%] | +34.04% [-27.48%, +95.56%] | +15.3% [-25.0%, +55.6%] (9) | 5 |
| `goals` | opinions | 41570 | 11081 | 18255 | 47.5% [46.0%, 49.0%] | +1.03% [+0.67%, +1.38%] | -4.0% [-4.2%, -3.9%] (19829) | 314 |
| `goals` | bets | 263 | 150 | 60 | 73.9% [63.0%, 82.5%] | +2.91% [+1.71%, +4.11%] | -1.9% [-3.0%, -0.8%] (250) | 158 |
| `goals` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 51 | 30 | 16 | 85.7% [57.2%, 96.4%] | +2.53% [+0.71%, +4.35%] | -5.7% [-7.3%, -4.0%] (51) | 36 |
| `moneyline` | opinions | 630 | 267 | 71 | 47.8% [41.8%, 53.8%] | -0.29% [-0.71%, +0.13%] | -2.2% [-2.6%, -1.8%] (630) | 315 |
| `moneyline` | bets | 97 | 46 | 10 | 52.9% [38.0%, 67.3%] | +0.38% [-0.87%, +1.62%] | -1.5% [-2.7%, -0.3%] (97) | 97 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 36088 | 11267 | 9008 | 41.6% [40.5%, 42.8%] | +0.21% [-0.42%, +0.84%] | -5.2% [-5.4%, -4.9%] (27530) | 314 |
| `points` | bets | 1631 | 757 | 363 | 59.7% [54.7%, 64.5%] | +3.23% [-0.16%, +6.62%] | +0.4% [-3.0%, +3.7%] (1630) | 310 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 5431 | 2122 | 1346 | 51.9% [49.7%, 54.2%] | +0.41% [+0.08%, +0.74%] | -3.1% [-3.4%, -2.7%] (4800) | 320 |
| `puck_line` | bets | 332 | 174 | 63 | 64.7% [53.5%, 74.5%] | +0.86% [-0.14%, +1.86%] | -2.5% [-3.4%, -1.5%] (332) | 176 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 942 | 365 | 211 | 49.9% [44.7%, 55.2%] | -0.08% [-0.43%, +0.27%] | — | 314 |
| `regulation_3_way` | bets | 210 | 96 | 41 | 56.8% [45.8%, 67.2%] | +0.43% [-0.43%, +1.29%] | — | 210 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 37518 | 12828 | 8906 | 44.8% [43.1%, 46.5%] | +0.19% [-0.18%, +0.55%] | -4.7% [-4.9%, -4.6%] (21698) | 314 |
| `shots_on_goal` | bets | 2680 | 1438 | 489 | 65.6% [61.8%, 69.3%] | +3.47% [+2.69%, +4.24%] | -0.9% [-1.4%, -0.5%] (2085) | 313 |
| `shots_on_goal` | best-bet bar | 165 | 110 | 16 | 73.8% [62.5%, 82.7%] | +4.63% [+3.00%, +6.26%] | +1.9% [+0.4%, +3.5%] (165) | 122 |
| `team_total` | opinions | 14415 | 5161 | 3933 | 49.2% [47.8%, 50.6%] | +0.08% [-0.05%, +0.21%] | -4.9% [-5.0%, -4.7%] (14239) | 314 |
| `team_total` | bets | 662 | 294 | 146 | 57.0% [44.3%, 68.8%] | +0.62% [-0.46%, +1.70%] | -4.5% [-5.5%, -3.5%] (662) | 152 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 7942 | 2718 | 2338 | 48.5% [46.6%, 50.4%] | +0.04% [-0.15%, +0.24%] | -3.5% [-3.7%, -3.4%] (7774) | 320 |
| `total_goals` | bets | 531 | 233 | 109 | 55.2% [42.4%, 67.4%] | +0.58% [-0.40%, +1.56%] | -3.3% [-4.2%, -2.4%] (531) | 112 |
| `total_goals` | best-bet bar | 40 | 10 | 15 | 40.0% [10.9%, 78.5%] | -0.86% [-2.90%, +1.18%] | -4.7% [-6.4%, -3.0%] (40) | 11 |

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
- **Best-bet bar**: The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.
- **Games** is the sample each interval counts. A thousand rows
  from ten games are ten games of evidence, not a thousand.
- Positive CLV with a losing record is variance against us; a
  winning record with negative CLV is variance *for* us, and this
  lab treats the second as the more dangerous of the two.
