# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-15T20:46:36+00:00
- Opinions considered: **174618**; matched to a closing price: **165899**; no closing price found: **8719**.
- Within that count, priced before face-off but no close near face-off: **8463** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **231** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2984** opinion(s), 155 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 165899 | 52529 | 51120 | 45.8% [45.2%, 46.3%] | +0.29% [+0.14%, +0.45%] | -4.5% [-4.6%, -4.4%] (107794) | 313 |

8719 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 7556 | 3725 | 1623 | 62.8% [60.7%, 64.8%] | +2.55% [+1.92%, +3.18%] | -1.5% [-2.1%, -0.9%] (6587) | 312 |

388 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 396 | 231 | 76 | 72.2% [65.2%, 78.3%] | +4.32% [+1.56%, +7.07%] | -0.7% [-1.8%, +0.3%] (355) | 179 |

22 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 18371 | 5976 | 5318 | 45.8% [44.2%, 47.3%] | -0.52% [-0.98%, -0.06%] | -4.2% [-4.3%, -4.0%] (11517) | 307 |
| `assists` | bets | 833 | 367 | 221 | 60.0% [53.7%, 65.9%] | +1.07% [+0.67%, +1.47%] | -1.8% [-2.2%, -1.3%] (829) | 289 |
| `assists` | best-bet bar | 23 | 8 | 5 | 44.4% [18.3%, 74.0%] | +0.47% [-1.82%, +2.75%] | -2.0% [-4.5%, +0.4%] (23) | 21 |
| `blocked_shots` | opinions | 1111 | 195 | 664 | 43.6% [36.8%, 50.7%] | -0.22% [-0.55%, +0.10%] | -7.9% [-8.3%, -7.5%] (574) | 148 |
| `blocked_shots` | bets | 107 | 22 | 69 | 57.9% [35.6%, 77.3%] | +0.66% [-0.58%, +1.90%] | -6.9% [-7.7%, -6.1%] (102) | 78 |
| `blocked_shots` | best-bet bar | 10 | 5 | 5 | 100.0% [37.9%, 100.0%] | +1.91% [-0.45%, +4.28%] | -5.3% [-7.9%, -2.8%] (10) | 9 |
| `goalie_saves` | opinions | 4746 | 1315 | 2089 | 49.5% [43.1%, 55.9%] | -0.13% [-0.94%, +0.68%] | -3.2% [-3.7%, -2.7%] (979) | 165 |
| `goalie_saves` | bets | 261 | 165 | 57 | 80.9% [64.2%, 90.9%] | +7.14% [-1.73%, +16.00%] | +0.7% [-3.3%, +4.8%] (102) | 68 |
| `goalie_saves` | best-bet bar | 19 | 17 | 2 | 100.0% [32.8%, 100.0%] | +34.04% [-27.48%, +95.56%] | +15.3% [-25.0%, +55.6%] (9) | 5 |
| `goals` | opinions | 40637 | 10846 | 17803 | 47.5% [46.0%, 49.0%] | +1.02% [+0.66%, +1.38%] | -4.1% [-4.2%, -3.9%] (19379) | 307 |
| `goals` | bets | 256 | 145 | 59 | 73.6% [62.5%, 82.3%] | +2.83% [+1.65%, +4.02%] | -2.0% [-3.0%, -0.9%] (243) | 154 |
| `goals` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 51 | 30 | 16 | 85.7% [57.2%, 96.4%] | +2.53% [+0.71%, +4.35%] | -5.7% [-7.3%, -4.0%] (51) | 36 |
| `moneyline` | opinions | 616 | 264 | 68 | 48.2% [42.1%, 54.3%] | -0.27% [-0.70%, +0.15%] | -2.2% [-2.6%, -1.8%] (616) | 308 |
| `moneyline` | bets | 94 | 44 | 10 | 52.4% [37.3%, 67.1%] | +0.38% [-0.90%, +1.67%] | -1.5% [-2.8%, -0.3%] (94) | 94 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 35277 | 11046 | 8779 | 41.7% [40.5%, 42.8%] | +0.18% [-0.46%, +0.83%] | -5.1% [-5.4%, -4.9%] (26910) | 307 |
| `points` | bets | 1602 | 748 | 354 | 59.9% [54.9%, 64.8%] | +3.30% [-0.15%, +6.75%] | +0.4% [-3.0%, +3.8%] (1601) | 303 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 5323 | 2084 | 1313 | 52.0% [49.7%, 54.2%] | +0.41% [+0.08%, +0.75%] | -3.1% [-3.4%, -2.7%] (4708) | 313 |
| `puck_line` | bets | 323 | 172 | 58 | 64.9% [53.7%, 74.7%] | +0.87% [-0.15%, +1.90%] | -2.5% [-3.4%, -1.5%] (323) | 171 |
| `puck_line` | best-bet bar | 16 | 11 | 2 | 78.6% [39.1%, 95.4%] | +2.17% [-0.84%, +5.19%] | -0.4% [-2.5%, +1.7%] (16) | 13 |
| `regulation_3_way` | opinions | 921 | 361 | 202 | 50.2% [44.9%, 55.5%] | -0.07% [-0.43%, +0.29%] | — | 307 |
| `regulation_3_way` | bets | 204 | 94 | 39 | 57.0% [45.9%, 67.4%] | +0.45% [-0.44%, +1.34%] | — | 204 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 36677 | 12578 | 8681 | 44.9% [43.2%, 46.7%] | +0.21% [-0.17%, +0.58%] | -4.7% [-4.9%, -4.6%] (21225) | 307 |
| `shots_on_goal` | bets | 2621 | 1399 | 478 | 65.3% [61.4%, 68.9%] | +3.46% [+2.67%, +4.25%] | -1.0% [-1.4%, -0.5%] (2038) | 306 |
| `shots_on_goal` | best-bet bar | 160 | 105 | 16 | 72.9% [61.3%, 82.1%] | +4.70% [+3.02%, +6.38%] | +1.9% [+0.4%, +3.5%] (160) | 117 |
| `team_total` | opinions | 14083 | 5069 | 3805 | 49.3% [47.9%, 50.7%] | +0.08% [-0.05%, +0.21%] | -4.9% [-5.0%, -4.7%] (13912) | 307 |
| `team_total` | bets | 627 | 282 | 140 | 57.9% [45.2%, 69.6%] | +0.72% [-0.35%, +1.80%] | -4.4% [-5.4%, -3.3%] (627) | 147 |
| `team_total` | best-bet bar | 43 | 25 | 10 | 75.8% [36.3%, 94.5%] | +2.11% [-1.21%, +5.43%] | -3.5% [-6.5%, -0.5%] (43) | 18 |
| `total_goals` | opinions | 7763 | 2661 | 2292 | 48.6% [46.7%, 50.6%] | +0.06% [-0.14%, +0.25%] | -3.5% [-3.7%, -3.4%] (7600) | 313 |
| `total_goals` | bets | 508 | 230 | 104 | 56.9% [44.2%, 68.8%] | +0.70% [-0.26%, +1.67%] | -3.2% [-4.1%, -2.3%] (508) | 109 |
| `total_goals` | best-bet bar | 34 | 10 | 14 | 50.0% [14.4%, 85.6%] | -0.31% [-2.09%, +1.47%] | -4.3% [-5.8%, -2.7%] (34) | 10 |

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
