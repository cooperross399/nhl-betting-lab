# Forward evidence

The opinion the live card actually held, written down before puck drop, settled against the boxscore after, never revised. This is the only possible price evidence for the regulation three-way, which has never been bought historically (it is per-event only and was never requested), and the accumulating out-of-sample test for everything else.

- Generated: 2026-10-02T13:38:43+00:00
- Ledger rows: 39,577 — one per book — on 8,782 wager(s), each counted once at the best price the card could have taken (149 void, 0 unsettleable)

## Accumulated so far, at the shipped edge bars

**What the Bets column counts.** A bet here is an opinion whose edge clears the measurement bar (6% for a prop, 3.5% for a team market — the bar the historical backtest measures at). These are not the card's staked bets, and they are not what a bankroll following the card would have done. The card stakes only best bets, at an edge of 12% for a prop or 9% for a team market; an edge between the two bars is a lean, recorded and not staked. It also stakes nothing priced shorter than -160 or longer than +600, nothing in a stake-excluded market (`points`) and nothing in a hard-gated market (`goalie_saves`), whatever the edge. Some reasons are not about the price at all: the snapshot is frozen from the unfiltered prices before the card is built, so this also counts every rung of a ladder after the one that took the outcome's single stake (one stake per outcome), markets the card could not use that day (not allowlisted, or incomplete on a night the per-event fetch was capped), and the opinions of a day whose card was blocked. Every such opinion is still counted here. A game that had already started, or whose start cannot be confirmed, when the snapshot was frozen is the other way round: it is withheld from the snapshot by the same puck-drop rule the card's guard applies, so it appears in neither population — not among the opinions and not among these bets.

| Market | Opinions | Bets | Profit | ROI | 95% interval, uncorrected | Corrected interval | Survives correction |
|:-------|---------:|-----:|-------:|----:|:--|:--|:--|
| `assists` | 1,021 | 52 | -14.9u | -28.6% | -50.2% .. -7.0% | -59.9% .. +2.7% | no |
| `blocked_shots` | 8 | 2 | +1.6u | +80.1% | +73.8% .. +86.4% | +71.0% .. +89.2% | too few (<30) |
| `goalie_saves` | 89 | 5 | +0.7u | +13.7% | -77.5% .. +104.8% | -118.3% .. +145.6% | too few (<30) |
| `goals` | 2,067 | 24 | -5.9u | -24.6% | -105.3% .. +56.2% | -141.4% .. +92.3% | too few (<30) |
| `moneyline` | 32 | 6 | -0.2u | -3.7% | -127.8% .. +120.5% | -183.4% .. +176.1% | too few (<30) |
| `points` | 1,833 | 87 | -14.9u | -17.1% | -40.4% .. +6.2% | -50.8% .. +16.6% | no |
| `puck_line` | 328 | 22 | -3.8u | -17.3% | -52.9% .. +18.4% | -68.8% .. +34.3% | too few (<30) |
| `regulation_3_way` | 48 | 15 | -0.9u | -5.7% | -68.3% .. +56.9% | -96.4% .. +84.9% | too few (<30) |
| `shots_on_goal` | 2,026 | 168 | -9.6u | -5.7% | -35.0% .. +23.5% | -48.1% .. +36.6% | no |
| `team_total` | 763 | 57 | -5.1u | -9.0% | -56.6% .. +38.7% | -77.9% .. +60.0% | no |
| `total_goals` | 418 | 31 | -4.1u | -13.1% | -107.5% .. +81.3% | -149.7% .. +123.6% | no |

The corrected interval is the 95% interval widened (Bonferroni) for the 11 markets measured on the same data — the interval docs/when_this_ends.md registers the decision on. "Survives correction" reads it: yes when it excludes zero, no when it spans zero, and too few below 30 bets, where nothing survives whatever the interval says. The uncorrected interval is shown beside it for reference only. Both are clustered on the game: the rungs, sides and players of one game settle on one boxscore, so they count as one draw, never as independent bets.

- `assists`: -28.6% over 52 bets, 95% interval -50.2% to -7.0%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. But correcting for the 11 markets measured on the same data widens it to -59.9% to +2.7%, which includes zero — so on the family of tests actually run, **no demonstrated edge**.
- `blocked_shots`: 2 bets is far too few to measure anything. The point estimate is +80.1% and it means nothing yet: no demonstrated edge.
- `goalie_saves`: 5 bets is far too few to measure anything. The point estimate is +13.7% and it means nothing yet: no demonstrated edge.
- `goals`: 24 bets is far too few to measure anything. The point estimate is -24.6% and it means nothing yet: no demonstrated edge.
- `moneyline`: 6 bets is far too few to measure anything. The point estimate is -3.7% and it means nothing yet: no demonstrated edge.
- `points`: -17.1% over 87 bets, 95% interval -40.4% to +6.2%. The interval includes zero, which means **no demonstrated edge**.
- `puck_line`: 22 bets is far too few to measure anything. The point estimate is -17.3% and it means nothing yet: no demonstrated edge.
- `regulation_3_way`: 15 bets is far too few to measure anything. The point estimate is -5.7% and it means nothing yet: no demonstrated edge.
- `shots_on_goal`: -5.7% over 168 bets, 95% interval -35.0% to +23.5%. The interval includes zero, which means **no demonstrated edge**.
- `team_total`: -9.0% over 57 bets, 95% interval -56.6% to +38.7%. The interval includes zero, which means **no demonstrated edge**.
- `total_goals`: -13.1% over 31 bets, 95% interval -107.5% to +81.3%. The interval includes zero, which means **no demonstrated edge**.

## Registered decision statistic

docs/when_this_ends.md registers the stop/continue decision on "the forward ledger's pooled return on frozen opinions, one bet per wager at the best price the card could have taken, corrected across the markets measured", against a floor of 3,000 settled opinions. **The registration is ambiguous on which population it means, and Cooper must decide before 2027-04-25.** "Opinions, not bets" reads as every settled opinion (A), which pools both sides of every priced line and so carries the whole margin. The words "a frozen opinion scored against the price it was frozen at is the same test", with the edge bar among what the registration freezes, read as the opinions clearing the measurement bar (B) — not the card's staked bets; the note under the table says how the two differ. Both are computed below the same way: one per wager after the best-price collapse, pooled across markets, the 95% interval clustered on the game (every rung, side and player of one game settles on one boxscore, so a game is one draw, and the interval is never narrower than one counting each wager on its own) and widened (Bonferroni) for the markets measured, and each counted against the floor in its own settled opinions.

**No reading here is the decision.** No registered outcome is attached to either population while the population is undecided. The decision is not due until 2027-04-25, and a reading before then decides nothing: "If a mid-season result looks strong, the correct action is nothing."

| Population | Settled opinions | Pooled return | 95% interval, uncorrected | Corrected interval | Against zero |
|:--|:--|:--|:--|:--|:--|
| A. Every settled opinion | 8,633, against the floor of 3,000 — floor met | -15.2% (-1311.7u) | -29.9% .. -0.5% | -36.4% .. +6.0% | spans zero (no demonstrated edge) |
| B. Opinions clearing the edge bar | 469, against the floor of 3,000 — below the floor | Not printed: below the floor. Do not read the number. | — | — | — |

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
