# How a market becomes trusted

Nothing in this repository trusts a provider or a market by default. The
policy file `data/manual/staging_provider_policy.json` shipped allowlisting
**nothing**; what it allowlists now is Cooper's signed decision, recorded in
`CLAUDE.md`'s operating state with its receipt. The card refuses to select
from any market not named in it.

## The sequence

1. **Shadow runs.** A live fetch writes to `data/staging/`. The gameday card
   reads that directory — Gameday Refresh fetches into it and cards from it
   in one job — but prices a market from it only once the policy allowlists
   the market (and the gates below pass), so before step 6 a shadow run
   changes no pick. This proves the adapter parses the provider's real
   responses and produces the rows it claims to. (Until 2026-09-25 this step
   denied that the card reads `data/staging/`; `scripts/run_gameday_card.py`
   reads it by name.)
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

An allowlisted market still passes every other gate on every card
(`scripts/run_gameday_card.py`):

- **Completeness.** Priced for every game in the slate — every priced game
  plus every scheduled regular-season game on the same day not yet under
  way — or excluded as incomplete (`market_eligibility.assess_markets`).
- **Freshness.** The oldest staged row inside the policy's
  `max_provider_run_age_hours` (the stricter of its two limits; 12 hours as
  shipped), or the card is blocked and nothing is frozen.
- **The regular-season screen.** A game the cached club schedules do not know
  as regular season is excluded before pricing — when the cache holds every
  club; with holes in it the screen abstains and the run says so.
- **Model opinion, edge and juice.** No opinion, no selection; a prop clears a
  higher edge bar than a team market; nothing past the juice limit.
- **The puck-drop guard.** A game started, or with a start that cannot be
  confirmed, is quarantined and its stake removed.

Two checks this list used to name do not run on the card, and saying they do
would credit it with protection it does not have. Evidence checksums are
recomputed by the Provider Policy PR Gate, on a pull request that touches the
policy or a receipt and on every push to `main`; the card reads the policy
file and never opens a receipt. And nothing validates the staged files: a
staged file the card cannot parse is skipped, so its markets read as
unavailable, and a row whose price cannot be read is skipped — nothing is
invented, and nothing is flagged either. (Until 2026-09-25 this section
listed "staging validation" and "checksum" among the card's checks.)

Allowlisting says "this market's prices may be used"; it does not say "skip the
checks".

## The record stays on the record

If Cooper approves a market against the measurement's own recommendation, both
the evidence and the decision are recorded, and any answer to "what do the
card's picks rest on" says so plainly. That happened in the EPL lab and the
record is the reason the answer there is still honest.
