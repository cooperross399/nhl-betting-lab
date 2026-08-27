# Project status

Read this second, after `CLAUDE.md`. It is the shortest honest answer to
"where is this and what should I do next".

## Where the lab is

**Built and working:**

- Data layer. Three full seasons cached from the NHL API — 3,936 games,
  157,419 player-game rows. A completed boxscore is never refetched, so a
  rebuild is reproducible offline.
- Player props models for all seven prop markets (hits included), with
  dispersion measured rather than assumed and goalie saves modelled through
  shots against.
- A team model for moneyline, puck line and totals, with overtime handled
  explicitly — a -1.5 cover is computed on regulation scorelines only,
  because an overtime winner takes the game by exactly one.
- Walk-forward calibration of both models — 2.5 million prop samples and the
  full team-market grid — including an ice-time-conditional correction that
  straightens every volume bucket. See
  `docs/why_ice_time_gets_its_own_correction.md`. No calibration correction
  is in force on the card (each lost the price backtest in the only form a
  card could apply it); the two back-to-back rest adjustments are, because
  they won it. `verdicts.ships()` is the one door those decisions go through.
- The provider adapter, shadow-only. The card cannot read what it writes.
- A fail-closed provider policy and a PR gate that checks approval paperwork
  is real and current. Since 2026-08-27 the policy allowlists `the_odds_api`
  for all 11 measured markets, under receipt
  `odds_api-20260827T165300-0400-cooperross399` (PR #47, merged by Cooper).
- The gated card, with the puck-drop guard.
- The `Gameday Refresh` workflow and the pinned operating-home issue.

**Not built, deliberately:**

- Historical prices are bought and measured: 192 event-days of props (4,830
  bets under the shipped bars) and two seasons of team markets. The verdict —
  **no demonstrated edge anywhere** — is in
  `data/outputs/player_props_backtest.md` and
  `data/outputs/team_markets_measurement.md` with every sample size printed.
  Hits and the regulation three-way are retained by no book historically and
  accumulate forward evidence only.
- No confirmed-starter source, so goalie saves cannot reach the card. See
  `docs/goalie_props_need_a_confirmed_starter.md`.
- No xG source. MoneyPuck's CSVs need a data licence; see
  `docs/nhl_data_sources.md`.

## What the card does today

Prices every allowlisted market on the slate and recommends only where the
measured bars clear — minimum edge, juice no worse than −160, a confirmed
start time. A slate with no qualifying edge is a no-bet card that explains
itself, which is the expected outcome given the measurements. Every priced
opinion freezes into the forward ledger and settles against the boxscore;
goalie saves still cannot produce a selection without a confirmed starter.

## The two things only Cooper can do

1. **Allowlist a market.** That takes measurement against real prices and a
   signed human acceptance receipt. Claude prepares all six steps in
   `docs/provider_allowlist_approval.md` and stops at the sixth.
2. **Authorise credit spend** beyond a small measurement budget.

## What to do next, in order

1. Let `Gameday Refresh` run daily (its schedule covers Sept 29-30 and then
   Oct-Apr) and let the forward ledger accumulate. It is the only genuinely
   out-of-sample evidence stream, and the only one hits and the regulation
   three-way will ever have.
2. Watch for books posting player-prop lines in late September; until then
   the card carries team markets only, and that absence is the provider's,
   not a fault.
3. When the forward sample is large enough to say something, let
   `data/outputs/forward_evidence.md` say it — with intervals, and with an
   interval including zero read as "no demonstrated edge".
4. Read `data/outputs/what_we_can_claim.md` before believing any number.

## The honest summary

Everything measured shows no demonstrated edge, on samples large enough to
mean it. The card runs live anyway — Cooper's explicit, receipted decision,
made against that evidence — so the forward ledger can test the models where
no historical price exists. Machinery for finding out, now running in
production; still not evidence that there is anything to find.
