# Allowlist evidence bundle

Everything needed to decide whether to trust `the_odds_api` for a market, in one place.

- Generated: 2026-08-25T23:11:37+00:00

## Recommendation

**Enable nothing yet.** 3 evidence file(s) are missing, so the picture is incomplete: provider_shadow_verification.md, provider_market_discovery.md, historical_props_retention.json.

## What the evidence supports, market by market

- `shots_on_goal`: **not supported** — +3.3% over 683 bets. Corrected for the 7 markets measured on the same data it runs -6.9% to +13.5%, which includes zero. No demonstrated edge.
- `points`: **not supported** — -6.9% over 288 bets. Corrected for the 7 markets measured on the same data it runs -22.3% to +8.5%, which includes zero. No demonstrated edge.
- `goals`: **not supported** — only 7 measured bet(s), below the 200 needed before a result is worth reading. Separating a +10% edge from zero takes about 385 bets.
- `assists`: **not supported** — only 111 measured bet(s), below the 200 needed before a result is worth reading. Separating a +10% edge from zero takes about 385 bets.
- `goalie_saves`: **not supported** — only 23 measured bet(s), below the 200 needed before a result is worth reading. Separating a +10% edge from zero takes about 385 bets.
- `blocked_shots`: **not supported** — only 156 measured bet(s), below the 200 needed before a result is worth reading. Separating a +10% edge from zero takes about 385 bets.
- `moneyline`: **not supported** — no price-based measurement exists.
- `puck_line`: **not supported** — no price-based measurement exists.
- `total_goals`: **not supported** — no price-based measurement exists.

## The evidence, and exactly which version of it

| File | Size | SHA-256 |
|:-----|-----:|:--------|
| `data/outputs/player_props_backtest.md` | 6,073 bytes | `7fd9ef3a8ed49730da8bd6a69c5496a37b2a792f666585b38aa48234bcb7978d` |
| `data/outputs/props_calibration.md` | 15,403 bytes | `93443a9c0046f0ad5cc1038e59dbf454066d5adf4c71661a2bfc71b52ed82769` |
| `data/outputs/team_markets_measurement.md` | 4,675 bytes | `73701c7fcb7761c6a3408b076c44c8ad7f8cce095d4763ff3f7066d47ee4c57e` |
| `data/outputs/what_we_can_claim.md` | 3,529 bytes | `bb3f8c5609d635c88dcbe8cebc06aaae6884abe0bea71a76c2f2e6720f527874` |
| `provider_shadow_verification.md` | **missing** | — |
| `provider_market_discovery.md` | **missing** | — |
| `historical_props_retention.json` | **missing** | — |

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
      "checksum_sha256": "7fd9ef3a8ed49730da8bd6a69c5496a37b2a792f666585b38aa48234bcb7978d"
    },
    {
      "path": "data/outputs/props_calibration.md",
      "checksum_sha256": "93443a9c0046f0ad5cc1038e59dbf454066d5adf4c71661a2bfc71b52ed82769"
    },
    {
      "path": "data/outputs/team_markets_measurement.md",
      "checksum_sha256": "73701c7fcb7761c6a3408b076c44c8ad7f8cce095d4763ff3f7066d47ee4c57e"
    },
    {
      "path": "data/outputs/what_we_can_claim.md",
      "checksum_sha256": "bb3f8c5609d635c88dcbe8cebc06aaae6884abe0bea71a76c2f2e6720f527874"
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
