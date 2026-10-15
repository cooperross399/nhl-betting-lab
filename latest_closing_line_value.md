# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-15T13:44:55+00:00
- Opinions considered: **52737**; matched to a closing price: **49402**; no closing price found: **3335**.
- Within that count, priced before face-off but no close near face-off: **3217** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **108** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5814** opinion(s), 218 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 49402 | 15568 | 14863 | 45.1% [44.1%, 46.1%] | +0.18% [-0.07%, +0.44%] | -4.6% [-4.7%, -4.4%] (33130) | 102 |

3335 opinion(s) had no closing price and are not in this table.

The interval includes zero, which means **no demonstrated edge** (closing-line value).

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 2292 | 1178 | 451 | 64.0% [59.7%, 68.1%] | +3.68% [+1.92%, +5.44%] | -0.1% [-2.0%, +1.7%] (2055) | 101 |

122 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 5653 | 1719 | 1726 | 43.8% [41.2%, 46.4%] | -0.58% [-1.17%, +0.01%] | -4.6% [-5.0%, -4.3%] (3490) | 96 |
| `assists` | bets | 256 | 127 | 65 | 66.5% [55.5%, 76.0%] | +1.79% [+0.99%, +2.60%] | -1.1% [-2.0%, -0.3%] (254) | 88 |
| `blocked_shots` | opinions | 56 | 18 | 9 | 38.3% [21.2%, 58.9%] | -1.88% [-3.92%, +0.15%] | -8.4% [-10.2%, -6.6%] (56) | 22 |
| `blocked_shots` | bets | 5 | 3 | 2 | 100.0% [26.8%, 100.0%] | +1.68% [-0.79%, +4.15%] | -5.0% [-6.6%, -3.5%] (5) | 4 |
| `goalie_saves` | opinions | 100 | 30 | 16 | 35.7% [14.4%, 64.6%] | -5.34% [-19.66%, +8.98%] | -5.5% [-7.2%, -3.8%] (34) | 9 |
| `goalie_saves` | bets | 15 | 12 | 1 | 85.7% [39.2%, 98.2%] | +16.80% [-5.78%, +39.38%] | -5.1% [-10.8%, +0.5%] (6) | 5 |
| `goals` | opinions | 12686 | 3200 | 5416 | 44.0% [41.5%, 46.5%] | +0.68% [-0.02%, +1.37%] | -4.6% [-4.8%, -4.3%] (6048) | 96 |
| `goals` | bets | 89 | 50 | 22 | 74.6% [52.4%, 88.7%] | +2.35% [+0.57%, +4.13%] | -2.3% [-3.7%, -0.9%] (86) | 48 |
| `hits` | opinions | 76 | 30 | 16 | 50.0% [32.7%, 67.3%] | +0.14% [-0.87%, +1.15%] | -7.9% [-8.8%, -6.9%] (76) | 17 |
| `hits` | bets | 30 | 19 | 8 | 86.4% [52.5%, 97.3%] | +2.20% [+0.49%, +3.91%] | -6.0% [-7.5%, -4.4%] (30) | 16 |
| `moneyline` | opinions | 194 | 87 | 21 | 50.3% [39.6%, 60.9%] | -0.26% [-1.05%, +0.53%] | -2.3% [-3.0%, -1.5%] (194) | 97 |
| `moneyline` | bets | 37 | 19 | 4 | 57.6% [34.0%, 78.2%] | +0.48% [-1.56%, +2.53%] | -1.4% [-3.4%, +0.6%] (37) | 37 |
| `points` | opinions | 10618 | 3277 | 2701 | 41.4% [39.1%, 43.7%] | -0.36% [-1.22%, +0.49%] | -5.0% [-5.8%, -4.3%] (8209) | 96 |
| `points` | bets | 512 | 264 | 101 | 64.2% [55.2%, 72.3%] | +8.59% [-1.39%, +18.57%] | +5.6% [-4.3%, +15.4%] (512) | 93 |
| `puck_line` | opinions | 1937 | 651 | 624 | 49.6% [45.6%, 53.5%] | +0.52% [-0.13%, +1.17%] | -2.5% [-3.2%, -1.8%] (1762) | 102 |
| `puck_line` | bets | 114 | 55 | 25 | 61.8% [42.9%, 77.7%] | +1.23% [-1.19%, +3.64%] | -2.2% [-4.4%, +0.0%] (114) | 59 |
| `regulation_3_way` | opinions | 288 | 106 | 65 | 47.5% [38.2%, 57.0%] | -0.22% [-0.86%, +0.41%] | — | 96 |
| `regulation_3_way` | bets | 76 | 37 | 15 | 60.7% [42.5%, 76.3%] | +0.56% [-0.94%, +2.05%] | — | 76 |
| `shots_on_goal` | opinions | 10816 | 3971 | 2356 | 46.9% [43.8%, 50.1%] | +0.61% [-0.14%, +1.37%] | -4.6% [-4.9%, -4.4%] (6390) | 96 |
| `shots_on_goal` | bets | 749 | 400 | 126 | 64.2% [56.6%, 71.1%] | +3.26% [+1.88%, +4.63%] | -1.0% [-2.0%, +0.0%] (602) | 95 |
| `team_total` | opinions | 4526 | 1611 | 1223 | 48.8% [46.3%, 51.3%] | +0.07% [-0.18%, +0.32%] | -4.9% [-5.2%, -4.7%] (4469) | 96 |
| `team_total` | bets | 251 | 121 | 53 | 61.1% [39.7%, 79.0%] | +1.09% [-1.06%, +3.25%] | -4.2% [-6.3%, -2.1%] (251) | 53 |
| `total_goals` | opinions | 2452 | 868 | 690 | 49.3% [45.9%, 52.7%] | +0.16% [-0.20%, +0.51%] | -3.4% [-3.7%, -3.1%] (2402) | 102 |
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
