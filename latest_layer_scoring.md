# Layer scoring on settled live picks

Settled forward-ledger wagers frozen from 2026-10-22, one bet per wager at the best frozen price, flat 1u, intervals clustered on the game. Each layer is taken out alone and the same wagers repriced against the same prices and outcomes. **Contribution** is units with the layer minus units without it, over the wagers either version bets.

| Layer | Pop. B with | Pop. B without | Contribution (B) | Staked with | Staked without | Contribution (staked) | Verdict |
|:--|:--|:--|--:|:--|:--|--:|:--|
| Each team's own home ice (#344) | +22.9u / 226, +10.1% [-25.5%, +45.8%] | +17.9u / 221, +8.1% [-28.5%, +44.7%] | +5.0u (45 changed; halves +0.5 / +4.5) | -5.9u / 12, -49.2% [-144.9%, +46.4%] | -5.9u / 12, -49.2% [-144.9%, +46.4%] | +0.0u | **keep** |
| Last-five team form, team markets (#345) | +22.9u / 226, +10.1% [-25.5%, +45.8%] | +14.9u / 110, +13.6% [-33.0%, +60.1%] | +8.0u (168 changed; halves +10.6 / -2.6) | -5.9u / 12, -49.2% [-144.9%, +46.4%] | +6.1u / 3, +203.0% [-inf%, +inf%] | -12.0u | **keep** |
| Rest and travel (#346) | +22.9u / 226, +10.1% [-25.5%, +45.8%] | +24.9u / 223, +11.1% [-24.5%, +46.8%] | -1.9u (25 changed; halves -1.1 / -0.8) | -5.9u / 12, -49.2% [-144.9%, +46.4%] | -4.2u / 13, -32.0% [-154.4%, +90.4%] | -1.8u | **keep (too few changed wagers to judge)** |
| Posted lineup: player ratings, aging, skater defence (#346, #353, #354, #356) | +22.9u / 226, +10.1% [-25.5%, +45.8%] | +43.5u / 204, +21.3% [-17.1%, +59.8%] | -20.6u (88 changed; halves -19.0 / -1.5) | -5.9u / 12, -49.2% [-144.9%, +46.4%] | +2.5u / 19, +13.2% [-95.8%, +122.2%] | -8.4u | **cut** |
| Tonight's starting goalies, team markets (#351) | +22.9u / 226, +10.1% [-25.5%, +45.8%] | +52.6u / 215, +24.4% [-16.0%, +64.8%] | -29.6u (111 changed; halves +2.9 / -32.6) | -5.9u / 12, -49.2% [-144.9%, +46.4%] | -8.1u / 13, -62.1% [-148.1%, +23.9%] | +2.2u | **keep** |
| Referee crews (#346, #348) | +22.9u / 226, +10.1% [-25.5%, +45.8%] | +22.9u / 226, +10.1% [-25.5%, +45.8%] | +0.0u (0 changed; halves +0.0 / +0.0) | -5.9u / 12, -49.2% [-144.9%, +46.4%] | -5.9u / 12, -49.2% [-144.9%, +46.4%] | +0.0u | **keep (too few changed wagers to judge)** |
| PostHockey pre-game blend, 50/50 (#350) | +22.9u / 226, +10.1% [-25.5%, +45.8%] | +20.2u / 251, +8.1% [-24.7%, +40.8%] | +2.7u (35 changed; halves -1.6 / +4.3) | -5.9u / 12, -49.2% [-144.9%, +46.4%] | -7.2u / 15, -47.8% [-129.5%, +34.0%] | +1.3u | **keep** |
| Last-five team form, props (#345) | -163.3u / 2,210, -7.4% [-14.1%, -0.6%] | -108.8u / 2,242, -4.9% [-14.3%, +4.6%] | -54.5u (1204 changed; halves -90.9 / +36.5) | +12.6u / 98, +12.9% [-11.1%, +36.8%] | +9.7u / 77, +12.6% [-13.1%, +38.3%] | +2.9u | **keep** |
| Matchup by position, props (#346) | -163.3u / 2,210, -7.4% [-14.1%, -0.6%] | -137.3u / 2,181, -6.3% [-13.1%, +0.5%] | -26.0u (271 changed; halves -19.6 / -6.4) | +12.6u / 98, +12.9% [-11.1%, +36.8%] | +13.3u / 89, +15.0% [-11.9%, +41.9%] | -0.7u | **keep** |
| Self-learning, by side (#383, #427) | +31.3u / 1,734, +1.8% [-9.8%, +13.4%] | -59.7u / 3,318, -1.8% [-9.7%, +6.1%] | +90.9u (2174 changed; halves +27.3 / +63.6) | +5.7u / 101, +5.6% [-34.5%, +45.8%] | -8.6u / 184, -4.7% [-27.4%, +18.1%] | +14.3u | **keep** |

## Notes

```
{
  "generated_at": "2026-11-10T01:35:31+00:00",
  "last_night": "2026-11-08",
  "props": {
    "corr_to_frozen": 0.9964708090942528,
    "full": 56674,
    "matched_wagers": 56674,
    "mean_abs_gap_to_frozen": 0.016253847105415296,
    "position_matchup": 56674,
    "team_form_props": 56674
  },
  "settled_wagers": 71550,
  "team": {
    "boards": 19,
    "games_matched": 95,
    "games_mismatched": 3,
    "games_with_factors": 98
  },
  "window_from": "2026-10-22"
}
```

Every interval spans zero unless it says otherwise: **no demonstrated edge** either way. The rule (fixed before the run) cuts a layer only when taking it out improves both populations, population B by 2+ points over the wagers either version bets, in both halves of the window.
