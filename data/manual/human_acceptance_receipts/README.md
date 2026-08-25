# Human acceptance receipts

One JSON file per approval. A receipt records that **Cooper** looked at the
measurement evidence for a provider and a specific set of markets, and decided
to allow them.

**Claude never writes a file in this directory.** Not a draft, not a template,
not "so it is ready to sign". A receipt Claude wrote is not evidence that a
human reviewed anything, and a directory where some receipts are real and some
are drafts is worse than an empty one.

## Shape

```json
{
  "receipt_id": "odds_api-20261001T090000-0400-<8 hex>",
  "provider_name": "the_odds_api",
  "reviewer_name": "cooperross399",
  "reviewed_at": "2026-10-01T09:00:00-04:00",
  "approved_markets": ["moneyline"],
  "evidence": [
    {
      "path": "data/outputs/player_props_backtest.md",
      "checksum_sha256": "<64 hex>"
    }
  ],
  "reviewer_statement": "I have read the evidence above, including where it recommends against enabling, and I am approving these markets anyway / on its recommendation.",
  "known_limitations": []
}
```

## What the PR gate can and cannot check

It **can** check that every newly-allowed market names a receipt, that the
receipt exists, that it is well formed, that it lists the markets being
allowed, and that every evidence file it cites exists with the checksum it
claims. A stale receipt pointing at a report that has since changed fails.

It **cannot** check that a human wrote it. Nothing in a file can prove that.
The protections that actually carry that weight are branch protection and
Cooper's own review on the pull request. The gate's job is to make sure the
paperwork is real and current, not to prove authorship — and saying so plainly
is better than implying a guarantee it cannot give.
