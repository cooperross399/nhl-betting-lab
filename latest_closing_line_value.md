# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-21T23:11:19+00:00
- Opinions considered: **76108**; matched to a closing price: **71903**; no closing price found: **4205**.
- Within that count, priced before face-off but no close near face-off: **4071** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **124** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1170** opinion(s), 64 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 71903 | 22859 | 21598 | 45.4% [44.6%, 46.3%] | +0.23% [+0.04%, +0.42%] | -4.6% [-4.7%, -4.4%] (48264) | 145 |

4205 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 3189 | 1616 | 647 | 63.6% [60.1%, 66.9%] | +3.29% [+1.99%, +4.58%] | -0.6% [-1.9%, +0.8%] (2843) | 144 |

150 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 8225 | 2581 | 2457 | 44.7% [42.6%, 46.9%] | -0.42% [-0.88%, +0.04%] | -4.5% [-4.8%, -4.2%] (5161) | 139 |
| `assists` | bets | 365 | 179 | 91 | 65.3% [56.1%, 73.6%] | +1.62% [+0.97%, +2.26%] | -1.3% [-2.0%, -0.7%] (363) | 128 |
| `blocked_shots` | opinions | 62 | 21 | 9 | 39.6% [23.0%, 59.0%] | -1.75% [-3.69%, +0.18%] | -8.4% [-10.1%, -6.7%] (62) | 25 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 100 | 30 | 16 | 35.7% [14.4%, 64.6%] | -5.34% [-19.66%, +8.98%] | -5.5% [-7.2%, -3.8%] (34) | 9 |
| `goalie_saves` | bets | 15 | 12 | 1 | 85.7% [39.2%, 98.2%] | +16.80% [-5.78%, +39.38%] | -5.1% [-10.8%, +0.5%] (6) | 5 |
| `goals` | opinions | 18375 | 4849 | 7861 | 46.1% [43.8%, 48.4%] | +1.10% [+0.51%, +1.68%] | -4.4% [-4.6%, -4.1%] (8732) | 139 |
| `goals` | bets | 125 | 70 | 30 | 73.7% [56.0%, 86.0%] | +2.36% [+0.72%, +4.00%] | -2.2% [-3.7%, -0.8%] (120) | 67 |
| `hits` | opinions | 176 | 69 | 38 | 50.0% [38.2%, 61.8%] | +0.02% [-0.81%, +0.86%] | -7.9% [-8.7%, -7.1%] (176) | 36 |
| `hits` | bets | 66 | 35 | 17 | 71.4% [50.7%, 85.9%] | +1.64% [+0.09%, +3.18%] | -6.4% [-7.8%, -5.0%] (66) | 35 |
| `moneyline` | opinions | 280 | 119 | 31 | 47.8% [38.9%, 56.8%] | -0.28% [-0.91%, +0.35%] | -2.2% [-2.8%, -1.6%] (280) | 140 |
| `moneyline` | bets | 49 | 23 | 6 | 53.5% [33.0%, 72.9%] | +0.44% [-1.24%, +2.11%] | -1.3% [-3.0%, +0.3%] (49) | 49 |
| `points` | opinions | 15566 | 4808 | 3907 | 41.2% [39.5%, 43.0%] | -0.44% [-1.05%, +0.17%] | -5.1% [-5.6%, -4.5%] (11994) | 139 |
| `points` | bets | 728 | 347 | 160 | 61.1% [53.0%, 68.6%] | +6.21% [-1.05%, +13.48%] | +3.2% [-3.9%, +10.4%] (728) | 136 |
| `puck_line` | opinions | 2693 | 962 | 802 | 50.9% [47.6%, 54.2%] | +0.44% [-0.06%, +0.95%] | -2.7% [-3.2%, -2.1%] (2440) | 145 |
| `puck_line` | bets | 161 | 85 | 33 | 66.4% [50.9%, 79.0%] | +1.07% [-0.69%, +2.83%] | -2.2% [-3.8%, -0.6%] (161) | 83 |
| `regulation_3_way` | opinions | 417 | 157 | 93 | 48.5% [40.6%, 56.4%] | -0.15% [-0.68%, +0.37%] | — | 139 |
| `regulation_3_way` | bets | 98 | 48 | 18 | 60.0% [44.1%, 74.0%] | +0.64% [-0.63%, +1.91%] | — | 98 |
| `shots_on_goal` | opinions | 15903 | 5700 | 3570 | 46.2% [43.6%, 48.8%] | +0.35% [-0.19%, +0.90%] | -4.7% [-4.9%, -4.5%] (9440) | 139 |
| `shots_on_goal` | bets | 1080 | 588 | 188 | 65.9% [59.7%, 71.7%] | +3.71% [+2.44%, +4.98%] | -0.6% [-1.5%, +0.2%] (848) | 138 |
| `team_total` | opinions | 6563 | 2334 | 1787 | 48.9% [46.8%, 50.9%] | +0.06% [-0.14%, +0.25%] | -4.9% [-5.1%, -4.7%] (6478) | 139 |
| `team_total` | bets | 310 | 146 | 67 | 60.1% [41.3%, 76.3%] | +1.03% [-0.76%, +2.82%] | -4.1% [-5.8%, -2.4%] (310) | 70 |
| `total_goals` | opinions | 3543 | 1229 | 1027 | 48.8% [46.0%, 51.7%] | +0.06% [-0.22%, +0.33%] | -3.5% [-3.8%, -3.3%] (3467) | 145 |
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
