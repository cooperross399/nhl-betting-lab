# What the twelve allowlisted markets actually rest on

**Written 2026-09-25, four days before the first live cards fire on
2026-09-29.** Twelve markets were allowlisted on 2026-09-23 and re-attested
three times on 2026-09-24, against an evidence bundle that recommends enabling
nothing. That decision is recorded and is not revisited here.

This document asks a narrower question, because the answer turned out to differ
market by market: **what is behind each of the twelve, and what happens
operationally when the card starts staking them?** Several findings below were
not visible from the policy file, and some of them are defects rather than
decisions. Every claim here was verified against the source on `origin/main`,
not taken from prose.

---

## 1. Zero markets clear the repository's own bar

The bar this lab states for itself is sample **and** correction **and**
replication. `data/outputs/what_we_can_claim.md`:

> **No demonstrated edge in any market.** 10 market(s) have been measured
> against real prices. Nothing survives correcting for the number of markets
> tested and then holds on a window it was not found on.

Two markets survive correction. Neither replicates.

| Market | `card` window (T−9.6h) | Corrected | Replication |
|:--|:--|:--|:--|
| `blocked_shots` | **+7.9%** / 3,026 | +2.7% .. +13.2% | **untestable** — survives within *neither* season |
| `points` | **−4.2%** / 6,140 | −7.6% .. −0.7% | untestable; holds within 2025-26 alone (−5.4% / 3,468) |

`blocked_shots` is registered as a forward hypothesis in
`docs/pre_registered_blocked_shots_forward.md`. `points` is the only market in
this repository measured as a **replicated loss**, and the evidence bundle's
verdict on it is worth quoting exactly: *"A loss that survives the correction
still argues against enabling this market, not for it."*

## 2. Two markets rest on nothing measured at all

**`regulation_3_way`** has no price-based measurement — the provider serves it
per-event only, with no bulk history. It carries walk-forward calibration only
(10,749 held-out samples), and that calibration is the worst-behaved of the
four: the 60–70% bucket predicts 63.9% and observes **51.9%** on 310 samples.

**`team_total`** rests on less than that. It has no price measurement *and no
walk-forward calibration row either* — it appears nowhere in
`team_markets_measurement.md`, whose header reads "347,510 walk-forward samples
across 4 market(s)... 3 market(s) have any price-based evidence."

For both, **the first live card is also the first measurement.** That is a
coherent reason to enable them — a forward ledger is the only evidence that
will ever exist for a market with no bulk history — but it is not the same
thing as approving against a recommendation. There was no recommendation to
override, because there was nothing to recommend on.

**`hits`** is a third case: measured in the `card` window only (−1.3% over
5,178), never in `late`, and it has **no row in `replication.md` at all**.

## 3. The receipt chain was never signed by a human

`data/manual/human_acceptance_receipts/README.md` states:

> **Claude never writes a file in this directory.** Not a draft, not a
> template, not "so it is ready to sign."

All five receipts in that directory were written by Claude. Three say so
outright in their own `prepared_by` field; the live one reads *"Claude, at
Cooper Ross's explicit direction on 2026-09-24 … Cooper chose re-attestation
over signing it himself."*

The receipts are **honest about it** — nothing was hidden, and the six evidence
checksums in the live receipt still match the tracked files byte-for-byte. The
decision behind them is genuinely Cooper's and is recorded as such.

But the artifact and its own governing rule contradict each other, and the PR
gate prints that same rule as a reassurance to whoever reads it next. **A
control that has never once been exercised by the party it names is not a
control.** Either the README should describe what actually happens, or the
receipts should be produced the way it says. That is a decision for Cooper, not
a defect Claude should quietly resolve in either direction.

## 3b. Steps 1 and 2 of the approval sequence have no artifact

`docs/provider_allowlist_approval.md` sets out six steps. Steps 1 (shadow runs)
and 2 (coverage discovery) produce `provider_shadow_verification.md` and
`provider_market_discovery.md`. **Neither file has ever been generated** — both
are absent from `origin/main` and from the primary checkout.

The evidence bundle says so itself, and it is the reason for its verdict:

> **Enable nothing yet.** 2 evidence file(s) are missing, so the picture is
> incomplete: provider_shadow_verification.md, provider_market_discovery.md.

So the current allowlist rests on steps 3–6 of a six-step sequence. Step 2 is
also the step whose absence has already cost this lab once: `hits` was written
off on a one-region probe, and the two-region purchase later returned 5,178
settled wagers. Coverage discovery is the step that catches exactly that.

## 3c. The market list is frozen until 2027-04-25, and the allowlist is the market list

`CLAUDE.md:693-694` and `docs/when_this_ends.md:59` both fix the forward test's
terms in advance. **May not** change before the decision date: *the model, the
edge bar, the market list, the staking rule.*

The allowlist **is** the market list. The twelve are in place before the
season, so the current state is consistent. But it means a thirteenth market
cannot be added mid-season without reshaping the forward test the freeze exists
to protect — which is the same reasoning that makes
`docs/pre_registered_blocked_shots_forward.md` worth having.

Two consequences follow, and they should be taken deliberately rather than
discovered in January:

- If any market is to be **removed** — `points` being the candidate, on §1 —
  removing it is also a change to the market list. It is cheaper to decide that
  now, before the first card, than to face it against live results.
- Recommendation 1 below (a per-outcome staking cap) touches **the staking
  rule**, which is frozen by the same sentence. It should be settled before
  2026-09-29 or not at all.

---

## 4. Operationally, what the first cards will do

Traced end-to-end through `run_gameday_card.py`, `gameday_card.py`,
`card_pricing.py` and `gameday-refresh.yml`.

### Every gate is open except one

`goalie_saves` is the only hard-gated market (`HARD_GATED_MARKETS`,
`gameday_card.py:106-114`). `assess_markets` is called with no `disabled=`
argument, so nothing else is turned off. **`points` will be staked**, at
0.25–0.5u ($6.25–$12.50 at `BANKROLL_UNIT_DOLLARS = 25.0`), whenever it clears
its edge bar.

### Alternate ladders stake the same player three times

`selection_key` includes `line`, and the alternate ladders map to the same
project market. So `points` over 0.5, over 1.5 and over 2.5 **on one player**
are three independent staked selections on one outcome.

There is **no bankroll cap, no per-slate cap, no per-game cap, no per-player
cap, and no correlation control** anywhere on the staking path.
`ladder_coherence.py` is a measurement run by `line-movement.yml`, not a gate —
it cannot reach the card. The only collapse implemented is anytime-scorer →
`goals` over 0.5, in `odds_api.normalize_event`.

This is the finding with the largest practical consequence, and it compounds
with §1: the market most likely to stack this way is a prop, and the prop
measured as a replicated loss is `points`.

### Tier C is dead code

A candidate reaches the staking section only when `edge >= best_bar`, and
`_tier_for` returns "C" only when `edge < best_bar`. Every staked bet is
therefore 0.5u or 0.25u. `TIER_UNITS["C"] = 0.1` and its `.get(..., 0.1)`
fallback are unreachable.

### The hard-gated market is still bought, and still enters the ledger

`player_total_saves` and `player_total_saves_alternate` remain in
`PER_EVENT_PROVIDER_MARKETS` — 4 of the 38 credits per event, costing exactly
one extra game of per-event coverage on every credit-clipped night, for a
market the card can never stake.

Worse, `write_snapshot` runs on the **unfiltered** price frame *before*
`build_card` strips the market. So the forward ledger will accumulate
`goalie_saves` rows for a market that can never produce a selection, voiding
whenever the named goalie did not dress.

### Per-event coverage breaks in October, not on opening night

`gameday-refresh.yml` passes no `--max-events` at a `--credit-cap 320`. At 38
credits per event that funds 8 events. Opening night is five games, so this
does not bite on 09-29 or 09-30. The workflow states its own measured cost:

> that clips 72 of the 185 nights and leaves 254 games unpriced … 608 is the
> smallest cap that clips no night (16 games × 38).

On a clipped night the card carries **only** `moneyline`, `puck_line` and
`total_goals` — measured at −6.6% / 954, −4.2% / 1,117 and −4.0% / 1,216, every
interval including zero.

### Opening-night rosters

No rosters are cached, so each player's side comes from his last cached game —
last season's club for everyone who moved. Those props produce **no opinion at
all**, which is correct behaviour and not a pass.

---

## What this document recommends, and what it does not

It does **not** recommend withdrawing the approval. That is Cooper's decision,
the reasoning behind it is recorded, and a forward record is a legitimate thing
to want.

It recommends three things be settled before 2026-09-29, because each is
cheaper to fix now than to explain afterwards:

1. **A per-player or per-outcome cap on the staking path**, so one player's
   `points` ladder cannot become three correlated stakes. This is the one item
   here that changes exposure rather than tidiness.
2. **Either drop the two saves keys from the per-event buy, or ungate the
   market.** Paying for a market that cannot be staked, and freezing its
   opinions into the ledger, is the worst of both.
3. **Raise `--credit-cap` to 608, or pass `--max-events`,** so October nights
   do not silently collapse the card to the three team markets.

And it records, without recommending either way, that the receipt directory's
README and the receipts inside it say different things.
