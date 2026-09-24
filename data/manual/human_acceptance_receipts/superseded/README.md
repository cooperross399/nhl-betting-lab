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
`odds_api-20260924-cooperross399`, which the policy now cites. This file
approves nothing; the approval continues under the new receipt.
