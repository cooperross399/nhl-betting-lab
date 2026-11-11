# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-11-11T13:44:39+00:00
- Ledger rows: 865,135 — one per book — on 155,830 wager(s), each counted once at the best price the card could have taken (2,826 void, 0 unsettleable)
- Set aside: 67,873 team-market ledger row(s) frozen before 2026-10-22, priced on the goals ratings or the first xG ratings. From that day the team markets are priced on shooter-adjusted xG with each team's own home ice, and only those are measured here (Cooper's decision, 2026-10-21).
- Set aside: 192 goalie-saves ledger row(s) frozen before 2026-10-21, priced on the props model's own saves mean. From that day saves are priced on the game-context model, and only those are measured here (Cooper's decision, 2026-10-20).

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 17,207 | 776 | -21.1u | -2.7% | -8.9% .. +3.4% | -11.7% .. +6.3% | no |
| `blocked_shots` | 938 | 92 | +2.2u | +2.4% | -18.9% .. +23.7% | -28.7% .. +33.5% | no |
| `goalie_saves` | 3,367 | 162 | +4.1u | +2.5% | -41.5% .. +46.6% | -61.9% .. +66.9% | no |
| `goals` | 36,682 | 237 | -1.1u | -0.5% | -22.3% .. +21.3% | -32.4% .. +31.4% | no |
| `hits` | 436 | 138 | +13.8u | +10.0% | -5.8% .. +25.8% | -13.1% .. +33.1% | no |
| `moneyline` | 278 | 36 | +4.6u | +12.8% | -24.1% .. +49.6% | -41.1% .. +66.6% | no |
| `points` | 32,797 | 1,475 | -67.9u | -4.6% | -10.2% .. +1.0% | -12.8% .. +3.6% | no |
| `puck_line` | 2,206 | 134 | +17.7u | +13.2% | -4.2% .. +30.6% | -12.3% .. +38.7% | no |
| `regulation_3_way` | 417 | 88 | +4.2u | +4.8% | -22.2% .. +31.7% | -34.7% .. +44.2% | no |
| `shots_on_goal` | 34,428 | 2,431 | +69.1u | +2.8% | -6.7% .. +12.4% | -11.1% .. +16.8% | no |
| `team_total` | 6,177 | 243 | -0.8u | -0.3% | -26.4% .. +25.8% | -38.5% .. +37.9% | no |
| `total_goals` | 3,546 | 257 | +30.0u | +11.7% | -23.2% .. +46.5% | -39.3% .. +62.7% | no |

The corrected interval is the 95% interval widened (Bonferroni) for the 12 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: -2.7% over 776 bets, 95% interval -8.9% to +3.4%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: +2.4% over 92 bets, 95% interval -18.9% to +23.7%. The interval includes zero, which means **no demonstrated edge**.
- `goalie_saves`: +2.5% over 162 bets, 95% interval -41.5% to +46.6%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: -0.5% over 237 bets, 95% interval -22.3% to +21.3%. The interval includes zero, which means **no demonstrated edge**.
- `hits`: +10.0% over 138 bets, 95% interval -5.8% to +25.8%. The interval includes zero, which means **no demonstrated edge**.
- `moneyline`: +12.8% over 36 bets, 95% interval -24.1% to +49.6%. The interval includes zero, which means **no demonstrated edge**.
- `points`: -4.6% over 1475 bets, 95% interval -10.2% to +1.0%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: +13.2% over 134 bets, 95% interval -4.2% to +30.6%. The interval includes zero, which means **no demonstrated edge**.
- `regulation_3_way`: +4.8% over 88 bets, 95% interval -22.2% to +31.7%. The interval includes zero, which means **no demonstrated edge**.
- `shots_on_goal`: +2.8% over 2431 bets, 95% interval -6.7% to +12.4%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: -0.3% over 243 bets, 95% interval -26.4% to +25.8%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: +11.7% over 257 bets, 95% interval -23.2% to +46.5%. The interval includes zero, which means **no demonstrated edge**.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. The registration could be read as two populations: every settled opinion (A), which pools both sides of every priced line and so carries the whole margin, or the opinions clearing the measurement bar (B) — not the card's staked bets. **On 2026-11-09 Cooper decided that the registration means B, the opinions clearing the measurement bar. B is the registered statistic; A is shown for reference only.** The note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** The decision is read on population B under docs/when_this_ends.md, and it is not due until 2027-04-25; a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing." No registered outcome is attached to either population before that date, and none is ever attached to A.

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion (reference only) | 138,479, against the floor of 3,000 — floor met | -20.6% (-28529.7u) | -23.0% .. -18.2% | -24.1% .. -17.1% | excludes zero, negative |
| B. Opinions clearing the edge bar (registered) | 6,069, against the floor of 3,000 — floor met | +0.9% (+54.7u) | -4.7% .. +6.5% | -7.2% .. +9.0% | spans zero (no demonstrated edge) |

- **A. Every settled opinion (reference only)**: every settled opinion in every market, whatever its edge.
- **B. Opinions clearing the edge bar (registered)**: the settled opinions whose edge clears the measurement bar for their market — 6% for a prop, 3.5% for a team market, the bar the historical backtest measures at and the same filter as the per-market Bets column. These are not the card's staked bets; the note below says how they differ.

**What population B counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

## How far along the road this is

Separating a true +8% edge from zero takes about 601 bets per market. Every interval that includes zero means **no demonstrated edge** — those words, for as long as they are true.

## What this stream is and is not

- Frozen before the games: nothing here was repriced after the fact, which the historical backtest cannot claim.
- Settled by the same identity join and settlement rules as the historical backtest — one copy of each, on purpose.
- A void is a player who never entered (stake returned, as books do), or a goalie with under 40 minutes of ice time — the backtest's start rule, not a book's: it also voids a starter pulled early, whom a book would grade. An unsettleable row is a game that produced no final result inside the 14-day patience window, or a row that could not be settled against a game that was found and final (a name matching two players, a goalie's ice time not recorded, a missing line or stat, an unknown selection, a level final) — counted, never guessed.
- Recommendations were never placed as bets. This ledger prices a paper record of the shipped policy, nothing more.
