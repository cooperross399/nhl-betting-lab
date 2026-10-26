# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-10-26T20:42:13+00:00
- Ledger rows: 535,003 — one per book — on 94,676 wager(s), each counted once at the best price the card could have taken (1,704 void, 0 unsettleable)
- Set aside: 67,873 team-market ledger row(s) frozen before 2026-10-22, priced on the goals ratings or the first xG ratings. From that day the team markets are priced on shooter-adjusted xG with each team's own home ice, and only those are measured here (Cooper's decision, 2026-10-21).
- Set aside: 192 goalie-saves ledger row(s) frozen before 2026-10-21, priced on the props model's own saves mean. From that day saves are priced on the game-context model, and only those are measured here (Cooper's decision, 2026-10-20).

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 10,592 | 468 | -30.2u | -6.4% | -13.9% .. +1.0% | -17.3% .. +4.4% | no |
| `blocked_shots` | 299 | 25 | +5.8u | +23.3% | -14.4% .. +60.9% | -31.8% .. +78.3% | too few (<30) |
| `goalie_saves` | 768 | 47 | +12.4u | +26.4% | -72.0% .. +124.8% | -117.5% .. +170.2% | no |
| `goals` | 22,755 | 147 | +18.0u | +12.2% | -18.5% .. +42.9% | -32.7% .. +57.1% | no |
| `hits` | 402 | 129 | +7.3u | +5.7% | -10.7% .. +22.0% | -18.3% .. +29.6% | no |
| `moneyline` | 62 | 11 | +7.4u | +67.0% | -0.6% .. +134.6% | -31.9% .. +165.8% | too few (<30) |
| `points` | 19,994 | 917 | -5.6u | -0.6% | -7.9% .. +6.7% | -11.3% .. +10.1% | no |
| `puck_line` | 499 | 45 | +12.6u | +28.0% | -6.6% .. +62.6% | -22.6% .. +78.6% | no |
| `regulation_3_way` | 93 | 23 | +4.9u | +21.3% | -40.2% .. +82.8% | -68.7% .. +111.2% | too few (<30) |
| `shots_on_goal` | 20,723 | 1,442 | +139.5u | +9.7% | -3.3% .. +22.6% | -9.2% .. +28.6% | no |
| `team_total` | 1,469 | 71 | +9.6u | +13.5% | -37.3% .. +64.3% | -60.7% .. +87.8% | no |
| `total_goals` | 791 | 31 | +6.1u | +19.8% | -94.9% .. +134.5% | -147.9% .. +187.5% | no |

The corrected interval is the 95% interval widened (Bonferroni) for the 12 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: -6.4% over 468 bets, 95% interval -13.9% to +1.0%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: 25 bets is far too few to measure anything. The point estimate is +23.3% and it means nothing yet: no demonstrated edge.
- `goalie_saves`: +26.4% over 47 bets, 95% interval -72.0% to +124.8%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: +12.2% over 147 bets, 95% interval -18.5% to +42.9%. The interval includes zero, which means **no demonstrated edge**.
- `hits`: +5.7% over 129 bets, 95% interval -10.7% to +22.0%. The interval includes zero, which means **no demonstrated edge**.
- `moneyline`: 11 bets is far too few to measure anything. The point estimate is +67.0% and it means nothing yet: no demonstrated edge.
- `points`: -0.6% over 917 bets, 95% interval -7.9% to +6.7%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: +28.0% over 45 bets, 95% interval -6.6% to +62.6%. The interval includes zero, which means **no demonstrated edge**.
- `regulation_3_way`: 23 bets is far too few to measure anything. The point estimate is +21.3% and it means nothing yet: no demonstrated edge.
- `shots_on_goal`: +9.7% over 1442 bets, 95% interval -3.3% to +22.6%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: +13.5% over 71 bets, 95% interval -37.3% to +64.3%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: +19.8% over 31 bets, 95% interval -94.9% to +134.5%. The interval includes zero, which means **no demonstrated edge**.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. **The registration is ambiguous on which population it means, and Cooper must decide before 2027-04-25.** "Opinions, not bets" reads as every settled opinion (A), which pools both sides of every priced line and so carries the whole margin. The words "a frozen opinion scored against the price it was frozen at is the same test", with the edge bar among what the registration freezes, read as the opinions clearing the measurement bar (B) — not the card's staked bets; the note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** No registered outcome is attached to either population while the population is undecided. The decision is not due until 2027-04-25, and a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing."

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion | 78,447, against the floor of 3,000 — floor met | -21.4% (-16766.4u) | -24.7% .. -18.1% | -26.2% .. -16.6% | excludes zero, negative |
| B. Opinions clearing the edge bar | 3,356, against the floor of 3,000 — floor met | +5.6% (+187.8u) | -2.1% .. +13.3% | -5.6% .. +16.8% | spans zero (no demonstrated edge) |

- **A. Every settled opinion**: every settled opinion in every market, whatever its edge.
- **B. Opinions clearing the edge bar**: the settled opinions whose edge clears the measurement bar for their market — 6% for a prop, 3.5% for a team market, the bar the historical backtest measures at and the same filter as the per-market Bets column. These are not the card's staked bets; the note below says how they differ.

**What population B counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

## How far along the road this is

Separating a true +8% edge from zero takes about 601 bets per market. Every interval that includes zero means **no demonstrated edge** — those words, for as long as they are true.

## What this stream is and is not

- Frozen before the games: nothing here was repriced after the fact, which the historical backtest cannot claim.
- Settled by the same identity join and settlement rules as the historical backtest — one copy of each, on purpose.
- A void is a player who never entered (stake returned, as books do), or a goalie with under 40 minutes of ice time — the backtest's start rule, not a book's: it also voids a starter pulled early, whom a book would grade. An unsettleable row is a game that produced no final result inside the 14-day patience window, or a row that could not be settled against a game that was found and final (a name matching two players, a goalie's ice time not recorded, a missing line or stat, an unknown selection, a level final) — counted, never guessed.
- Recommendations were never placed as bets. This ledger prices a paper record of the shipped policy, nothing more.
