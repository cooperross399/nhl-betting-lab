# CLAUDE.md — NHL Betting Lab Operating Instructions

This repository is the source of truth for the NHL Betting Lab. Claude operates
it directly. Where anything else in the repo conflicts with this file, this file
wins.

**Active repo path: `/Users/cooperross/Projects/nhl-betting-lab`.**

The lab is modelled on `epl-betting-lab`, deliberately: the gates, the provider
staging discipline, and the honesty rules are carried over because they were
earned there. The centre of gravity is different. In the EPL lab player props
were the best-built and most honestly measured part of the pipeline but were
never enabled; **here props are the primary product**, and team markets exist so
that an edge anywhere can be found.

## Read these first

**The card is produced by GitHub Actions, not by anything on Cooper's machine.**
`.github/workflows/gameday-refresh.yml` — workflow name **`Gameday Refresh`** —
runs daily through the season: fetch results, fetch prices, rebuild every
report, render the card. It needs no laptop and no terminal. Read it at
Actions → Gameday Refresh → latest run. Never tell Cooper to open a terminal to
get a card.

Every session, in this order. These replace chat history as project memory.

1. `CLAUDE.md` (this file) — hard rules, which override everything.
2. `docs/what_we_can_and_cannot_claim.md` — what the evidence actually
   supports. Read before making any claim about whether this works.
3. `docs/nhl_data_sources.md` — where every number comes from and what each
   source cannot tell us.
4. `docs/provider_allowlist_approval.md` — how a market becomes trusted, and
   why Claude can never do it alone.
5. `docs/puck_drop_guard.md` — why a started game can never appear as a play.
6. `README.md` — full command reference.
7. Latest `data/outputs/` reports, then GitHub PRs, Actions runs, and the
   pinned **"NHL Betting Lab — Claude Operating Home"** issue.

## Current operating state

Every number below is measured, walk-forward, and carries its sample size.
Re-derive rather than trust if the data has moved.

- **The full two-season population is bought, and the model loses on it.**
  2,710 events, 1,261,440 price rows, **73,918 bets**: **−1.6%, 95% interval
  −2.3% to −0.8%**, which excludes zero on the *negative* side and survives
  correcting for the seven markets tested (−2.5% to −0.6%). The earlier
  +1.4% came from a 192-event sample thirty times smaller; it was noise, and
  it is on the record as noise.
  Per market: `points` −5.2% (16,421), `goalie_saves` −4.7% (5,335),
  `shots_on_goal` −0.5% (38,037, spans zero), `assists` −1.6% (6,810, spans
  zero), `goals` −8.4% (576, spans zero). `blocked_shots` is the only
  positive at +4.7% over 6,739 — and it **failed replication**: same
  direction on the unseen window (+4.5% over 2,950) but its own interval
  includes zero, and a window that merely fails to contradict is not
  confirmation. The only result that survives correction *and* replicates is
  `points` at **−6.6% over 9,047** — a demonstrated deficit, not an edge.
- **A duplicated store does not look wrong, it looks significant.** The
  purchase deduplicated on the whole row, timestamps included, so two buys of
  the same window wrote every quote twice under two snapshot labels. ROI is
  unchanged by exact duplication and the interval narrows by root two — the
  first clean run reported 144,060 bets and an interval half again too tight.
  `stores.dedupe_prices` keys on the quote (event, market, player, selection,
  line, book) and never on when it was fetched.
- **`what_we_can_claim` announced a replicated loss as good news.** Its
  headline predicate tested measured + survives-correction + replicated and
  never read the sign, so `points` at −6.6% triggered "at least one survived
  the correction and then replicated". The one document whose job is to stop
  a number being misread must not be the thing misreading it; it now
  separates a demonstrated edge from a demonstrated deficit and names the
  deficit.
- **Team markets show no edge either.** Under the shipped policy: moneyline
  −2.4% over 1,504 bets, puck line −4.3% over 1,541, totals −0.5% over 1,150
  — every interval includes zero after the family correction. Match rate
  against the bought prices is 96% per market (was 66% on totals before the
  sample grid covered the whole-number lines the books actually hang); the
  remaining 4% are warm-up-window games, counted as exactly that. Whole-number
  spreads and totals push on exact margins, the ±1 push includes the entire
  overtime mass, and both the model and settlement price it.
- **What ships is what the recorded verdicts say, through one door.**
  `verdicts.ships()` reads each experiment's `ships` list;
  the card and the default sample generators consult it rather than asserting
  policy in code. In force now: the **team back-to-back adjustment**
  (+19.4u on the corrected joins, must-not-lose, not an edge) and the **props
  back-to-back adjustment** (+11.4u, same bar — own-side scoring −6%,
  opponent-side +5%, both-tired cancelling, the tired team's goalie busier,
  across seven independent settlement columns). Not in force: **every
  calibration correction** — the pooled Platt improved calibration and lost
  −97.0u; the by-TOI correction won +162.8u bucketed on *actual* ice time and
  loses −37.6u on *expected* ice time, the only TOI a card can know. The
  standard for any conditioned quantity: **conditioned on what, known when?**
  `docs/why_the_toi_correction_does_not_ship.md`.
- **The third game in four nights was checked and not built.** One suggestive
  cell (−7.4 over 232) with a contradicting mirror (−2.3 where fatigue
  predicts positive) is what noise looks like.
  `docs/schedule_states_checked.md` holds that record — in `docs/`, because
  its first draft was appended to a regenerated output and lasted one re-run.
- **The join-vocabulary bug family is at five members, all fixed and all
  tested by reproduction**: provider team names vs abbreviations, UTC dates
  vs league game dates (69% of all bought prices silently discarded), `home
  −1.5` vs `home_minus`, `h2h_3_way` outcomes staged as team names, and a
  CSV round-trip turning empty players into the truthy string `"nan"` on one
  side of a hand-built key. One `selection_key` function now builds every
  join key on every side, the fixtures use it too, and `season.clean_text` /
  `row_game_date` are the only readers of CSV-borne text and dates.
- **The backtest joins players by identity, not by string.** Every alias of
  a name (including initials collapsed: "J.T." meets "JT"), disambiguated by
  the teams in the priced game; a lone candidate on the wrong team is a void,
  not a match; a parenthesised birth year — the provider's own disambiguator
  for the two Elias Petterssons — never aliases to the bare name. The two
  Sebastian Ahos settle against their own games on all 123 nights both
  dressed.
- **The earlier headline numbers were data defects, and stay on the record as
  such**: +18.1% shots_on_goal came from the UTC join discarding seven prices
  in ten (survivors were matinees); the goalie-saves "miscalibration" was
  relief appearances nobody can bet; the fixed line grid threw away a third
  of the bought totals. Each fix is tested by reproducing the defect.
- **92% of prop bets lean Under, and the claimed edge shrinks on
  realisation** — books hang the vigged, publicly-shaded side on the Over, and
  bets are selected exactly where estimation error concentrates. Diagnosis,
  not finding; stated in the backtest report.
- **The forward-evidence organ exists and runs in Gameday Refresh.** After
  the card prices a slate, every opinion is frozen into a dated snapshot —
  the first opinion of the day stands, never repriced — and once a day's
  games are all final it settles as a unit into
  `data/processed/forward_evidence.csv`, by the same identity join and
  settlement rules as the historical backtest. Voids return the stake;
  a game with no result inside fourteen days is counted unsettleable, never
  guessed. `data/outputs/forward_evidence.md` restates what the ledger
  supports, in the house vocabulary. This is the only possible price
  evidence for hits and the regulation three-way, and the accumulating
  out-of-sample test for every market and every shipped policy at once.
- **Hits and the regulation three-way accumulate evidence forward.** Hits is
  served live and retained by no book historically (256 events probed, 2,600
  credits). The three-way is per-event only — and was wired end to end
  without ever being *requested* until the dead-code test caught it; every
  declared market must now appear in a fetch list.
- **The price CSVs are derived data**; every bought response is cached raw
  and the CSVs rebuild from the cache. `build_datasets` refuses to shrink an
  accumulated table by more than half (each file guarded on its own, rows not
  existence, `--allow-shrink` as the deliberate override).
- **Caches are checked before reuse, four ways**: renamed market, added
  market, schema change, and a widened line grid — the last because the CI
  state artifact restores the previous run's samples forever, which would
  have reproduced the biased totals measurement indefinitely.
- **The measured historical rate is ten credits per market returned per
  event.** Quota: **88,527 of 100,000 remaining** as of 2026-08-26.
- **A player's side comes from the roster, not from his last game.** The
  models learn rates from game logs and that is right — shooting travels with
  the player — but the logs also carry the club he last played for, which in
  October is the club he left. Measured on the real 2026-27 rosters against
  the fitted model: **166 of 815 priced players (20.4%) had changed clubs**,
  and each one matched neither side of tonight's game, so each produced no
  opinion at all. A fifth of the pool missing from opening night, looking
  exactly like books not posting props. `current_rosters()` decides the side
  now; the logs are the fallback, and a roster naming a club not in the game
  fails the same safe way a stale log does.
- **The season fits the quota, measured against the real schedule.** 185
  game days, 1,344 games, 2026-09-29 to 2027-04-10; a mean of 7.3 games a
  night and a maximum of 16. At 19 asked per-event markets that is **26,091
  credits for one fetch a day** and 52,182 for two, against 88,527 remaining.
  The 320-credit daily cap clips **zero** of the 185 nights (16 games x 19 =
  304). The second scheduled trigger now stands down when the first already
  published a clean card to `card-feed`, so the ordinary season costs the
  one-run figure and the backup still fires whenever the primary did not
  finish or finished degraded.
- **Gameday Refresh runs green end to end** (verified 2026-08-26: live team
  prices staged, models fitted, card correctly blocked, comment posted).
  Props return no rows this far from the season — an absence, not a fault.
  The alternate ladders and all per-event markets ride the per-event fetch;
  asking the bulk endpoint for them 422s the whole request.
- **No market is allowlisted. The 2026-08-27 approval was withdrawn on
  2026-08-29**, because the evidence it cited moved underneath it: the
  receipt was signed against +1.4% over 4,830 bets, and the full population
  says -1.6% over 73,918. The gate caught it on its own — the receipt's
  evidence checksums stopped matching — which is exactly what that check is
  for. Claude withdrew it, which is the only direction Claude may move that
  file, because withdrawal can only ever reduce what the card may do.
  **Re-enabling anything needs Cooper to read the current evidence and sign
  a new receipt**, and the superseded one is kept under
  `data/manual/human_acceptance_receipts/superseded/` as the record of a
  decision that was really made. The card therefore produces no selection,
  no lean, no pass and no stake, and says why. `goalie_saves` still cannot
  produce a selection even if allowlisted, for want of a confirmed-starter
  source (`docs/goalie_props_need_a_confirmed_starter.md`).
- **The season fits the quota, measured against the real schedule.** 185
  game days, 1,344 games, 2026-09-29 to 2027-04-10; a mean of 7.3 games a
  night and a maximum of 16. At 19 asked per-event markets that is **26,091
  credits for one fetch a day** and 52,182 for two, against 88,527 remaining.
  The 320-credit daily cap clips **zero** of the 185 nights (16 games x 19 =
  304). The second scheduled trigger now stands down when the first already
  published a clean card to `card-feed`, so the ordinary season costs the
  one-run figure and the backup still fires whenever the primary did not
  finish or finished degraded.
- **Gameday Refresh runs green end to end** (verified 2026-08-26: live team
  prices staged, models fitted, card correctly blocked, comment posted).
  Props return no rows this far from the season — an absence, not a fault.
  The alternate ladders and all per-event markets ride the per-event fetch;
  asking the bulk endpoint for them 422s the whole request.
- **All 11 markets are allowlisted, as of 2026-08-27.** Cooper approved
  everything by explicit instruction, against the evidence's enable-nothing
  recommendation — the receipt
  (`odds_api-20260827T165300-0400-cooperross399`) records both facts and its
  provenance verbatim, and he merged PR #47 himself. The evidence did not
  change: **no demonstrated edge** stands everywhere it stood. The card now
  prices every market and recommends only where the measured bars clear; a
  slate with no qualifying edge is a no-bet card, which remains correct
  behaviour and not a failure. `goalie_saves` still cannot produce a
  selection without a confirmed-starter source
  (`docs/goalie_props_need_a_confirmed_starter.md`).
- **The provider's whole NHL catalogue is either wired or recorded as
  deferred with its reason** (`docs/periphery_markets_decision.md`,
  2026-08-27): the six prop alternate ladders and the anytime scorer land on
  existing approved markets; `team_total` is new, priced off the scoreline
  matrix, settles from the boxscore, and stays card-excluded until a human
  receipt names it while its opinions accumulate forward. Period markets and
  first/last scorer are deferred — no period model, no goal-order data —
  not silently dropped. The per-event fetch is windowed to the day's slate
  (`--horizon-days 1`; an unwindowed 32-event August board starved the
  nearest nine games) and the cap is 320 against the pessimistic bound;
  an asked-for market nobody quotes costs nothing.
- **Data**: three seasons cached — 3,936 games, 157,419 player-game rows,
  121 unresolved names (0.08%). A completed boxscore is never refetched.
- **Calibration** (can rule out, never in): 2.5M walk-forward prop samples,
  every skater market bent by ice time
  (`docs/why_ice_time_gets_its_own_correction.md`); team model overconfident
  on favourites (its docstring's opposite prediction left on the record in
  `models/team_model.py`).

## Contract strings — never change these

Cooper's local scheduled tasks hard-code these. Renaming any of them silently
breaks his automation, and the breakage looks like the lab going quiet.

| Thing | Exact value |
|:------|:------------|
| Workflow name | `Gameday Refresh` |
| Workflow file | `.github/workflows/gameday-refresh.yml` |
| Operating home issue title | `NHL Betting Lab — Claude Operating Home` |
| Changed-selections marker | `Selections changed` (first paragraph of the comment) |
| Props backtest output | `data/outputs/player_props_backtest.md` |
| Props calibration output | `data/outputs/props_calibration.md` |
| Claims output | `data/outputs/what_we_can_claim.md` |

The issue title uses an em dash (—), not a hyphen. The marker phrase is matched
literally.

## Hard rules (never break these)

- **Never fabricate odds.** A missing price stays missing. An incomplete market
  is excluded, and **an excluded market is never described as a pass, an avoid,
  or a no-value call**. A blocked card produces no selections rather than
  placeholders.
- **Never place bets** or automate betting in any form. This repository
  produces recommendations and nothing else.
- **No market reaches the card without measurement against real prices plus a
  reviewed human approval.** Shadow runs, checklists, evidence bundles and PR
  gates are *evidence for* a human decision. None of them allowlists anything
  on its own.
- **Calibration is a precondition, not a goal.** It can rule a model out; it can
  never rule one in. Where historical prices exist, a price-based backtest
  decides. A change that improves calibration but loses the backtest does not
  ship. (This is not theoretical: in the EPL lab a change that improved
  calibration on every market cost about 140 units in the backtest.)
- **State the sample size next to every measured number.** An interval that
  includes zero means **"no demonstrated edge"**, and the docs say so in those
  words.
- **Before concluding a prop line "isn't offered", check per-bookmaker coverage
  including alternate lines.** In the EPL lab `total_2_5` was wrongly excluded
  for exactly this mistake: the complete line was absent from the bulk `totals`
  market and present all along in `alternate_totals`. Use
  `scripts/run_provider_market_discovery.py --line-coverage` before writing off
  a market.
- **Never print, write, compare, or commit an API key.** `tests/test_no_secrets_committed.py`
  enforces this; do not weaken it. The production credential is the GitHub
  secret `NHL_ODDS_API_KEY`; `.env` is local-only.
- **Never weaken a gate**, and never sign a human acceptance receipt on
  Cooper's behalf.
- **Never merge with failing CI**, and never force-push.
- **Never enable cron** for anything that spends API credits beyond the
  reviewed Gameday Refresh budget, and never run a live provider fetch outside
  that budget without asking.
- **Never edit protected manual files** unless the requested workflow
  explicitly allows it:
  - `data/manual/staging_provider_policy.json`
  - `data/manual/human_acceptance_receipts/*`

## The puck-drop guard

Built in from day one, because the EPL lab had to retrofit it after a card
carried a fixture that had already kicked off.

Every selection is checked against the provider's `commence_time`. A selection
whose game has **started**, or whose start **cannot be confirmed**, is moved
into an **"Already started — no longer plays"** section and its stake is removed
with it. Ambiguity falls on the not-a-play side, always. A missing or
unparseable commence time is not a reason to let a pick through; it is a reason
to pull it.

## Model and betting discipline

- Props are the priority: shots on goal, points, goals (including anytime
  scorer), assists, goalie saves, blocked shots, hits.
- Team markets — moneyline, puck line, totals, and the regulation three-way —
  are priced and modelled so an edge anywhere can be found, but they are not
  the point of the lab.
- Prop edges must clear a **higher** bar than team edges, never a lower one. The
  card is built hours before the lineup, the scratches, and the confirmed
  starting goalie are known, and books reprice on all three. That is a
  structural information deficit on every prop.
- Avoid heavy juice, roughly worse than `-160`. Prefer plus-money props and
  alternate lines over forcing a heavy price.
- Never present a model edge as a guaranteed winner. Separate best bets, leans,
  and passes/avoids.
- Do not change model logic because one slate lost. Require backtest evidence.

## Main commands

```bash
# One-time local setup
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt && .venv/bin/python -m pip install -e .

# Data
PYTHONPATH=src .venv/bin/python scripts/fetch_nhl_data.py
PYTHONPATH=src .venv/bin/python scripts/build_datasets.py

# Measurement
PYTHONPATH=src .venv/bin/python scripts/run_props_calibration.py
PYTHONPATH=src .venv/bin/python scripts/run_player_props_backtest.py
PYTHONPATH=src .venv/bin/python scripts/run_what_we_can_claim.py

# Card (gated; produces nothing unless every gate passes)
PYTHONPATH=src .venv/bin/python scripts/run_gameday_card.py

# Tests
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m compileall -q src scripts
```

## Provider automation

Provider automation is **not trusted** unless the provider policy
(`data/manual/staging_provider_policy.json`), the acceptance checklist, and the
human acceptance receipt say it is. The shipped policy allowlists
`the_odds_api` for the 11 measured markets under receipt
`odds_api-20260827T165300-0400-cooperross399`; the PR gate re-verifies that
paperwork — receipt, coverage, evidence checksums — on every policy change.
Shadow runs still write to `data/staging/`, and eligibility still gates what
the card may read from there.

## What Claude decides, and what Cooper decides

Claude works autonomously on: data, models, measurement, reports, tests,
workflows, docs, and opening PRs with green CI.

Claude stops and asks for: **provider/market allowlisting approvals**, and
**anything spending API credits beyond a small measurement budget**. Those two
are Cooper's alone.
