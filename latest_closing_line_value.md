# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-18T14:11:17+00:00
- Opinions considered: **184883**; matched to a closing price: **176074**; no closing price found: **8809**.
- Within that count, priced before face-off but no close near face-off: **8550** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **234** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1580** opinion(s), 63 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 176074 | 55576 | 54472 | 45.7% [45.2%, 46.2%] | +0.29% [+0.14%, +0.43%] | -4.5% [-4.6%, -4.4%] (114162) | 331 |

8809 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 8065 | 3988 | 1733 | 63.0% [60.9%, 65.0%] | +2.51% [+1.91%, +3.10%] | -1.5% [-2.1%, -1.0%] (7043) | 330 |

393 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 432 | 254 | 79 | 72.0% [64.7%, 78.2%] | +4.29% [+1.73%, +6.85%] | -0.6% [-1.7%, +0.5%] (391) | 194 |

23 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 19434 | 6317 | 5631 | 45.8% [44.3%, 47.3%] | -0.51% [-0.95%, -0.07%] | -4.1% [-4.3%, -4.0%] (12183) | 325 |
| `assists` | bets | 885 | 388 | 234 | 59.6% [53.5%, 65.4%] | +1.02% [+0.63%, +1.41%] | -1.8% [-2.2%, -1.4%] (881) | 307 |
| `assists` | best-bet bar | 25 | 9 | 5 | 45.0% [19.6%, 73.3%] | +0.41% [-1.81%, +2.63%] | -2.1% [-4.4%, +0.3%] (25) | 23 |
| `blocked_shots` | opinions | 1258 | 215 | 734 | 41.0% [34.3%, 48.1%] | -0.35% [-0.68%, -0.01%] | -7.9% [-8.2%, -7.5%] (646) | 163 |
| `blocked_shots` | bets | 122 | 29 | 75 | 61.7% [40.3%, 79.4%] | +0.84% [-0.38%, +2.05%] | -6.7% [-7.5%, -5.8%] (117) | 88 |
| `blocked_shots` | best-bet bar | 11 | 6 | 5 | 100.0% [42.2%, 100.0%] | +2.65% [-0.44%, +5.74%] | -4.7% [-7.7%, -1.7%] (11) | 10 |
| `goalie_saves` | opinions | 5392 | 1489 | 2373 | 49.3% [43.5%, 55.2%] | -0.09% [-0.82%, +0.63%] | -3.2% [-3.6%, -2.7%] (1101) | 183 |
| `goalie_saves` | bets | 283 | 174 | 68 | 80.9% [65.0%, 90.7%] | +6.74% [-1.48%, +14.95%] | +0.8% [-3.1%, +4.6%] (110) | 74 |
| `goalie_saves` | best-bet bar | 19 | 17 | 2 | 100.0% [32.8%, 100.0%] | +34.04% [-27.48%, +95.56%] | +15.3% [-25.0%, +55.6%] (9) | 5 |
| `goals` | opinions | 43074 | 11520 | 18950 | 47.8% [46.3%, 49.2%] | +1.02% [+0.68%, +1.37%] | -4.0% [-4.2%, -3.8%] (20554) | 325 |
| `goals` | bets | 278 | 161 | 63 | 74.9% [64.4%, 83.1%] | +3.01% [+1.86%, +4.16%] | -1.8% [-2.8%, -0.7%] (264) | 165 |
| `goals` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 51 | 30 | 16 | 85.7% [57.2%, 96.4%] | +2.53% [+0.71%, +4.35%] | -5.7% [-7.3%, -4.0%] (51) | 36 |
| `moneyline` | opinions | 652 | 274 | 77 | 47.7% [41.8%, 53.6%] | -0.30% [-0.71%, +0.11%] | -2.2% [-2.6%, -1.8%] (652) | 326 |
| `moneyline` | bets | 98 | 46 | 10 | 52.3% [37.5%, 66.7%] | +0.37% [-0.86%, +1.60%] | -1.5% [-2.7%, -0.3%] (98) | 98 |
| `moneyline` | best-bet bar | 9 | 4 | 1 | 50.0% [14.4%, 85.6%] | -0.33% [-5.82%, +5.16%] | -2.6% [-8.0%, +2.9%] (9) | 9 |
| `points` | opinions | 37354 | 11664 | 9324 | 41.6% [40.5%, 42.7%] | +0.21% [-0.41%, +0.82%] | -5.2% [-5.4%, -4.9%] (28485) | 325 |
| `points` | bets | 1695 | 788 | 380 | 59.9% [55.0%, 64.6%] | +3.16% [-0.11%, +6.42%] | +0.3% [-3.0%, +3.5%] (1694) | 321 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 5600 | 2200 | 1382 | 52.2% [50.0%, 54.4%] | +0.43% [+0.11%, +0.75%] | -3.0% [-3.3%, -2.7%] (4942) | 331 |
| `puck_line` | bets | 337 | 176 | 66 | 64.9% [53.8%, 74.7%] | +0.85% [-0.13%, +1.84%] | -2.4% [-3.3%, -1.5%] (337) | 180 |
| `puck_line` | best-bet bar | 18 | 13 | 2 | 81.2% [43.7%, 96.0%] | +2.23% [-0.44%, +4.90%] | -0.3% [-2.2%, +1.6%] (18) | 14 |
| `regulation_3_way` | opinions | 975 | 376 | 222 | 49.9% [44.7%, 55.1%] | -0.07% [-0.42%, +0.27%] | — | 325 |
| `regulation_3_way` | bets | 215 | 98 | 43 | 57.0% [46.1%, 67.2%] | +0.45% [-0.41%, +1.30%] | — | 215 |
| `regulation_3_way` | best-bet bar | 31 | 16 | 5 | 61.5% [34.8%, 82.8%] | +1.28% [-1.70%, +4.25%] | — | 31 |
| `shots_on_goal` | opinions | 38816 | 13219 | 9212 | 44.7% [43.0%, 46.3%] | +0.15% [-0.21%, +0.50%] | -4.7% [-4.8%, -4.6%] (22429) | 325 |
| `shots_on_goal` | bets | 2783 | 1511 | 500 | 66.2% [62.4%, 69.7%] | +3.49% [+2.73%, +4.24%] | -0.8% [-1.3%, -0.4%] (2173) | 324 |
| `shots_on_goal` | best-bet bar | 179 | 121 | 18 | 75.2% [64.3%, 83.5%] | +5.00% [+3.32%, +6.67%] | +2.3% [+0.8%, +3.9%] (179) | 130 |
| `team_total` | opinions | 14928 | 5356 | 4046 | 49.2% [47.8%, 50.6%] | +0.09% [-0.04%, +0.21%] | -4.9% [-5.0%, -4.7%] (14752) | 325 |
| `team_total` | bets | 684 | 307 | 148 | 57.3% [44.8%, 68.9%] | +0.65% [-0.40%, +1.71%] | -4.5% [-5.5%, -3.5%] (684) | 157 |
| `team_total` | best-bet bar | 47 | 26 | 10 | 70.3% [33.3%, 91.8%] | +1.64% [-1.74%, +5.03%] | -4.0% [-7.1%, -0.8%] (47) | 20 |
| `total_goals` | opinions | 8217 | 2812 | 2415 | 48.5% [46.6%, 50.3%] | +0.08% [-0.11%, +0.27%] | -3.5% [-3.7%, -3.3%] (8044) | 331 |
| `total_goals` | bets | 565 | 253 | 112 | 55.8% [43.3%, 67.7%] | +0.72% [-0.28%, +1.72%] | -3.2% [-4.1%, -2.3%] (565) | 117 |
| `total_goals` | best-bet bar | 42 | 12 | 15 | 44.4% [13.4%, 80.6%] | -0.28% [-2.99%, +2.42%] | -4.2% [-6.5%, -1.9%] (42) | 12 |

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
