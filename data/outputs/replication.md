# Replication

Did a result found on one window hold on another? No amount of extra precision on the first window can answer that — a result measured more carefully on the data that produced it is still that data.

- Generated: 2026-09-24T18:10:03+00:00
- Discovery window: **player_props_backtest_2024-25**
- Test window: **player_props_backtest_2025-26**

Nothing survived correction on **player_props_backtest_2024-25**, so there is no result to replicate. That is not a failure of the test window.

| Market | Discovery | Test | Verdict |
|:-------|:----------|:-----|:--------|
| `assists` | +1.8% / 1502 bets | -3.3% / 2259 bets | **untestable** |
| `blocked_shots` | +4.6% / 2697 bets | +5.5% / 1589 bets | **untestable** |
| `goalie_saves` | -0.8% / 848 bets | -4.1% / 879 bets | **untestable** |
| `goals` | -10.4% / 286 bets | -3.0% / 278 bets | **untestable** |
| `points` | -3.3% / 2726 bets | -5.4% / 3468 bets ✓ | **untestable** |
| `shots_on_goal` | +2.0% / 5377 bets | +0.4% / 4002 bets | **untestable** |

✓ marks an interval that excludes zero after correcting for the markets tested in that window.

## Market by market

- `assists`: Nothing survived correction on the first window, so there is no result here to replicate.
- `blocked_shots`: Nothing survived correction on the first window, so there is no result here to replicate.
- `goalie_saves`: Nothing survived correction on the first window, so there is no result here to replicate.
- `goals`: Nothing survived correction on the first window, so there is no result here to replicate.
- `points`: Nothing survived correction on the first window, so there is no result here to replicate.
- `shots_on_goal`: Nothing survived correction on the first window, so there is no result here to replicate.

## How much data would settle it

Separating a +10% edge from zero takes about 385 bets; a +18% edge, about 119. A window below 100 bets cannot test anything, which is why such markets are reported as untestable rather than failed.

## Standing notes

- The two windows are never pooled here. Pooling asks what the edge is across everything bought, which is a different question — and it launders a strong first window into a merged average that reads like confirmation.
- Replication requires the test window to exclude zero on its own, not merely to avoid contradicting the first. Most windows fail to contradict most things.
- A failure to replicate does not mean the strategy is worthless. It means the first result is not yet evidence of anything durable.
- Two windows agreeing is worth considerably more than one window measured precisely, and it is still two windows.
