# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-10-27T13:09:18+00:00
- Ledger rows: 544,857 — one per book — on 96,330 wager(s), each counted once at the best price the card could have taken (1,756 void, 0 unsettleable)
- Set aside: 67,873 team-market ledger row(s) frozen before 2026-10-22, priced on the goals ratings or the first xG ratings. From that day the team markets are priced on shooter-adjusted xG with each team's own home ice, and only those are measured here (Cooper's decision, 2026-10-21).
- Set aside: 192 goalie-saves ledger row(s) frozen before 2026-10-21, priced on the props model's own saves mean. From that day saves are priced on the game-context model, and only those are measured here (Cooper's decision, 2026-10-20).

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 10,766 | 479 | -32.2u | -6.7% | -14.1% .. +0.6% | -17.5% .. +4.0% | no |
| `blocked_shots` | 309 | 26 | +6.7u | +25.7% | -10.8% .. +62.2% | -27.6% .. +79.0% | too few (<30) |
| `goalie_saves` | 848 | 49 | +12.1u | +24.7% | -69.6% .. +118.9% | -113.1% .. +162.4% | no |
| `goals` | 23,120 | 148 | +18.8u | +12.7% | -17.8% .. +43.2% | -31.9% .. +57.3% | no |
| `hits` | 436 | 138 | +13.8u | +10.0% | -5.8% .. +25.8% | -13.1% .. +33.1% | no |
| `moneyline` | 68 | 12 | +8.9u | +74.1% | +10.9% .. +137.4% | -18.4% .. +166.7% | too few (<30) |
| `points` | 20,312 | 932 | -12.3u | -1.3% | -8.6% .. +5.9% | -11.9% .. +9.3% | no |
| `puck_line` | 547 | 49 | +14.6u | +29.7% | -2.0% .. +61.4% | -16.6% .. +76.0% | no |
| `regulation_3_way` | 102 | 24 | +3.9u | +16.2% | -43.5% .. +76.0% | -71.1% .. +103.5% | too few (<30) |
| `shots_on_goal` | 21,066 | 1,467 | +131.5u | +9.0% | -3.8% .. +21.7% | -9.7% .. +27.6% | no |
| `team_total` | 1,609 | 74 | +11.5u | +15.5% | -32.9% .. +63.9% | -55.3% .. +86.2% | no |
| `total_goals` | 866 | 35 | +16.5u | +47.0% | -66.7% .. +160.8% | -119.2% .. +213.3% | no |

The corrected interval is the 95% interval widened (Bonferroni) for the 12 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: -6.7% over 479 bets, 95% interval -14.1% to +0.6%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: 26 bets is far too few to measure anything. The point estimate is +25.7% and it means nothing yet: no demonstrated edge.
- `goalie_saves`: +24.7% over 49 bets, 95% interval -69.6% to +118.9%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: +12.7% over 148 bets, 95% interval -17.8% to +43.2%. The interval includes zero, which means **no demonstrated edge**.
- `hits`: +10.0% over 138 bets, 95% interval -5.8% to +25.8%. The interval includes zero, which means **no demonstrated edge**.
- `moneyline`: 12 bets is far too few to measure anything. The point estimate is +74.1% and it means nothing yet: no demonstrated edge.
- `points`: -1.3% over 932 bets, 95% interval -8.6% to +5.9%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: +29.7% over 49 bets, 95% interval -2.0% to +61.4%. The interval includes zero, which means **no demonstrated edge**.
- `regulation_3_way`: 24 bets is far too few to measure anything. The point estimate is +16.2% and it means nothing yet: no demonstrated edge.
- `shots_on_goal`: +9.0% over 1467 bets, 95% interval -3.8% to +21.7%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: +15.5% over 74 bets, 95% interval -32.9% to +63.9%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: +47.0% over 35 bets, 95% interval -66.7% to +160.8%. The interval includes zero, which means **no demonstrated edge**.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. **The registration is ambiguous on which population it means, and Cooper must decide before 2027-04-25.** "Opinions, not bets" reads as every settled opinion (A), which pools both sides of every priced line and so carries the whole margin. The words "a frozen opinion scored against the price it was frozen at is the same test", with the edge bar among what the registration freezes, read as the opinions clearing the measurement bar (B) — not the card's staked bets; the note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** No registered outcome is attached to either population while the population is undecided. The decision is not due until 2027-04-25, and a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing."

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion | 80,049, against the floor of 3,000 — floor met | -21.3% (-17034.4u) | -24.5% .. -18.0% | -26.0% .. -16.5% | excludes zero, negative |
| B. Opinions clearing the edge bar | 3,433, against the floor of 3,000 — floor met | +5.6% (+193.6u) | -1.9% .. +13.2% | -5.4% .. +16.7% | spans zero (no demonstrated edge) |

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
