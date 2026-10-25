# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-10-25T22:47:10+00:00
- Opinions considered: **93054**; matched to a closing price: **88189**; no closing price found: **4865**.
- Within that count, priced before face-off but no close near face-off: **4702** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **10** are in a market the store holds no price for, in their game, from before face-off: `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **153** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **1622** opinion(s), 113 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 88189 | 28035 | 26832 | 45.7% [45.0%, 46.4%] | +0.26% [+0.10%, +0.43%] | -4.5% [-4.6%, -4.4%] (58857) | 174 |

4865 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 3937 | 1984 | 814 | 63.5% [60.6%, 66.4%] | +3.02% [+1.96%, +4.08%] | -0.8% [-2.0%, +0.3%] (3495) | 173 |

212 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 10012 | 3200 | 2906 | 45.0% [43.1%, 47.0%] | -0.35% [-0.75%, +0.05%] | -4.4% [-4.6%, -4.2%] (6288) | 168 |
| `assists` | bets | 442 | 209 | 109 | 62.8% [54.6%, 70.3%] | +1.42% [+0.84%, +2.00%] | -1.5% [-2.1%, -0.9%] (440) | 156 |
| `blocked_shots` | opinions | 264 | 60 | 122 | 42.3% [31.1%, 54.2%] | -0.52% [-1.43%, +0.40%] | -8.0% [-9.0%, -7.1%] (174) | 50 |
| `blocked_shots` | bets | 22 | 8 | 12 | 80.0% [36.4%, 96.5%] | +2.27% [-2.27%, +6.80%] | -6.0% [-7.8%, -4.2%] (21) | 20 |
| `goalie_saves` | opinions | 790 | 220 | 304 | 45.3% [32.6%, 58.6%] | -0.96% [-3.40%, +1.48%] | -3.9% [-4.9%, -3.0%] (180) | 34 |
| `goalie_saves` | bets | 53 | 34 | 12 | 82.9% [52.6%, 95.5%] | +7.03% [-2.98%, +17.03%] | -1.7% [-4.9%, +1.4%] (24) | 18 |
| `goals` | opinions | 22226 | 5960 | 9610 | 47.2% [45.1%, 49.4%] | +1.24% [+0.70%, +1.77%] | -4.2% [-4.5%, -4.0%] (10590) | 168 |
| `goals` | bets | 142 | 82 | 32 | 74.5% [58.6%, 85.8%] | +2.59% [+1.07%, +4.10%] | -2.1% [-3.4%, -0.8%] (136) | 81 |
| `hits` | opinions | 326 | 118 | 90 | 50.0% [40.8%, 59.2%] | +0.04% [-0.62%, +0.70%] | -7.9% [-8.5%, -7.3%] (326) | 61 |
| `hits` | bets | 107 | 49 | 31 | 64.5% [43.6%, 81.0%] | +0.94% [-0.52%, +2.39%] | -7.1% [-8.4%, -5.8%] (107) | 54 |
| `moneyline` | opinions | 338 | 143 | 37 | 47.5% [39.4%, 55.7%] | -0.28% [-0.86%, +0.30%] | -2.2% [-2.8%, -1.7%] (338) | 169 |
| `moneyline` | bets | 58 | 28 | 7 | 54.9% [35.7%, 72.8%] | +0.65% [-0.96%, +2.26%] | -1.2% [-2.7%, +0.4%] (58) | 58 |
| `points` | opinions | 18960 | 5904 | 4777 | 41.6% [40.1%, 43.1%] | -0.39% [-0.90%, +0.13%] | -5.0% [-5.5%, -4.6%] (14557) | 168 |
| `points` | bets | 882 | 417 | 190 | 60.3% [53.2%, 67.0%] | +5.32% [-0.76%, +11.39%] | +2.4% [-3.6%, +8.4%] (882) | 164 |
| `puck_line` | opinions | 3155 | 1157 | 904 | 51.4% [48.4%, 54.4%] | +0.49% [+0.02%, +0.96%] | -2.8% [-3.2%, -2.3%] (2840) | 174 |
| `puck_line` | bets | 199 | 108 | 39 | 67.5% [53.7%, 78.8%] | +1.07% [-0.40%, +2.54%] | -2.3% [-3.6%, -0.9%] (199) | 104 |
| `regulation_3_way` | opinions | 504 | 191 | 111 | 48.6% [41.5%, 55.8%] | -0.12% [-0.60%, +0.35%] | — | 168 |
| `regulation_3_way` | bets | 118 | 57 | 22 | 59.4% [44.8%, 72.4%] | +0.73% [-0.46%, +1.91%] | — | 118 |
| `shots_on_goal` | opinions | 19405 | 6785 | 4552 | 45.7% [43.4%, 48.0%] | +0.27% [-0.19%, +0.73%] | -4.7% [-4.9%, -4.5%] (11546) | 168 |
| `shots_on_goal` | bets | 1344 | 716 | 246 | 65.2% [59.7%, 70.3%] | +3.50% [+2.44%, +4.56%] | -0.6% [-1.3%, +0.1%] (1058) | 167 |
| `team_total` | opinions | 7929 | 2810 | 2171 | 48.8% [46.9%, 50.7%] | +0.07% [-0.12%, +0.25%] | -4.9% [-5.1%, -4.7%] (7830) | 168 |
| `team_total` | bets | 359 | 178 | 79 | 63.6% [45.9%, 78.2%] | +1.22% [-0.38%, +2.83%] | -3.9% [-5.5%, -2.4%] (359) | 82 |
| `total_goals` | opinions | 4280 | 1487 | 1248 | 49.0% [46.4%, 51.6%] | +0.07% [-0.18%, +0.33%] | -3.5% [-3.7%, -3.3%] (4188) | 174 |
| `total_goals` | bets | 211 | 98 | 35 | 55.7% [37.7%, 72.3%] | +1.01% [-0.67%, +2.69%] | -2.9% [-4.4%, -1.5%] (211) | 50 |

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
