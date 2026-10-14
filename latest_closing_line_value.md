# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-14T20:42:22+00:00
- Opinions considered: **51631**; matched to a closing price: **48308**; no closing price found: **3323**.
- Within that count, priced before face-off but no close near face-off: **3205** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **108** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1106** opinion(s), 38 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 48308 | 15265 | 14519 | 45.2% [44.2%, 46.2%] | +0.22% [-0.04%, +0.47%] | -4.5% [-4.7%, -4.4%] (32408) | 100 |

3323 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2254 | 1158 | 447 | 64.1% [59.7%, 68.2%] | +3.72% [+1.94%, +5.51%] | -0.1% [-2.0%, +1.8%] (2021) | 99 |

122 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 5532 | 1685 | 1692 | 43.9% [41.3%, 46.5%] | -0.54% [-1.13%, +0.05%] | -4.6% [-4.9%, -4.3%] (3416) | 94 |
| `assists` | bets | 250 | 123 | 65 | 66.5% [55.2%, 76.2%] | +1.75% [+0.93%, +2.57%] | -1.2% [-2.0%, -0.3%] (248) | 86 |
| `blocked_shots` | opinions | 54 | 17 | 9 | 37.8% [20.5%, 58.8%] | -1.92% [-4.01%, +0.18%] | -8.4% [-10.2%, -6.5%] (54) | 21 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 96 | 29 | 15 | 35.8% [14.0%, 65.6%] | -5.55% [-20.54%, +9.44%] | -5.1% [-6.9%, -3.2%] (30) | 8 |
| `goalie_saves` | bets | 13 | 11 | 1 | 91.7% [42.6%, 99.4%] | +19.37% [-2.71%, +41.46%] | -3.6% [-7.6%, +0.4%] (4) | 4 |
| `goals` | opinions | 12401 | 3139 | 5289 | 44.1% [41.6%, 46.7%] | +0.74% [+0.04%, +1.43%] | -4.6% [-4.8%, -4.3%] (5917) | 94 |
| `goals` | bets | 88 | 49 | 22 | 74.2% [51.8%, 88.6%] | +2.36% [+0.56%, +4.15%] | -2.3% [-3.8%, -0.8%] (85) | 47 |
| `hits` | opinions | 74 | 30 | 14 | 50.0% [32.7%, 67.3%] | +0.15% [-0.89%, +1.18%] | -7.9% [-8.8%, -6.9%] (74) | 16 |
| `hits` | bets | 29 | 19 | 7 | 86.4% [52.5%, 97.3%] | +2.28% [+0.54%, +4.01%] | -5.9% [-7.5%, -4.3%] (29) | 15 |
| `moneyline` | opinions | 190 | 85 | 21 | 50.3% [39.5%, 61.0%] | -0.27% [-1.06%, +0.52%] | -2.3% [-3.0%, -1.5%] (190) | 95 |
| `moneyline` | bets | 36 | 18 | 4 | 56.2% [32.5%, 77.4%] | +0.31% [-1.73%, +2.34%] | -1.6% [-3.6%, +0.4%] (36) | 36 |
| `points` | opinions | 10379 | 3208 | 2652 | 41.5% [39.2%, 43.9%] | -0.33% [-1.20%, +0.53%] | -5.0% [-5.7%, -4.2%] (8028) | 94 |
| `points` | bets | 503 | 259 | 101 | 64.4% [55.3%, 72.7%] | +8.68% [-1.46%, +18.83%] | +5.7% [-4.3%, +15.7%] (503) | 91 |
| `puck_line` | opinions | 1897 | 637 | 615 | 49.7% [45.7%, 53.7%] | +0.52% [-0.13%, +1.18%] | -2.5% [-3.2%, -1.8%] (1726) | 100 |
| `puck_line` | bets | 112 | 53 | 25 | 60.9% [41.8%, 77.2%] | +1.21% [-1.25%, +3.67%] | -2.2% [-4.4%, +0.0%] (112) | 58 |
| `regulation_3_way` | opinions | 282 | 104 | 64 | 47.7% [38.3%, 57.3%] | -0.24% [-0.89%, +0.40%] | — | 94 |
| `regulation_3_way` | bets | 74 | 36 | 15 | 61.0% [42.6%, 76.8%] | +0.50% [-1.01%, +2.01%] | — | 74 |
| `shots_on_goal` | opinions | 10573 | 3899 | 2281 | 47.0% [43.8%, 50.2%] | +0.64% [-0.13%, +1.41%] | -4.6% [-4.9%, -4.3%] (6248) | 94 |
| `shots_on_goal` | bets | 735 | 395 | 123 | 64.5% [56.9%, 71.5%] | +3.36% [+1.98%, +4.74%] | -0.9% [-1.9%, +0.1%] (590) | 93 |
| `team_total` | opinions | 4429 | 1579 | 1195 | 48.8% [46.3%, 51.3%] | +0.07% [-0.19%, +0.32%] | -4.9% [-5.2%, -4.7%] (4373) | 94 |
| `team_total` | bets | 251 | 121 | 53 | 61.1% [39.7%, 79.0%] | +1.09% [-1.06%, +3.25%] | -4.2% [-6.3%, -2.1%] (251) | 53 |
| `total_goals` | opinions | 2401 | 853 | 672 | 49.3% [45.9%, 52.8%] | +0.17% [-0.19%, +0.53%] | -3.4% [-3.7%, -3.1%] (2352) | 100 |
| `total_goals` | bets | 158 | 71 | 29 | 55.0% [35.9%, 72.8%] | +0.79% [-1.04%, +2.62%] | -3.2% [-4.8%, -1.6%] (158) | 37 |

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
