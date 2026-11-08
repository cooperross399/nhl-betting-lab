# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-08T14:07:26+00:00
- Opinions considered: **146719**; matched to a closing price: **138838**; no closing price found: **7881**.
- Within that count, priced before face-off but no close near face-off: **7659** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **212** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **3385** opinion(s), 167 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 138838 | 43914 | 42316 | 45.5% [44.9%, 46.1%] | +0.13% [-0.02%, +0.29%] | -4.5% [-4.6%, -4.4%] (90785) | 265 |

7881 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 6249 | 3093 | 1326 | 62.8% [60.5%, 65.1%] | +2.54% [+1.84%, +3.23%] | -1.4% [-2.1%, -0.6%] (5498) | 264 |

344 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 15546 | 5045 | 4443 | 45.4% [43.8%, 47.1%] | -0.60% [-1.13%, -0.06%] | -4.2% [-4.4%, -4.0%] (9728) | 259 |
| `assists` | bets | 711 | 316 | 185 | 60.1% [53.3%, 66.5%] | +1.16% [+0.71%, +1.60%] | -1.6% [-2.1%, -1.2%] (707) | 243 |
| `blocked_shots` | opinions | 815 | 152 | 472 | 44.3% [36.8%, 52.1%] | -0.27% [-0.65%, +0.10%] | -7.9% [-8.4%, -7.5%] (443) | 116 |
| `blocked_shots` | bets | 85 | 18 | 55 | 60.0% [34.7%, 80.9%] | +0.77% [-0.75%, +2.29%] | -6.8% [-7.8%, -5.9%] (82) | 63 |
| `goalie_saves` | opinions | 3095 | 820 | 1372 | 47.6% [40.4%, 54.9%] | -0.54% [-1.51%, +0.42%] | -3.5% [-4.0%, -3.1%] (676) | 117 |
| `goalie_saves` | bets | 153 | 77 | 47 | 72.6% [49.3%, 87.9%] | +2.93% [-1.29%, +7.14%] | -1.6% [-3.2%, -0.1%] (72) | 50 |
| `goals` | opinions | 34306 | 9063 | 14918 | 46.7% [45.1%, 48.4%] | +0.97% [+0.57%, +1.36%] | -4.2% [-4.4%, -4.0%] (16403) | 259 |
| `goals` | bets | 218 | 120 | 50 | 71.4% [59.0%, 81.3%] | +2.28% [+1.15%, +3.41%] | -2.4% [-3.4%, -1.4%] (208) | 128 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 520 | 220 | 59 | 47.7% [41.2%, 54.4%] | -0.29% [-0.76%, +0.17%] | -2.2% [-2.7%, -1.8%] (520) | 260 |
| `moneyline` | bets | 78 | 37 | 10 | 54.4% [37.6%, 70.3%] | +0.59% [-0.82%, +2.00%] | -1.3% [-2.7%, +0.1%] (78) | 78 |
| `points` | opinions | 29722 | 9215 | 7428 | 41.3% [40.1%, 42.6%] | -0.40% [-1.03%, +0.22%] | -5.1% [-5.4%, -4.8%] (22622) | 259 |
| `points` | bets | 1369 | 641 | 301 | 60.0% [54.5%, 65.3%] | +3.74% [-0.27%, +7.74%] | +0.9% [-3.0%, +4.8%] (1369) | 255 |
| `puck_line` | opinions | 4582 | 1780 | 1175 | 52.2% [49.8%, 54.7%] | +0.45% [+0.09%, +0.82%] | -2.9% [-3.3%, -2.6%] (4078) | 265 |
| `puck_line` | bets | 272 | 150 | 51 | 67.9% [56.2%, 77.6%] | +1.06% [-0.04%, +2.15%] | -2.3% [-3.3%, -1.3%] (272) | 145 |
| `regulation_3_way` | opinions | 777 | 302 | 168 | 49.6% [43.8%, 55.4%] | -0.09% [-0.49%, +0.30%] | — | 259 |
| `regulation_3_way` | bets | 171 | 83 | 31 | 59.3% [47.2%, 70.3%] | +0.62% [-0.38%, +1.63%] | — | 171 |
| `shots_on_goal` | opinions | 30709 | 10658 | 7144 | 45.2% [43.4%, 47.1%] | +0.18% [-0.24%, +0.59%] | -4.7% [-4.9%, -4.6%] (17825) | 259 |
| `shots_on_goal` | bets | 2157 | 1171 | 380 | 65.9% [61.6%, 69.9%] | +3.51% [+2.64%, +4.39%] | -0.8% [-1.4%, -0.3%] (1675) | 258 |
| `team_total` | opinions | 11835 | 4270 | 3124 | 49.0% [47.5%, 50.6%] | +0.06% [-0.08%, +0.21%] | -4.9% [-5.0%, -4.7%] (11693) | 259 |
| `team_total` | bets | 511 | 242 | 111 | 60.5% [46.5%, 73.0%] | +0.91% [-0.32%, +2.14%] | -4.2% [-5.4%, -3.0%] (511) | 123 |
| `total_goals` | opinions | 6557 | 2255 | 1907 | 48.5% [46.4%, 50.6%] | +0.06% [-0.15%, +0.27%] | -3.5% [-3.7%, -3.3%] (6423) | 265 |
| `total_goals` | bets | 404 | 181 | 71 | 54.4% [40.7%, 67.4%] | +0.71% [-0.46%, +1.87%] | -3.2% [-4.2%, -2.1%] (404) | 92 |

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
