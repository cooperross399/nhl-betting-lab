# Allowlist evidence bundle

Everything needed to decide whether to trust `the_odds_api` for a market, in one place.

- Generated: 2026-09-24T18:23:30+00:00

## Recommendation

**Enable nothing yet.** 2 evidence file(s) are missing, so the picture is incomplete: provider_shadow_verification.md, provider_market_discovery.md.

## What the evidence supports, market by market

- `shots_on_goal`: **not supported** — +1.3% over 9,379 bets. Corrected for the 7 markets measured on the same data it runs -1.5% to +4.2%, which includes zero. No demonstrated edge.
- `points`: **not supported** — **-4.4% over 6,194 bets, and the corrected interval excludes zero on the LOSING side.** The held-out window did not confirm it (untestable), so it is not a demonstrated deficit. A loss that survives the correction still argues against enabling this market, not for it.
- `goals`: **not supported** — -6.8% over 564 bets. Corrected for the 7 markets measured on the same data it runs -21.1% to +7.6%, which includes zero. No demonstrated edge.
- `assists`: **not supported** — -1.3% over 3,761 bets. Corrected for the 7 markets measured on the same data it runs -5.1% to +2.5%, which includes zero. No demonstrated edge.
- `goalie_saves`: **not supported** — -2.5% over 1,727 bets. Corrected for the 7 markets measured on the same data it runs -8.6% to +3.7%, which includes zero. No demonstrated edge.
- `blocked_shots`: **not supported** — +4.9% over 4,286 bets, and the interval excludes zero even after correcting for the 7 markets measured on the same data. That is the strongest thing this repository can currently say, and it rests on one snapshot window. **The held-out window did not confirm it (untestable).** One window is a candidate; two agreeing is a finding. This is the first.
- `hits`: **not supported** — -1.3% over 5,178 bets. Corrected for the 8 markets measured on the same data it runs -5.0% to +2.4%, which includes zero. No demonstrated edge. Measured only in the `card` window, 9.6 hours before face-off.
- `moneyline`: **not supported** — -6.6% over 954 bets. No demonstrated edge.
- `puck_line`: **not supported** — -4.2% over 1,117 bets. No demonstrated edge.
- `total_goals`: **not supported** — -4.0% over 1,216 bets. No demonstrated edge.
- `regulation_3_way`: **not supported** — no price-based measurement exists.
- `team_total`: **not supported** — no price-based measurement exists.

## The evidence, and exactly which version of it

| File | Size | SHA-256 |
|:-----|-----:|:--------|
| `data/outputs/player_props_backtest.md` | 7,950 bytes | `642684c1a0a5510d13b07a94ea4244c6d876bbb248c27766050e3a9010014aed` |
| `data/outputs/props_calibration.md` | 17,658 bytes | `fb8eb3e3d50dd05c762d8b1b8278886cb59d47e58128e92c3c28ae434f827aef` |
| `data/outputs/team_markets_measurement.md` | 7,725 bytes | `6505c077d4a62bf8433015f5a288a7956c6e7570cb77dbe7d1f197c044c5993e` |
| `data/outputs/what_we_can_claim.md` | 4,532 bytes | `a0b4192e845a063c29bce0ac713b660b8e4a3155ec28ba4e1291348428be5a38` |
| `provider_shadow_verification.md` | **missing** | — |
| `provider_market_discovery.md` | **missing** | — |
| `data/outputs/historical_props_retention.json` | 1,328 bytes | `e8eb86f049c75a2a9048a3a1e13fc6469f64830119060779f2252cd50f739691` |
| `data/outputs/replication.md` | 2,657 bytes | `6ff525edc3d4ea17768d5f3cdd9a2d7b5155fb5810f59c1c9ef9a8e6f521cd85` |

A missing file is listed rather than omitted. It means that part of the picture has not been produced yet, not that it was reviewed and found unremarkable.

## If you decide to approve

Write the receipt yourself, into `data/manual/human_acceptance_receipts/<receipt_id>.json`. Claude does not write one, and does not leave a draft — a receipt Claude wrote is not evidence that a human reviewed anything. `data/manual/human_acceptance_receipts/README.md` has the full shape; these are the values from this bundle:

```json
{
  "provider_name": "the_odds_api",
  "approved_markets": [
    "<the markets you are approving>"
  ],
  "evidence": [
    {
      "path": "data/outputs/player_props_backtest.md",
      "checksum_sha256": "642684c1a0a5510d13b07a94ea4244c6d876bbb248c27766050e3a9010014aed"
    },
    {
      "path": "data/outputs/props_calibration.md",
      "checksum_sha256": "fb8eb3e3d50dd05c762d8b1b8278886cb59d47e58128e92c3c28ae434f827aef"
    },
    {
      "path": "data/outputs/team_markets_measurement.md",
      "checksum_sha256": "6505c077d4a62bf8433015f5a288a7956c6e7570cb77dbe7d1f197c044c5993e"
    },
    {
      "path": "data/outputs/what_we_can_claim.md",
      "checksum_sha256": "a0b4192e845a063c29bce0ac713b660b8e4a3155ec28ba4e1291348428be5a38"
    },
    {
      "path": "data/outputs/historical_props_retention.json",
      "checksum_sha256": "e8eb86f049c75a2a9048a3a1e13fc6469f64830119060779f2252cd50f739691"
    },
    {
      "path": "data/outputs/replication.md",
      "checksum_sha256": "6ff525edc3d4ea17768d5f3cdd9a2d7b5155fb5810f59c1c9ef9a8e6f521cd85"
    }
  ]
}
```

Then add the same markets to `required_markets` in `data/manual/staging_provider_policy.json`, and the provider name to `allowed_provider_names`. The Provider Policy PR Gate checks that the paperwork matches and that every checksum above still holds.

## Standing notes

- Claude assembled this bundle and stops here. Claude never writes a human acceptance receipt, never adds a name to `allowed_provider_names`, and never adds a market to `required_markets`.
- The checksums above are what makes an approval current. The PR gate recomputes them, so a receipt citing a report that has since changed fails rather than passing quietly.
- Allowlisting a market does not skip any other gate. Staging validation, completeness, freshness and the puck-drop guard all still run on every card.
- An approval made against this evidence's recommendation is a legitimate decision, and it stays on the record as one. The EPL lab has exactly that on file.
- Where several markets are measured on one body of data, the interval that counts is the one corrected for how many were tested. The uncorrected number for whichever market cleared 95% describes a search.
