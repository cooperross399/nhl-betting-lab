# Replication

Did a result found on one window hold on another? No amount of extra precision on the first window can answer that — a result measured more carefully on the data that produced it is still that data.

- Generated: 2026-08-25T23:10:47+00:00
- Discovery window: **2025-26**
- Test window: **2024-25**

`shots_on_goal` survived on **2025-26** and did **not** replicate on **2024-25**. The first result is not yet evidence of anything durable: no demonstrated edge.

| Market | Discovery | Test | Verdict |
|:-------|:----------|:-----|:--------|
| `assists` | -2.4% / 72 bets | +7.2% / 39 bets | **untestable** |
| `blocked_shots` | +1.5% / 67 bets | +19.0% / 89 bets | **untestable** |
| `goalie_saves` | +20.8% / 14 bets | +82.9% / 9 bets | **untestable** |
| `goals` | -49.6% / 3 bets | -28.2% / 4 bets | **untestable** |
| `points` | -16.4% / 137 bets | +1.7% / 151 bets | **untestable** |
| `shots_on_goal` | +18.1% / 263 bets ✓ | -6.0% / 420 bets | **contradicted** |

✓ marks an interval that excludes zero after correcting for the markets tested in that window.

## Market by market

- `assists`: Nothing survived correction on the first window, so there is no result here to replicate.
- `blocked_shots`: Nothing survived correction on the first window, so there is no result here to replicate.
- `goalie_saves`: Nothing survived correction on the first window, so there is no result here to replicate.
- `goals`: Nothing survived correction on the first window, so there is no result here to replicate.
- `points`: Nothing survived correction on the first window, so there is no result here to replicate.
- `shots_on_goal`: The test window points the other way (-6.0% against +18.1%). No demonstrated edge.

## How much data would settle it

Separating a +10% edge from zero takes about 385 bets; a +18% edge, about 119. A window below 100 bets cannot test anything, which is why such markets are reported as untestable rather than failed.

## Standing notes

- The two windows are never pooled here. Pooling asks what the edge is across everything bought, which is a different question — and it launders a strong first window into a merged average that reads like confirmation.
- Replication requires the test window to exclude zero on its own, not merely to avoid contradicting the first. Most windows fail to contradict most things.
- A failure to replicate does not mean the strategy is worthless. It means the first result is not yet evidence of anything durable.
- Two windows agreeing is worth considerably more than one window measured precisely, and it is still two windows.
