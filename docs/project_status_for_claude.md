# Project status

Read this second, after `CLAUDE.md`. It is the shortest honest answer to
"where is this and what should I do next".

## Where the lab is

**Built and working:**

- Data layer. Three full seasons cached from the NHL API — 3,936 games,
  157,419 player-game rows. A completed boxscore is never refetched, so a
  rebuild is reproducible offline.
- Player props models for all six priced markets, with dispersion measured
  rather than assumed and goalie saves modelled through shots against.
- A team model for moneyline, puck line and totals, with overtime handled
  explicitly — a -1.5 cover is computed on regulation scorelines only,
  because an overtime winner takes the game by exactly one.
- Walk-forward calibration, including an ice-time-conditional correction that
  straightens every volume bucket. See
  `docs/why_ice_time_gets_its_own_correction.md`.
- The provider adapter, shadow-only. The card cannot read what it writes.
- A fail-closed provider policy that ships allowlisting nothing, and a PR gate
  that checks approval paperwork is real and current.
- The gated card, with the puck-drop guard.
- The `Gameday Refresh` workflow and the pinned operating-home issue.

**Not built, deliberately:**

- No historical prop prices have been bought, so **no market has been measured
  against a real price**. That is the single biggest gap and it is a spending
  decision, not a technical one: ten credits per market per event, 720 for one
  twelve-game night across six markets.
- No confirmed-starter source, so goalie saves cannot reach the card. See
  `docs/goalie_props_need_a_confirmed_starter.md`.
- No xG source. MoneyPuck's CSVs need a data licence; see
  `docs/nhl_data_sources.md`.

## What the card does today

Nothing, correctly. The policy allowlists no market, so the card produces no
selection, no lean, no pass and no stake, and lists every market with its
reason. An empty card that explains itself is useful; a card with invented
content is worse than no card.

## The two things only Cooper can do

1. **Allowlist a market.** That takes measurement against real prices and a
   signed human acceptance receipt. Claude prepares all six steps in
   `docs/provider_allowlist_approval.md` and stops at the sixth.
2. **Authorise credit spend** beyond a small measurement budget.

## What to do next, in order

1. Set the `NHL_ODDS_API_KEY` repository secret so `Gameday Refresh` can fetch
   prices. Until then it fails loudly at the credential check, by design.
2. Run one retention probe (`scripts/buy_historical_props.py --probe --live
   --credit-cap 60`) to find out which prop markets the provider actually
   retains historically. Sixty credits, and it turns "unknown" into a measured
   fact in `data/outputs/player_props_backtest.md`.
3. Buy a stratified sample of game-days for the markets that are retained, and
   let the backtest decide whether anything is worth allowlisting.
4. Read `data/outputs/what_we_can_claim.md` before believing any of it.

## The honest summary

Nothing in this repository has a demonstrated edge, because nothing has been
measured against real prices yet. Everything above is machinery for finding
out — carefully, with the sample sizes printed — not evidence that there is
anything to find.
