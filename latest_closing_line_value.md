# Closing-line value

Did the card take prices the market later disagreed with, in our
favour? This answers that on a far smaller sample than the price
backtest needs, which is the whole reason it exists — but it answers
a *narrower* question. Beating the close is evidence of finding
something; it is not profit, and this file never calls it profit.

- Generated: 2026-11-12T14:54:04+00:00
- Opinions considered: **159292**; matched to a closing price: **151270**; no closing price found: **8022**.
- Within that count, priced before face-off but no close near face-off: **7777** — no capture was taken within 150 minutes of face-off (a round missed, or none is scheduled that close). An older price is an intraday price, not the market's last word, so they are not scored.
- Of those, **25** are in a market the store holds no price for, in their game, from before face-off: `blocked_shots` (15), `moneyline` (10). No book pulled these. The capture never priced that market for that game — its request for that market failed or was not yet made (the bulk moneyline, puck line and total joined the capture after its first rounds), or no capture ran before face-off — so they are a gap in what is captured and say nothing about the model.
- The other **220** are in a market that was captured for their game, but their own line or side never was before face-off: the books pulled or moved it, or the capture's ladders did not carry that line.
- Not yet played: **5868** opinion(s), 330 of them clearing the measurement bar (not the card's staked bets), whose game starts after this report was built. None has a closing price yet and none is counted above; each is scored against its close once its game has started.

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
| 151270 | 47915 | 46337 | 45.7% [45.1%, 46.2%] | +0.22% [+0.07%, +0.38%] | -4.5% [-4.6%, -4.4%] (98639) | 287 |

8022 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## All bets

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 6780 | 3360 | 1433 | 62.8% [60.7%, 65.0%] | +2.65% [+1.96%, +3.35%] | -1.4% [-2.1%, -0.7%] (5952) | 286 |

349 bet(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval excludes zero on the negative side: the market moved against these opinions more often than not.

## The card's best-bet bar

The opinions that clear the card's best-bet bar as far as a frozen opinion shows it: an edge of 12% for a prop or 9% for a team market, priced -160 to +600, not in `points`, a moneyline side the model gives at least 40%, and a prop clearing its odds-bracket floor. It approximates the bets the card stakes and is not a list of them: the card stakes on the self-learned edge, applied after the snapshot is frozen, and also applies the win-chance floor to puck lines and regulation sides, the saves starter check and one stake per outcome, none of which a frozen row carries.

| Rows | Beat close | Tied | Beat rate [95%] | Mean CLV% [95%] | EV at close [95%] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- |
| 339 | 201 | 65 | 73.4% [66.0%, 79.6%] | +4.75% [+1.57%, +7.94%] | -0.5% [-1.7%, +0.7%] (301) | 163 |

21 opinion(s) had no closing price and are not in this table.

The interval excludes zero on the positive side.

On expected value at the close — the money figure: The interval includes zero, which means **no demonstrated edge** (value against the closing line).

## By market

Every interval here is corrected for the 12 markets that
share the table (Bonferroni: z = 2.865 in place of 1.960), because a
row that only looks remarkable among a dozen is not remarkable.

| Market | View | Rows | Beat close | Tied | Beat rate [95% family-wise, 12 markets] | Mean CLV% [95% family-wise, 12 markets] | EV at close [95% family-wise, 12 markets] (n) | Games |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `assists` | opinions | 16855 | 5519 | 4825 | 45.9% [44.3%, 47.5%] | -0.53% [-1.03%, -0.04%] | -4.1% [-4.3%, -3.9%] (10545) | 281 |
| `assists` | bets | 773 | 347 | 198 | 60.3% [53.9%, 66.5%] | +1.14% [+0.71%, +1.56%] | -1.7% [-2.1%, -1.2%] (769) | 264 |
| `assists` | best-bet bar | 22 | 8 | 5 | 47.1% [19.5%, 76.5%] | +0.63% [-1.71%, +2.97%] | -1.8% [-4.4%, +0.7%] (22) | 20 |
| `blocked_shots` | opinions | 944 | 173 | 551 | 44.0% [36.7%, 51.6%] | -0.26% [-0.59%, +0.07%] | -7.9% [-8.3%, -7.5%] (509) | 132 |
| `blocked_shots` | bets | 93 | 20 | 59 | 58.8% [35.3%, 78.9%] | +0.71% [-0.70%, +2.11%] | -6.9% [-7.8%, -6.0%] (90) | 69 |
| `blocked_shots` | best-bet bar | 8 | 3 | 5 | 100.0% [26.8%, 100.0%] | +1.26% [-0.77%, +3.29%] | -6.0% [-8.3%, -3.7%] (8) | 7 |
| `goalie_saves` | opinions | 3763 | 972 | 1687 | 46.8% [40.4%, 53.3%] | -0.38% [-1.29%, +0.53%] | -3.4% [-3.9%, -2.8%] (803) | 139 |
| `goalie_saves` | bets | 178 | 99 | 49 | 76.7% [55.3%, 89.8%] | +7.75% [-4.96%, +20.46%] | +0.3% [-4.7%, +5.2%] (81) | 56 |
| `goalie_saves` | best-bet bar | 15 | 13 | 2 | 100.0% [26.8%, 100.0%] | +41.07% [-30.34%, +112.48%] | +18.3% [-33.8%, +70.3%] (7) | 4 |
| `goals` | opinions | 37249 | 9855 | 16310 | 47.1% [45.5%, 48.6%] | +0.98% [+0.61%, +1.36%] | -4.2% [-4.3%, -4.0%] (17810) | 281 |
| `goals` | bets | 235 | 134 | 52 | 73.2% [61.5%, 82.4%] | +2.73% [+1.49%, +3.96%] | -2.1% [-3.2%, -0.9%] (224) | 139 |
| `goals` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `hits` | opinions | 374 | 134 | 106 | 50.0% [41.4%, 58.6%] | +0.01% [-0.70%, +0.73%] | -7.9% [-8.6%, -7.3%] (374) | 67 |
| `hits` | bets | 120 | 57 | 34 | 66.3% [47.1%, 81.3%] | +1.07% [-0.29%, +2.43%] | -7.0% [-8.2%, -5.8%] (120) | 59 |
| `hits` | best-bet bar | 51 | 30 | 16 | 85.7% [57.2%, 96.4%] | +2.53% [+0.71%, +4.35%] | -5.7% [-7.3%, -4.0%] (51) | 36 |
| `moneyline` | opinions | 564 | 240 | 63 | 47.9% [41.6%, 54.3%] | -0.30% [-0.74%, +0.14%] | -2.2% [-2.7%, -1.8%] (564) | 282 |
| `moneyline` | bets | 84 | 40 | 10 | 54.1% [37.9%, 69.4%] | +0.52% [-0.82%, +1.86%] | -1.4% [-2.7%, -0.1%] (84) | 84 |
| `moneyline` | best-bet bar | 8 | 4 | 1 | 57.1% [16.7%, 89.8%] | +0.36% [-5.46%, +6.17%] | -1.9% [-7.6%, +3.9%] (8) | 8 |
| `points` | opinions | 32286 | 10106 | 8029 | 41.7% [40.5%, 42.9%] | -0.07% [-0.71%, +0.58%] | -5.1% [-5.4%, -4.8%] (24583) | 281 |
| `points` | bets | 1471 | 685 | 321 | 59.6% [54.2%, 64.7%] | +3.52% [-0.22%, +7.26%] | +0.7% [-3.0%, +4.4%] (1470) | 277 |
| `points` | best-bet bar | 0 | 0 | 0 | — | — | — | 0 |
| `puck_line` | opinions | 4922 | 1920 | 1243 | 52.2% [49.8%, 54.5%] | +0.46% [+0.11%, +0.81%] | -3.0% [-3.3%, -2.7%] (4365) | 287 |
| `puck_line` | bets | 295 | 161 | 53 | 66.5% [55.1%, 76.3%] | +1.03% [-0.02%, +2.07%] | -2.4% [-3.3%, -1.4%] (295) | 155 |
| `puck_line` | best-bet bar | 14 | 9 | 2 | 75.0% [33.8%, 94.6%] | +1.76% [-1.48%, +5.01%] | -0.6% [-2.9%, +1.8%] (14) | 12 |
| `regulation_3_way` | opinions | 843 | 328 | 184 | 49.8% [44.2%, 55.3%] | -0.10% [-0.47%, +0.28%] | — | 281 |
| `regulation_3_way` | bets | 186 | 89 | 37 | 59.7% [48.0%, 70.4%] | +0.63% [-0.30%, +1.57%] | — | 186 |
| `regulation_3_way` | best-bet bar | 30 | 16 | 5 | 64.0% [36.4%, 84.7%] | +1.61% [-1.30%, +4.52%] | — | 30 |
| `shots_on_goal` | opinions | 33504 | 11582 | 7834 | 45.1% [43.3%, 46.9%] | +0.20% [-0.19%, +0.59%] | -4.7% [-4.9%, -4.6%] (19423) | 281 |
| `shots_on_goal` | bets | 2375 | 1287 | 422 | 65.9% [61.8%, 69.7%] | +3.58% [+2.75%, +4.41%] | -0.8% [-1.3%, -0.3%] (1849) | 280 |
| `shots_on_goal` | best-bet bar | 138 | 90 | 13 | 72.0% [59.4%, 81.9%] | +4.93% [+3.08%, +6.78%] | +2.2% [+0.5%, +3.9%] (138) | 106 |
| `team_total` | opinions | 12857 | 4642 | 3424 | 49.2% [47.7%, 50.7%] | +0.07% [-0.06%, +0.21%] | -4.9% [-5.0%, -4.7%] (12702) | 281 |
| `team_total` | bets | 546 | 253 | 118 | 59.1% [45.6%, 71.4%] | +0.83% [-0.35%, +2.01%] | -4.3% [-5.4%, -3.1%] (546) | 130 |
| `team_total` | best-bet bar | 35 | 21 | 9 | 80.8% [37.3%, 96.7%] | +2.44% [-1.29%, +6.18%] | -3.1% [-6.5%, +0.3%] (35) | 14 |
| `total_goals` | opinions | 7109 | 2444 | 2081 | 48.6% [46.6%, 50.6%] | +0.06% [-0.14%, +0.26%] | -3.5% [-3.7%, -3.3%] (6961) | 287 |
| `total_goals` | bets | 424 | 188 | 80 | 54.7% [41.1%, 67.5%] | +0.70% [-0.41%, +1.81%] | -3.2% [-4.2%, -2.2%] (424) | 95 |
| `total_goals` | best-bet bar | 18 | 7 | 7 | 63.6% [15.5%, 94.3%] | +0.02% [-2.24%, +2.28%] | -4.0% [-6.2%, -1.7%] (18) | 6 |

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
