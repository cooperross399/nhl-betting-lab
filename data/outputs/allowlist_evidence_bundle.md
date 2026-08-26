# Allowlist evidence bundle

Everything needed to decide whether to trust `the_odds_api` for a market, in one place.

- Generated: 2026-08-26T01:39:06+00:00

## Recommendation

**Enable nothing yet.** 3 evidence file(s) are missing, so the picture is incomplete: provider_shadow_verification.md, provider_market_discovery.md, historical_props_retention.json.

## What the evidence supports, market by market

- `shots_on_goal`: **not supported** — +2.4% over 2,476 bets. Corrected for the 7 markets measured on the same data it runs -3.0% to +7.9%, which includes zero. No demonstrated edge.
- `points`: **not supported** — -4.5% over 913 bets. Corrected for the 7 markets measured on the same data it runs -13.5% to +4.5%, which includes zero. No demonstrated edge.
- `goals`: **not supported** — only 37 measured bet(s), below the 200 needed before a result is worth reading. Separating a +10% edge from zero takes about 385 bets.
- `assists`: **not supported** — -6.1% over 386 bets. Corrected for the 7 markets measured on the same data it runs -18.1% to +6.0%, which includes zero. No demonstrated edge.
- `goalie_saves`: **not supported** — -2.5% over 410 bets. Corrected for the 7 markets measured on the same data it runs -14.9% to +9.9%, which includes zero. No demonstrated edge.
- `blocked_shots`: **not supported** — +11.8% over 555 bets. Corrected for the 7 markets measured on the same data it runs -0.1% to +23.7%, which includes zero. No demonstrated edge.
- `moneyline`: **not supported** — no price-based measurement exists.
- `puck_line`: **not supported** — no price-based measurement exists.
- `total_goals`: **not supported** — no price-based measurement exists.

## The evidence, and exactly which version of it

| File | Size | SHA-256 |
|:-----|-----:|:--------|
| `data/outputs/player_props_backtest.md` | 6,380 bytes | `a810da60bae4cddafd3d213f93c02752ed283e1a97b596ae69cac04aa83c50f8` |
| `data/outputs/props_calibration.md` | 15,403 bytes | `7fa5f0866504e1336ea198d43d253632c611230da1f3754336dfde5a1e31010a` |
| `data/outputs/team_markets_measurement.md` | 4,675 bytes | `73701c7fcb7761c6a3408b076c44c8ad7f8cce095d4763ff3f7066d47ee4c57e` |
| `data/outputs/what_we_can_claim.md` | 3,461 bytes | `e92e382d14e9b9a339be27b3c9721a27c34871b67567cb62bf27987317921dbf` |
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
      "checksum_sha256": "a810da60bae4cddafd3d213f93c02752ed283e1a97b596ae69cac04aa83c50f8"
    },
    {
      "path": "data/outputs/props_calibration.md",
      "checksum_sha256": "7fa5f0866504e1336ea198d43d253632c611230da1f3754336dfde5a1e31010a"
    },
    {
      "path": "data/outputs/team_markets_measurement.md",
      "checksum_sha256": "73701c7fcb7761c6a3408b076c44c8ad7f8cce095d4763ff3f7066d47ee4c57e"
    },
    {
      "path": "data/outputs/what_we_can_claim.md",
      "checksum_sha256": "e92e382d14e9b9a339be27b3c9721a27c34871b67567cb62bf27987317921dbf"
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
