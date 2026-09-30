# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-09-30T13:40:18+00:00
- Ledger rows: 11,151 — one per book — on 2,799 wager(s), each counted once at the best price the card could have taken (62 void, 0 unsettleable)

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`) and nothing in a hard-gated market (`goalie_saves`), whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 327 | 12 | -4.3u | -35.9% | -81.9% .. +10.2% | -101.8% .. +30.1% | too few (<30) |
| `goalie_saves` | 87 | 5 | +0.7u | +13.7% | -77.5% .. +104.8% | -116.9% .. +144.2% | too few (<30) |
| `goals` | 634 | 7 | -2.6u | -37.1% | -126.4% .. +52.3% | -165.0% .. +90.9% | too few (<30) |
| `moneyline` | 10 | 2 | +1.6u | +78.0% | -270.9% .. +426.9% | -421.7% .. +577.7% | too few (<30) |
| `points` | 613 | 30 | -2.7u | -9.0% | -45.0% .. +27.0% | -60.5% .. +42.6% | no |
| `puck_line` | 103 | 7 | +1.8u | +26.1% | -30.1% .. +82.3% | -54.4% .. +106.5% | too few (<30) |
| `regulation_3_way` | 15 | 5 | -0.8u | -16.2% | -119.9% .. +87.5% | -164.7% .. +132.3% | too few (<30) |
| `shots_on_goal` | 577 | 49 | +7.2u | +14.8% | -25.2% .. +54.8% | -42.5% .. +72.1% | no |
| `team_total` | 242 | 20 | -4.0u | -19.8% | -99.7% .. +60.1% | -134.2% .. +94.6% | too few (<30) |
| `total_goals` | 129 | 7 | -7.0u | -100.0% | -inf% .. +inf% | -inf% .. +inf% | too few (<30) |

The corrected interval is the 95% interval widened (Bonferroni) for the 10 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: 12 bets is far too few to measure anything. The point estimate is -35.9% and it means nothing yet: no demonstrated edge.
- `goalie_saves`: 5 bets is far too few to measure anything. The point estimate is +13.7% and it means nothing yet: no demonstrated edge.
- `goals`: 7 bets is far too few to measure anything. The point estimate is -37.1% and it means nothing yet: no demonstrated edge.
- `moneyline`: 2 bets is far too few to measure anything. The point estimate is +78.0% and it means nothing yet: no demonstrated edge.
- `points`: -9.0% over 30 bets, 95% interval -45.0% to +27.0%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: 7 bets is far too few to measure anything. The point estimate is +26.1% and it means nothing yet: no demonstrated edge.
- `regulation_3_way`: 5 bets is far too few to measure anything. The point estimate is -16.2% and it means nothing yet: no demonstrated edge.
- `shots_on_goal`: +14.8% over 49 bets, 95% interval -25.2% to +54.8%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: 20 bets is far too few to measure anything. The point estimate is -19.8% and it means nothing yet: no demonstrated edge.
- `total_goals`: 7 bets is far too few to measure anything. The point estimate is -100.0% and it means nothing yet: no demonstrated edge.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. **The registration is ambiguous on which population it means, and Cooper must decide before 2027-04-25.** "Opinions, not bets" reads as every settled opinion (A), which pools both sides of every priced line and so carries the whole margin. The words "a frozen opinion scored against the price it was frozen at is the same test", with the edge bar among what the registration freezes, read as the opinions clearing the measurement bar (B) — not the card's staked bets; the note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** No registered outcome is attached to either population while the population is undecided. The decision is not due until 2027-04-25, and a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing."

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion | 2,737, against the floor of 3,000 — below the floor | Not printed: below the floor. Do not read the number. | — | — | — |
| B. Opinions clearing the edge bar | 144, against the floor of 3,000 — below the floor | Not printed: below the floor. Do not read the number. | — | — | — |

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
