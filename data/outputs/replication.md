# Replication

Did a result found on one window hold on another? No amount of extra precision on the first window can answer that — a result measured more carefully on the data that produced it is still that data.

- Generated: 2026-08-26T02:01:30+00:00
- Discovery window: **2024-25**
- Test window: **2025-26**

Nothing survived correction on **2024-25**, so there is no result to replicate. That is not a failure of the test window.

| Market | Discovery | Test | Verdict |
|:-------|:----------|:-----|:--------|
| `assists` | -1.0% / 220 bets | -12.8% / 166 bets | **untestable** |
| `blocked_shots` | +13.4% / 411 bets | +7.4% / 144 bets | **untestable** |
| `goalie_saves` | -3.3% / 257 bets | -1.2% / 153 bets | **untestable** |
| `goals` | +20.4% / 26 bets | +1.6% / 11 bets | **untestable** |
| `points` | +0.0% / 611 bets | -13.6% / 302 bets | **untestable** |
| `shots_on_goal` | +3.0% / 1925 bets | +0.6% / 551 bets | **untestable** |

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
