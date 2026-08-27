# Allowlist evidence bundle

Everything needed to decide whether to trust `the_odds_api` for a market, in one place.

- Generated: 2026-08-27T00:33:38+00:00

## Recommendation

**Enable nothing yet.** 2 evidence file(s) are missing, so the picture is incomplete: provider_shadow_verification.md, provider_market_discovery.md.

## What the evidence supports, market by market

- `shots_on_goal`: **not supported** — +2.4% over 2,476 bets. Corrected for the 7 markets measured on the same data it runs -3.0% to +7.9%, which includes zero. No demonstrated edge.
- `points`: **not supported** — -4.5% over 913 bets. Corrected for the 7 markets measured on the same data it runs -13.5% to +4.5%, which includes zero. No demonstrated edge.
- `goals`: **not supported** — only 37 measured bet(s), below the 200 needed before a result is worth reading. Separating a +10% edge from zero takes about 385 bets.
- `assists`: **not supported** — -6.1% over 386 bets. Corrected for the 7 markets measured on the same data it runs -18.1% to +6.0%, which includes zero. No demonstrated edge.
- `goalie_saves`: **not supported** — -2.5% over 410 bets. Corrected for the 7 markets measured on the same data it runs -14.9% to +9.9%, which includes zero. No demonstrated edge.
- `blocked_shots`: **not supported** — +11.8% over 555 bets. Corrected for the 7 markets measured on the same data it runs -0.1% to +23.7%, which includes zero. No demonstrated edge.
- `hits`: **not supported** — no price-based measurement exists; it has been calibration-checked on 616,730 walk-forward samples, which can rule the model out and can never rule it in.
- `moneyline`: **not supported** — -3.3% over 1,536 bets. No demonstrated edge.
- `puck_line`: **not supported** — -4.6% over 1,563 bets. No demonstrated edge.
- `total_goals`: **not supported** — -0.1% over 823 bets. No demonstrated edge.
- `regulation_3_way`: **not supported** — no price-based measurement exists.

## The evidence, and exactly which version of it

| File | Size | SHA-256 |
|:-----|-----:|:--------|
| `data/outputs/player_props_backtest.md` | 7,296 bytes | `282b0322ae40fdf8491532a4d39ce003af7a74366db5268ff0b02795323653ef` |
| `data/outputs/props_calibration.md` | 17,659 bytes | `369b4c14dfcc65e2ad90334f8c041105638e8ae915d99ecdee56349ccba57c6f` |
| `data/outputs/team_markets_measurement.md` | 6,467 bytes | `34e27414b912eaae97b9550c30b8c3b9643f573dba310025e26b68850acf9f27` |
| `data/outputs/what_we_can_claim.md` | 4,108 bytes | `986d33612333f460a11b58042234788e393a04026c2c1826e57e061005a5f49c` |
| `provider_shadow_verification.md` | **missing** | — |
| `provider_market_discovery.md` | **missing** | — |
| `data/outputs/historical_props_retention.json` | 851 bytes | `7b129822ae5c3624299dd78e0812a8d85ed06c06e6f15e33cda15dfb937a377f` |

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
      "checksum_sha256": "282b0322ae40fdf8491532a4d39ce003af7a74366db5268ff0b02795323653ef"
    },
    {
      "path": "data/outputs/props_calibration.md",
      "checksum_sha256": "369b4c14dfcc65e2ad90334f8c041105638e8ae915d99ecdee56349ccba57c6f"
    },
    {
      "path": "data/outputs/team_markets_measurement.md",
      "checksum_sha256": "34e27414b912eaae97b9550c30b8c3b9643f573dba310025e26b68850acf9f27"
    },
    {
      "path": "data/outputs/what_we_can_claim.md",
      "checksum_sha256": "986d33612333f460a11b58042234788e393a04026c2c1826e57e061005a5f49c"
    },
    {
      "path": "data/outputs/historical_props_retention.json",
      "checksum_sha256": "7b129822ae5c3624299dd78e0812a8d85ed06c06e6f15e33cda15dfb937a377f"
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
