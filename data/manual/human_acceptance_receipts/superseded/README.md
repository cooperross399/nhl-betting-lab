# Superseded receipts

A receipt lands here when the approval it carried has been withdrawn, or
when the same approval has been re-attested under a new receipt because
the evidence it cited was corrected. The two are different events and each
entry below says which. A receipt is kept because it is the record of a decision that was really made
— who approved what, when, against which evidence and which checksums —
and deleting that would erase the audit trail the whole gate exists to
produce.

**A receipt in this directory approves nothing.** The shipped policy
cites no receipt from here, the PR gate never reads it, and the card
cannot reach a market through it. Re-enabling a market means a new
receipt, signed against the evidence as it reads now.

## odds_api-20260827T165300-0400-cooperross399.json

Approved all eleven markets on 2026-08-27, explicitly overriding an
enable-nothing recommendation, on evidence reporting +1.4% over 4,830
bets with an interval including zero. Withdrawn 2026-08-29: the full
two-season population (73,918 bets) put the same measurement at -1.6%
with the interval excluding zero on the losing side. The approval was
not wrong to have been made on what was known; it is simply no longer
supported by what is known.

## odds_api-20260923-cooperross399.json

**Re-attested, not withdrawn.** Approved all twelve markets on 2026-09-23
against the evidence bundle's own recommendation. On 2026-09-24 the team
measurement it cites, `team_markets_measurement.md`, was found taking the
best price per wager across two snapshot windows and across face-off, so its
checksum stopped matching, which is the gate doing its job. Corrected, all
three team markets measure lower (moneyline +0.0% over 1,366 to -6.6% over
954) and every interval still includes zero. Cooper re-attested the same
twelve markets against the corrected report in
`odds_api-20260924-cooperross399`, which was itself re-attested later the
same day (below). This file approves nothing.

## odds_api-20260924-cooperross399.json

**Re-attested, not withdrawn.** The first re-attestation of the twelve
markets, against the corrected team report. Later the same day three of the
records it cites were regenerated: `replication.md` had never been rebuilt
since per-quote counting was retired, and rebuilt at one bet per wager,
`points` no longer replicates as a loss; `what_we_can_claim.md` and
`allowlist_evidence_bundle.md` had been stale since 2026-09-02 and
2026-08-27. Its statement also carried three claims from those records that
were wrong: that `points` replicated, that `hits` was never measured (it has
5,021 wagers in the `card` window), and out-of-date `points` and
`blocked_shots` figures. Cooper re-attested the same twelve markets in
`odds_api-20260924T095805-0400-cooperross399`, which the policy now cites and which
corrects those claims. This file approves nothing.
