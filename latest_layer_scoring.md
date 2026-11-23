# Layer scoring on settled live picks

Settled forward-ledger wagers frozen from 2026-10-22, one bet per wager at the best frozen price, flat 1u, intervals clustered on the game. Each layer is taken out alone and the same wagers repriced against the same prices and outcomes. **Contribution** is units with the layer minus units without it, over the wagers either version bets.

| Layer | Pop. B with | Pop. B without | Contribution (B) | Staked with | Staked without | Contribution (staked) | Verdict |
|:--|:--|:--|--:|:--|:--|--:|:--|
| Each team's own home ice (#344) | +30.0u / 445, +6.7% [-21.6%, +35.1%] | +42.4u / 445, +9.5% [-21.5%, +40.5%] | -12.4u (66 changed; halves +0.5 / -12.9) | -5.9u / 48, -12.3% [-73.5%, +49.0%] | -6.7u / 49, -13.7% [-74.0%, +46.6%] | +0.8u | **keep** |
| Last-five team form, team markets (#345) | +30.0u / 445, +6.7% [-21.6%, +35.1%] | +24.6u / 322, +7.6% [-26.2%, +41.4%] | +5.4u (287 changed; halves +10.6 / -5.2) | -5.9u / 48, -12.3% [-73.5%, +49.0%] | +6.8u / 10, +68.1% [-52.3%, +188.5%] | -12.7u | **keep** |
| Rest and travel (#346) | +30.0u / 445, +6.7% [-21.6%, +35.1%] | +35.1u / 449, +7.8% [-20.0%, +35.6%] | -5.1u (34 changed; halves -1.1 / -4.1) | -5.9u / 48, -12.3% [-73.5%, +49.0%] | -4.1u / 49, -8.4% [-71.3%, +54.5%] | -1.8u | **keep** |
| Posted lineup: player ratings, aging, skater defence (#346, #353, #354, #356) | +30.0u / 445, +6.7% [-21.6%, +35.1%] | +50.6u / 423, +12.0% [-17.6%, +41.5%] | -20.6u (88 changed; halves -19.0 / -1.5) | -5.9u / 48, -12.3% [-73.5%, +49.0%] | +2.5u / 55, +4.6% [-56.2%, +65.4%] | -8.4u | **cut** |
| Tonight's starting goalies, team markets (#351) | +30.0u / 445, +6.7% [-21.6%, +35.1%] | +64.1u / 437, +14.7% [-15.0%, +44.3%] | -34.1u (220 changed; halves +2.9 / -37.0) | -5.9u / 48, -12.3% [-73.5%, +49.0%] | -0.4u / 32, -1.4% [-84.0%, +81.2%] | -5.4u | **keep** |
| Referee crews (#346, #348) | +30.0u / 445, +6.7% [-21.6%, +35.1%] | +30.0u / 445, +6.7% [-21.6%, +35.1%] | +0.0u (0 changed; halves +0.0 / +0.0) | -5.9u / 48, -12.3% [-73.5%, +49.0%] | -5.9u / 48, -12.3% [-73.5%, +49.0%] | +0.0u | **keep (too few changed wagers to judge)** |
| PostHockey pre-game blend, 50/50 (#350) | +30.0u / 445, +6.7% [-21.6%, +35.1%] | +27.3u / 492, +5.6% [-20.2%, +31.3%] | +2.7u (73 changed; halves -1.6 / +4.3) | -5.9u / 48, -12.3% [-73.5%, +49.0%] | -9.1u / 58, -15.6% [-67.1%, +35.9%] | +3.2u | **keep** |
| Last-five team form, props (#345) | +3.9u / 3,716, +0.1% [-6.3%, +6.6%] | +80.6u / 3,665, +2.2% [-5.5%, +9.9%] | -76.7u (1987 changed; halves -90.9 / +14.3) | +23.1u / 212, +10.9% [-3.9%, +25.7%] | +2.7u / 173, +1.6% [-14.7%, +17.9%] | +20.3u | **keep** |
| Matchup by position, props (#346) | +3.9u / 3,716, +0.1% [-6.3%, +6.6%] | -6.1u / 3,715, -0.2% [-6.6%, +6.3%] | +10.0u (489 changed; halves -19.6 / +29.6) | +23.1u / 212, +10.9% [-3.9%, +25.7%] | +17.7u / 197, +9.0% [-7.2%, +25.1%] | +5.4u | **keep** |
| Self-learning, by side (#383, #427) | +1.9u / 2,514, +0.1% [-10.5%, +10.7%] | +58.6u / 5,735, +1.0% [-5.7%, +7.8%] | -56.8u (3943 changed; halves +27.3 / -84.1) | -21.5u / 185, -11.6% [-38.5%, +15.3%] | -10.4u / 473, -2.2% [-16.7%, +12.4%] | -11.1u | **keep** |

## Notes

```
{
  "generated_at": "2026-11-23T08:02:58+00:00",
  "last_night": "2026-11-21",
  "props": {
    "corr_to_frozen": 0.9966295521899509,
    "full": 95662,
    "matched_wagers": 95662,
    "mean_abs_gap_to_frozen": 0.01623983321601507,
    "position_matchup": 95662,
    "team_form_props": 95662
  },
  "settled_wagers": 121981,
  "team": {
    "boards": 32,
    "games_matched": 185,
    "games_mismatched": 5,
    "games_with_factors": 190
  },
  "window_from": "2026-10-22"
}
```

Every interval spans zero unless it says otherwise: **no demonstrated edge** either way. The rule (fixed before the run) cuts a layer only when taking it out improves both populations, population B by 2+ points over the wagers either version bets, in both halves of the window.
