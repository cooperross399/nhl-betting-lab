# Replication

Did a result found on one window hold on another? No amount of extra precision on the first window can answer that — a result measured more carefully on the data that produced it is still that data.

- Generated: 2026-08-29T00:20:43+00:00
- Discovery window: **player_props_backtest_2024-25**
- Test window: **player_props_backtest_2025-26**

`points` held on **player_props_backtest_2025-26** as well as **player_props_backtest_2024-25**. Two windows agreeing is worth considerably more than one window measured precisely, and it is still two windows.

| Market | Discovery | Test | Verdict |
|:-------|:----------|:-----|:--------|
| `assists` | +1.4% / 2683 bets | -3.6% / 4127 bets | **untestable** |
| `blocked_shots` | +4.8% / 3789 bets ✓ | +4.5% / 2950 bets | **not confirmed** |
| `goalie_saves` | -3.3% / 2217 bets | -5.7% / 3118 bets ✓ | **untestable** |
| `goals` | -12.9% / 294 bets | -3.8% / 282 bets | **untestable** |
| `points` | -3.5% / 7374 bets ✓ | -6.6% / 9047 bets ✓ | **replicated** |
| `shots_on_goal` | +0.8% / 21112 bets | -2.2% / 16925 bets ✓ | **untestable** |

✓ marks an interval that excludes zero after correcting for the markets tested in that window.

## Market by market

- `assists`: Nothing survived correction on the first window, so there is no result here to replicate.
- `blocked_shots`: Same direction (+4.5% over 2950 bets) but the interval does not exclude zero on its own. A window that merely fails to contradict is not confirmation — most windows fail to contradict most things. No demonstrated edge.
- `goalie_saves`: Nothing survived correction on the first window, so there is no result here to replicate.
- `goals`: Nothing survived correction on the first window, so there is no result here to replicate.
- `points`: -6.6% over 9047 bets, same direction, and the interval excludes zero on its own after correction.
- `shots_on_goal`: Nothing survived correction on the first window, so there is no result here to replicate.

## How much data would settle it

Separating a +10% edge from zero takes about 385 bets; a +18% edge, about 119. A window below 100 bets cannot test anything, which is why such markets are reported as untestable rather than failed.

## Standing notes

- The two windows are never pooled here. Pooling asks what the edge is across everything bought, which is a different question — and it launders a strong first window into a merged average that reads like confirmation.
- Replication requires the test window to exclude zero on its own, not merely to avoid contradicting the first. Most windows fail to contradict most things.
- A failure to replicate does not mean the strategy is worthless. It means the first result is not yet evidence of anything durable.
- Two windows agreeing is worth considerably more than one window measured precisely, and it is still two windows.
