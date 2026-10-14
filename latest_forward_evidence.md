# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-10-14T13:41:45+00:00
- Ledger rows: 284,845 — one per book — on 51,631 wager(s), each counted once at the best price the card could have taken (911 void, 0 unsettleable)
- Set aside: 17,306 team-market ledger row(s) frozen before 2026-10-06, priced on the goals ratings. From that day the team markets are priced on the xG ratings, and only those are measured here (Cooper's decision, 2026-10-05).

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 5,823 | 261 | -15.5u | -5.9% | -15.6% .. +3.8% | -20.1% .. +8.3% | no |
| `blocked_shots` | 60 | 5 | +2.3u | +45.4% | -25.9% .. +116.7% | -58.8% .. +149.6% | too few (<30) |
| `goalie_saves` | 112 | 13 | +2.0u | +15.6% | -49.9% .. +81.0% | -80.1% .. +111.3% | too few (<30) |
| `goals` | 12,626 | 91 | +15.0u | +16.5% | -29.8% .. +62.7% | -51.2% .. +84.1% | no |
| `hits` | 96 | 35 | +12.4u | +35.5% | +5.8% .. +65.2% | -7.9% .. +78.9% | no |
| `moneyline` | 124 | 24 | -1.0u | -4.0% | -48.1% .. +40.0% | -68.4% .. +60.3% | too few (<30) |
| `points` | 10,903 | 512 | +3.6u | +0.7% | -8.6% .. +10.0% | -12.8% .. +14.2% | no |
| `puck_line` | 1,232 | 63 | -6.0u | -9.5% | -30.5% .. +11.5% | -40.3% .. +21.2% | no |
| `regulation_3_way` | 183 | 46 | -3.5u | -7.7% | -46.2% .. +30.9% | -63.9% .. +48.6% | no |
| `shots_on_goal` | 11,320 | 780 | +39.4u | +5.1% | -9.0% .. +19.1% | -15.5% .. +25.6% | no |
| `team_total` | 2,894 | 125 | +3.3u | +2.6% | -28.9% .. +34.1% | -43.5% .. +48.7% | no |
| `total_goals` | 1,549 | 99 | +14.9u | +15.0% | -38.3% .. +68.3% | -62.9% .. +92.9% | no |

The corrected interval is the 95% interval widened (Bonferroni) for the 12 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: -5.9% over 261 bets, 95% interval -15.6% to +3.8%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: 5 bets is far too few to measure anything. The point estimate is +45.4% and it means nothing yet: no demonstrated edge.
- `goalie_saves`: 13 bets is far too few to measure anything. The point estimate is +15.6% and it means nothing yet: no demonstrated edge.
- `goals`: +16.5% over 91 bets, 95% interval -29.8% to +62.7%. The interval includes zero, which means **no demonstrated edge**.
- `hits`: +35.5% over 35 bets, 95% interval +5.8% to +65.2%. The interval excludes zero, so this sample is profitable beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. But correcting for the 12 markets measured on the same data widens it to -7.9% to +78.9%, which includes zero — so on the family of tests actually run, **no demonstrated edge**.
- `moneyline`: 24 bets is far too few to measure anything. The point estimate is -4.0% and it means nothing yet: no demonstrated edge.
- `points`: +0.7% over 512 bets, 95% interval -8.6% to +10.0%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: -9.5% over 63 bets, 95% interval -30.5% to +11.5%. The interval includes zero, which means **no demonstrated edge**.
- `regulation_3_way`: -7.7% over 46 bets, 95% interval -46.2% to +30.9%. The interval includes zero, which means **no demonstrated edge**.
- `shots_on_goal`: +5.1% over 780 bets, 95% interval -9.0% to +19.1%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: +2.6% over 125 bets, 95% interval -28.9% to +34.1%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: +15.0% over 99 bets, 95% interval -38.3% to +68.3%. The interval includes zero, which means **no demonstrated edge**.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. **The registration is ambiguous on which population it means, and Cooper must decide before 2027-04-25.** "Opinions, not bets" reads as every settled opinion (A), which pools both sides of every priced line and so carries the whole margin. The words "a frozen opinion scored against the price it was frozen at is the same test", with the edge bar among what the registration freezes, read as the opinions clearing the measurement bar (B) — not the card's staked bets; the note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** No registered outcome is attached to either population while the population is undecided. The decision is not due until 2027-04-25, and a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing."

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion | 46,922, against the floor of 3,000 — floor met | -20.9% (-9816.5u) | -25.6% .. -16.3% | -27.7% .. -14.1% | excludes zero, negative |
| B. Opinions clearing the edge bar | 2,054, against the floor of 3,000 — below the floor | Not printed: below the floor. Do not read the number. | — | — | — |

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
