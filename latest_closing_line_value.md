# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-08T20:40:56+00:00
- Opinions considered: **147980**; matched to a closing price: **140068**; no closing price found: **7912**.
- Within that count, priced before face-off but no close near face-off: **7674** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **213** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **2153** opinion(s), 99 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 140068 | 44250 | 42822 | 45.5% [44.9%, 46.1%] | +0.13% [-0.03%, +0.28%] | -4.5% [-4.6%, -4.4%] (91591) | 267 |

7912 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 6317 | 3131 | 1343 | 62.9% [60.7%, 65.2%] | +2.54% [+1.85%, +3.23%] | -1.4% [-2.1%, -0.6%] (5550) | 266 |

345 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 15679 | 5080 | 4496 | 45.4% [43.7%, 47.1%] | -0.60% [-1.13%, -0.07%] | -4.2% [-4.4%, -4.0%] (9810) | 261 |
| `assists` | bets | 721 | 321 | 190 | 60.5% [53.7%, 66.8%] | +1.16% [+0.72%, +1.60%] | -1.6% [-2.1%, -1.2%] (717) | 245 |
| `blocked_shots` | opinions | 815 | 152 | 472 | 44.3% [36.8%, 52.1%] | -0.27% [-0.65%, +0.10%] | -7.9% [-8.4%, -7.5%] (443) | 116 |
| `blocked_shots` | bets | 85 | 18 | 55 | 60.0% [34.7%, 80.9%] | +0.77% [-0.75%, +2.29%] | -6.8% [-7.8%, -5.9%] (82) | 63 |
| `goalie_saves` | opinions | 3121 | 840 | 1373 | 48.1% [40.9%, 55.3%] | -0.50% [-1.46%, +0.45%] | -3.5% [-4.0%, -3.1%] (682) | 119 |
| `goalie_saves` | bets | 164 | 87 | 47 | 74.4% [52.2%, 88.5%] | +3.39% [-0.74%, +7.53%] | -1.5% [-3.0%, +0.1%] (74) | 51 |
| `goals` | opinions | 34582 | 9108 | 15062 | 46.7% [45.0%, 48.3%] | +0.94% [+0.55%, +1.34%] | -4.2% [-4.4%, -4.0%] (16534) | 261 |
| `goals` | bets | 218 | 120 | 50 | 71.4% [59.0%, 81.3%] | +2.28% [+1.15%, +3.41%] | -2.4% [-3.4%, -1.4%] (208) | 128 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `moneyline` | opinions | 524 | 222 | 60 | 47.8% [41.3%, 54.5%] | -0.29% [-0.76%, +0.17%] | -2.2% [-2.7%, -1.8%] (524) | 262 |
| `moneyline` | bets | 79 | 38 | 10 | 55.1% [38.3%, 70.8%] | +0.62% [-0.77%, +2.02%] | -1.3% [-2.6%, +0.1%] (79) | 79 |
| `points` | opinions | 29979 | 9287 | 7534 | 41.4% [40.1%, 42.6%] | -0.41% [-1.03%, +0.21%] | -5.1% [-5.4%, -4.8%] (22814) | 261 |
| `points` | bets | 1380 | 646 | 306 | 60.1% [54.7%, 65.4%] | +3.72% [-0.25%, +7.70%] | +0.9% [-3.0%, +4.8%] (1380) | 257 |
| `puck_line` | opinions | 4612 | 1791 | 1183 | 52.2% [49.8%, 54.7%] | +0.45% [+0.09%, +0.82%] | -3.0% [-3.3%, -2.6%] (4102) | 267 |
| `puck_line` | bets | 276 | 154 | 51 | 68.4% [56.9%, 78.1%] | +1.12% [+0.03%, +2.22%] | -2.3% [-3.3%, -1.3%] (276) | 146 |
| `regulation_3_way` | opinions | 783 | 306 | 169 | 49.8% [44.1%, 55.6%] | -0.09% [-0.48%, +0.31%] | — | 261 |
| `regulation_3_way` | bets | 173 | 85 | 31 | 59.9% [47.8%, 70.8%] | +0.66% [-0.34%, +1.65%] | — | 173 |
| `shots_on_goal` | opinions | 31061 | 10759 | 7284 | 45.2% [43.4%, 47.1%] | +0.18% [-0.23%, +0.58%] | -4.7% [-4.9%, -4.6%] (18050) | 261 |
| `shots_on_goal` | bets | 2180 | 1181 | 387 | 65.9% [61.6%, 69.9%] | +3.50% [+2.63%, +4.36%] | -0.8% [-1.4%, -0.3%] (1693) | 260 |
| `team_total` | opinions | 11932 | 4300 | 3161 | 49.0% [47.5%, 50.6%] | +0.06% [-0.09%, +0.20%] | -4.9% [-5.0%, -4.7%] (11787) | 261 |
| `team_total` | bets | 517 | 243 | 111 | 59.9% [45.9%, 72.3%] | +0.88% [-0.34%, +2.10%] | -4.2% [-5.4%, -3.0%] (517) | 124 |
| `total_goals` | opinions | 6606 | 2271 | 1922 | 48.5% [46.4%, 50.6%] | +0.05% [-0.16%, +0.26%] | -3.5% [-3.7%, -3.4%] (6471) | 267 |
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
