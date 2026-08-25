# How a market becomes trusted

Nothing in this repository trusts a provider or a market by default. The
policy file `data/manual/staging_provider_policy.json` ships allowlisting
**nothing**, and the card refuses to select from any market not named in it.

## The sequence

1. **Shadow runs.** A live fetch writes to `data/staging/`, which the card
   cannot read. This proves the adapter parses the provider's real responses
   and produces the rows it claims to.
2. **Coverage discovery.** Per bookmaker, per market, including alternate
   lines. A market is not "unavailable" until this says so. (`total_2_5` in the
   EPL lab was excluded on a coverage check that only looked at the bulk
   `totals` market; the line was in `alternate_totals` the whole time.)
3. **Measurement against real prices.** Historical prices are bought per event
   where the provider retains them. Where it does not, that is recorded by name
   as unmeasurable, and a calibration number is **not** offered as a substitute.
4. **Evidence bundle.** Shadow report, coverage report, measurement reports,
   and their checksums, assembled into one reviewable artifact by
   `scripts/run_allowlist_evidence.py` →
   `data/outputs/allowlist_evidence_bundle.md`. It states what the evidence
   supports market by market, and its honest default — the one every market
   in this repository currently gets — is **not supported**. A market with
   only a calibration number is never supported by it, however large the
   sample.
5. **PR gate.** A pull request that changes the policy file must carry a
   matching evidence bundle and a human acceptance receipt, or CI fails.
6. **Human acceptance receipt.** Cooper reviews the evidence and signs. Only
   this step allowlists anything.

## What Claude may never do

- Write or edit a human acceptance receipt.
- Add a provider or market to `allowed_provider_names` / `required_markets`.
- Weaken, skip, or work around the PR gate.
- Present shadow evidence as though it had allowlisted something.

Claude prepares every one of the six steps and then stops. Step 6 is Cooper's.

## What approval does not buy

An allowlisted market still passes every other gate on every run: staging
validation, completeness, freshness, checksum, and the puck-drop guard.
Allowlisting says "this market's prices may be used"; it does not say "skip the
checks".

## The record stays on the record

If Cooper approves a market against the measurement's own recommendation, both
the evidence and the decision are recorded, and any answer to "what do the
card's picks rest on" says so plainly. That happened in the EPL lab and the
record is the reason the answer there is still honest.
