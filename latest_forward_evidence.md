# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-11-27T20:38:54+00:00
- Ledger rows: 1,192,594 — one per book — on 216,467 wager(s), each counted once at the best price the card could have taken (3,951 void, 0 unsettleable)
- Set aside: 67,873 team-market ledger row(s) frozen before 2026-10-22, priced on the goals ratings or the first xG ratings. From that day the team markets are priced on shooter-adjusted xG with each team's own home ice, and only those are measured here (Cooper's decision, 2026-10-21).
- Set aside: 192 goalie-saves ledger row(s) frozen before 2026-10-21, priced on the props model's own saves mean. From that day saves are priced on the game-context model, and only those are measured here (Cooper's decision, 2026-10-20).

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 10% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 23,504 | 1,095 | -16.0u | -1.5% | -6.8% .. +3.9% | -9.3% .. +6.3% | no |
| `blocked_shots` | 1,571 | 151 | -1.8u | -1.2% | -16.9% .. +14.5% | -24.2% .. +21.8% | no |
| `goalie_saves` | 7,188 | 370 | -38.6u | -10.4% | -39.2% .. +18.3% | -52.5% .. +31.6% | no |
| `goals` | 50,663 | 330 | -4.5u | -1.4% | -20.6% .. +17.8% | -29.4% .. +26.7% | no |
| `hits` | 436 | 138 | +13.8u | +10.0% | -5.8% .. +25.8% | -13.1% .. +33.1% | no |
| `moneyline` | 492 | 60 | +9.3u | +15.6% | -14.3% .. +45.4% | -28.1% .. +59.2% | no |
| `points` | 45,134 | 2,047 | -73.1u | -3.6% | -8.7% .. +1.5% | -11.0% .. +3.9% | no |
| `puck_line` | 3,857 | 230 | +13.9u | +6.0% | -6.7% .. +18.7% | -12.6% .. +24.6% | no |
| `regulation_3_way` | 738 | 154 | -1.7u | -1.1% | -22.0% .. +19.7% | -31.6% .. +29.4% | no |
| `shots_on_goal` | 47,254 | 3,421 | +179.5u | +5.2% | -3.3% .. +13.8% | -7.2% .. +17.7% | no |
| `team_total` | 10,933 | 445 | +5.8u | +1.3% | -20.3% .. +22.9% | -30.3% .. +32.9% | no |
| `total_goals` | 6,221 | 470 | +34.0u | +7.2% | -20.6% .. +35.1% | -33.4% .. +47.9% | no |

The corrected interval is the 95% interval widened (Bonferroni) for the 12 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: -1.5% over 1095 bets, 95% interval -6.8% to +3.9%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: -1.2% over 151 bets, 95% interval -16.9% to +14.5%. The interval includes zero, which means **no demonstrated edge**.
- `goalie_saves`: -10.4% over 370 bets, 95% interval -39.2% to +18.3%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: -1.4% over 330 bets, 95% interval -20.6% to +17.8%. The interval includes zero, which means **no demonstrated edge**.
- `hits`: +10.0% over 138 bets, 95% interval -5.8% to +25.8%. The interval includes zero, which means **no demonstrated edge**.
- `moneyline`: +15.6% over 60 bets, 95% interval -14.3% to +45.4%. The interval includes zero, which means **no demonstrated edge**.
- `points`: -3.6% over 2047 bets, 95% interval -8.7% to +1.5%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: +6.0% over 230 bets, 95% interval -6.7% to +18.7%. The interval includes zero, which means **no demonstrated edge**.
- `regulation_3_way`: -1.1% over 154 bets, 95% interval -22.0% to +19.7%. The interval includes zero, which means **no demonstrated edge**.
- `shots_on_goal`: +5.2% over 3421 bets, 95% interval -3.3% to +13.8%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: +1.3% over 445 bets, 95% interval -20.3% to +22.9%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: +7.2% over 470 bets, 95% interval -20.6% to +35.1%. The interval includes zero, which means **no demonstrated edge**.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. The registration could be read as two populations: every settled opinion (A), which pools both sides of every priced line and so carries the whole margin, or the opinions clearing the measurement bar (B) — not the card's staked bets. **On 2026-11-09 Cooper decided that the registration means B, the opinions clearing the measurement bar. B is the registered statistic; A is shown for reference only.** The note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** The decision is read on population B under docs/when_this_ends.md, and it is not due until 2027-04-25; a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing." No registered outcome is attached to either population before that date, and none is ever attached to A.

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion (reference only) | 197,991, against the floor of 3,000 — floor met | -19.1% (-37779.5u) | -21.3% .. -16.8% | -22.4% .. -15.8% | excludes zero, negative |
| B. Opinions clearing the edge bar (registered) | 8,911, against the floor of 3,000 — floor met | +1.4% (+120.5u) | -3.6% .. +6.3% | -5.9% .. +8.6% | spans zero (no demonstrated edge) |

- **A. Every settled opinion (reference only)**: every settled opinion in every market, whatever its edge.
- **B. Opinions clearing the edge bar (registered)**: the settled opinions whose edge clears the measurement bar for their market — 6% for a prop, 3.5% for a team market, the bar the historical backtest measures at and the same filter as the per-market Bets column. These are not the card's staked bets; the note below says how they differ.

**What population B counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 10% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`), and no moneyline, puck line or regulation side the model gives under a 40% chance to win, and no prop whose model hit chance falls short of what the shortest price in its odds bracket would need, whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

## How far along the road this is

Separating a true +8% edge from zero takes about 601 bets per market. Every interval that includes zero means **no demonstrated edge** — those words, for as long as they are true.

## What this stream is and is not

- Frozen before the games: nothing here was repriced after the fact, which the historical backtest cannot claim.
- Settled by the same identity join and settlement rules as the historical backtest — one copy of each, on purpose.
- A void is a player who never entered (stake returned, as books do), or a goalie with under 40 minutes of ice time — the backtest's start rule, not a book's: it also voids a starter pulled early, whom a book would grade. An unsettleable row is a game that produced no final result inside the 14-day patience window, or a row that could not be settled against a game that was found and final (a name matching two players, a goalie's ice time not recorded, a missing line or stat, an unknown selection, a level final) — counted, never guessed.
- Recommendations were never placed as bets. This ledger prices a paper record of the shipped policy, nothing more.
