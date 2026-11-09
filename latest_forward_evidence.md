# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-11-09T13:53:34+00:00
- Ledger rows: 833,703 — one per book — on 150,143 wager(s), each counted once at the best price the card could have taken (2,767 void, 0 unsettleable)
- Set aside: 67,873 team-market ledger row(s) frozen before 2026-10-22, priced on the goals ratings or the first xG ratings. From that day the team markets are priced on shooter-adjusted xG with each team's own home ice, and only those are measured here (Cooper's decision, 2026-10-21).
- Set aside: 192 goalie-saves ledger row(s) frozen before 2026-10-21, priced on the props model's own saves mean. From that day saves are priced on the game-context model, and only those are measured here (Cooper's decision, 2026-10-20).

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 16,625 | 757 | -22.6u | -3.0% | -9.2% .. +3.2% | -12.1% .. +6.1% | no |
| `blocked_shots` | 855 | 87 | -0.4u | -0.5% | -22.3% .. +21.3% | -32.3% .. +31.4% | no |
| `goalie_saves` | 3,010 | 158 | +4.5u | +2.8% | -42.3% .. +48.0% | -63.2% .. +68.8% | no |
| `goals` | 35,358 | 230 | +4.1u | +1.8% | -20.6% .. +24.2% | -30.9% .. +34.5% | no |
| `hits` | 436 | 138 | +13.8u | +10.0% | -5.8% .. +25.8% | -13.1% .. +33.1% | no |
| `moneyline` | 258 | 32 | +4.6u | +14.4% | -25.1% .. +53.8% | -43.3% .. +72.0% | no |
| `points` | 31,662 | 1,434 | -68.4u | -4.8% | -10.4% .. +0.9% | -13.1% .. +3.5% | no |
| `puck_line` | 2,051 | 124 | +20.0u | +16.1% | -1.3% .. +33.5% | -9.3% .. +41.6% | no |
| `regulation_3_way` | 387 | 82 | +2.9u | +3.5% | -24.4% .. +31.5% | -37.4% .. +44.4% | no |
| `shots_on_goal` | 33,198 | 2,327 | +36.1u | +1.6% | -7.7% .. +10.8% | -12.0% .. +15.1% | no |
| `team_total` | 5,722 | 219 | +11.5u | +5.2% | -21.2% .. +31.7% | -33.4% .. +43.9% | no |
| `total_goals` | 3,289 | 241 | +43.7u | +18.1% | -17.8% .. +54.1% | -34.5% .. +70.7% | no |

The corrected interval is the 95% interval widened (Bonferroni) for the 12 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: -3.0% over 757 bets, 95% interval -9.2% to +3.2%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: -0.5% over 87 bets, 95% interval -22.3% to +21.3%. The interval includes zero, which means **no demonstrated edge**.
- `goalie_saves`: +2.8% over 158 bets, 95% interval -42.3% to +48.0%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: +1.8% over 230 bets, 95% interval -20.6% to +24.2%. The interval includes zero, which means **no demonstrated edge**.
- `hits`: +10.0% over 138 bets, 95% interval -5.8% to +25.8%. The interval includes zero, which means **no demonstrated edge**.
- `moneyline`: +14.4% over 32 bets, 95% interval -25.1% to +53.8%. The interval includes zero, which means **no demonstrated edge**.
- `points`: -4.8% over 1434 bets, 95% interval -10.4% to +0.9%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: +16.1% over 124 bets, 95% interval -1.3% to +33.5%. The interval includes zero, which means **no demonstrated edge**.
- `regulation_3_way`: +3.5% over 82 bets, 95% interval -24.4% to +31.5%. The interval includes zero, which means **no demonstrated edge**.
- `shots_on_goal`: +1.6% over 2327 bets, 95% interval -7.7% to +10.8%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: +5.2% over 219 bets, 95% interval -21.2% to +31.7%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: +18.1% over 241 bets, 95% interval -17.8% to +54.1%. The interval includes zero, which means **no demonstrated edge**.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. **The registration is ambiguous on which population it means, and Cooper must decide before 2027-04-25.** "Opinions, not bets" reads as every settled opinion (A), which pools both sides of every priced line and so carries the whole margin. The words "a frozen opinion scored against the price it was frozen at is the same test", with the edge bar among what the registration freezes, read as the opinions clearing the measurement bar (B) — not the card's staked bets; the note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** No registered outcome is attached to either population while the population is undecided. The decision is not due until 2027-04-25, and a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing."

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion | 132,851, against the floor of 3,000 — floor met | -20.6% (-27302.9u) | -23.0% .. -18.1% | -24.1% .. -17.0% | excludes zero, negative |
| B. Opinions clearing the edge bar | 5,829, against the floor of 3,000 — floor met | +0.9% (+49.7u) | -4.6% .. +6.3% | -7.2% .. +8.9% | spans zero (no demonstrated edge) |

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
