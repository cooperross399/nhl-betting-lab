# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-17T20:42:39+00:00
- Opinions considered: **61244**; matched to a closing price: **57216**; no closing price found: **4028**.
- Within that count, priced before face-off but no close near face-off: **3908** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **110** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5786** opinion(s), 199 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 57216 | 18032 | 17304 | 45.2% [44.3%, 46.1%] | +0.23% [+0.00%, +0.45%] | -4.5% [-4.7%, -4.4%] (38431) | 117 |

4028 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2611 | 1326 | 524 | 63.5% [59.6%, 67.3%] | +3.57% [+2.01%, +5.13%] | -0.3% [-1.9%, +1.3%] (2339) | 116 |

144 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 6540 | 1982 | 2010 | 43.8% [41.4%, 46.1%] | -0.53% [-1.06%, -0.01%] | -4.5% [-4.9%, -4.2%] (4068) | 111 |
| `assists` | bets | 292 | 140 | 76 | 64.8% [54.4%, 74.0%] | +1.69% [+0.94%, +2.44%] | -1.3% [-2.1%, -0.5%] (290) | 102 |
| `blocked_shots` | opinions | 62 | 21 | 9 | 39.6% [23.0%, 59.0%] | -1.75% [-3.69%, +0.18%] | -8.4% [-10.1%, -6.7%] (62) | 25 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 100 | 30 | 16 | 35.7% [14.4%, 64.6%] | -5.34% [-19.66%, +8.98%] | -5.5% [-7.2%, -3.8%] (34) | 9 |
| `goalie_saves` | bets | 15 | 12 | 1 | 85.7% [39.2%, 98.2%] | +16.80% [-5.78%, +39.38%] | -5.1% [-10.8%, +0.5%] (6) | 5 |
| `goals` | opinions | 14672 | 3823 | 6246 | 45.4% [42.9%, 47.9%] | +0.99% [+0.31%, +1.66%] | -4.4% [-4.7%, -4.1%] (6997) | 111 |
| `goals` | bets | 101 | 55 | 27 | 74.3% [53.5%, 87.9%] | +2.40% [+0.64%, +4.16%] | -2.2% [-3.6%, -0.7%] (98) | 54 |
| `hits` | opinions | 82 | 33 | 16 | 50.0% [33.4%, 66.6%] | +0.20% [-0.86%, +1.26%] | -7.8% [-8.8%, -6.8%] (82) | 19 |
| `hits` | bets | 33 | 21 | 8 | 84.0% [53.2%, 96.0%] | +2.44% [+0.81%, +4.07%] | -5.7% [-7.2%, -4.2%] (33) | 18 |
| `moneyline` | opinions | 224 | 100 | 24 | 50.0% [40.1%, 59.9%] | -0.19% [-0.93%, +0.55%] | -2.2% [-2.9%, -1.5%] (224) | 112 |
| `moneyline` | bets | 43 | 22 | 5 | 57.9% [35.6%, 77.3%] | +0.58% [-1.31%, +2.48%] | -1.2% [-3.1%, +0.6%] (43) | 43 |
| `points` | opinions | 12325 | 3785 | 3173 | 41.4% [39.3%, 43.4%] | -0.38% [-1.13%, +0.36%] | -5.0% [-5.7%, -4.4%] (9523) | 111 |
| `points` | bets | 582 | 280 | 122 | 60.9% [51.5%, 69.5%] | +7.53% [-1.38%, +16.45%] | +4.5% [-4.3%, +13.3%] (582) | 108 |
| `puck_line` | opinions | 2232 | 766 | 703 | 50.1% [46.4%, 53.8%] | +0.48% [-0.10%, +1.07%] | -2.5% [-3.1%, -1.9%] (2035) | 117 |
| `puck_line` | bets | 134 | 69 | 28 | 65.1% [47.7%, 79.2%] | +1.25% [-0.84%, +3.33%] | -2.1% [-4.0%, -0.2%] (134) | 67 |
| `regulation_3_way` | opinions | 333 | 122 | 75 | 47.3% [38.6%, 56.1%] | -0.18% [-0.79%, +0.43%] | — | 111 |
| `regulation_3_way` | bets | 86 | 42 | 17 | 60.9% [43.8%, 75.7%] | +0.71% [-0.71%, +2.13%] | — | 86 |
| `shots_on_goal` | opinions | 12573 | 4524 | 2793 | 46.3% [43.4%, 49.2%] | +0.45% [-0.21%, +1.12%] | -4.6% [-4.9%, -4.4%] (7459) | 111 |
| `shots_on_goal` | bets | 862 | 463 | 149 | 64.9% [58.1%, 71.2%] | +3.62% [+2.19%, +5.06%] | -0.8% [-1.7%, +0.2%] (690) | 110 |
| `team_total` | opinions | 5237 | 1863 | 1424 | 48.9% [46.5%, 51.2%] | +0.09% [-0.14%, +0.32%] | -4.9% [-5.1%, -4.7%] (5169) | 111 |
| `team_total` | bets | 284 | 139 | 58 | 61.5% [41.6%, 78.2%] | +1.12% [-0.82%, +3.07%] | -4.1% [-6.0%, -2.2%] (284) | 61 |
| `total_goals` | opinions | 2836 | 983 | 815 | 48.6% [45.5%, 51.8%] | +0.10% [-0.22%, +0.42%] | -3.5% [-3.8%, -3.2%] (2778) | 117 |
| `total_goals` | bets | 174 | 80 | 31 | 55.9% [37.1%, 73.2%] | +0.92% [-0.85%, +2.69%] | -3.0% [-4.6%, -1.5%] (174) | 40 |

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
