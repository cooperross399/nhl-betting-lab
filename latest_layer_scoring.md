# Layer scoring on settled live picks

Settled forward-ledger wagers frozen from 2026-10-22, one bet per wager at the best frozen price, flat 1u, intervals clustered on the game. Each layer is taken out alone and the same wagers repriced against the same prices and outcomes. **Contribution** is units with the layer minus units without it, over the wagers either version bets.

| Layer | Pop. B with | Pop. B without | Contribution (B) | Staked with | Staked without | Contribution (staked) | Verdict |
|:--|:--|:--|--:|:--|:--|--:|:--|
| Each team's own home ice (#344) | +21.2u / 340, +6.2% [-24.2%, +36.7%] | +34.3u / 339, +10.1% [-24.6%, +44.8%] | -13.1u (55 changed; halves +0.5 / -13.6) | -6.2u / 35, -17.6% [-89.8%, +54.6%] | -7.0u / 36, -19.5% [-90.0%, +51.1%] | +0.8u | **keep** |
| Last-five team form, team markets (#345) | +21.2u / 340, +6.2% [-24.2%, +36.7%] | +18.8u / 202, +9.3% [-30.3%, +48.9%] | +2.4u (212 changed; halves +10.6 / -8.2) | -6.2u / 35, -17.6% [-89.8%, +54.6%] | +5.2u / 7, +74.1% [-96.2%, +244.5%] | -11.4u | **keep** |
| Rest and travel (#346) | +21.2u / 340, +6.2% [-24.2%, +36.7%] | +25.2u / 339, +7.4% [-22.8%, +37.7%] | -4.1u (27 changed; halves -1.1 / -3.0) | -6.2u / 35, -17.6% [-89.8%, +54.6%] | -4.4u / 36, -12.3% [-87.2%, +62.7%] | -1.8u | **keep (too few changed wagers to judge)** |
| Posted lineup: player ratings, aging, skater defence (#346, #353, #354, #356) | +21.2u / 340, +6.2% [-24.2%, +36.7%] | +41.7u / 318, +13.1% [-19.1%, +45.3%] | -20.6u (88 changed; halves -19.0 / -1.5) | -6.2u / 35, -17.6% [-89.8%, +54.6%] | +2.3u / 42, +5.4% [-66.1%, +76.9%] | -8.4u | **cut** |
| Tonight's starting goalies, team markets (#351) | +21.2u / 340, +6.2% [-24.2%, +36.7%] | +79.5u / 322, +24.7% [-13.1%, +62.5%] | -58.4u (166 changed; halves +2.9 / -61.3) | -6.2u / 35, -17.6% [-89.8%, +54.6%] | +3.2u / 26, +12.4% [-82.4%, +107.2%] | -9.4u | **keep** |
| Referee crews (#346, #348) | +21.2u / 340, +6.2% [-24.2%, +36.7%] | +21.2u / 340, +6.2% [-24.2%, +36.7%] | +0.0u (0 changed; halves +0.0 / +0.0) | -6.2u / 35, -17.6% [-89.8%, +54.6%] | -6.2u / 35, -17.6% [-89.8%, +54.6%] | +0.0u | **keep (too few changed wagers to judge)** |
| PostHockey pre-game blend, 50/50 (#350) | +21.2u / 340, +6.2% [-24.2%, +36.7%] | +15.7u / 372, +4.2% [-23.8%, +32.3%] | +5.5u (56 changed; halves -1.6 / +7.1) | -6.2u / 35, -17.6% [-89.8%, +54.6%] | -7.8u / 41, -19.0% [-81.7%, +43.7%] | +1.6u | **keep** |
| Last-five team form, props (#345) | +12.3u / 2,880, +0.4% [-7.3%, +8.1%] | +83.5u / 2,892, +2.9% [-6.3%, +12.0%] | -71.2u (1590 changed; halves -90.9 / +19.8) | +9.2u / 113, +8.2% [-13.5%, +29.8%] | +17.7u / 88, +20.2% [-4.9%, +45.2%] | -8.5u | **keep** |
| Matchup by position, props (#346) | +12.3u / 2,880, +0.4% [-7.3%, +8.1%] | +22.3u / 2,854, +0.8% [-7.0%, +8.5%] | -10.0u (378 changed; halves -19.6 / +9.6) | +9.2u / 113, +8.2% [-13.5%, +29.8%] | +10.2u / 102, +10.0% [-14.3%, +34.2%] | -1.0u | **keep** |
| Self-learning, by side (#383, #427) | +9.5u / 2,166, +0.4% [-11.2%, +12.1%] | +38.6u / 4,474, +0.9% [-7.0%, +8.7%] | -29.1u (2938 changed; halves +27.3 / -56.4) | -2.2u / 134, -1.6% [-38.3%, +35.0%] | -9.1u / 271, -3.4% [-24.3%, +17.6%] | +6.9u | **keep** |

## Notes

```
{
  "generated_at": "2026-11-16T07:09:26+00:00",
  "last_night": "2026-11-14",
  "props": {
    "corr_to_frozen": 0.9966073987300162,
    "full": 75159,
    "matched_wagers": 75159,
    "mean_abs_gap_to_frozen": 0.016155784875948005,
    "position_matchup": 75159,
    "team_form_props": 75159
  },
  "settled_wagers": 95635,
  "team": {
    "boards": 25,
    "games_matched": 138,
    "games_mismatched": 5,
    "games_with_factors": 143
  },
  "window_from": "2026-10-22"
}
```

Every interval spans zero unless it says otherwise: **no demonstrated edge** either way. The rule (fixed before the run) cuts a layer only when taking it out improves both populations, population B by 2+ points over the wagers either version bets, in both halves of the window.
