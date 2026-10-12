# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-10-12T14:50:48+00:00
- Ledger rows: 230,398 — one per book — on 41,691 wager(s), each counted once at the best price the card could have taken (703 void, 0 unsettleable)
- Set aside: 17,306 team-market ledger row(s) frozen before 2026-10-06, priced on the goals ratings. From that day the team markets are priced on the xG ratings, and only those are measured here (Cooper's decision, 2026-10-05).

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), nothing in a hard-gated market (`goalie_saves`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 4,737 | 215 | -19.8u | -9.2% | -20.0% .. +1.6% | -24.8% .. +6.4% | no |
| `blocked_shots` | 42 | 5 | +2.3u | +45.4% | -25.9% .. +116.7% | -57.8% .. +148.6% | too few (<30) |
| `goalie_saves` | 112 | 13 | +2.0u | +15.6% | -49.9% .. +81.0% | -79.2% .. +110.4% | too few (<30) |
| `goals` | 10,199 | 80 | +7.2u | +9.0% | -41.5% .. +59.6% | -64.2% .. +82.2% | no |
| `moneyline` | 86 | 16 | -2.8u | -17.6% | -73.1% .. +37.9% | -98.0% .. +62.8% | too few (<30) |
| `points` | 8,781 | 424 | -6.0u | -1.4% | -11.6% .. +8.8% | -16.2% .. +13.4% | no |
| `puck_line` | 846 | 42 | -11.5u | -27.4% | -52.0% .. -2.8% | -63.1% .. +8.2% | no |
| `regulation_3_way` | 126 | 33 | -5.8u | -17.4% | -62.9% .. +28.1% | -83.3% .. +48.5% | no |
| `shots_on_goal` | 9,215 | 651 | +8.7u | +1.3% | -14.3% .. +17.0% | -21.3% .. +24.0% | no |
| `team_total` | 1,988 | 89 | -6.4u | -7.2% | -48.9% .. +34.5% | -67.6% .. +53.1% | no |
| `total_goals` | 1,058 | 80 | +21.7u | +27.1% | -35.5% .. +89.7% | -63.6% .. +117.8% | no |

The corrected interval is the 95% interval widened (Bonferroni) for the 11 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: -9.2% over 215 bets, 95% interval -20.0% to +1.6%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: 5 bets is far too few to measure anything. The point estimate is +45.4% and it means nothing yet: no demonstrated edge.
- `goalie_saves`: 13 bets is far too few to measure anything. The point estimate is +15.6% and it means nothing yet: no demonstrated edge.
- `goals`: +9.0% over 80 bets, 95% interval -41.5% to +59.6%. The interval includes zero, which means **no demonstrated edge**.
- `moneyline`: 16 bets is far too few to measure anything. The point estimate is -17.6% and it means nothing yet: no demonstrated edge.
- `points`: -1.4% over 424 bets, 95% interval -11.6% to +8.8%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: -27.4% over 42 bets, 95% interval -52.0% to -2.8%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. But correcting for the 11 markets measured on the same data widens it to -63.1% to +8.2%, which includes zero — so on the family of tests actually run, **no demonstrated edge**.
- `regulation_3_way`: -17.4% over 33 bets, 95% interval -62.9% to +28.1%. The interval includes zero, which means **no demonstrated edge**.
- `shots_on_goal`: +1.3% over 651 bets, 95% interval -14.3% to +17.0%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: -7.2% over 89 bets, 95% interval -48.9% to +34.5%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: +27.1% over 80 bets, 95% interval -35.5% to +89.7%. The interval includes zero, which means **no demonstrated edge**.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. **The registration is ambiguous on which population it means, and Cooper must decide before 2027-04-25.** "Opinions, not bets" reads as every settled opinion (A), which pools both sides of every priced line and so carries the whole margin. The words "a frozen opinion scored against the price it was frozen at is the same test", with the edge bar among what the registration freezes, read as the opinions clearing the measurement bar (B) — not the card's staked bets; the note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** No registered outcome is attached to either population while the population is undecided. The decision is not due until 2027-04-25, and a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing."

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion | 37,190, against the floor of 3,000 — floor met | -21.7% (-8064.2u) | -26.6% .. -16.8% | -28.8% .. -14.6% | excludes zero, negative |
| B. Opinions clearing the edge bar | 1,648, against the floor of 3,000 — below the floor | Not printed: below the floor. Do not read the number. | — | — | — |

- **A. Every settled opinion**: every settled opinion in every market, whatever its edge.
- **B. Opinions clearing the edge bar**: the settled opinions whose edge clears the measurement bar for their market — 6% for a prop, 3.5% for a team market, the bar the historical backtest measures at and the same filter as the per-market Bets column. These are not the card's staked bets; the note below says how they differ.

**What population B counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), nothing in a hard-gated market (`goalie_saves`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

## How far along the road this is

Separating a true +8% edge from zero takes about 601 bets per market. Every interval that includes zero means **no demonstrated edge** — those words, for as long as they are true.

## What this stream is and is not

- Frozen before the games: nothing here was repriced after the fact, which the historical backtest cannot claim.
- Settled by the same identity join and settlement rules as the historical backtest — one copy of each, on purpose.
- A void is a player who never entered (stake returned, as books do), or a goalie with under 40 minutes of ice time — the backtest's start rule, not a book's: it also voids a starter pulled early, whom a book would grade. An unsettleable row is a game that produced no final result inside the 14-day patience window, or a row that could not be settled against a game that was found and final (a name matching two players, a goalie's ice time not recorded, a missing line or stat, an unknown selection, a level final) — counted, never guessed.
- Recommendations were never placed as bets. This ledger prices a paper record of the shipped policy, nothing more.
