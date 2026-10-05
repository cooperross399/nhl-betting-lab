# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-10-05T21:44:08+00:00
- Ledger rows: 90,054 — one per book — on 17,741 wager(s), each counted once at the best price the card could have taken (264 void, 0 unsettleable)

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`) and nothing in a hard-gated market (`goalie_saves`), whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 2,067 | 103 | -19.2u | -18.6% | -34.7% .. -2.5% | -41.9% .. +4.7% | no |
| `blocked_shots` | 14 | 2 | +1.6u | +80.1% | +73.8% .. +86.4% | +71.0% .. +89.2% | too few (<30) |
| `goalie_saves` | 112 | 13 | +2.0u | +15.6% | -49.9% .. +81.0% | -79.2% .. +110.4% | too few (<30) |
| `goals` | 4,303 | 40 | +5.8u | +14.5% | -72.3% .. +101.2% | -111.2% .. +140.1% | no |
| `moneyline` | 78 | 13 | -0.9u | -7.1% | -76.6% .. +62.5% | -107.7% .. +93.6% | too few (<30) |
| `points` | 3,700 | 170 | -23.4u | -13.7% | -30.5% .. +3.0% | -38.0% .. +10.5% | no |
| `puck_line` | 711 | 42 | -3.3u | -7.8% | -29.8% .. +14.3% | -39.7% .. +24.2% | no |
| `regulation_3_way` | 102 | 28 | -2.6u | -9.2% | -53.0% .. +34.6% | -72.6% .. +54.3% | too few (<30) |
| `shots_on_goal` | 3,872 | 286 | -26.0u | -9.1% | -28.9% .. +10.7% | -37.8% .. +19.6% | no |
| `team_total` | 1,613 | 96 | +6.4u | +6.6% | -40.4% .. +53.7% | -61.4% .. +74.7% | no |
| `total_goals` | 905 | 50 | -2.8u | -5.5% | -81.2% .. +70.2% | -115.1% .. +104.0% | no |

The corrected interval is the 95% interval widened (Bonferroni) for the 11 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: -18.6% over 103 bets, 95% interval -34.7% to -2.5%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. But correcting for the 11 markets measured on the same data widens it to -41.9% to +4.7%, which includes zero — so on the family of tests actually run, **no demonstrated edge**.
- `blocked_shots`: 2 bets is far too few to measure anything. The point estimate is +80.1% and it means nothing yet: no demonstrated edge.
- `goalie_saves`: 13 bets is far too few to measure anything. The point estimate is +15.6% and it means nothing yet: no demonstrated edge.
- `goals`: +14.5% over 40 bets, 95% interval -72.3% to +101.2%. The interval includes zero, which means **no demonstrated edge**.
- `moneyline`: 13 bets is far too few to measure anything. The point estimate is -7.1% and it means nothing yet: no demonstrated edge.
- `points`: -13.7% over 170 bets, 95% interval -30.5% to +3.0%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: -7.8% over 42 bets, 95% interval -29.8% to +14.3%. The interval includes zero, which means **no demonstrated edge**.
- `regulation_3_way`: 28 bets is far too few to measure anything. The point estimate is -9.2% and it means nothing yet: no demonstrated edge.
- `shots_on_goal`: -9.1% over 286 bets, 95% interval -28.9% to +10.7%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: +6.6% over 96 bets, 95% interval -40.4% to +53.7%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: -5.5% over 50 bets, 95% interval -81.2% to +70.2%. The interval includes zero, which means **no demonstrated edge**.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. **The registration is ambiguous on which population it means, and Cooper must decide before 2027-04-25.** "Opinions, not bets" reads as every settled opinion (A), which pools both sides of every priced line and so carries the whole margin. The words "a frozen opinion scored against the price it was frozen at is the same test", with the edge bar among what the registration freezes, read as the opinions clearing the measurement bar (B) — not the card's staked bets; the note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** No registered outcome is attached to either population while the population is undecided. The decision is not due until 2027-04-25, and a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing."

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion | 17,477, against the floor of 3,000 — floor met | -20.1% (-3511.1u) | -28.3% .. -11.8% | -32.0% .. -8.1% | excludes zero, negative |
| B. Opinions clearing the edge bar | 843, against the floor of 3,000 — below the floor | Not printed: below the floor. Do not read the number. | — | — | — |

- **A. Every settled opinion**: every settled opinion in every market, whatever its edge.
- **B. Opinions clearing the edge bar**: the settled opinions whose edge clears the measurement bar for their market — 6% for a prop, 3.5% for a team market, the bar the historical backtest measures at and the same filter as the per-market Bets column. These are not the card's staked bets; the note below says how they differ.

**What population B counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`) and nothing in a hard-gated market (`goalie_saves`), whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

## How far along the road this is

Separating a true +8% edge from zero takes about 601 bets per market. Every interval that includes zero means **no demonstrated edge** — those words, for as long as they are true.

## What this stream is and is not

- Frozen before the games: nothing here was repriced after the fact, which the historical backtest cannot claim.
- Settled by the same identity join and settlement rules as the historical backtest — one copy of each, on purpose.
- A void is a player who never entered (stake returned, as books do), or a goalie with under 40 minutes of ice time — the backtest's start rule, not a book's: it also voids a starter pulled early, whom a book would grade. An unsettleable row is a game that produced no final result inside the 14-day patience window, or a row that could not be settled against a game that was found and final (a name matching two players, a goalie's ice time not recorded, a missing line or stat, an unknown selection, a level final) — counted, never guessed.
- Recommendations were never placed as bets. This ledger prices a paper record of the shipped policy, nothing more.
