# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-08-25T20:18:50+00:00
- Edge threshold: **6.0%**
- No bets were placed, so nothing is measured. That is a statement about the evidence, not about the model.

## Not measured

No historically-priced outcome cleared the edge threshold with a model opinion behind it, so no bet was placed and **nothing is measured**.

- Priced outcomes seen: 0
- Without a model opinion: 0
- Below the edge threshold: 0

This is a statement about the evidence, not about the model. It means **no demonstrated edge** — and equally, no demonstrated absence of one.

## Which markets can be measured at all

No retention probe has been run, so which prop markets the provider retains historically is **unknown**. It is not assumed to be all of them and it is not assumed to be none.

Markets this lab prices: `shots_on_goal`, `points`, `goals`, `assists`, `goalie_saves`, `blocked_shots`. Until a retention probe has run, none of them is established as measurable or unmeasurable.

## Standing notes

- Settlement comes from the NHL boxscore, never from the odds provider. A provider outage can change what was measured; it can never change what a bet did.
- Prop prices are one-sided at most books, so the implied probability used here includes the vig. That overstates the true probability and therefore **understates** every edge below — the measurement is conservative in that one direction.
- A player who did not dress produces no bet, matching how a book voids a prop on a player who never enters.
- A market the provider does not retain historically cannot be measured historically. Those markets are named below as unmeasurable. A calibration number is not offered in their place.
- This report decides. A change that improves calibration and loses here does not ship.
