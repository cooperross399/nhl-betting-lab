# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-22T22:44:01+00:00
- Opinions considered: **77278**; matched to a closing price: **73059**; no closing price found: **4219**.
- Within that count, priced before face-off but no close near face-off: **4085** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **124** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **6780** opinion(s), 313 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 73059 | 23230 | 21914 | 45.4% [44.6%, 46.2%] | +0.22% [+0.03%, +0.41%] | -4.5% [-4.7%, -4.4%] (49027) | 147 |

4219 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 3249 | 1649 | 656 | 63.6% [60.2%, 66.8%] | +3.28% [+2.01%, +4.55%] | -0.6% [-1.9%, +0.7%] (2899) | 146 |

154 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 8356 | 2634 | 2477 | 44.8% [42.7%, 46.9%] | -0.43% [-0.88%, +0.03%] | -4.5% [-4.8%, -4.2%] (5251) | 141 |
| `assists` | bets | 371 | 182 | 91 | 65.0% [55.9%, 73.1%] | +1.60% [+0.97%, +2.24%] | -1.4% [-2.1%, -0.7%] (369) | 130 |
| `blocked_shots` | opinions | 78 | 26 | 11 | 38.8% [23.9%, 56.2%] | -1.51% [-3.09%, +0.07%] | -8.3% [-9.9%, -6.8%] (70) | 26 |
| `blocked_shots` | bets | 6 | 3 | 3 | 100.0% [26.8%, 100.0%] | +1.40% [-0.77%, +3.57%] | -5.4% [-7.1%, -3.7%] (6) | 5 |
| `goalie_saves` | opinions | 168 | 42 | 44 | 33.9% [16.6%, 56.9%] | -4.04% [-12.82%, +4.75%] | -4.5% [-6.6%, -2.4%] (51) | 11 |
| `goalie_saves` | bets | 16 | 12 | 2 | 85.7% [39.2%, 98.2%] | +15.75% [-6.28%, +37.78%] | -4.1% [-9.5%, +1.3%] (7) | 6 |
| `goals` | opinions | 18645 | 4915 | 7974 | 46.1% [43.8%, 48.3%] | +1.06% [+0.48%, +1.65%] | -4.4% [-4.6%, -4.1%] (8865) | 141 |
| `goals` | bets | 128 | 72 | 30 | 73.5% [56.3%, 85.6%] | +2.51% [+0.88%, +4.14%] | -2.2% [-3.6%, -0.8%] (122) | 69 |
| `hits` | opinions | 190 | 76 | 38 | 50.0% [38.7%, 61.3%] | +0.04% [-0.79%, +0.87%] | -7.9% [-8.7%, -7.1%] (190) | 38 |
| `hits` | bets | 71 | 37 | 17 | 68.5% [46.2%, 84.6%] | +1.53% [-0.16%, +3.23%] | -6.5% [-8.1%, -5.0%] (71) | 37 |
| `moneyline` | opinions | 284 | 121 | 31 | 47.8% [39.0%, 56.8%] | -0.29% [-0.93%, +0.34%] | -2.2% [-2.8%, -1.6%] (284) | 142 |
| `moneyline` | bets | 50 | 24 | 6 | 54.5% [34.1%, 73.6%] | +0.46% [-1.19%, +2.10%] | -1.3% [-2.9%, +0.3%] (50) | 50 |
| `points` | opinions | 15806 | 4887 | 3968 | 41.3% [39.6%, 43.0%] | -0.43% [-1.04%, +0.17%] | -5.0% [-5.6%, -4.5%] (12176) | 141 |
| `points` | bets | 745 | 358 | 161 | 61.3% [53.4%, 68.6%] | +6.17% [-0.93%, +13.27%] | +3.2% [-3.8%, +10.2%] (745) | 138 |
| `puck_line` | opinions | 2723 | 978 | 804 | 51.0% [47.7%, 54.2%] | +0.45% [-0.06%, +0.97%] | -2.7% [-3.2%, -2.1%] (2467) | 147 |
| `puck_line` | bets | 163 | 86 | 33 | 66.2% [50.8%, 78.7%] | +1.05% [-0.69%, +2.79%] | -2.2% [-3.8%, -0.7%] (163) | 85 |
| `regulation_3_way` | opinions | 423 | 160 | 94 | 48.6% [40.9%, 56.5%] | -0.13% [-0.65%, +0.39%] | — | 141 |
| `regulation_3_way` | bets | 99 | 49 | 18 | 60.5% [44.7%, 74.4%] | +0.69% [-0.57%, +1.96%] | — | 99 |
| `shots_on_goal` | opinions | 16138 | 5779 | 3627 | 46.2% [43.6%, 48.8%] | +0.36% [-0.18%, +0.90%] | -4.7% [-4.9%, -4.5%] (9588) | 141 |
| `shots_on_goal` | bets | 1102 | 600 | 193 | 66.0% [59.9%, 71.7%] | +3.70% [+2.46%, +4.94%] | -0.6% [-1.5%, +0.2%] (868) | 140 |
| `team_total` | opinions | 6656 | 2367 | 1809 | 48.8% [46.8%, 50.9%] | +0.04% [-0.15%, +0.24%] | -4.9% [-5.1%, -4.7%] (6570) | 141 |
| `team_total` | bets | 311 | 146 | 68 | 60.1% [41.3%, 76.3%] | +1.03% [-0.76%, +2.82%] | -4.1% [-5.8%, -2.4%] (311) | 71 |
| `total_goals` | opinions | 3592 | 1245 | 1037 | 48.7% [45.9%, 51.6%] | +0.04% [-0.23%, +0.31%] | -3.5% [-3.8%, -3.3%] (3515) | 147 |
| `total_goals` | bets | 187 | 80 | 34 | 52.3% [34.0%, 70.0%] | +0.66% [-1.06%, +2.38%] | -3.3% [-4.8%, -1.8%] (187) | 44 |

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
