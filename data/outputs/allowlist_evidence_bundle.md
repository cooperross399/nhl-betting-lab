# Allowlist evidence bundle

Everything needed to decide whether to trust `the_odds_api` for a market, in one place.

- Generated: 2026-08-27T05:59:11+00:00

## Recommendation

**Enable nothing yet.** 2 evidence file(s) are missing, so the picture is incomplete: provider_shadow_verification.md, provider_market_discovery.md.

## What the evidence supports, market by market

- `shots_on_goal`: **not supported** — +3.0% over 2,508 bets. Corrected for the 7 markets measured on the same data it runs -2.4% to +8.5%, which includes zero. No demonstrated edge.
- `points`: **not supported** — -5.5% over 940 bets. Corrected for the 7 markets measured on the same data it runs -14.3% to +3.3%, which includes zero. No demonstrated edge.
- `goals`: **not supported** — only 34 measured bet(s), below the 200 needed before a result is worth reading. Separating a +10% edge from zero takes about 385 bets.
- `assists`: **not supported** — -4.5% over 403 bets. Corrected for the 7 markets measured on the same data it runs -16.2% to +7.3%, which includes zero. No demonstrated edge.
- `goalie_saves`: **not supported** — -1.7% over 397 bets. Corrected for the 7 markets measured on the same data it runs -14.3% to +10.9%, which includes zero. No demonstrated edge.
- `blocked_shots`: **not supported** — +11.9% over 548 bets. Corrected for the 7 markets measured on the same data it runs -0.1% to +23.9%, which includes zero. No demonstrated edge.
- `hits`: **not supported** — no price-based measurement exists; it has been calibration-checked on 616,730 walk-forward samples, which can rule the model out and can never rule it in.
- `moneyline`: **not supported** — -2.4% over 1,504 bets. No demonstrated edge.
- `puck_line`: **not supported** — -4.3% over 1,541 bets. No demonstrated edge.
- `total_goals`: **not supported** — -0.5% over 1,150 bets. No demonstrated edge.
- `regulation_3_way`: **not supported** — no price-based measurement exists.

## The evidence, and exactly which version of it

| File | Size | SHA-256 |
|:-----|-----:|:--------|
| `data/outputs/player_props_backtest.md` | 7,393 bytes | `641fa0de7988c6351f9b69f4ca7d9719179e4e76bd48fbcb1fd165998fa9fdf8` |
| `data/outputs/props_calibration.md` | 17,658 bytes | `8457e54905d9a02c4819c8b22db6df739a82b8dbd3e35121697b4d5b305cf869` |
| `data/outputs/team_markets_measurement.md` | 6,857 bytes | `0714ca1705a753a7205639258a4763243fc3d6546bf3cee0a06dfb23bd3a8afa` |
| `data/outputs/what_we_can_claim.md` | 4,028 bytes | `9d9da7dca919e041ff845bd0ba7f65a698a5b0171f5605f5e08757c226784fbe` |
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
      "checksum_sha256": "641fa0de7988c6351f9b69f4ca7d9719179e4e76bd48fbcb1fd165998fa9fdf8"
    },
    {
      "path": "data/outputs/props_calibration.md",
      "checksum_sha256": "8457e54905d9a02c4819c8b22db6df739a82b8dbd3e35121697b4d5b305cf869"
    },
    {
      "path": "data/outputs/team_markets_measurement.md",
      "checksum_sha256": "0714ca1705a753a7205639258a4763243fc3d6546bf3cee0a06dfb23bd3a8afa"
    },
    {
      "path": "data/outputs/what_we_can_claim.md",
      "checksum_sha256": "9d9da7dca919e041ff845bd0ba7f65a698a5b0171f5605f5e08757c226784fbe"
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
