**Selections changed** since the previous card — there is no card this run, and the previous run had one or this is the first run. No regular-season game is left to card today: the slate holds none, and the schedule has none still to be played on this league day. Not a fault, and it does not degrade the run.

# NHL gameday card

- Generated: 2026-11-20T13:47:00+00:00
- No card. 1 blocker(s); no selection, lean, pass, or stake was produced.
- Included markets: **none**
- Unit size: $25

## No card

- No market is eligible for automated picks. Every market is listed under excluded markets with its reason. None of them is a pass, an avoid, or a no-value call.

**No best bet, lean, pass, or stake was produced.** An empty card that explains itself is useful; a card with invented content is worse than no card.

## Stat sides

Who the model expects to win each game, from the same team ratings the card prices on. The card stakes a team bet (moneyline, puck line, regulation) only when it beats the price and the model gives that team at least a 40% chance, so an underdog with a real chance can still be a bet; the last column says how this side's chance compares with its best moneyline price.

_No game on tonight's slate has a moneyline opinion to show._

## Hits lines (PrizePicks)

No sportsbook the lab can reach has posted hits since October 27. PrizePicks still posts hits lines, so each one is listed with the model's chance of the over and the under. PrizePicks is a pick'em app, not a sportsbook: its lines carry no odds to beat, so nothing here is a bet.

_PrizePicks has not posted a hits line for tonight's games yet._

## Due List

Backtest of the shipped rule (either bar) on 2024-25 and 2025-26 bought prices, best price, card window, flat stake: points -3.5% over 574 wagers (95% -10.8% to +3.8%); goals +1.3% over 972 wagers (95% -8.6% to +11.5%); assists +9.2% over 301 wagers (95% -2.0% to +19.9%); no category's interval sits above zero.

Big games, re-measured 2026-11-17 on 2024-25 and 2025-26 (scripts/run_due_list_big_games.py, Due List Tuning run 44104405522; each setting is the cell both seasons agreed on, picked after seeing it, so the figures flatter it). 2+ goals, 40+ goal scorers 25+ games without one: hit 7.9% against 10.6% implied, -23.0% over 253 (95% -55.4% to +12.8%; -31.3% in 2024-25, +10.1% in 2025-26), no demonstrated edge. Hat trick, 40+ at 50+: -63.1% over 853 (95% -87.8% to -33.9%), a demonstrated loss at every setting tried. Both bars were lengthened on Cooper's word; a longer drought did not make either likelier. 2+ points, new: 100+ point scorers 3+ games without one, -0.8% over 174 (95% -19.7% to +17.9%; -1.6% and +0.6% by season), no demonstrated edge. Shutouts, 4+ last season at 12+ starts without one: 5.2% of 656 starts at 10+ against 9.7% to 9.8% the season before; no book in this feed prices a shutout, so those rows are graded for hits only. A drought made none of these likelier than the player's own rate. Cooper picks from the list.

_Nobody on tonight's slate qualifies._

- No regular-season game is scheduled for 2026-11-20.

## Hot List

Hot List: 80+ points last season and 8+ points in his last 5; 60+ assists and 6+ assists in his last 5; 40+ goals and a goal in 2+ straight games. On two past seasons at the best price: points +0.7% over 360, assists -0.6% over 382, goals -0.9% over 264; this season so far +1.2% over 141, +11.4% over 101 and -13.6% over 38. Every range spans zero: no demonstrated edge. Books already price a hot streak.

_Nobody on tonight's slate qualifies._

- No regular-season game is scheduled for 2026-11-20.

## Excluded markets

- `assists`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `blocked_shots`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `goalie_saves`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `goals`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `hits`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `moneyline`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `points`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `puck_line`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `regulation_3_way`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `shots_on_goal`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `team_total`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.
- `total_goals`: The provider returned no rows for this market. That is an absence, not a price of zero and not a no-value call. Check per-bookmaker coverage including alternate lines before concluding it is not offered.

An excluded market is **not** a pass, an avoid, or a no-value call, and no price was invented for it.

## Safety

- Bets placed: **No**
- Excluded market shown as a pass: **No**
- Odds fabricated: **No**
- Policy edited: **No**
- Started game offered as a play: **No**

## Standing notes

- Recommendations only. No bet is placed by this repository, ever.
- An excluded market is not a pass, an avoid, or a no-value call. It is a market that was not usable, for the stated reason, and no price was invented for it.
- A selection whose game has started — or whose start could not be confirmed — appears under 'Already started — no longer plays' with its stake removed. Ambiguity falls on the not-a-play side.
- Nothing worse than -160 is selected. Plus-money props and alternate lines are preferred over forcing a heavy price.
- Leans are recorded and not staked. The smallest edges are mostly estimation error, and in the EPL lab they lost.
- One outcome is staked once. Where an alternate ladder prices the same outcome at several lines, the highest-edge rung is staked and the rest are recorded as leans naming it. This is not a per-game, per-slate or bankroll cap; there is none.
- No edge here is a demonstrated edge. See `data/outputs/what_we_can_claim.md` for what the evidence actually supports.
- Stakes are sized by each market's closing-line value (Cooper, 2026-11-10): x1.5 where the bets' 95% game-clustered CLV interval sits above zero, x0.5 where it spans zero, x0.25 below it, unchanged under 200 bets or 30 games. Table of 2026-11-19T22:47: `assists` x1.5 (beats the close, +1.01% over 895); `blocked_shots` x1 (too few to judge, +0.82% over 125); `goalie_saves` x1.5 (beats the close, +6.74% over 283); `goals` x1.5 (beats the close, +3.01% over 278); `hits` x1 (too few to judge, +1.07% over 120); `moneyline` x1 (too few to judge, +0.37% over 98); `points` x1.5 (beats the close, +3.13% over 1,709); `puck_line` x1.5 (beats the close, +0.85% over 340); `regulation_3_way` x0.5 (no demonstrated CLV, +0.47% over 217); `shots_on_goal` x1.5 (beats the close, +3.49% over 2,811); `team_total` x0.5 (no demonstrated CLV, +0.67% over 690); `total_goals` x1.5 (beats the close, +0.72% over 565). Beating the close is not a demonstrated edge.


---

What the evidence actually supports:

- `data/outputs/player_props_backtest.md`
- `data/outputs/props_calibration.md`
- `data/outputs/what_we_can_claim.md`

Run: https://github.com/cooperross399/nhl-betting-lab/actions/runs/44718175636

Recommendations only. No bet was placed, no policy was edited, and no market was allowlisted by this run.