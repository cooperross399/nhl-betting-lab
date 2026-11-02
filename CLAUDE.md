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

- **Book access is worth +0.68 points and saturates by five books.** ROI at
  the shipped bar as reachable books grow: 1 → −1.02%, 2 → −0.81%, 3 →
  −0.59%, 5 → −0.40%, 8 → −0.34%; the last three books add 0.06 between them.
  No single book is positive alone (best Bovada −0.67%, worst Caesars
  −3.68%). **Opening more accounts cannot close the gap.**
- **The −0.34% headline assumes perfect shopping, which is the most
  favourable assumption available.** It takes the best of eight books on
  every wager, while real prop limits are small, books restrict winners, and
  the best price is disproportionately the stale one about to move. The
  honest bracket is **−1.6% (every quote, average price) to −0.34% (perfect
  shopping)**, and a real result sits nearer the middle. Quoting −0.34% as
  *the* number overstates what is reachable exactly as −1.6% understated it.
- **The card's hour costs nothing, measured. The mismatch was a
  documentation problem, not a performance one.** The same 2,555–2,887
  wagers, same outcomes, priced at both moments: **T−4.0h +4.41% [+0.47%,
  +8.35%]** against **T−9.5h +4.18% [+0.45%, +7.90%]** — the card's window is
  worth **−0.23 points**, inside noise. Compared on the wagers present in
  BOTH buys, because the 4h purchase predates the alternate ladders and a raw
  comparison would confound *when* with *what*. So the published numbers do
  transfer to production, and the last measured lever with an unknown answer
  is closed.
- **Those overlap figures are +4% and are NOT a finding.** The overlap is
  featured lines only. Splitting the full card window into featured and
  alternate rungs gives featured +1.50% [−0.50%, +3.49%] over 9,570 and
  alternate −2.45% over **270** — too few to say anything either way. Three
  slices of one dataset read +4.41%, +1.50% and −0.34%; the full population
  is −0.34% and the rest is what subsetting does. Recorded so nobody quotes
  the +4.4%.
- **A credit cap that could not hold, and now does.** The purchase estimates
  cost from the market keys asked for, but the provider bills per market
  *returned* and every alternate ladder bills on its own. A run capped at
  200,000 spent **289,984** — 107 credits an event against a predicted 70 —
  while the code and its test both asserted the cap "cannot be breached".
  The estimate stays at the documented 10x, because a guess dressed as a
  bound is worse than a guess; the cap is now enforced against the
  **measured running total** read from `x-requests-last`, which is far harder
  to mis-specify than an estimate, though not impossible (below). The test
  that asserted the false promise was replaced rather than satisfied.
  **2026-09-26 (#234): that measured gate could still overshoot by one
  event.** It asked whether spend had already *reached* the cap
  (`credits_spent >= cap`), not whether the next event would pass it (stub:
  107 charged against 70 estimated, cap 200, spent 214 with no error). It now
  projects one event ahead at the dearest charge seen, seeded with the
  estimate, as the team buy and the retention probe do, and a refusal is a
  counted budget skip rather than a stop. The bound is the rise in the
  charge: a run can pass the cap by at most how much the next charge exceeds
  the dearest seen, and not at all while charges do not rise. Any overspend
  is named in the buy's errors and fails `buy_historical_props.py` with
  exit 2.
- **The lab measured one thing and shipped another, by five and a half hours;
  it now holds both.** The first purchase bought every historical price at a
  median **4.0 hours** before face-off (p10 4.0, p90 4.0), while the
  production card runs **9.5 hours** before a 19:00 ET face-off, its backup
  8.0 — so every number here described a window the card does not operate in.
  It is the stale-minutes finding in structural form: at four hours the lineup
  is largely known, at nine and a half it is guessed. The second purchase
  bought the card's own window, and both are on disk and separately measured.
  Being bought and measured, not argued about.
- **A store holding two windows now refuses to be measured as one.**
  `stores.label_phases` derives hours-before-face-off from the snapshot, the
  backtest auto-detects the window and **raises** if the store holds more
  than one, and every report states the window it describes. Without it the
  best-price collapse would take the better of a four-hour and a nine-hour
  quote for one wager — a price nobody could have taken. The first version of
  this guard hardcoded a window that matched nothing and fell through
  silently, measuring the mixture it was written to prevent; it now
  auto-detects.
- **That guard then told the operator to do something the CLI could not do.**
  It raises "name the window explicitly" — and `run_player_props_backtest.py`
  had no `--phase` flag, so the only way to obey was to edit the source. This
  went unnoticed while the store held one window and fired the moment the
  line-movement capture added a second, which is the worst possible timing: an
  error instructing an impossible action reads as operator error and sends the
  reader hunting their own mistake. The flag exists now, and a test asserts the
  message names a flag the runner actually accepts.
- **And naming a window the store did not have measured every window at
  once.** The phase filter was applied only `if not kept.empty`, so
  `--phase card` against a store holding nothing but four-hour prices left the
  whole frame in scope and reported it under no label — the same silent
  fall-through the auto-detect was written to remove, still live on the path
  where a window is named. It had never fired because nothing named a window;
  both workflows now do, on every run. A named window that matches nothing
  measures nothing and says so. The three instalments of this guard —
  hardcoded and matching nothing, an error naming a flag that did not exist,
  and a named window falling through — are one lesson: **a filter that does
  nothing when it matches nothing is not a filter.**
- **The second window then overwrote the first, and 89.5% of the measured
  population was deleted without a word.** `PRICE_IDENTITY` carries no
  timestamp — correctly, because two labels of one moment are one quote — so
  when the 9.5-hour purchase was appended to a store already holding the same
  2,710 events at 4.0 hours, every card-window quote landed on the identity of
  the four-hour quote it matched and `keep="last"` gave the collision to the
  newcomer. **1,126,739 of the 1,259,312 four-hour rows were destroyed**,
  leaving 132,573 — only the quotes whose line or book happened not to recur.
  Nothing raised, the store still held 2,675,428 rows, and
  `player_props_backtest.md` went on reporting "−0.3% over 25,947 bets, 4.0
  hours before face-off" against a store that could produce 8,007. Replaying
  the append on the real files reproduces the store on disk **to the row**
  (2,675,428) under the old key and keeps 3,802,164 under the new one. The key
  is now the quote **plus the window** `label_phases` derives, which is the
  granularity every measurement here already slices on; under-collapsing
  across windows costs a window. (This said over-collapsing inside a window
  "costs nothing the backtest can see". That was wrong: the alternate ladders
  and the anytime scorer fold onto the featured market, line and selection,
  so one book at one instant can quote one identity twice, and keeping the
  last row discarded a takeable better price. Fixed 2026-09-28, below.)
- **It was recoverable, because the raw cache is the evidence and the CSV is
  not.** Every response was still in `data/raw/historical_props` — 5,688
  event-odds files, 2,723 events, both windows — so `rebuild_price_files.py`
  reconstructed the store: **3,804,233 rows**, and the rebuilt four-hour
  window is identical on the quote identity to the store the purchase run
  uploaded minutes before the clobber (1,259,309 quotes, zero rows different
  in either direction). The local checkout held 516 of those 6,252 cached
  files and the rest were in the CI artifacts; both have been restored to
  disk. This is the second time the raw cache has turned a destroyed price
  file into a five-minute recovery.
- **`player_props_backtest.md` and `player_props_backtest_card.md` were built
  on the six-entry alias team map until 2026-09-24.** With no `team_names.csv` or boxscore cache beside the run, the
  backtest voided the non-Utah side of every Utah game: 902 bets in the
  `late` window, every one in a Utah game, and the committed report read
  25,009 bets at −0.2% where the full map gives 25,911 at −0.3%. Rebuilt with
  the full map, they are the figures below. No market's verdict moved in
  either window.
- **Both windows are now measured, and neither shows a demonstrated edge.**
  `late` (T−4.07h, 1,259,312 rows, 2,704 events, 8 books, 6 markets):
  **25,911 bets, −0.3%, 95% interval −1.5% to +1.0%**. `card` (T−9.57h,
  2,544,921 rows, 2,722 events, 14 books, 7 markets): **28,287 bets, −0.0%,
  95% interval −1.2% to +1.1%**. Both include zero. Per market in the card
  window: `points` −4.2% (6,140) and `blocked_shots` +7.9% (3,026) both still
  exclude zero and survive the family correction; `shots_on_goal` +1.5%
  (9,245), `assists` −1.0% (3,742), `hits` −1.3% (5,178), `goals` −2.8%
  (842), `goalie_saves` −5.5% (114) all span zero. In the late window
  `points` −4.4% (6,194) and `blocked_shots` +4.9% (4,286) survive; the rest
  span zero. **These two rows are not a window comparison.** The 9.5-hour buy
  asked a second region and got six more books, so its best-of-N is taken
  across fourteen rather than eight; it carries `hits`, which the four-hour
  buy has none of; and it holds almost no `goalie_saves` (114 bets against
  1,727), because at nine and a half hours the books have not yet posted them.
  The window question was already answered on the matched overlap — +4.41%
  against +4.18%, −0.23 points — and that comparison stands.
- **The canonical 25,947 very nearly reproduces, once the team map is
  right.** This bullet said it "does not reproduce from anything that still
  exists": the rebuilt four-hour window gave 25,009 bets, and 24,996 of the
  canonical 25,947 rebuilt exactly while 951 did not. Every one of those runs
  used the six-entry alias team map, which voided the non-Utah side of every
  Utah game. With the full map the raw cache rebuilds **25,911 bets, and
  25,895 of the canonical 25,947 reproduce exactly** — same book, same odds,
  model probability identical to the last bit — while 52 do not and 16 are
  new. The verdict is unchanged in every version: no demonstrated edge.
- **`dedupe_prices` deduplicated on whatever identity columns it was handed.**
  `PRICE_IDENTITY` includes `provider_event_id`; a frame read without it has
  nothing telling one date from another, so every night's quote on the same
  player-market-line-book collapsed onto one row. Asked to dedupe the real
  2,675,428-row store that way it returned **64,253** rows and reported
  success — silent 40x data loss inside the one function whose entire job is to
  be trusted. The live measurement path never hit it (`run_backtest` uses
  `best_price_per_wager` on a full key, and both buy scripts pass whole rows),
  so this was a trap rather than a live defect, and it was found by an analysis
  script walking into it. It now raises and names the missing column.
- **The −2.70% null was misdocumented, and the error flattered the model.**
  "Betting every wager it has an opinion on" meant every wager with a
  **positive** model edge — a population already **77.6% unders**, so the null
  already contained the model's direction. Betting literally every wager
  returns **−27.45% over 475,395**, wrecked by 153,320 longshot alternate-line
  overs at implied <0.10 returning −71.6%. The −2.70% reproduces exactly
  (−2.63%, n=99,931) under the correct reading. Quoting it as "the model
  recovers 87% of the vig" was wrong in the model's favour and that phrasing
  reached two external reviews before it was caught.
- **The honest decomposition, which is better for the model than the wrong
  one was.** Anchored on a direction-neutral baseline (bet both sides of every
  two-sided market, best price): −5.74% → blind unders −3.90% → the model's
  90.1/9.9 side mix −4.26% → the shipped card −0.29%. So **direction is worth
  +1.85 points, side mix is worth −0.37, and within-side selection is worth
  +3.97** — the three reconcile exactly. Selection carries all of the weight.
- **The model's selection is real and survives a placebo, which nothing else
  in this project has.** Its unders beat a size-matched random draw of unders
  it did not pick by +4.75 points, and **+3.34 points [+1.04%, +5.71%]** after
  matching on market × line × 5-point price bucket (107 cells, 99.9% of the
  card). Bonferroni-corrected for 7 markets: [+0.14%, +6.54%]. It reproduces
  in both seasons (+2.90, +4.05) — including 2025-26, where the over-shade
  disappears entirely (+0.0032, includes zero), which is the strongest
  available evidence that the selection is not the direction in disguise.
  **Not redundant is not profitable:** the card is still −0.29% over 25,947,
  95% [−1.76%, +1.19%], **no demonstrated edge**.
- **Above its own 6-point bar the edge ranks nothing.** ROI slope on claimed
  edge inside the unders +0.337 [−0.081, +0.734]; inside the overs −0.352
  [−1.357, +0.701]. Both include zero. Ranking the card's own bets by claimed
  edge does not beat ranking them at random (top-1000 permutation p=0.069).
  The 6% bar is a **gate that works and a ranking that does not** — do not
  size by edge, do not trim to a top decile, and do not read 6% as a measured
  optimum. Below the bar the edge does rank, within fixed price buckets
  (+6.61 points top vs bottom quintile), so the ranking is real and exhausted
  by the time the gate fires.
- **No threshold rescues the model, and not for the reason it looked like.**
  Realised over-edge regressed on model–market disagreement gives a slope of
  **0.18**, so a 6-point disagreement is worth ~1.1 points of true edge
  against a 2.70-point toll; clearing the toll needs ~15 points of
  disagreement, which **does occur** (3.0% of markets, n=6,474). But every
  threshold from 0% to 25% has an interval including zero, the sweep is
  **flat, not decreasing** (so there is no winner's curse — the curse is a
  uniform 24% haircut on claimed edge, not a reversal), and the swept optimum
  of 16% (+4.55%) sits at the 64th percentile of a permutation null
  (p=0.36) and collapses to **−0.00% held out**.
- **The model anticipates price movement, but negligibly.** Its disagreement
  with the card price predicts the direction of the move to the late window:
  +0.0112 logit per unit [+0.0095, +0.0127], **after** controlling for mean
  reversion, and 0 of 200 permutations that destroy only its player-level
  information reach that coefficient (z=58.8). But reversion is ~17× stronger,
  and the effect is worth about 0.06 probability points per standard
  deviation. Real, and not worth money on its own.
- **The over side is a measured drag.** The card's 2,572 overs return
  **−4.48%** [−8.92%, −0.10%] and cost 0.37 points. Dropping the over side is
  the one change the analysis actively supports — but it was not
  pre-registered, so it is now written down as a hypothesis with a forward
  test and a decision rule (`docs/pre_registered_over_side_drop.md`, 2026-09-02).
  **The card is not changed:** both sides keep being priced and frozen,
  because dropping the side now would destroy the only sample that could test
  it, and a rule that removes its own evidence can never be wrong.
- **A lineup feed cannot fix the stale-ice-time cell, and there is no
  detector specification to hold one to.** Sweeping an 11x11 sensitivity x
  specificity grid on the target a feed can see — a role change that persists
  past tonight — **all 121 cells span zero**, including the corner: a
  *perfect* detector leaves the card at **+0.26% [-1.45%, +1.86%]** over
  20,855 bets. The cell is three groups and a feed sees the wrong two: rises
  that persist −9.98% (n=2,662, visible), one-off big nights −7.22%
  (n=5,160, **invisible** — two thirds of the cell's 638 lost units sit here,
  and it is tonight's game variance, not deployment), and players whose role
  IS expanding but who were quiet tonight **+5.57%** (n=2,430) — whom a feed
  would tell you to abstain from. `docs/why_a_lineup_feed_cannot_fix_the_cell.md`.
- **The last open route is registered, not being tried.** Alternate-ladder
  staleness was recorded as "not yet" rather than "no", because
  `scripts/buy_historical_props.py` never bought the alternate ladders and
  the store therefore offers **83 comparable rung pairs in two seasons** —
  one violation, which is a sample, not a rate. The forward capture does
  request them, so the question becomes answerable for the first time this
  season. Registered 2026-09-22 with its tiers, placebo, cluster floor and a
  2026-12-01 feasibility checkpoint fixed in advance:
  `docs/pre_registered_ladder_coherence.md`. The detector
  (`src/nhl_betting_lab/ladder_coherence.py`) is deliberately unreachable
  from the card and from the forward ledger — the ledger is written *before*
  the eligibility gate, so anything reaching the probability map would
  contaminate the 2027-04-25 measurement.
  `tests/test_ladder_route_cannot_reach_the_ledger.py` holds that apart.
- **2026-09-25: the ladder depth checkpoint reads its registered unit, and
  can run.** Two detector defects, fixed and recorded here as the
  registration permits. `ladders_with_two_rungs` — the field the
  registration names for its 2,000 floor, and defines as ladders carrying two
  or more *de-viggable* rungs — counted two or more lines of either side, so
  the report and the Line Movement summary printed **284,544** for the
  bought store where the registered count is **57**, and **13,010** for the
  first seventeen game days of 2025-26 (core markets only, the shape a 422
  fallback leaves) where it is **0**: history cleared the floor 142 times
  over and the depth-zero alarm could never fire. It now counts rungs with a
  de-vigged price; the line count is kept as `ladders_with_two_lines`. And
  the scan grouped on `snapshot`, which forward captures do not carry — they
  stamp `captured_at` — so it raised on every capture and every run summary
  read "Ladder scan wrote no report"; the runner now takes `captured_at` as
  the moment. No threshold, band, floor or date moved, and no report from
  this scan had ever been published.
  `tests/test_ladder_depth_counts_deviggable_rungs.py`.
  **2026-09-26 (#240): a damaged day is named, not skipped.**
  `run_ladder_coherence.py` skipped a damaged line-movement day without a
  word, and the Line Movement step's `|| true` hid an undecodable byte. The
  scanner now names each unreadable day, in the report and in the JSON's
  `unreadable_captures`, and leaves it out of the depth. **The run is red
  only for the day it wrote.** The step passes `--fail-on-day` with the
  league day the capture appended to; damage in that file is an `::error::`
  and exits 2, which the step keeps under `continue-on-error` until a final
  gate after every upload (`steps.ladder.outcome == 'failure'`) turns the
  run red. A damaged *earlier* day is a standing `::warning::` and a summary
  line on every later run, and exits 0: the chain carries every day and
  each run restores the newest copy, so otherwise one bad October day would
  red every run of the season and bury the line-unit and scratch-list gates.
  Run by hand with no day named, any damage exits 2. No step repairs a
  damaged file in the chain. Since stage two (#298) the chain is branch
  `movement` of the private `cooperross399/nhl-closing-lines`, and earlier
  copies of a day are in that branch's history (no `line-movement` artifact
  is uploaded any more). `private_movement_chain.py push` cannot replace a
  damaged tip copy: it keeps the repaired file beside it as an `unmerged/`
  sidecar and exits 2 (see "Merging a sidecar"). Whether to add a repair
  procedure is still Cooper's call.
- **The oracle ceiling was an outcome filter, not a line-label result.**
  Abstaining above a 2-minute realised rise gives +3.11% [+1.39%, +4.80%] and
  a random-removal placebo reaches only −0.30% (z=8.3), so the cell is
  genuinely special — but realised ice time correlates with tonight's settled
  stat (+0.175 shots, +0.163 blocks), so "abstain when minutes were high" is
  substantially "abstain when the under was going to lose". A **one-bit
  placebo** carrying only the SIGN of the ice-time move — no band, no rank,
  no minutes — reproduces it (+3.05% vs +3.12%, difference +0.07
  [-1.04, +1.31]), and league-wide quantile bins with no line structure
  **beat** it by 1.77 points. It also fails replication: +5.23% in 2024-25,
  +0.76% [-1.76%, +3.17%] in 2025-26.
- **The feasible role-to-minutes translator is worth nothing, and is built
  anyway.** `models/role_minutes.py` maps a line label to a predictive
  distribution over minutes, walk-forward, wired into nothing. Re-pricing the
  card with the best label inferable from a player's own history returns
  **−0.02 points [-0.84, +0.81]** — any label derived from a player's history
  is a coarsening of that history. It scores AUC 0.568 at seeing the rise
  against 0.560 for a plain trailing read (a perfect label scores 0.839), and
  **47.5% of >2-minute rises involve no band change at all**. Trailing-10
  beats it at predicting minutes outright, MAE 1.984 vs 2.551.
- **Collection continues regardless, as a cheap option and not a thesis.**
  Every number above uses realised ice-time RANK as a stand-in for a line
  label, because no real label exists for these two seasons. A posted line
  states intent before the game and carries no same-game leakage, which is a
  reason to keep the option open and not a reason to expect it to pay. The
  forward test is pre-registered with its decision rule.
- **The promotion half of the deployment signal is now collected.**
  `capture_deployment.py` records who is OUT; `capture_line_combinations.py`
  records who moved UP — first line, top power-play unit — which is the
  "usage about to rise" event that costs −6.44% over 5,661 bets. Both run in
  the Line Movement job beside the price capture, so all three share an
  instant. Rehearsed 2026-09-02: 32 teams, 1,236 role rows, 655 players.
  **Every row carries two timestamps and they are not interchangeable:**
  `source_updated_at` is the source's claim about freshness, `retrieved_at` is
  when this lab held the value, and `line_combinations.usable_before` gates on
  the second and never the first. Gating on the source's own stamp would let a
  page fetched tonight count as available this afternoon, which would
  manufacture a deployment edge out of information nobody had. It cannot be
  collected retroactively — the source keeps no archive.
- **The store holds no line-movement capture yet, only two fixed windows**
  (card ~9.5h, late ~4.07h; median gap 5.50h with an IQR of exactly
  5.50–5.50h). The shipped bets were struck at the **later** of the two, so
  beat-the-close is undefined rather than negative, and any event study of
  price reaction is a forward exercise from 2026-09-29 onward.
- **The loss is stale ice time, measured to four times the size of the loss
  itself.** Split the card by whether a player's near-future usage rises or
  falls against the model's trailing-ten estimate: usage about to fall
  +5.82%/+3.22%, stable −0.13%, **usage about to rise by >2 minutes −6.44%
  over 5,661 bets, −364.6u** — 98% of them unders, against a card that loses
  89.6u in total. Substituting next-three-game mean TOI takes the card to
  **+4.63%**, and realised TOI to +5.16%; both are **oracles** that use
  information from after the card is built and are quoted as an upper bound,
  never as an achievable figure. Every prior-only reshuffle of box-score
  history lands between −0.30% and +0.02%, and a box-score proxy for the
  coming shift has R²=0.080 — **the information is not in the box score**.
- **The venue route is closed, measured rather than assumed.** The model
  recovers ~87% of the toll it pays and stops 0.29 points short, so a venue
  charging less would close the gap with no model change. Priced on one event
  where every venue is comparable at the same instant (130 credits, run
  33629672530): **Pinnacle charges 7.18% on NHL props against DraftKings'
  6.31%** — 1.08 points *dearer* than the toll already paid, pricing like
  BetMGM. Its reduced juice is a main-markets fact (3.00% moneyline vs a 4.47%
  field) that does not reach props. And **no exchange lists NHL props at all**:
  Novig, ProphetX, Betfair, Matchbook and Smarkets returned the moneyline and
  nothing else, the prop calls billing zero. Already visible in owned data —
  LowVig.ag holds 18,102 NHL team-market rows and zero prop rows. The `us,us2`
  string now stands on measurement, not on the reachability argument in
  `odds_api.py`. `docs/the_venue_route_is_closed.md`.
- **No book is materially sharper than any other.** On a common slate of
  21,642 markets the seven major books forecast within **0.0006 log loss**
  (0.0003 Brier) of one another; FanDuel leads on points but the lead does not
  separate from BetOnline.ag under a date-cluster bootstrap and **reverses in
  2025-26**. The raw full-sample ranking is a schedule artifact — it tracks
  each book's base rate (0.26 to 0.50), so a book quoting mostly 0.5-line goal
  props scores well for free. There is no sharp book here to use as truth.
- **Betting the outlier against the consensus loses.** Full population
  **−5.84% [−6.09%, −5.61%] over 642,947 quotes**; zero of 40 credible cells
  positive before or after correction; the one positive-pointing season cell
  (2025-26 +2.84%, spans zero) inverts to −6.94% in 2024-25. The premise fails
  too: where a book diverges from consensus, the outlier forecasts at least as
  well as the consensus does.
- **Boosts are real money and the model is mostly redundant to them.** The
  break-even profit boost on the canonical population is **3.2%** (3.7%
  clustered by date), so any boost of 10% or more is positive with the
  interval excluding zero (10% → +4.55% [+3.27%, +5.80%]). That is mechanical,
  not a forecasting result: a roughly fair-priced population is handed B ×
  0.484 per unit. **Within its own bets the model cannot rank better than a
  free market devig** (paired top-quartile difference +1.59% [−1.94%, +5.03%],
  spans zero) and the market's probability is the better-calibrated one
  (Brier +0.0084 [+0.0069, +0.0099] in the market's favour). The binding
  constraint is the menu: books boost **overs on stars**, and this model
  favours the over on 20.6% of markets with a card-grade over edge on **0.5%**.
  Priced at stated assumptions, boosts are worth **$0.3k–$1.6k a season** at
  $25–$50 caps — a separate, capped, book-rationed income, **not a change to
  the card's edge**.
- **Thirteen candidate inputs were investigated and none survived.**
  MoneyPuck xG and per-shot files, per-game PP time on ice, linemates from
  shift charts, opposing goalie identity and quality, shot-danger share,
  scratches, ESPN opening lines. Several are real, free, per-game and cover
  both bought seasons; none beats the price. The confirmed-goalie idea was
  **inverted**: the card already has the starter implicitly, because books
  only post goalie props for the goalie they expect to start.
- **Two textbook fixes made the card worse, which is the point.** Per-player
  rates are over-shrunk (out-of-sample slopes 1.32 assists, 1.26 shots, 1.21
  points, 1.80 hits) and dispersion is mis-specified (one league-wide
  variance-to-mean ratio). Correcting either is statistically right and moved
  the card to −1.27% and −0.47%/−0.93% respectively. **The market already
  holds the corrected view**, so improving agreement with a reality that is
  already priced buys nothing. `docs/where_the_remaining_error_lives.md`.
- **Both leakage-free attacks on the stale-minutes cell are dead, measured.**
  Teammate absence — the mechanical cause of a role expanding, and knowable
  from participation history with no new source — moves R² on the *shift*
  from 0.0117 to 0.0117, flags 175 of 49,857 player-games and catches 1.3%
  of real rises. Pre-game ice-time volatility does not separate the bad bets
  either: five equal bands run −1.33%, +0.59%, −0.40%, +0.68%, −1.30%, every
  one spanning zero with no gradient, and dropping the two most volatile
  bands takes the card from −0.35% to −0.38%. **Nothing knowable before puck
  drop from this lab's data predicts the shift.** The only remaining path is
  an external projected-lineup feed, which has no historical archive for the
  bought seasons and therefore cannot be measured before it is used — it
  would have to be collected forward from opening night and judged a season
  later. `docs/where_the_remaining_error_lives.md`.
- **The full two-season population is bought, and the model shows no
  demonstrated edge on it — in either direction.** 2,704 events and 1,259,312
  four-hour price rows collapsing to **25,911 distinct wagers** at the shipped
  bar: **−0.3%, 95% interval −1.5% to +1.0%**, which includes zero. The earlier
  +1.4% came from a 192-event sample thirty times smaller and was noise.
  This bullet has read 25,949 and 25,009. The 25,949-era counts (26,091,
  25,949, 25,947) came from a local store that no longer exists; the 25,009
  was the raw cache rebuilt on the six-entry alias team map. With the full
  map the raw cache gives 25,911, and 25,895 of the 25,947 canonical bets
  reproduce exactly. Nothing about the verdict moves.
- **An earlier version of this bullet said −1.6% over 73,918 bets, interval
  excluding zero, and called it a demonstrated loss. That was wrong, and how
  it was wrong is worth keeping.** The price store holds every book's quote
  on the same selection — 2.83 of them on average — and `run_backtest`
  counted each as an independent bet. That measured a strategy this lab
  would never run (every book at its average price, rather than the one best
  price `gameday_card.build_candidates` actually takes) and made every
  interval about √2.83 too narrow, because eight quotes on one outcome are
  eight copies of one coin flip. One wager is now one bet at the best price.
  The sibling football lab already did this and says so in its own report;
  this one did not, which is the cost of two labs that share no code.
  **Best-of-N is optimistically biased in the other direction** — the best
  price is the likeliest to be stale — so −0.3% and −1.6% bracket the truth
  rather than one replacing the other. Both ends are ≤ 0.
  Per market at one bet per wager, on the four-hour window the raw cache
  reproduces: `points` **−4.4% (6,194)** still excludes zero and still
  survives correction; `goalie_saves` −2.5% (1,727) now **spans zero**, where
  per-quote counting had it as a demonstrated loss; `shots_on_goal` +1.3%
  (9,379, spans zero); `assists` −1.3% (3,761, spans zero); `goals` −6.8%
  (564, spans zero). `blocked_shots` is the only positive at +4.9% over
  4,286. **No result survives correction and then replicates.** Until
  2026-09-24 this line said `points` did, as a demonstrated deficit, and that
  `blocked_shots` failed replication; but `replication.md` had not been
  rebuilt since per-quote counting was retired, and its two seasons summed
  to 73,918 bets. At one bet per wager they are 13,436 and 12,475, which sum
  to the 25,911. `blocked_shots` survives the correction in neither season,
  and `points` survives it only in 2025-26. 2024-25 has `points` −3.3%
  (2,726) and `blocked_shots` +4.6% (2,697), both inside the correction, so
  there is nothing for 2025-26 to confirm. Run the other way, `points`
  survives in 2025-26 (−5.4%, 3,468) and is not confirmed on 2024-25. So
  neither survives correction and then replicates. (Until 2026-09-24 this
  line also said neither season carried either market alone, which was never
  true of `points` in 2025-26.)
  (These counts read 6,202 / 1,733 / 9,395 / 3,762 / 564 / 4,293 until
  2026-09-02, and 5,984 / 1,680 / 9,043 / 3,630 / 546 / 4,126 on the alias
  team map until 2026-09-24; no ROI moves by more than three tenths of a
  point and no verdict moves at all.)
- **The reason it loses is that the model's disagreement with the market
  carries no information.** Fitting its bias on 2024-25 and testing on the
  145,751 opinions of 2025-26 it had not seen: raw error −6.34%, corrected
  −0.63%, market −2.11% — so the model *can* be made calibrated. Then
  `outcome ~ market_implied + (corrected_model − market_implied)` puts the
  coefficient on the disagreement at **+0.032, interval [−0.037, +0.102]**.
  Zero. The market's error stays flat near −1% however loudly the model
  disagrees, while the model's error grows in proportion to the disagreement
  (−3.6% at ±3%, −19.5% at +15% and above). This rules out every fix that is
  a re-weighting of the same signal: a higher bar is worse because higher
  claimed edge is where it is more wrong, and shrinking toward the market is
  arithmetically the same as raising the bar. `docs/why_the_model_has_no_edge.md`.
- **Line shopping was tested too, and there is nothing to harvest.**
  De-vigging each book and pricing every quote against the leave-one-out
  consensus of the *other* books: of 161,891 quotes only **1,557 (under 1%)**
  were positive-EV at all, and those realised −3.4% with an interval spanning
  zero. The eight books are tightly aligned on NHL props at this snapshot.
  Ladder staleness is **untestable** on bought history (3,208 of 647,126
  player-game-book combinations carry 3+ rungs) and becomes answerable only
  as the live fetch accumulates. Three hypotheses have now been tested
  against this one dataset; a fourth would be fishing, and the honest
  position is that what remains is information the market lacks, not a
  cleverer statistic. `docs/why_the_model_has_no_edge.md`.
- **A duplicated store does not look wrong, it looks significant.** The
  purchase deduplicated on the whole row, timestamps included, so two buys of
  the same window wrote every quote twice under two snapshot labels. ROI is
  unchanged by exact duplication and the interval narrows by root two — the
  first clean run reported 144,060 bets and an interval half again too tight.
  `stores.dedupe_prices` keys on the quote (event, market, player, selection,
  line, book) and never on when it was fetched. The key is still time-free;
  since 2026-09-28 time picks the survivor inside a window: the latest
  snapshot, then the better price at that instant (#244).
- **`what_we_can_claim` announced a replicated loss as good news.** Its
  headline predicate tested measured + survives-correction + replicated and
  never read the sign, so `points` at −6.6% triggered "at least one survived
  the correction and then replicated". The one document whose job is to stop
  a number being misread must not be the thing misreading it; it now
  separates a demonstrated edge from a demonstrated deficit and names the
  deficit.
- **Team markets are now bought in full, and show no demonstrated edge.**
  16,920 credits bought every snapshot of both seasons: **308,944 price rows
  over 398 game dates from 21 books**, up from 24,292 rows over 77 dates. At
  one bet per wager, in the `late` window strictly before face-off: moneyline
  **−6.6% over 954** (−13.6% to +0.4%), puck line **−4.2% over 1,117** (−9.4%
  to +0.9%), totals **−4.0% over 1,216** (−9.4% to +1.4%). Every interval
  includes zero. `data/outputs/team_markets_measurement.md` is the source.
- **Those figures read +0.0% / −1.3% / −2.5% until 2026-09-24, and all three
  were flattered.** The measurement took the best price per wager across
  *every* snapshot the store held, and never called `label_phases` — whose own
  docstring names exactly this defect. Two things leaked in. The store holds
  two windows, `late` (inside six hours) and `early` (fifteen or more), and
  7,410 of 24,726 wagers are quoted in both, so the collapse took whichever
  paid more. And **34,196 rows were captured at or after face-off** — 21,434
  at exactly the start, 12,692 inside the first three hours, 70 later, one
  event 26 days after its game — which `label_phases` files under `late`
  because a negative number of hours is fewer than six. A flat-stake loss
  costs one unit whatever the price, so a maximum taken across time only ever
  inflates the winners. Removing the post-start rows alone moves moneyline
  +0.0% → −3.9%; choosing one window moves it to −6.6%. The `early` window,
  measured separately: moneyline +4.1% over 347, puck line −0.4% over 505,
  totals −1.3% over 923, every interval spanning zero. `late` is committed
  because it is nearer the card's window (the card prices ≈9.5h out; `late`'s
  median is 1.5h, `early`'s 24h) and holds four times the prices. It is also
  the less flattering of the two, so the choice cannot be read as shopping for
  a number. The measurement now refuses an unnamed window, as the props
  backtest already did, and drops anything not captured strictly before
  face-off in every window — the closing rule this lab already uses for CLV.
  **No verdict moved**: every interval spanned zero before and spans zero now.
  Match rate is 96%, 96% and 95% of WAGERS (moneyline, puck line, totals)
  after the line grid was widened to every line the full buy actually
  holds — totals from 2.0 to 13.5, puck lines to 6.5 — because a line the
  grid does not carry is a price the measurement silently discards, which is
  how a third of the bought totals once vanished. (2026-09-25: the report's
  reconciliation counts one per wager at its best price and printed it as
  "prices seen" — moneyline's "4,200 prices seen" are 4,200 wagers from
  71,430 quote rows, beside "Prices measured: 212,964" rows. It now says
  wagers and prints the quotes; no number moved, and the committed report
  keeps the old labels until it is regenerated.)
- **The thin sample's +9.1% totals was noise, and the full buy proves it.**
  On 217 wagers totals read +9.1%; on 2,201 it read −2.5% (−4.0% over 1,216
  once measured in one window before face-off). That is what a
  small sample does when repriced, and it is the reason a number is never a
  finding until the sample can carry it.
- **The same data counted per QUOTE says all three are demonstrated losses.**
  Run without the collapse, the full store gives moneyline −7.3% over 17,937,
  puck line −5.4% over 19,418, totals −5.0% over 14,971 (measured on the
  mixed-window store, post-start prices included, before the 2026-09-24
  window fix; the point it illustrates does not depend on that) — every interval
  excluding zero and surviving the family correction. Per wager, all three
  span zero. Twenty-one books quoting one game is not twenty-one bets, and
  the distortion is large enough to manufacture three demonstrated losses out
  of three null results. It is the clearest demonstration in this repository
  of why `stores.best_price_per_wager` exists.
- **What ships is what the recorded verdicts say, through one door.**
  `verdicts.ships()` reads each experiment's `ships` list;
  the card and the default sample generators consult it rather than asserting
  policy in code. In force now: the **team back-to-back adjustment**
  (+5.8u in the `late` window, must-not-lose, not an edge; the +19.4u this
  line used to quote counted every book's quote as a bet, mixed two windows
  and took 1,070 bets priced after face-off) and the **props
  back-to-back adjustment** (+18.7u in the `card` window, **all of it from
  `shots_on_goal`**, +41.9u, while the other six markets net −23.2u; same
  must-not-lose bar. The diagnostic behind it: own-side scoring −6%,
  opponent-side +5%, both-tired cancelling, the tired team's goalie busier,
  across seven independent settlement columns). Not in force: **every
  calibration correction**. The pooled Platt, which improved calibration,
  finishes 168.5u behind raw. The by-TOI correction won +162.8u bucketed on
  *actual* ice time and lost 37.6u against raw on *expected* ice time, the
  only TOI a card can know, both on the original 4,777-bet sample; on the
  full `card`-window population it finishes 95.9u behind raw. (The records
  were rebuilt on 2026-09-24 on the full population at one bet per wager,
  with the full team-name map; the first rebuild that day ran on the
  six-entry alias map. They had said +11.4u and −97.0u on the original
  sample. No verdict moved.)
  The
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
- **The team-name map is never empty, so "is it missing?" is asked another
  way.** `build_team_name_map` always adds the Utah and Arizona aliases, so
  with no boxscores cached it returns six entries: `if not map` can never
  fire, and neither can a guard counting resolved *sides*, because the
  aliases resolve one side of every Utah game. Measured on the bought
  stores, the alias-only map resolves both teams of 0 rows and one side of
  14,514 (team, `late` window, 212,964 rows) and 229,388 (props, 3,804,233).
  Four readers ran on it silently wherever `team_names.csv` and the
  boxscore cache were absent: the team measurement (0 bets in every market,
  rendered downstream as "no historical prices have been bought"), forward
  settlement (every row written off as unsettleable after 14 days, and the
  day marked settled for good), the props backtest (the team check skipped,
  and in Utah games the other side voided), and the card (a dead blocker,
  and the six-entry map saved as `team_names.csv`, which every later
  reader preferred to a rebuild). All four now read the map from
  `--processed-dir`, refuse with `UnresolvedTeamsError` when no row
  resolves BOTH teams, and the card blocks on — and never saves — a map
  `cache_derived_spellings` says the cache supplied nothing to (#107, #108,
  #116, #117).
- **A settled day is marked only after its rows reach the ledger** (#113).
  The marker used to be touched before the write, so a write refused for a
  damaged or short ledger left the day marked with its rows never written,
  and it was never retried. And every shrink guard's floor now counts rows
  as pandas reads them (#115): blank lines, which pandas skips, had made a
  ledger with one row and three blank lines "hold" four, so every honest
  append to it was refused.
- **The earlier headline numbers were data defects, and stay on the record as
  such**: +18.1% shots_on_goal came from the UTC join discarding seven prices
  in ten (survivors were matinees); the goalie-saves "miscalibration" was
  relief appearances nobody can bet; the fixed line grid threw away a third
  of the bought totals. Each fix is tested by reproducing the defect.
- **92% of prop bets lean Under, and the claimed edge shrinks on
  realisation** — books hang the vigged, publicly-shaded side on the Over, and
  bets are selected exactly where estimation error concentrates. Diagnosis,
  not finding; stated in the backtest report.
- **The weekly Experiment Refresh works, and it took six firings to get
  there.** It re-runs every experiment against everything known that week and
  compares the verdicts it produces with the ones committed; a moved verdict
  opens a pull request rather than editing the card's policy, because a job
  that rewrites policy on its own is tuning by another name. **Its first
  firing reported a clean bill having re-decided nothing.** The six defects,
  in order: (1) a false "nothing moved" while all three experiments had
  failed; (2) the bought prices and walk-forward samples never restored;
  (3) the samples could not be built because the processed tables came from a
  later step; (4) the experiments hit the phase guard, since the store now
  holds two snapshot windows and they named neither; (5) one experiment
  genuinely re-decided while the step named "Note when this run started" sat
  *after* the work, so fresh files read as stale; (6) green, and correct.
  **Five of the six failed in the direction of reporting that nothing had
  changed.** Every one would have first appeared on a Monday in season.
  **After 2026-11-29 it re-decides nothing, on purpose.** The bought prices
  exist in CI only in Historical Props Purchase's artifacts, and on
  2026-09-25 the owner decided to let them expire (public repo; the
  provider's terms forbid redistributing them as files). When every listing
  answers and none of the three price-carrying pairs restores a run, the
  restore step emits a `::notice::` and `prices=expired`, the experiments,
  the drift check and the evidence upload are skipped, and the run is green;
  the committed verdicts stand. A failed listing or download, or a carrier
  that restores without prices, stays red. Re-decide locally (README,
  Experiment Refresh).
- **On the current data, all three recorded verdicts still hold**: `by_toi`
  off, `props_b2b` in force, `team_b2b` in force — re-decided rather than
  assumed, and now measured in the window the card actually runs in.
- **A guard that has never fired is an assumption**, and this lab has now
  proved that twice. Fire every scheduled workflow at least once before
  trusting its silence.
- **`closing-lines.yml` stays unscheduled on purpose, and CLV works anyway.**
  It was about to be given a cron for ~24,600 credits a season before the
  obvious question got asked: the line-movement capture already runs **five
  times a day** in season and writes every column a closing price needs. Its
  rounds (14:00, 18:00, 21:00, 23:00 and 01:00 UTC) close a 19:00 ET start
  with the 23:00 round in EST, an hour out. In EDT it depends on the
  provider's `commence_time`, the face-off the close is judged against: for
  a game listed at the NHL's 19:00, the 23:00 round lands at face-off, the
  strictly-before rule excludes it, and the close is the 21:00 round, two
  hours out; for a game listed at 19:10, the 23:00 round closes it ten
  minutes out. The provider listed 58% of 2025-26 games ten minutes late
  (see the 2026-09-30 entry). A second job
  would have re-bought the same board and added another scheduled surface to
  fire and fix. `closing_lines.load_captures` now falls back to the movement
  store, the dedicated store still wins when it holds anything, and the
  closing rule is the same for both — the last price captured strictly before
  the face-off and, since 2026-09-26, no more than 150 minutes before it
  (`closing_lines.CLOSE_MAX_LEAD`; the dated entry below says which starts
  that leaves with no close). **"CLV works anyway" was true on a laptop and false in CI until
  2026-09-24:** the movement store lives on Line Movement's runner, Gameday
  Refresh never downloaded it, and the `closing-lines` branch it reads had no
  writer and did not exist, so every in-season CLV report would have read
  nothing. From 2026-09-24 each Line Movement run handed its closing prices
  over as the `closing-line-captures` artifact for Closing Lines to merge
  into that branch; since 2026-10-01 neither exists (see the next entry), and
  Closing Lines derives the rows from the chain (since stage two, pulled from
  the private repository's `movement` branch) and pushes them to the private
  store. That path fetches nothing and spends no credit. **Except the bulk team markets (found 2026-09-25):**
  the retired capture also bought `h2h`, `spreads` and `totals`, and Line
  Movement asks only for the per-event markets and their ladders, so no
  moneyline opinion can ever meet a close, and a featured puck line or total
  only when an alternate ladder repeats its line. The CLV report now names
  those opinions as uncaptured rather than as selections the books pulled.
  **Cooper decided to capture them (2026-09-29):** each Line Movement round
  now also calls `fetch_team_markets` (3 markets x 2 regions = about 6
  credits, outside the per-event cap) on the same `captured_at`, `now`,
  window and preseason screen, and writes its rows into the same day file
  and the closing-line store (`capture_line_movement.capture_team_markets`).
  It runs after the per-event fetch and never moves the exit: an
  EmptySlateError is an absence, any other failure a `::warning::`, and a
  lost per-event round still exits 2 with the team rows kept. A bulk row's
  `fetched_at` is its own request's instant (microseconds) where a per-event
  row's is the round's `captured_at`; `closing_lines.team_market_rows` reads
  that, and `run_ladder_coherence.py` drops those rows so the registered
  ladder depth still counts one book's one response. The site reads the
  moneyline open from them and still no open total or puck line.
- **The closing-line store is the PRIVATE repository
  `cooperross399/nhl-closing-lines` (2026-10-01), and since stage two (#298)
  so is the movement chain it is derived from; only the public
  `line-movement` artifacts uploaded before stage two are still
  downloadable, until they expire. Read both halves.** This repository is public, so a
  `closing-lines` branch here (or a release, a Pages site, or an artifact)
  would be a permanent, downloadable file of captured odds (book, price,
  line, capture time), and The Odds API's terms forbid redistributing their
  data as downloadable files that serve as raw data. That is why Closing
  Lines was disabled on 2026-09-25 (#126), before its first in-season run.
  Cooper's decision on 2026-10-01: closing-line data must never be published
  publicly, and CLV must work. What #286 did:
  - **Closing Lines** runs when Line Movement completes, pulls the chain from
    the private repository's `movement` branch onto its runner (until stage
    two it downloaded that run's public `line-movement` artifact), derives
    one best-price row per selection per round from **every day file the
    chain holds**, one at a time
    (`closing_lines.load_movement_captures`, the dedicated store's rows by
    construction), and pushes them with `scripts/private_closing_store.py
    push` to `captures/<UTC day>.csv` in the private repository, merging
    through `merge_capture_store.merge` (no row a day file held is dropped,
    except an exact duplicate of another row in it). Reading every day means a failed push, or a week without the
    token, heals on the next push for as long as the chain carries the days.
    It holds **no write grant** on this repository. Line Movement no longer
    uploads the `closing-line-captures` artifact (the 17 uploaded before #286
    merged expire seven days after upload, the last on 2026-10-09).
  - **The script refuses** this repository (and the repository a run is in)
    by exact name, accepts a `--remote` (tests only) only as a local path
    not named for a public lab or a canonical github.com URL naming exactly
    the checked repository, and asks the GitHub API that the target is
    private (`"private": true`, not merely not false) before every push. Exit codes:
    0 pushed or nothing new; 1 GitHub unreachable; 2 a damaged movement day,
    dispatched file or remote day file (every other day is still pushed; a
    damaged movement day keeps it red until repaired, as it keeps the CLV
    report red); 3 no token; 5 refused (public target, not private, token
    turned away, a repository rule declining the push, store without
    `main`). A damaged store day file is repaired by restoring
    `captures/<day>.csv` from the private repository's history.
  - **Gameday Refresh** pulls the store with `private_closing_store.py pull`
    into `$RUNNER_TEMP`, outside the workspace, because "Upload the state for
    the next run" uploads `data/processed` whole as the public `gameday-state`
    artifact, and deletes it after the report. It **always** restores the
    movement chain too, and `run_closing_line_value.py` scores the union of
    both (`--captures-dir` is repeatable), so a round the store has not
    received yet is still scored. Since stage two both sources are private
    (the store on `main`, the chain on `movement`) and both are pulled into
    `$RUNNER_TEMP`. Store exit 4 (no captures yet) is a clean run, and so is
    a `movement` branch that exists and holds no day (the chain's pull exits
    0); chain exit 4 means the private repository has no `movement` branch,
    which since 2026-10-02 means it was deleted or renamed, so the step fails
    red with `store_fault=missing-chain`. Exit 1 (unreachable) degrades the
    run; exit 2 (a damaged day file: the good days
    are still scored), 5 (token turned away; "Report the outcome" says to
    replace the secret) and 3 (no token at all: nothing private can be read)
    fail the step red without degrading it, because a backup would hit the
    same fault. The published report (`latest_closing_line_value.md` on
    card-feed, and `gameday-reports`)
    is aggregate only: counts, rates and intervals, never a price, a line or
    a book.
  - **The secret is `NHL_CLOSING_LINES_TOKEN`**, an Actions secret on this
    repository: a fine-grained personal access token, resource owner
    cooperross399, repository access *only* `cooperross399/nhl-closing-lines`,
    repository permissions **Contents: Read and write** (Metadata: Read is
    added automatically), nothing else. The steps that read it: Gameday
    Refresh's CLV step; Closing Lines' hand-off and publish steps; and Line
    Movement's restore, private push, private check and seal (the seal reads
    it only to list the tip). The fallback key `NHL_CHAIN_FALLBACK_KEY` is
    read only by Line Movement's restore (to unseal) and its seal step.
    `tests/test_closing_prices_never_reach_the_public_repo.py` pins both
    lists across every workflow, at workflow, job and step level and in any
    spelling (`TOKEN_HOLDERS`, `KEY_HOLDERS`).
  - **Closing Lines stays disabled until that secret exists and one push has
    landed in the private repository.** Re-enable it then, and only then:
    `gh workflow enable closing-lines.yml`. Verified locally on 2026-10-01
    with the real private repository: a push of the 2026-10-01 14:00
    `line-movement` artifact (23,363 rows over three days), an idempotent
    second push, a pull, and a CLV report from the pulled store
    byte-identical to the one from the movement chain (4,244 of 4,333
    opinions matched).
  - **The movement chain moved too, in two stages (Cooper chose "staged",
    2026-10-02).** Line Movement's day files hold every book's every rung,
    face-off round included, a superset of the private store; until stage
    two they lived in the public `line-movement` artifact, where anyone could
    download them and run `load_movement_captures`.
    - **Stage one (#289, 2026-10-02): dual-write.** Each round restored from
      the public artifact, folded in the private copy on branch `movement`
      of `cooperross399/nhl-closing-lines`, pushed its three stores there,
      and checked the private tip held every row it uploaded publicly
      (`scripts/private_movement_chain.py` pull/push/verify). Every merge is
      `restore_state.union_csv`: no row dropped, exact duplicates kept (3.7%
      of movement rows are), a file whose parse disagrees with its line
      count never merged. Public retention dropped from 90 days to 7. The
      branch is separate from `main` because a movement file there would be
      read by the store's pull as closing prices. Seeded 2026-10-02 from run
      37032219942 (12 files, 258,447 rows; a fresh pull was byte-identical).
      Its first weekend ran with a token GitHub rejected (401), so nothing
      reached the private copy from Actions until 2026-10-05.
    - **Stage two: the chain's only home is the private repository.** Line
      Movement restores from it (`pull`), folds in any sealed round
      (`unseal`), pushes straight after the captures (default branch only),
      and checks the tip holds the round (`verify`). No step uploads the
      chain publicly. A round whose push fails, or whose check finds the
      private tip short of it, is SEALED (since the pre-merge review, the
      check alone decides: see below): encrypted with
      AES-256 under Cooper's key (secret `NHL_CHAIN_FALLBACK_KEY`, which only
      Cooper set and nobody has read) into a 7-day `line-movement-sealed-N`
      artifact that is unreadable without the key; every later round
      decrypts and folds it in, and that round's push brings it home. The
      gate says whether a failed round was sealed or is on no copy. A
      re-run's second attempt recovers the first from the private chain or
      its seal; `--fold-run` and `line-movement-attempt-N` are gone. Closing
      Lines pulls the chain from the private repository onto its runner
      (uploading nothing), and the CLV step pulls both the store and the
      chain into `$RUNNER_TEMP`, never `data/processed`. The site's moneyline
      open, which no frozen board ever carried, simply stays empty: the site
      may never hold the store's token.
    - **Review fixes (third commit of #298):** a missing `movement` branch is a
      fault everywhere (Line Movement's restore, Closing Lines, the CLV step),
      and `push` refuses to recreate it (`--allow-new-chain` is for a manual
      seed only), so a deleted branch cannot come back as a thin chain. A day
      file whose copy cannot be merged with the tip's is kept on the private
      branch as a sidecar (`unmerged/<store>/<day>/<blob>.csv`), counted as
      held by `verify`, and parked the same way by `unseal`, so no rows strand
      in a seal that expires. `unseal` skips sealed copies the tip already
      holds; `seal` holds only what the tip lacks (everything, when the tip
      cannot be listed in time or lacks nothing). `restore_state.union_csv`
      takes an older copy whole when it extends the newer byte for byte. The
      fallback key must be at least 32 characters with no surrounding
      whitespace (one saved as whitespace only reads as not set, exit 3).
      **Known limit:** a seal lasts 7 days and no Line Movement
      round runs from May to late September, so a round sealed in the
      season's last week (push failing then) would expire unfolded; the lab's
      end date (2027-04-25) falls inside that window.
    - **Pre-merge review fixes (2026-10-06, last commit of #298):**
      - **The check decides the seal, not the push.** The seal runs when
        the check did not pass (failed, timed out or cancelled). A push that
        failed while the check passed (an earlier attempt landed, or a copy
        kept as a sidecar) has nothing to seal; before this it sealed the
        whole season and the gate said the round would "fold in". The push
        step records its exit (`steps.private_push.outputs.exit`) and the
        gate says which: exit 2 means "merge the sidecar by hand", any other
        means "nothing is lost, the push log says why".
      - **The seal cannot wait out its step on a stalled GitHub.** Listing
        the tip (to trim the seal) is one attempt, each git call killed with
        its whole process group after 20 seconds (`TIP_LISTING_SECONDS`);
        on a timeout everything on disk is sealed. Unbounded, git waited past
        the step's 2 minutes and the round was on no copy, in exactly the
        case the seal exists for. Seals are gzip-compressed at level 1, so a
        whole-season seal still fits the step (`unseal` opens plain ones
        too), and `unseal` names a wrong key even when CBC's padding check
        lets it through (about once in 256) by checking for an archive.
      - **Every check warns while a sidecar waits** (`::warning::` and a run
        summary line naming it), because only the round that kept it is red.
      - The guards now pin the fallback key's readers across every workflow
        (reading every raw string, so `secrets['NAME']` inside a `run:` is
        seen, and counting any index that is not a quoted literal, or
        `toJSON(secrets)`, as reading every secret); read upload paths line
        by line and fail closed (the private folders, the runner's temp
        directory in any spelling, an unresolved `${{ }}`, `~`, an absolute
        path or `..` are refused, the seal being the one pinned exception);
        treat any action named `upload-artifact` as an upload whatever its
        owner, and pin the set of actions used; keep the site from naming
        the chain's script or the key; and `.gitignore` the chain's folders,
        `merged/`, `unmerged/` and `round.enc`/`round.tar`, so a local pull
        or an opened seal cannot be committed here.
    - **Merging a sidecar.** A push that cannot merge this run's copy of a
      day file with the tip's (a different header, or a parse that disagrees
      with its line count) keeps it as `unmerged/<store>/<day>/<blob>.csv` on
      `movement` and exits 2. Its rows reach no reader until merged: pull,
      Closing Lines, the CLV report and the ladder scan read day files only.
      By hand, in a folder outside any checkout of this public repository:
      `D=$(mktemp -d); gh repo clone cooperross399/nhl-closing-lines
      "$D/chain" -- -b movement`. In `$D/chain`, compare each
      `unmerged/<store>/<day>/<blob>.csv` with `<store>/<day>.csv`, repair
      whichever side is damaged so both share the header, and write the day
      file as the multiset union of both (no row dropped, exact duplicates
      kept, as `restore_state.union_csv` does). Then MOVE each merged
      sidecar, do not delete it: `mkdir -p merged/<store>/<day> && git mv
      unmerged/<store>/<day>/<blob>.csv merged/<store>/<day>/`. A sealed
      round holding the same copy stays downloadable for up to 7 days, and
      the `merged/` mark is what tells its unseal the copy is home; deleted,
      it would be parked again and that round would go red. Commit, push
      normally (never force), and `rm -rf "$D"`. The next check stops
      warning; `merged/` is never read as a day file.
    - **The fallback key.** Cooper set `NHL_CHAIN_FALLBACK_KEY` on
      2026-10-05 with `openssl rand -base64 48 | tr -d '\n' | gh secret set
      NHL_CHAIN_FALLBACK_KEY -R cooperross399/nhl-betting-lab`, which keeps
      no copy, so today only a workflow round can open a seal. To be able to
      open one by hand (the known limit above is the case for it), replace
      it with a key you keep, at a moment when both of these print nothing:
      no Line Movement run unfinished (`gh run list -R
      cooperross399/nhl-betting-lab -w line-movement.yml -L 50 --json status
      -q '.[] | select(.status != "completed") | .status'`; a run reads its
      secrets when it is queued, so one already waiting would seal with the
      old key), and no unexpired seal (`gh api
      repos/cooperross399/nhl-betting-lab/actions/artifacts --paginate -q
      '.artifacts[] | select(.name | startswith("line-movement-sealed-")) |
      select(.expired | not) | .name'`), because a seal opens only with the
      key that made it. Then `KEY=$(openssl rand -base64 48)`, keep `$KEY`
      somewhere safe off GitHub, and `gh secret set NHL_CHAIN_FALLBACK_KEY -R
      cooperross399/nhl-betting-lab --body "$KEY"`. To open a seal by hand,
      outside any checkout of this repository: `D=$(mktemp -d); gh run
      download <run-id> -R cooperross399/nhl-betting-lab -n
      line-movement-sealed-<attempt> -D "$D"`, then
      `NHL_CHAIN_FALLBACK_KEY="$KEY" openssl enc -d -aes-256-cbc -pbkdf2 -iter
      200000 -md sha256 -pass env:NHL_CHAIN_FALLBACK_KEY -in "$D/round.enc"
      -out "$D/round.tar" && tar -xf "$D/round.tar" -C "$D"` (gzip or plain).
      Its files go home with `private_movement_chain.py push --processed-dir
      "$D"` and the store token; then `rm -rf "$D"`.
    - **Never re-run a Line Movement run created before #298 merged.** A
      re-run executes that run's own workflow file (GitHub re-runs a run at
      its original commit, up to 30 days after it started) with the secrets
      as they are today. Stage one's file (#289 until #298) pulled the whole
      private chain into `data/processed` and uploaded it as the public
      `line-movement` artifact, and every older file uploads its own fresh
      paid capture publicly. That is every such run, green or red: the red
      runs of 2026-10-02 to 10-05 (the 401-token weekend) look like
      candidates and are not, and those rounds cannot be captured again
      anyway. Only deleting the runs makes a re-run impossible (`gh run
      delete <id>`, which also deletes their public artifacts; list them
      with `gh run list -R cooperross399/nhl-betting-lab -w line-movement.yml
      -L 500 --json databaseId,createdAt -q '.[] | select(.createdAt <
      "<merge time, UTC>") | .databaseId'`). Moving the token to a new secret
      name would stop a re-run pulling the chain, but not uploading its own
      fresh capture. Either is Cooper's call.
    - **The cutover.** A run executes the workflow file of the commit it was
      created at, and Line Movement runs are created hours before their
      round. So any stage-one run still queued or in progress when #298
      merged runs stage one's file afterwards: it uploads the chain publicly,
      as every stage-one round did, and pushes its round privately. Runs
      created after the merge use stage two's file. Waiting for a gap would
      not have helped: the in-flight runs upload either way, and every run
      created while waiting would have been one more stage-one upload; nor
      would cancelling them, which loses rounds that cannot be captured
      again. What the cutover needs is a check of each in-flight run after it
      finishes: if its private push or check failed, its round is only in
      its public artifact, which no stage-two round reads, so fold it in by
      hand within its 7 days, outside any checkout (`D=$(mktemp -d); gh run
      download <run-id> -R cooperross399/nhl-betting-lab -n line-movement -D
      "$D"`; the artifact unpacks to the three store folders, so
      `private_movement_chain.py push --processed-dir "$D"` with the store
      token takes them; then `rm -rf "$D"`). The runs in flight at the merge
      and what their checks said are recorded on #298.
    - **What is still downloadable:** the `line-movement` artifacts uploaded
      before stage two, until they expire (90 days for those before
      2026-10-02, 7 after). Deleting them needs `actions: write` and is
      Cooper's call. `gameday-state` also still carries that run's staging
      quotes, as before.
  - `tests/test_closing_prices_never_reach_the_public_repo.py` holds the
    routes it can: no push here carries a capture store, no artifact names
    one, the set of uploads that can carry captured or bought prices is
    pinned to the known four, however a path is spelled (so a new carrier
    fails), the CLV step replayed against a
    real private store leaves no captured price in the workspace, the
    script's refusals, and a report built from sentinel prices prints none
    of them.
- **2026-10-05: the modern stats are a shadow model, not the card's.**
  Cooper asked for the model to use Corsi, Fenwick, xG, high-danger
  attempts, PDO, GSAx, special-teams rates and iCF/iFF/ixG, and chose to
  build them beside the card rather than into it, because the card's model
  is frozen until 2027-04-25. `nhl_betting_lab.shadow` computes them from
  the NHL's free play-by-play (the lab's own xG, each season fitted on
  earlier seasons only) and `scripts/run_shadow_stats.py` measures them
  walk-forward against the card's team and prop rates on outcomes, which
  can rule a stat out and never in. The **Shadow Stats** workflow runs it
  (no credit). Nothing on the card's path may import the package
  (`tests/test_the_shadow_model_cannot_reach_the_card.py`); promoting a
  stat onto the card needs a price backtest and Cooper's decision.
  **The public site is rated on them (Cooper, 2026-10-05: "built into it,
  not separate").** The first measurement found recent xG with a
  goaltending (GSAx) and a finishing factor beat the goals ratings on every
  column (moneyline +7.58 per 1,000 games [+3.46, +12.15], 2,603 games), so
  Publish Site builds those ratings each run (`run_shadow_stats.py
  --tables-only`, writing `shadow_team_ratings.json`) and the board's
  projections, win probabilities, fair prices, puck line, totals and
  regulation split read off them (`web/build_site_json.py::rate_on_xg`;
  `board.json` says `ratings`). The site reads a file and imports nothing
  from the package. The pick and its edge are the card's, priced on the same
  ratings since the switch below. A missing or
  stale ratings file falls back to goals with a warning, never to no board.
  **2026-10-05, NOT a defect fix: Cooper moved the card's team markets onto
  the same ratings ("Full switch" on a decision card), before the decision
  date, which `docs/when_this_ends.md` lists under "may not".** Moneyline,
  puck line, totals, the regulation three-way and team totals are priced on
  the xG ratings from the first card of `XG_RATINGS_FROM` (2026-10-06,
  `models/team_ratings.py`), and those are the opinions frozen into the
  ledger. Props are untouched. Unlike the `points` staking change, this one
  changes what is tested, so the team-market half of the test restarts:
  `build_forward_report` sets aside team-market rows frozen before that day
  (counted as `superseded_team_rows`, measured nowhere) and the 2027-04-25
  verdict on team markets covers xG games only, a shorter season of
  evidence. Gameday Refresh builds the ratings (`run_shadow_stats.py
  --fetch --tables-only`, free) before the card; the card reads the JSON
  and still imports nothing from the shadow package. A missing or stale
  file prices the team markets on goals and notes it on the card
  (`team_ratings: "goals"`); the run is not degraded, because a backup
  would rebuy the prices to hit the same NHL outage. The evidence before the switch: outcomes only (moneyline +7.58
  log-loss per 1,000 games [+3.46, +12.15] over 2,603 games); the price
  backtest against the bought team markets is
  `run_shadow_stats.py --price-backtest` (Shadow Stats, `price_backtest`).
- **2026-10-08: PostHockey's glossary is in the shadow model, not the
  card's.** Cooper asked for the knowledge of posthockey.com/glossary to go
  into the model. Built the same way as the 2026-10-05 modern stats, beside
  the card and measured before anything moves: a context expected-goals
  model (`xg.context_design_matrix`, column `xg_ctx`: the play before the
  attempt, its owner, how long ago and how far away, a rush flag, the score
  state), Bayesian shooter and goalie talent updated shot by shot exactly as
  the glossary's section 4 states (`shadow/talent.py`; no age drift and no
  league-environment term, and the random-walk variances are this lab's
  choice), shooter-adjusted xGF/xGA (`xgf_adj`/`xga_adj`, since `_sh` already
  means shorthanded), GSAx(sh), GSAx+ and the A-F tiers. Two team variants
  (`xg_context_luck`, `xg_shooter_gsax`) and two goals-prop variants
  (`ixg_context_finishing`, `ixg_talent`) join the Shadow Stats
  measurement. Only the full measurement builds them; `--tables-only`, which
  writes the ratings the site and the card read, does not, and
  `tests/test_shadow_posthockey.py` checks the plain columns and the ratings
  file are unchanged. Not built: Net Rating's on-ice half, QoC/QoT, Implied
  Purpose, xGAx, WPAx and iWPA (shift charts and a win-probability model;
  linemates from shift charts already failed against prices here), badges
  (a display), All Three Zones microstats (licensed to PostHockey's
  patrons). Moving any of it onto the card is Cooper's call, after a price
  backtest.
- **This lab has an end date, decided before the data existed: 2027-04-25.**
  Everything measurable on bought history has been measured and comes back
  null. The single open question is whether the model beats prices on data
  that did not exist when it was built, which only the forward ledger can
  answer. The rule is pre-registered in `docs/when_this_ends.md`: a corrected
  interval spanning zero or negative means **stop** — archive both labs and
  disable the routines; positive on one season is a candidate needing a
  second season, never a green light; under 3,000 settled opinions means the
  pipeline failed rather than the model. **Nothing about the model, the edge
  bar or the market list may change before that date.** Defect fixes may,
  each recorded here with its date, because a fix that silently alters what
  is being measured is indistinguishable from tuning.
- **The forward-evidence organ exists and runs in Gameday Refresh.** After
  the card prices a slate, every opinion is frozen into a dated snapshot —
  the first opinion of the day stands, never repriced — and once a day's
  games are all final it settles as a unit into
  `data/processed/forward_evidence.csv`, by the same identity join and
  settlement rules as the historical backtest. Voids return the stake;
  a game with no result inside fourteen days is counted unsettleable, never
  guessed. `data/outputs/forward_evidence.md` restates what the ledger
  supports, in the house vocabulary. This is the only price evidence the
  regulation three-way has so far, since it has never been bought
  historically (it is per-event only and was never requested); the only
  price evidence `team_total` has so far, since it too has never been
  measured against real prices; and the accumulating out-of-sample test for
  every market and every shipped policy at once. (Until 2026-09-26 this
  line named hits too; hits has had
  historical prices since the 9.5-hour purchase, 5,178 settled wagers — see
  "Hits is retained historically after all" below.)
- **2026-09-25, a defect fix recorded as `docs/when_this_ends.md` requires:
  the forward report counts one bet per wager.** The snapshot and the ledger
  keep one row per book — they are evidence, and the CLV report reads them —
  but `build_forward_report` counted every row, so a selection quoted by
  eight books was eight opinions and eight bets: the per-quote counting
  retired from the backtests on 2026-08-31, still live in the report the
  2027-04-25 decision reads. Replayed on the bought card window, the
  per-quote rule reads −1.34% over 114,292, interval excluding zero ("Stop"),
  where one bet per wager reads −0.03% over 28,287, spanning zero; and the
  3,000-opinion floor would have been met about 3.7× early. Every count is
  now taken after `closing_lines.collapse_to_best`, and the report prints
  ledger rows beside the wagers they collapse to. The model, the edge bar,
  the market list and the staking rule are unchanged, and the published
  ledger held no rows when this landed (card-feed, last card 2026-08-28).
- **2026-09-25: the props backtest counted one wager per UTC day, and one
  per spelling.** Its best-price collapse keyed on the raw `date` column —
  the UTC commence date — so a 7pm ET face-off and the next afternoon's game
  shared a key, and each player's wager on a back-to-back collapsed to
  whichever game paid more: 4,196 late-window and 5,337 card-window keys
  spanned two games, while the reconciliation printed "Accounted for: all of
  them". It also keyed the raw player string, so one player spelled two ways
  by two books was two wagers. It now keys on the game and
  `player_props.player_key`. Measured on the bought store with the fixed
  code: late **26,050 bets, −0.33% [−1.55%, +0.89%]** (was 25,911, −0.27%),
  card **28,452, −0.10% [−1.26%, +1.06%]** (was 28,287, −0.03%). No verdict
  moves: `points` and `blocked_shots` still exclude zero and survive the
  family correction in both windows, and every other market still spans
  zero. **The committed reports under `data/outputs` still carry the
  pre-fix figures, and the receipts pin them by checksum** — regenerating
  them and re-attesting is Cooper's call, not a side effect of the fix.
- **2026-09-26, a defect fix recorded as `docs/when_this_ends.md` requires:
  the forward report's zero column reads the corrected interval.**
  `build_forward_report` already computed each market's interval corrected
  across the markets measured, as the 2027-04-25 rule corrects, but only the
  verdict sentence used it. The payload's `low`/`high`/`includes_zero` and
  the table's "Includes zero" column were the plain 95% interval, so a market
  could read "no" there while its corrected interval spanned zero and the
  verdict beneath it said no demonstrated edge (the test fixture: 100
  even-money bets at 60-40 over two markets, plain +0.7% .. +39.3%,
  corrected −2.1% .. +42.1%). The payload now also carries `adjusted_low`,
  `adjusted_high`, `survives_correction` and `looks` from the same
  `RoiInterval`; the table labels "95% interval, uncorrected" and "Corrected
  interval", and its "Survives correction" column reads the verdict's own
  `survives_correction` — yes, no, or "too few (<30)" under the 30-bet
  floor below which nothing survives. `low`/`high`/`includes_zero` keep
  their meaning. Counting, bet selection, the verdict rule, the model, the
  edge bar, the market list, the staking rule and the ledger's schema are
  unchanged, and the forward ledger held zero rows on 2026-09-26.
  `tests/test_the_forward_zero_column_reads_the_corrected_interval.py`.
- **2026-09-26, an open question, not a fix: which population the
  registered statistic pools.** `docs/when_this_ends.md` decides the lab on
  "the forward ledger's pooled return on frozen opinions, one bet per wager
  at the best price the card could have taken, corrected across the markets
  measured. Opinions, not bets", against a floor of "3,000 settled
  opinions". That reads two ways: **every settled opinion**, both sides of
  every line and every rung, with no edge bar; or **only the opinions that
  clear the shipped edge bar**. It awaits Cooper's decision, and neither reading is the
  decision until he makes it. The registration itself is not edited.
- **2026-09-26, a defect fix recorded as `docs/when_this_ends.md` requires:
  a close is a price near face-off.** `closing_lines.closing_prices` took the
  last capture strictly before face-off however early it was, so on a night
  the 21:00 UTC Line Movement round missed, an 18:00 UTC price was scored as
  the close of a 23:00 UTC game, five hours out (and a 14:00 price, had the
  18:00 round missed too). A close must now also be no more
  than `CLOSE_MAX_LEAD` — **150 minutes**, inclusive — before face-off. A
  selection priced before face-off but never within the bound is counted
  under `no_close_not_near_face_off`, a subset of `no_close` that every CLV
  report prints, zero included: never scored, never dropped, and kept apart
  from markets never captured at all. The bound comes from the crons: a
  19:00 EDT start's best close is the 21:00 round, 120 minutes out, and
  from 1 October every 19:00, 19:30 and 22:00 ET start, EDT or EST, has a
  round within 120 minutes when the rounds run on time. **Some starts can
  never close under today's crons**: 13:00, 13:30, 14:00 and 17:00 EDT;
  12:00, 12:30, 13:00, 16:00 and 23:00 EST. On 29-30 September only the
  18:00 and 23:00 rounds are scheduled, so on both days every start from
  17:00 to 19:00 EDT has none (and, with no 14:00 round, every start up to
  14:00 EDT), and on the 29th so do 22:00, 22:30 and 23:00 EDT; the 30th's
  late games close on the 01:00 round of 1 October. Their opinions always
  land in that bucket.
  A late round that slips past face-off is excluded, and the close falls to
  the round before: 19:00 EST and 22:00 EDT starts lose their close once
  that round runs more than 60 minutes late, 19:30 EST past 90, 19:00 EDT
  and 22:00 EST past 120, and 19:30 EDT never, its fallback round sitting
  exactly 150 minutes out. A round at about 15:30-16:00 UTC would close the
  12:00-14:00 ET starts above (12:00, 12:30 and 13:00 EST; 13:00, 13:30 and
  14:00 EDT) at 38 credits an event. It would not close 17:00 EDT or 16:00
  EST (both 21:00 UTC, whose nearest round is 18:00, 180 minutes out) or
  23:00 EST. Adding one is Cooper's credit decision; no cron changed. CLV is a report, not the 2027-04-25
  measurement, so no opinion, ledger row or decision figure moves.
  `tests/test_a_close_is_a_price_near_face_off.py`.
- **2026-09-26 (#235): a damaged line-movement day is named in the CLV
  report, not skipped.** `load_movement_captures` skipped a damaged
  `line_movement/<day>.csv` (does not parse, zero bytes, missing a capture
  column, or parses short of its line count) silently, so that day's
  opinions read as "no closing price found" and the CLV run exited 0. It is
  now named in `closing_line_value.md` and in an `::error::`, every other
  day is still scored, and `run_closing_line_value.py` exits 2 — the same
  rule as a damaged priced snapshot. It is not raised, as the dedicated
  store is, because the movement store is per-day and raising would stop the
  good days being scored. The run is red for *any* damaged movement day,
  including one that predates a schema change and lacks a capture column
  (the old code skipped those on purpose), until the file is restored or
  removed. Live: Gameday Refresh's CLV step scores the movement chain beside
  the store (since stage two it pulls the chain from the private
  repository).
- **2026-09-26: seven passages of wording said something the numbers did
  not.** No
  number, verdict, gate, stake or ledger row moved in any of them, and a
  committed report under `data/outputs` that carries the old wording keeps
  it until Cooper regenerates it (the receipts pin them by checksum).
  `what_we_can_claim.md` and `player_props_backtest.md` called the prop
  return "understated" and the measurement "conservative in that one
  direction"; the one-sided vig makes only bet *selection* stricter, and
  the printed return is best-of-N, which leans optimistic (both generators,
  the backtest docstring and `docs/what_we_can_and_cannot_claim.md`). The
  forward report called the ledger the only price evidence for hits, which
  has 5,178 settled historical wagers; it now names the regulation
  three-way, which has never been bought historically (it is per-event only
  and was never requested). `team_total` has never been measured against
  real prices either. The `points` stake-exclusion
  reason on the card quoted two windows as one measurement; each figure now
  names its window, as the staking-rule entry below does. The evidence
  bundle said the held-out window "did not confirm" `points` when nothing
  was tested — 2024-25 did not carry it alone, and 2025-26 excludes zero on
  its own — and now names why a replication is untestable. The props
  backtest set a probability-point claimed edge beside a per-unit ROI; it now
  sets the model's expected return per unit staked, (1 − P(push)) × (p ×
  decimal − 1) over every bet, against the ROI, and labels the point edge as
  points (the bets CSV keeps its 14 columns). The card listed stake-excluded
  `points` leans under the one-stake-per-outcome ladder heading; each
  demoted lean now sits under the reason its row carries. And `web/SCHEMA.md`
  named sources the site builder never reads: finals come from the live NHL
  schedule endpoint (a build with no network fails and writes neither file),
  and `record.forward` from `forward_evidence.json`, never `closing_lines`.
- **2026-09-26: workflow faults that read as success, and one success that
  read as a fault.** None moves a price, measurement, verdict, the model,
  the edge bar, the market list, the staking rule or the ledger's schema.
  Gameday Refresh: a failed fetch of `closing-lines` took the "No capture
  store yet" branch and CLV then scored the previous run's restored
  `closing_line_captures.csv` as today's; any restored store is now deleted
  first, and `git ls-remote` tells an absent branch (clean, and expected
  while Closing Lines is disabled) from an unreachable or unreadable one
  (degraded). The `gameday-state` upload ran after the card-feed publish and
  nothing read its outcome, so a failed upload published `degraded: false`
  and stood the 15:00 backup down; it now runs straight after the last step
  that writes state, and anything but a success goes into
  `run_degraded.txt`. The card notification called a clean forced post, and
  a card blocked only for a reason the card names as benign (no market the
  card may pick from is allowlisted, which includes an allowlist holding
  only hard-gated markets; or no game left today),
  "degraded" while the run published `degraded: false`; it now reads
  `nothing_to_card` as the workflow does, and such a block still posts.
  Experiment Refresh restored with `|| true` and no `--refuse-unreachable`,
  so one 502 on the purchase listing re-decided every verdict on an older
  price file with a green run; it now uses the purchase's
  `--refuse-unreachable --attempts 3` and fails naming GitHub, and a listing
  that answers with no carrier is still an absence. Its drift check's "not
  re-decided" branch was held only by a source grep that the summary text
  also matched, and is now behaviour-tested. Historical Props Purchase
  dropped a day whose listing failed and exited 0, so a partial window, or
  none, read as a finished buy and a probe wrote its retention record over a
  thinned window; it now names each failed day and exits 2 (a buy still buys
  the days that listed; a probe asks nothing). A purchase run refused at the
  restore, or whose rebuild failed, printed the checkout's committed
  `player_props_backtest.md` into its summary as its own measurement; it now
  says no measurement was produced. And the `Full test suite` job's pyflakes
  and compileall lines now read `web/`, with a test that fails any
  top-level directory of Python the gates do not name.
- **2026-09-26: four inputs that could go wrong without a word.** A capped
  fetch spent on games already under way: `fetch_player_props` sorted the
  board by start and spent `max_events` and the credit cap front to back,
  nothing dropped a started game, and on the 15:00 UTC backup an afternoon
  game in progress was bought first — then quarantined by the puck-drop
  guard — while the evening games it displaced went unpriced, and
  `fetch_team_markets` truncated its capped board to the same first games.
  Both fetches, `fetch_player_props` and `fetch_team_markets`, now drop,
  before the sort and the cap, every event whose start is at or before the
  fetch instant or cannot be confirmed, and warn how many. The two scripts
  that run both (`run_provider_shadow.py` and `capture_closing_lines.py`)
  pass one clock reading to each, because a game staged by one and not the
  other would leave every per-event market "priced for N−1 of N". A started game
  could never reach the card, so no opinion that could be frozen changes;
  its rows are simply no longer staged. `fetch_club_season_schedule` cached
  the API's `{"games": []}` for a season not yet published, and nothing
  refreshes a club schedule, so a club asked too early had no game ids and
  no boxscores all season; an answer with no regular-season game is now
  never written and a cached one is asked again — the club-schedule twin of
  the registry fix below. `run_forward_evidence.py` given a non-default
  `--output-dir` or `--archive-dir` alone paired a scratch archive with the
  real forward ledger, so a scratch card's snapshots settled into it. It now
  exits 2 when a non-default archive (named, or implied by a non-default
  `--output-dir`) meets the default processed directory because
  `--processed-dir` was left out; naming `--processed-dir`, even the real
  one, runs. Gameday Refresh, which passes no flags and so uses the real
  archive, is unchanged. And the site's history index counted best bets
  without reading `priced`, so the Archive listed a board with no priced
  game as "0 best bets", an excluded state shown as a no-value call; it is
  now `bets: null`, shown as "not priced".
- **2026-09-26: two public-board defects, site only.** The card, the forward
  ledger, the model, the edge bar, the market list and the staking rule are
  untouched by either. (#233) The board judged preseason per night, not per
  game: on a night mixing a regular-season game with an exhibition, both
  were projected, priced and picked, frozen into the site's history, and
  graded on the next morning's Results page. Every game that is not
  `gameType` 2 is now published as schedule only and never settled; the card
  already screened exhibitions per game. (#236) The board published a lean
  as a best bet: `build_board` picked the highest edge among best bets and
  leans and set no `kind`, so a lean was headed "Best bet", counted in the
  history index, graded into Results' Model picks, and could displace the
  game's real best bet. The pick now prefers a best bet, labels a lean as a
  lean, and the picks record counts best bets only. This one was latent
  until 2026-09-29, when #275 carried the staged prices to Publish Site.
- **2026-09-26, NOT a defect fix: Cooper changed the staking rule before the
  decision date, which `docs/when_this_ends.md` lists under "may not".** The
  card no longer stakes `points`. This entry exists because the alternative
  was the change landing silently, and in April nobody could have said what
  was actually tested.
  `points` is the one market here measured as a loss that survives
  correction: **-4.2% over 6,140 card-window wagers**, 95% interval -6.7% to
  -1.7%, -7.6% to -0.7% after correcting for the 8 figures measured on the
  same data (7 markets and the overall figure), -256.8 units realised. In the late window it is -4.4% over 6,194, 95% interval -6.9% to
  -2.0%, holding within that window's 2025-26 season alone at -5.4% over
  3,468 (2,726 + 3,468 = 6,194; this sentence ran the two windows together
  until 2026-09-26). On the late window the evidence bundle's verdict is that
  "a loss that survives the correction still argues against enabling this
  market, not for it".
  **Why this does not change what is being tested, which is the ground the
  decision stands on.** `write_snapshot` runs on the unfiltered priced frame
  before `build_card` is called, and the frozen row carries market, player,
  selection, line, price, book, model probability and edge -- and **no
  column for a section, a stake, a unit count or a tier**. So the forward
  ledger, and every interval computed from it, is identical whether or not
  the card staked the row. `when_this_ends.md` says the test scores
  "opinions, not bets"; the opinions are untouched. Two tests now pin this
  (`test_an_excluded_market_still_freezes_into_the_snapshot`,
  `test_the_snapshot_schema_carries_no_stake_at_all`), the second so that a
  later change cannot make the ledger stake-dependent without going red.
  So the LETTER of the freeze names the staking rule and the PURPOSE of the
  freeze -- "a test whose subject changes mid-run measures nothing" -- is not
  engaged, because the subject is unchanged. Cooper decided on 2026-09-26
  that the purpose governs. That is a judgement, not a derivation, and it is
  recorded as his.
  The mechanism is `STAKE_EXCLUDED_MARKETS`, deliberately separate from
  `HARD_GATED_MARKETS`, which is about information this lab lacks and says
  outright it is "not a judgement that the market has no value". This is that
  judgement. An excluded rung becomes a lean at zero units naming the
  measurement that withheld the stake -- never a pass, never deleted.
  Reversible by deleting one dict entry. The model, the edge bar and the
  market list are unchanged, and `points` stays allowlisted. It landed before
  the first live card: forward ledger **zero rows**, card-feed's last card
  2026-08-28 (`decision: none`).
- **2026-09-26, a defect fix recorded as `docs/when_this_ends.md` requires:
  one outcome is staked once.** `selection_key` includes the line and
  `ALTERNATE_PROVIDER_KEYS` maps every alternate ladder back to one project
  market, so a single player's `points` ladder -- over 0.5, over 1.5, over
  2.5 -- was three staked selections on one outcome at three prices. On the
  worked fixture that is 1.0 unit ($25.00) where the card intended 0.5
  ($12.50); all three rungs settle together on one point, so it was one
  position sized three times, not three positions. Staked rows are now
  grouped on `selection_key` minus the line and only the highest-edge rung
  keeps the stake; the rest become leans at zero units naming the rung that
  took it. `selection` stays in the grouping, so team-total home and away,
  both puck-line sides, and an `over` against its own `under` never collapse.
  **This is NOT a per-game, per-slate, cross-market or bankroll cap**, and the
  card says so in its standing notes.
  **Read the tension rather than the boilerplate: this one does change how
  many stakes an outcome receives, which is the staking rule.** It is
  recorded as a defect on the ground that the card already intended one stake
  per outcome and already collapses anytime-scorer into `goals` over 0.5
  "exactly so their measurements can never drift apart", and that
  `selection_key`'s own docstring records this same bug class fixed once
  before -- two spellings of a player meant "the card listed one outcome
  twice", 234 wager keys across 61 events. Cooper made that call on
  2026-09-26 and this line is the record of it, not a claim that the question
  was never open. The model, the edge bar and the market list are unchanged.
  It landed before the first live card: the forward ledger held **zero rows**
  and card-feed's last card was 2026-08-28 (`decision: none`), so nothing
  already measured is re-cut by it.
- **2026-09-26, a defect fix recorded as `docs/when_this_ends.md` requires:
  a player new this season gets a name.** `fetch_player_registry` served any
  cached registry and `fetch_nhl_data.py` never refreshed one, so a season's
  first answer stood all season. 2026-27's came on 2026-08-26, before a game
  was played, and named nobody (the stats API answers `{"data": [], "total":
  0}` for a season that has not started); every Gameday Refresh since logged
  "Registry 20262027: 0 players (cache)." and carried the file forward in
  gameday-state. A nameless player's props land under "Names that could not
  be matched": no opinion, no card, **no forward-ledger row**. On the 2025-26
  analog that is 160 players, 58 of them past the model's 15-game minimum,
  3,033 of 52,478 player-game rows, 55 of the 58 quoted in the bought prices
  (4,937 of 135,284 event-player-market triples) — the season's rookies, a
  non-random slice, silently absent from the 2027-04-25 measurement. A
  registry is now read from cache only once its season has closed (fetched
  on or after 1 August of its second year); the season being played is asked
  again every run and merged, never shrunk; an answer naming nobody is never
  written; a malformed or short page fails the fetch rather than being cached
  as the season; and pages are requested in `playerId` order, because
  unsorted paging lost 22 of 2025-26's 940 players and 25 of 2024-25's 924.
  **Closed seasons are untouched**: every cached 2023-24 to 2025-26 registry,
  local and in CI (whose first run was 2026-08-25), was fetched after its
  season closed and is read as before, so no published figure moves. The
  model, the edge bar, the market list, the staking rule and the ledger's
  schema are unchanged. It lands before opening night, and no newcomer can
  reach the 15-game minimum before mid-November, so no frozen opinion is
  re-cut.
  `tests/test_a_registry_cached_before_its_season_ended_is_asked_again.py`.
- **2026-09-26, a defect fix recorded as `docs/when_this_ends.md` requires:
  a saves prop on a goalie who did not start is void.** The boxscore lists
  every goalie who dressed, so the backup who sat all night is in the logs
  with no ice time and no saves, and forward settlement graded him: a saves
  under on him settled as a win the book would have refunded, and an over as
  a loss. The historical backtest never scored those games — a goalie
  appearance under `walk_forward.GOALIE_START_SECONDS` (2,400 seconds)
  produces no sample and so no bet — so the ledger was settling by a rule the
  backtest it is compared with never used. It now voids a `goalie_saves` row
  under that threshold, and leaves one with no recorded ice time
  unsettleable rather than guessing. Skater props are untouched. **This is
  the backtest's rule, not a book's**: books grade a starter pulled at 28
  minutes as action, and this voids him, as the backtest always has dropped
  him. So pulled starters — mostly under wins — are missing from both sides
  of the comparison, a survivorship bias the two share on purpose rather
  than one the ledger alone would carry. Settling both on the boxscore's
  starter flag, which `build_datasets` does not yet record, is the fix for
  that and would move historical figures, so it is not made here. The model,
  the edge bar, the market list, the staking rule and the ledger's schema
  are unchanged, and the ledger held zero rows when this landed.
  `tests/test_a_goalie_who_did_not_start_voids_his_saves.py`.
- **2026-09-26 (#239), a defect fix recorded as `docs/when_this_ends.md`
  requires: a postponed game is not tonight's regular-season game.**
  `season.known_regular_season_games`, which the card's preseason screen
  matches every price row against, ignored `gameScheduleState`, while
  `scheduled_regular_season_starts`, which builds the eligibility slate,
  drops any stated state other than `OK`. A game postponed on the day
  (`PPD`) stays in the cache under its original date, and a provider still
  listing it has a future commence time, so it passed the screen and the
  puck-drop guard: it was priced, could be staked, and was frozen into the
  night's snapshot. `settle_snapshots` then held the whole night for the
  14-day patience window and wrote that game's rows off as `unsettleable`.
  Both readers now share one rule (`season._is_scheduled`), so the screen
  drops a called-off game before pricing and no opinion is frozen for it.
  What the forward ledger records changes in exactly one way: a game the
  cached club schedules mark called off, with no copy marking it `OK`,
  contributes no rows, where it used to contribute `unsettleable` ones. A
  club-schedule cache fetched before the postponement (a local run, or a
  restore from the purchase artifact) still lets the game through, and where
  the two clubs' copies disagree a stale `OK` outvotes a fresh `PPD`; which
  of the two rules should win is Cooper's call. A game postponed *after* the
  card freezes (or frozen while the cache is partial, where the screen
  deliberately abstains) still holds its night for 14 days and settles as
  `unsettleable`; that is unchanged and is also Cooper's call. The model,
  the edge bar, the market list, the staking rule and the ledger's schema
  are unchanged. It lands before opening night, with zero ledger rows.
  `tests/test_a_postponed_game_is_not_a_regular_season_game_tonight.py`.
- **2026-09-26 (#242), a defect fix recorded as `docs/when_this_ends.md`
  requires: exhibition games no longer spend the per-event cap.**
  `run_provider_shadow.py` spent the 320-credit cap in face-off order before
  the card's preseason screen ran. On a mixed night (2026-09-29 onward) an
  early exhibition took one of the 8 places, and every per-event market for
  the regular-season game it displaced read "priced for k of N": INCOMPLETE,
  excluded, and missing from the frozen snapshot. Both fetches now drop
  posted events the cached regular-season schedule does not know, before the
  cap, by the card's own rule (`known_regular_season_games`, same key, same
  team map, abstaining past the cached range), and only when
  `schedule_cache_is_complete` holds; an incomplete cache screens nothing.
  The model, the edge bar, the market list and the staking rule are
  unchanged. It changes which regular-season games get per-event prices on
  a mixed night, restoring games the cap was meant to buy. The screen runs
  in every `run_provider_shadow.py` run, so exhibitions no longer take
  Provider Market Discovery probe slots either (the whole posted board,
  `--max-events 20`). With a complete cache, exhibitions no longer reach
  staging, so the card's "N price row(s) are for games the regular-season
  schedule does not know ... excluded" line normally no longer prints, and
  the count appears in the shadow run's log instead ("N posted event(s) are
  not on the cached regular-season schedule"). **It merged on 2026-09-28,
  before the first mixed night (2026-09-29), so no frozen opinion is re-cut.**
- **2026-09-28 (#243): a branch run never publishes the card.** Gameday
  Refresh read no ref. Dispatched on a feature branch, it commented its card,
  built by unreviewed code, on the operating home and committed a clean
  `latest_status.json` for today to card-feed; main's next scheduled
  precheck then read today's card as already published and stood the run
  down, and main restores only from main's runs, so that day's frozen
  opinions never reached the forward ledger. The post and card-feed steps now
  run only on a schedule or when `github.ref` is the default branch (the
  schedule is let through first because `github.event.repository` has never
  been seen on a cron run here). A branch dispatch still fetches, gates and
  renders the card as a rehearsal, publishes nothing, and finishes green;
  "Report the outcome" counts a skipped publish as a failure only where the
  publish was meant to run. The status line records the ref that wrote it,
  and the precheck counts only a clean card from its own ref. Still open, and
  Cooper's call: the restore fallback takes `forward_evidence.csv` from
  card-feed without checking the ref, and a branch dispatch still runs the
  live price fetch (`skip_provider_fetch` rehearses for free). No card,
  snapshot, ledger row, gate, cap or contract string changed.
  `tests/test_a_branch_run_never_publishes_the_card.py`.
- **2026-09-28 (#249), a defect fix recorded as `docs/when_this_ends.md`
  requires: Line Movement screens exhibitions before its cap.**
  `capture_line_movement.py` spent its 600-credit cap (15 events at 38) in
  face-off order over an unscreened board, so from 2026-09-29 into early
  October an exhibition facing off first could skip a regular-season game for
  budget and lose that round's movement and closing price, which cannot be
  collected later. It now runs the shadow run's preseason screen, moved to
  `nhl_betting_lab.preseason_screen`, with the same abstentions. The screen
  now also keeps, game by game, any game whose two clubs do not both resolve
  (it had dropped them), and drops a game only when both clubs resolve and
  the schedule holds the pairing in neither orientation; the card still
  drops what it cannot resolve, so the screen can cost a place under a cap
  but never a game the card would keep. Line Movement caches the season's
  club schedules for free first (`fetch_nhl_data.py --schedules-only`,
  bounded at 3 minutes). No card, snapshot, ledger row, cap or verdict
  changed. Watch the first 2026-09-29 Line Movement log: "Preseason screen:"
  means it is screening; "WARNING: the team-name map holds only the built-in
  aliases" means it abstained.
- **2026-09-28 (#248), a defect fix: the CLV report no longer counts
  tonight's slate as unclosed.** Gameday Refresh builds
  `closing_line_value.md` minutes after the card freezes the day's opinions,
  so every report counted tonight's games under "no closing price found" and
  explained them as "No book pulled these". `build_clv_report` now takes
  `now` (the runner passes the clock, or `--now`); an opinion whose parsed
  start is strictly after it is counted on its own line as not yet played and
  in none of the matched, no-close, uncaptured or bet counts. An unparseable
  start stays in the ordinary counts. The closing rule, the close-lead bound,
  the snapshot and the forward ledger are unchanged. Latent while Closing
  Lines is disabled.
- **2026-09-28 (#246), wording only, not a defect in what is measured:
  population B and the Bets streams are the measurement bar, not the
  stake.** The forward report called population B "the opinions the card
  would have bet", and the CLV report said its Bets view measured "what the
  bankroll would actually have done". Both filters are the 6% prop / 3.5%
  team measurement bar. The card stakes only best bets (12% / 9%), nothing
  shorter than -160 or longer than +600, and nothing in `points` or
  `goalie_saves`; and because the snapshot is frozen from the unfiltered
  prices, B also holds rungs one-stake-per-outcome demoted, markets the card
  could not use that day, a blocked card's opinions, and rows the puck-drop
  guard pulled. The pages now say so, built from the card's own constants.
  No number, population, bar or computation moved. Whether the 2027-04-25
  decision should instead read a staked "population C" is Cooper's call.
- **2026-09-28 (#245): the evidence documents give the true reason nothing
  is supported.** The allowlist bundle's recommendation said every market
  was unmeasured or spanned zero, above its own lines recording `points` (a
  loss) and `blocked_shots` (one window, not confirmed) with corrected
  intervals excluding zero; it now names each for what it is, and a market
  under the 200-bet reading floor is "too thin to read". The claims document
  said "does not exclude zero" for any market under 30 bets, where the
  correction is refused rather than failed, and now says too few bets. No
  verdict moves. The committed bundle and claims document keep the old
  wording until regenerated, which is Cooper's call.
- **2026-09-28 (#244), a defect fix: the rebuild deduplicates as the
  purchase does, and `dedupe_prices` keeps the later moment, then the better
  simultaneous price.** `rebuild_price_files.py` deduplicated on the whole
  row, so two cached responses of one event inside one window kept every
  quote twice; it now writes through `stores.dedupe_prices`. And
  `dedupe_prices` kept whichever colliding row came last: anytime +250 beside
  goals over 0.5 +210 kept +210, discarding a takeable better price. Within
  one identity and window it now keeps the latest snapshot, better or worse,
  and at that snapshot the better price, parsing `snapshot` as ISO 8601 so
  two spellings of one instant are one instant (`label_phases`, which draws
  the window, still infers the format from the first row; changing that
  changes measurement and is Cooper's call). **This changes what every future
  purchase append keeps.** The rebuilt `late` window's 1,259,312 rows against
  1,259,309 quotes means a fixed rebuild writes at most 3,804,230 rows, not
  3,804,233; the "identical on the quote identity" comparison is unaffected.
  Every figure computed from the rebuilt store can move if it is rebuilt —
  the backtests, the `props_b2b` and `by_toi` experiments, `replication.md`,
  `what_we_can_claim.md`, the allowlist bundle and this file's per-quote
  counts; only bet counts and per-wager best prices have a guaranteed
  direction (they can only stay or fall). Nothing committed is regenerated.
  Owner notes: a rebuilt TEAM store is not the purchased one (the rebuild
  stamps the provider's returned time, minutes before a round-hour face-off,
  so the 21,434 "at exactly the start" rows would pass the strictly-before
  filter), and `label_phases` files post-start rows under `late`, so
  keep-latest can replace a pre-start quote with one the measurement drops.
- **2026-09-29 (#252), a defect fix: the calibration report's ice-time
  correction is indexed on expected ice time.** `props_calibration.measure_market`
  bucketed its grouped correction, and the "beats the pooled curve" verdict,
  on actual TOI even when `expected_toi_seconds` was present — the hindsight
  index `docs/why_the_toi_correction_does_not_ship.md` retired. It now fits,
  scores and tables on expected TOI only, and with no expected column the
  grouped correction is not measured (no fallback). The actual-TOI table stays
  as a labelled hindsight diagnostic with no verdict, and the JSON names
  `grouped_index`. No shipped verdict moves (`by_toi` reads
  `correction_experiment.json`, `ships: []`). The committed
  `props_calibration.md` still says the correction beats the pooled curve for
  all 7 markets until it is regenerated, which is Cooper's call.
- **2026-09-29 (#254), a defect fix: a replication needs a held-out window of
  the same phase.** `run_replication.py` accepted one file as both windows, a
  re-run of one window under a second label, and a `late` payload against a
  `card` one, and recorded every survivor `replicated`, which
  `allowlist_evidence` reads as a held-out confirmation. It now refuses
  (exit 1, nothing written) the same file, the same measurement apart from
  `generated_at`, a missing phase and differing phases, and the report names
  both windows. A survivor too thin to test is headlined "not tested (too few
  bets)", never "did not replicate". Overlapping `--from/--to` windows are
  still not detected, and `--phase all` payloads cannot be replicated. The
  committed `replication.md` is not regenerated.
- **2026-09-29 (#256), two defect fixes.** `what_we_can_claim.md`'s pooled
  prop line copied the naive interval's `includes_zero`, so it could say "the
  interval excludes zero" where the backtest's own corrected verdict was no
  demonstrated edge; it now reads the corrected interval, with the market
  lines' branches. And `run_player_props_backtest.py` given a `--from/--to`
  window matching none of N>0 rows reported "No historical prop prices are on
  disk" and overwrote the contract `player_props_backtest.json`/`.md` with a
  zero-row measurement; it now errors, exits 1 and writes nothing. No workflow
  passes those flags.
- **2026-09-29 (#257), two defect fixes in Gameday Refresh.** card-feed's
  `latest_status.json` was dated by the publish step's wall clock, so a clean
  card for day D published after midnight stood day D+1's scheduled runs down.
  It is now dated by the card's own league day (`generated_at` in
  America/New_York; with no card, `run_league_day.txt`, the day the run
  started) and carries `card_day`; the precheck stands a run down only for a
  clean, default-branch status whose `card_day` is today, so a pre-fix status
  never counts (at most one duplicate backup the day it landed). And a 200
  board listing none of the window's games is an empty slate (exit 3) only
  when the cached schedule lists no regular-season game there still to face
  off; otherwise it is a failed fetch (exit 2, degraded, and the 15:00 backup
  runs its budgeted ~326-credit fetch, the existing response to any failed
  fetch). No cap, gate or contract string changed.
- **2026-09-29 (#253), a defect fix: a red run's frozen snapshot is laid
  back.** `restore_state._fill_from_last_success` laid only the newest success
  under a red restored run, so when the 15:00 backup could not download a red
  13:30 primary that had frozen and posted day D's snapshot, the backup froze
  its own later opinion as D, and no later restore ever read the primary
  again: the posted first opinion never reached the forward ledger. The fill
  now lays every carrier down to and including the newest success, newest
  first, `overwrite=False`, keeping the longer ledger; where an older carrier
  froze a *different* snapshot for a day, the older (first-frozen) copy
  replaces the restored one, unless that day has settled (a `.settled` marker
  or its rows in the ledger, as `settle_snapshots` reads it; an unreadable
  ledger replaces nothing). A passed-over red run that will not download is a
  `::warning::` and is asked for again next restore, not a red run (which
  would fire the ~326-credit backup daily until the artifact expired); under
  `--refuse-unreachable` (Historical Props Purchase) it still refuses before
  spending. Owner notes: the laid-back 13:30 opinion replaces a 15:00 one the
  backup may have posted; a long red streak costs one download per red
  carrier (worst case ~29, ~1 GB); a run re-run by hand keeps its place in the
  listing and can be misread as the earlier freeze.
- **2026-09-29 (#255), three defect fixes.** (1) A Line Movement re-run
  deleted attempt 1's round: its restore could not see its own in-progress run
  and "Keep the captures" uploads `line-movement` with `overwrite: true`,
  which in upload-artifact v4 is per run, not per attempt. A re-run now folds
  the run's own artifact in first (`restore_state.py --fold-run
  $GITHUB_RUN_ID`, the restore's `union_csv`). If that download fails, or a
  CSV cannot be merged, nothing is overwritten: this attempt is uploaded as
  `line-movement-attempt-N` and the run goes red. Nothing restores that name,
  so the two must be unioned by hand, and a later green attempt does not
  bring it back into the chain. (2) Provider Market Discovery now caches the
  club schedules (free, never fatal, 3 minutes) before its probe, so the #242
  preseason screen runs there too; it restores nothing and had always
  abstained. (3) `fetch_player_props`' `events_seen` counts the windowed,
  unstarted, screened slate, as the team fetch does; it read "2 of 13" on a
  two-game night. It feeds only a log line. No cap, gate or verdict changed.
- **2026-09-29 (#258), a defect fix recorded as `docs/when_this_ends.md`
  requires: the forward report's intervals count the game, not the wager.**
  Populations A and B and each market's Bets interval were `stats.roi_interval`
  over the collapsed wagers, and the page called each wager "an independent
  draw", but every rung, both sides of a line and every player in a game settle
  on one boxscore. In a null through the real `build_forward_report` (90 games
  x 8 players x a 5-rung ladder at fair prices, 3,600 wagers), population B's
  corrected interval read "excludes zero" in 18.0% of runs, 51.7% with a shared
  game-pace shock. They are now `stats.clustered_mean_interval` on (home, away,
  league game date) with the same `len(markets)` looks: 5.3% and 7.0%. It is
  the old interval exactly when every game holds one wager and never narrower,
  so a market can stop surviving correction but never start; the point
  estimate, populations, bars and ledger schema are unchanged, and the ledger
  held no settled rows. A market whose bets all come from one game reads
  `-inf% .. +inf%` until a second settles. The props backtest and team
  measurement still use the unclustered interval (an owner item). Three
  wording fixes rode along: the CLV "not yet played" line no longer says
  "staked"; the measurement-bar note says games the puck-drop guard withheld
  at the freeze are in neither population; the goalie void sentences are built
  from `GOALIE_START_SECONDS`.
- **2026-09-29 (#261), a defect fix recorded as `docs/when_this_ends.md`
  requires: the card's player resolver reads every alias of the provider's
  spelling.** `PlayerPropsModel.resolve_player` looked up only the provider
  name's plain normalisation, while the backtest and forward settlement join
  on `player_name_aliases` on both sides, so a book's "A.J. Greer" against
  registry "Anthony-John (AJ) Greer" (or "J.J. Peterka" against "JJ
  Peterka") got no card opinion and no ledger row while the measurement bet
  him. The resolver now unions the players every form reaches and resolves
  only when that is exactly one (team narrows as before), settlement's own
  candidate rule; "Elias Pettersson (2004)" still never binds the bare name.
  A spelling whose forms reach two players now has no opinion. Merged at
  06:10 UTC, before the first card, with zero ledger rows, so no frozen
  opinion is re-cut. The model, edge bar, market list and staking rule are
  unchanged.
- **2026-09-29 (#262), two defect fixes.** (1) With one club's roster
  refresh lost, `price_props` fell back to a mover's logged club even though
  that club's fresh roster was held and left him off, pricing him against his
  own club. A held logged-club roster that omits him now leaves him
  unresolved and named, **but only while one of tonight's two clubs has no
  roster held**: the roster endpoint leaves active regulars off (22 measured
  on 2026-09-29, Bedard among them), so with both rosters held the logs still
  decide his side, as before. (2) The selection fingerprint keyed on the
  best-price book's raw spelling, so a best-book switch between "Lafrenière"
  and "Lafreniere" posted "Selections changed"; it now keys on `player_key`,
  and the previous card's fingerprint is recomputed from its saved
  `best_bets` so the change of rule posts nothing spurious. The marker
  string is unchanged.
- **2026-09-29 (#263), a defect fix: a passed-over red run is asked for
  again.** After #253 a red run whose download failed was only a warning
  ("the next restore asks for it again"), but when the run that warned was
  green the next restore took it alone and never asked, and the same run
  settled the day from the backup's later opinion, which `_first_opinions`
  can never replace once settled. The restore now writes such runs to
  `data/processed/unlaid_runs.json` (inside gameday-state); every later
  merging restore asks for them again, dropping one when laid, expired, or
  after `UNLAID_TRIES` = 3 restores, each with a warning. While the file
  lists a run, `settle_snapshots` settles no pending day and
  `run_forward_evidence.py` prints a `::warning::`; the run stays green.
  Inside an unbroken red streak a run can be listed afresh, so the hold can
  recur, but the ledger settles at least every third restore. Owner calls:
  the 3-restore bound, and holding every pending day rather than only the
  days that run could have frozen. A hand run with a stale list holds until
  the file is removed.
- **2026-09-29 (#264), three defect fixes in Line Movement, none spending a
  credit.** A board with nothing in the window while the cached schedule
  lists regular-season games still to face off now exits 2 (#257's rule,
  shared as `season.regular_season_games_still_to_play`, on the capture's
  own clock). `capture_line_combinations.py` names every lost team in a
  `::warning::` and exits 2 when fewer than half the pages were read (the
  threshold is the fixer's choice). And "Restore today's captures" runs with
  `--attempts 3 --limit 10 --problem-file` under a 5-minute step timeout,
  with a final gate that turns the run red when the restore failed, timed
  out, or could not reach a carrier; the timeout keeps a GitHub outage from
  starving the paid capture of the 20-minute job. Thin runs still count
  toward `--union 3`, so three in a row can still drop older carriers
  (now red the same day); skipping them is an owner item.
- **2026-09-29 (#265), three defect fixes in calibration.**
  `run_props_calibration.py` refuses a named `--start-date/--end-date`
  window that yields no sample from non-empty logs (exit 1, writes nothing),
  and an empty fit never overwrites a `current_corrections.json` holding
  curves (the card applies them only when `by_toi` ships, which it does
  not). The calibration report's standing note is derived from the recorded
  `by_toi` verdict and no longer says no historical prices have been bought.
  `correction_experiment.json` records `phase`, `phase_hours` and
  `phase_hours_by_window`, and its `.md` names the window. No workflow
  passes date flags; the committed reports keep the old text until
  regenerated.
- **2026-09-29 (#266), a defect fix: a ledger that parses short is refused,
  not written over.** One stray quote made pandas read 4 ledger rows as 3
  without raising, and the shrink guard compared the total after the append
  with the file, so the new day's rows hid the loss and a settled day
  vanished while its marker stood. `_read_ledger` now refuses a parse shorter
  than the file's rows (`CorruptStoreError`, exit 2), and the guard compares
  the existing part at write time. Rows on disk are counted by
  `_ledger_rows_on_disk`, which leaves out lines a quoted newline spans
  (judged blank as bytes, as `existing_row_count` does) so a whole ledger
  with multi-line fields is still appended to, but never a folded line that
  begins with a snapshot date, which is a swallowed row. This also fixes such
  a ledger being refused as a shrink. `closing_lines.append_captures`
  refuses a short read the same way. `load_ledger`, read-only, stays
  forgiving (an owner item).
- **2026-09-29 (#267), four defect fixes.** Readers of `replication.json`
  (the allowlist bundle and the claims document) apply a verdict only to a
  figure of the same snapshot phase as both compared windows; a record naming
  no phase (pre-#254) is no record, which can only remove support. The
  replication headline names contradicted, unconfirmed and untested
  survivors after replicated ones. `fetch_player_props` resets
  `events_seen` after `max_events`. And `ladder_coherence._rungs_from`
  resolved a same-instant duplicate rung by row order; it now keeps the
  better-paying price per line and side, as `dedupe_prices` does. **This is
  a detector defect fix recorded as the ladder registration permits, before
  the first game and before any registered result exists.** No band, floor
  or unit moved, but it is a choice: it can only raise the violation count
  against a featured-market-only or per-provider-market rule (it cannot
  invent a violation no single market offered, because de-vigging is
  proportional). Keeping each provider market's rung apart instead is
  Cooper's call.
- **2026-09-29 (#269), two defect fixes.** A Daily Faceoff team page served
  200 without a `combinations` payload (a Next.js soft-error page) returned
  no rows without raising, so it never counted as lost and #264's
  half-the-teams rule could not fire; it now counts as lost, named in the
  `::warning::`. A real team page with an empty `players` list (no lines
  posted yet) is read, not lost, and is listed on a plain line, so a quiet
  round stays green (whether it should warn is Cooper's call). And the
  forward report defined an unsettleable row only as a game with no final
  result; it now also names rows that cannot be settled against a found,
  final game (a name matching two players, unrecorded goalie ice time, a
  missing line or stat, an unknown selection, a level final), from one
  helper for both branches. No number moved.
- **2026-09-29 (#270), a defect fix: Gameday Refresh's soft Fetch results
  step is bounded.** It had no step timeout inside the 45-minute job, so an
  NHL API outage (four attempts with backoff and a 30-second client timeout
  per request, some 160 live requests before any boxscore) could use up the
  job and leave the day with no card and no snapshot, though the step is
  documented as soft. The fetch now runs under `timeout 18m` (the datasets
  are still rebuilt on the restored cache, and a `::warning::` says so), the
  step has `timeout-minutes: 20` as a backstop, and "Record what went wrong"
  treats a `cancelled` outcome like `failure`, so the run is degraded and the
  15:00 backup runs. The heaviest healthy run on today's command took 6.3
  minutes (600 new boxscores, 2026-08-28). Owner items: a circuit breaker in
  `fetch_nhl_data.py`, and carrying `data/raw/nhl/club_schedule` in
  gameday-state (about 128 live requests a run).
- **2026-09-29 (#273), two defect fixes.** `merge_capture_store.py`, which
  Closing Lines uses to publish its store, compared the merged total with the
  remote's rows, so a remote that parsed short (a stray quote) was hidden by
  the local rows and a shorter store was written; each side's parse is now
  checked against its own file's row count, as #266 does for the ledger, and
  a refusal is an `::error::`, exit 1, nothing written (Closing Lines is
  disabled, so no run changes). And the ladder report's printed rate divided
  one-per-wager violations by every rung pair; it now prints violations over
  comparable wagers (`comparable_wagers`, display only) beside the pair count.
  No registered count, band, floor or JSON field moved.
- **2026-09-30 (#285), a documentation fix: the close is judged on the
  provider's clock.** `CLOSE_MAX_LEAD`'s comment, and the CLV paragraph
  above, said the 23:00 round "is never a close" for a 19:00 EDT start
  because it lands at face-off. Face-off for the close is the provider's
  `commence_time`, and it is often not the NHL's time. Across 2,459 events
  of the bought team prices, it was the NHL time for 65% and about ten
  minutes later for 35%: 12% in 2024-25, 58% in 2025-26, and 6 of the 7
  games of 29-30 September. A late-listed game closes on the round at its
  NHL start, ten minutes out. The comment now gives the close lead, the
  lateness tolerance and the no-close starts under both listings, generated
  by a half-hour sweep. `test_the_bound_is_what_the_capture_schedule_can_meet`
  now checks every common evening start under both listings. Moving the
  evening rounds to a quarter to the hour was measured on the 2026-27
  schedule and not adopted: about 1,284 games closed against 1,283 for
  today's rounds at 58% listed late, and 1,292 for today's at 6 in 7.
  No cron, bound, rule, report figure or verdict changed.
- **2026-09-25, a defect fix recorded as `docs/when_this_ends.md` requires:
  the card refuses stale prices.** The policy's `max_provider_run_age_hours`
  (12, policy-wide and on `the_odds_api`) was parsed and never applied —
  `run_is_fresh` had no caller outside the tests — while
  `docs/provider_allowlist_approval.md` and the evidence bundle said
  freshness runs on every card. Prices staged on a Monday and carded on the
  Wednesday, 50 hours later, staked 0.5u at Monday's price and froze it as
  the day's first opinion. The card now judges the oldest staged row at
  `--now` against the stricter of the two limits; stale, blank or
  unreadable stamps block the card with the age and the limit named, reach
  no pricer and freeze nothing, and every priced run prints the age. Gameday
  Refresh fetches in the same job and (until 2026-09-29, #275) never restored
  `data/staging/` — since then it restores the previous run's and clears it
  before the fetch — so no CI card, snapshot or ledger row changes.
- **2026-09-25: two credit caps did not hold.** `fetch_player_props` read
  `if credit_cap and ...`, so a cap of 0 (also its default) was no cap:
  on a 30-event board at 38 credits an event, cap 190 made 5 requests and
  cap 0 made 30 (1,140 credits), and `run_provider_shadow.py --props` and
  `capture_closing_lines.py` passed a dispatched "0" through. A missing,
  zero or negative cap is now refused, by the library before it asks
  anything and by both scripts at parse time. And the team-price buy gated
  each snapshot at one region (30 credits) while asking `us,us2` and being
  billed 60, never comparing its measured spend with the cap: cap 2,000
  over 90 snapshots spent 3,960, the workflow's default cap of 60 spent
  120, and the dry-run quote was half the bill. It now gates on
  `provider.region_count` and on measured spend, and quotes at the live
  region count. 395 of the 475 snapshots in the bought team store carry
  `us2` books, so past buys did ask for both regions. No price, measurement
  or verdict changes.
- **2026-09-25: the docs misstated the per-event cap and what the card
  reads.** The gameday and probe caps were documented at one region's
  arithmetic; the quota bullet below has what 320 buys, measured on the real
  schedule. Seven places said the card cannot read `data/staging/` — the
  `odds_api` docstring, the note in every provenance file, the shadow report
  and its docstring, the shadow script, the approval doc, the project status
  — while `run_gameday_card.py` reads it by name and stakes its prices. And
  `docs/provider_allowlist_approval.md` listed "staging validation" and
  "checksum" among every card's checks: the card opens no receipt (the PR
  gate recomputes evidence checksums) and validates no staged file (one it
  cannot parse is skipped). All corrected; no cap, input, verdict or policy
  changed. The committed evidence bundle, pinned by the receipt's checksum,
  still names "Staging validation" in its notes; regenerating it is
  Cooper's call. `tests/test_the_docs_state_the_cap_and_staging_truthfully.py`.
- **2026-09-25: both calibration reports printed a "95%" interval that
  counted rows as trials.** `props_calibration.md` prices every player-game
  at each line of a fixed grid (two lines for goals and assists, five for
  hits and goalie saves), and `team_markets_measurement.md` prices every
  selection at every line of a game, so one game is many rows sharing one
  outcome. The "95% on observed" was a Wilson interval on those rows, and
  the props ⚠ floor and market floor counted rows. The interval is now
  clustered on the game (`stats.clustered_wilson_interval`): a Wilson
  interval at the effective sample size the game-clustered variance implies,
  never narrower than the one on the rows. The props floors count
  player-games, and both tables print player-games or games beside the
  samples. Measured on the real samples (the unfixed code reproduces the
  committed props report byte for byte), the props intervals widen 1.03x
  (goals) to 1.62x (hits), so the printed ones covered about 77-94%. The
  goalie "pulled or partial" row, 830 line samples from 166 goalie-games,
  moves from 8.5% .. 12.6% to 7.7% .. 13.9%. In the team report 10 of 36
  rows move: the puck_line and total_goals 0-10% and 90-100% buckets widen
  1.82-1.87x (they covered about 71%). total_goals 90-100% goes from 97.3% ..
  97.6% to 97.2% .. 97.7%, and puck_line 10-20% from 17.0% .. 18.3% to 16.9%
  .. 18.4%, which still excludes the predicted 14.5%. No point estimate,
  Brier score, count or verdict moves, and no code reads these intervals.
  Every bucket still clears the floor (the smallest has 166 player-games).
  One reading moves: in blocked_shots "20 min and up" the pooled-corrected
  32.0% sat just outside 32.1% .. 32.6% and now sits inside 32.0% .. 32.7%,
  and that correction is not in force on the card. **Both committed reports
  still carry the pre-fix intervals, and the receipts pin them by
  checksum** — regenerating and re-attesting is Cooper's call. Still counted
  in rows: `PlattCalibration.MINIMUM_SAMPLES` and the 200-sample verdict
  floor, which gate the correction fit rather than an interval, and the team
  report's 200-row market floor.
- **2026-09-25: two corrections were labelled with the wrong count.** The
  props correction (its markets plus the overall figure) was printed as "the
  7 markets tested" for six markets (8 for the card window's seven) and now
  reads "7 figures measured on the same data (6 markets and the overall
  figure)"; and `what_we_can_claim.md` headed the `late` pool "Across every
  measured prop market" above a list carrying `hits` from the `card` window,
  and now reads "Across 6 of the 7 measured prop markets" and names `hits` as
  outside it. No number changed. The team measurement's family still counts
  every sample market, four with `regulation_3_way`, while the bought store
  prices three; narrowing it to three would loosen the correction slightly
  (moneyline −15.2% .. +2.0% against today's −15.5% .. +2.4%, no verdict
  moving), and loosening a gate is Cooper's call, so it is left at four. The
  committed reports still carry the old wording.
- **Hits is retained historically after all, and "no book keeps it" was a
  region artifact.** The 256-event probe that concluded hits could not be
  measured (2,600 credits) asked **one region**, and both books that quote it
  — ESPN BET and theScore Bet — are in the second. The 9.5-hour purchase,
  which asked `us,us2`, came back with **16,048 hits rows over 1,218 events**
  from those two books, 2025-10-14 to 2026-04-19, settling **5,178 wagers at
  −1.3%, 95% interval −4.0% to +1.4%** (5,021 at −1.2%, −3.9% to +1.5%, on
  the six-entry alias team map until 2026-09-24) — no demonstrated edge, and
  the first
  price evidence hits has ever had. The backtest now retires an unmeasurable
  verdict for any market the same run measures, because printing both in one
  document is the report contradicting itself — and **retention is no longer
  a paid snapshot that can go stale.** `buy_historical_props.py --from-cache`
  derives it from every response ever bought: 5,432 responses over 2,723
  events, for **zero credits and no network**, against the 256 a probe could
  afford. All seven prop markets are measurable on that evidence
  (`player_hits` seen in 1,218 of 5,432), and only responses that requested
  exactly the market list are read, because a market missing from a request
  that never mentioned it is not evidence of anything. **The regulation three-way
  still accumulates forward**: it is per-event only, and it was wired end to
  end without ever being *requested* until the dead-code test caught it, so
  every declared market must appear in a fetch list.
- **2026-09-25: the retention table counted responses under "Events
  probed".** `retention_from_cache` makes one probe per cached response, and
  the four-hour and 9.5-hour buys each priced nearly every event, so the
  table printed 5,432 "events" over 2,723, and three events priced at two
  moments could clear the absence floor of five. It now counts distinct
  events — an event is seen for a market when any of its responses carried
  it — and prints the response count beneath. Measured on the real cache
  with the fixed code: events probed 5,432 → 2,723 for every market; seen in
  5,431 → 2,723 for shots on goal, points, goals and assists,
  `player_total_saves` 2,570 → 2,298, `player_blocked_shots` 4,715 → 2,631,
  `player_hits` 1,218 of 5,432 → **1,218 of 2,723** (22% → 45%; the 2,706
  four-hour responses asked one region and carry no hits). No verdict moves:
  all seven stay measurable and none is unmeasurable. The cache key carries
  the market list and not the regions, so an event whose only response asked
  one region still counts as probed and unseen for hits (one event today).
  **The committed props reports still print the pre-fix table
  (`1218/5432`) and the receipts pin them by checksum**; regenerating them,
  and `historical_props_retention.json` (whose checksum the evidence bundle
  records), is Cooper's call.
- **The price CSVs are derived data**; every bought response is cached raw
  and the CSVs rebuild from the cache. `build_datasets` refuses to shrink an
  accumulated table by more than half (each file guarded on its own, rows not
  existence, `--allow-shrink` as the deliberate override).
- **Caches are checked before reuse, six ways**: renamed market, added
  market, schema change, and a widened line grid — the last because the CI
  state artifact restores the previous run's samples forever, which would
  have reproduced the biased totals measurement indefinitely — and, since
  2026-09-25, the back-to-back policy each row records (`use_rest`) against
  the verdict in force, and every game the logs hold from the cache's first
  sampled date. Before that a cache from the withdrawn policy passed (194,707
  of 749,115 fitted means differ) and a cache the logs had outgrown was
  reused forever. The correction experiment refuses samples from the other
  policy and samples the logs have outgrown (the same reach check). The
  calibration removes a cache it refuses before regenerating, so a rebuild
  that fails leaves no samples and Experiment Refresh fails rather than
  re-deciding on the refused file (2026-09-26, #241). A game the sample
  generator itself cannot price (a skipped refit window, or no priced
  player) now makes the experiment refuse freshly built samples too,
  failing Experiment Refresh until someone looks, which is the intended
  direction.
- **The measured historical rate is ten credits per market returned per
  event, per region.** One provider account funds every lab, and its quota
  is **3,635,739 remaining of 5,000,000** as of 2026-09-02 (1,364,261 used
  this cycle; read from the sibling lab's scheduled quota check). This line
  said "88,527 of 100,000" until 2026-09-02 — a figure from before the plan
  changed, forty times too small, and the denominator under every "fits the
  quota" sentence below. Those conclusions still hold; the margin is simply
  far wider than they state.
- **The props cost estimate omitted the region multiplier for its whole
  life.** `historical_props.estimate_credits` computed `events x markets x
  10` while the provider bills `10 x markets returned x regions` and the lab
  asks for `us,us2`. So the "107 an event against a predicted 70" above was
  not the documented rule being wrong: it was the rule with the region factor
  applied (10 x ~5.35 returned x 2) and the estimate leaving it out. The
  measured-spend gate meant nothing overspent because of it, but every
  dry-run quote was half the real figure. Callers now pass
  `provider.region_count`. (This said the sibling
  `historical_team_prices.estimate_credits` "carried the factor from the day
  it was written". Its signature did; its only caller did not, and the team
  buy had no measured-spend gate either — fixed 2026-09-25, above.)
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
- **The season fits the quota, measured against the real schedule; the
  per-event cap does not fit the slate.** 185 game days, 1,344 games,
  2026-09-29 to 2027-04-10; a mean of 7.3 games a night and a maximum of 16.
  The provider bills every asked per-event market once per region and the
  lab asks two (`us,us2`), so the 19 asked markets are 19 markets x 2
  regions = 38 credits an event. Uncapped, one fetch a day is **52,182
  credits** (51,072 per-event, 1,110 bulk) and two are 104,364, against the
  3,635,739 remaining read on 2026-09-02; at today's cap of 640 one fetch a
  day is at most 52,182, since 640 clips no night (42,530 at the old 320). (This line said 26,091 for one fetch and 52,182 for two
  until 2026-09-25, one region's arithmetic, and "88,527 remaining" until
  2026-09-02, a figure from before the plan changed. The conclusion held
  both times.) **The Gameday Refresh per-event cap of 640 buys 16 events,
  a full slate; until 2026-10-06 it was 320, which bought 8.** Until
  2026-09-25 this line said 320 clipped none of the
  185 nights, as 16 games x 19 = 304 — the region factor left out, since the
  cap was set on 2026-08-28 and `us2` was added the same day. Measured
  (read-only) on the real 2026-27 club schedules, it clips **72 of the 185
  nights** and leaves **254 games** unpriced; the fetch takes the first eight
  by face-off, and on those nights every market only the per-event fetch
  prices — the seven props, the regulation three-way, team totals, 9 of the
  12 allowlisted markets — is INCOMPLETE and excluded from the card. 608 is
  the smallest cap that clips no night (16 x 38); 640 clips 0. **2026-10-06:
  Cooper raised the cap to 640** after the first 9-game night (the first card
  on the xG ratings) lost all nine per-event markets as "priced for 8 of 9
  games" and carried 0 best bets. One fetch a day now costs at most 52,182
  credits a season (646 a run at most), and a small night costs what it did.
  Provider Market Discovery still has the gap: its 380 buys 10 events
  against a `--max-events 20`, and raising it is a separate credit decision.
  `tests/test_periphery_markets.py` now checks the gameday cap at markets x
  regions; the discovery check still divides by markets alone. The second scheduled trigger now stands down
  when the first already published a clean card to `card-feed`, so the
  ordinary season costs the one-run figure and the backup still fires
  whenever the primary did not finish or finished degraded.
- **Gameday Refresh runs green end to end** (verified 2026-08-26: live team
  prices staged, models fitted, card correctly blocked, comment posted).
  That card was blocked by the policy alone, because nothing was allowlisted
  then, and such a block is still a green run. **Since 2026-09-26 a card
  blocked by anything else on a game day is a degraded run**: red,
  `degraded: true` on card-feed, and the 15:00 backup runs. That covers a
  market priced for 7 of 8 games, stale prices, a model that would not fit,
  no prices at all, and a policy file that does not load. Until then the
  workflow read only the card step's exit, which is 0 on every blocked card,
  so such a run published itself as clean and stood the backup down
  (`tests/test_a_blocked_card_is_a_degraded_run.py`). The card's
  `nothing_to_card` says which kind of block it is.
  **Since 2026-09-26 (#238) a failed settlement, measurement rebuild,
  closing-line value report or card-feed publish fails the run red, and none
  of them degrades it.** The four steps were `continue-on-error` with no id,
  so `run_forward_evidence.py` exiting 2 on a torn ledger, or
  `run_closing_line_value.py` on a damaged store, finished green. "Report
  the outcome" now names each failure and exits non-zero, including on an
  empty slate. None of them is written into `run_degraded.txt`: the backup
  would restore the same state, run the same scripts and fail identically,
  buying the prices again for nothing. A failed card-feed push publishes no
  status, so the backup runs anyway
  (`tests/test_a_failed_settlement_fails_the_run.py`,
  `tests/test_a_failed_card_feed_push_fails_the_run.py`).
  Props return no rows this far from the season — an absence, not a fault.
  The alternate ladders and all per-event markets ride the per-event fetch;
  asking the bulk endpoint for them 422s the whole request.
- **Twelve markets are allowlisted as of 2026-09-23, against the evidence
  bundle's own recommendation**, which supports enabling nothing: no market
  survives correction and then replicates; `points` (−4.4%) and
  `blocked_shots` (+4.9%) survive correction on the pooled window, `points`
  also within 2025-26 alone and not on 2024-25, `blocked_shots` within
  neither season; `hits` is measured only in the
  9.5-hour window (−1.3% over 5,178, spanning zero); seven more show no
  demonstrated edge; and `regulation_3_way` and `team_total` have never been
  measured against real prices. The receipt says so in its own reviewer
  statement.
  Allowlisting says a market's prices may be used; it is not a claim that
  the model beats them, and every report continues to say it does not.
  The receipt is `odds_api-20260924T150657-0400-cooperross399`. It re-attests the
  approval a third time on 2026-09-24, against the props reports rebuilt on
  the full team-name map, and corrects the figures and the "within neither
  season" clause the previous statement carried. The three earlier receipts
  are in `superseded/`. The approval did not change; the evidence under it
  did.
- **The 2026-08-27 approval of the same markets was withdrawn on
  2026-08-29**, because the evidence it cited moved underneath it: the
  receipt was signed against +1.4% over 4,830 bets, and the full population
  says -1.6% over 73,918. The gate caught it on its own — the receipt's
  evidence checksums stopped matching — which is exactly what that check is
  for. Claude withdrew it, which is the only direction Claude may move that
  file, because withdrawal can only ever reduce what the card may do.
  **Re-enabling anything needed Cooper to read the current evidence and sign
  a new receipt, and that is what happened on 2026-09-23**, re-attested three
  times on 2026-09-24. Four receipts are kept under
  `data/manual/human_acceptance_receipts/superseded/` — the withdrawn
  2026-08-27 one and the three superseded re-attestations — each the record
  of a decision that was really made; a receipt in that directory approves
  nothing, and the shipped policy cites none of them. **This bullet is the
  history of the withdrawal, not the current state**: what the card produces
  now is decided by the remaining gates — completeness, freshness and
  puck-drop — and not by the allowlist. `goalie_saves` still cannot
  produce a selection even if allowlisted, for want of a confirmed-starter
  source (`docs/goalie_props_need_a_confirmed_starter.md`).
  **The withdrawal cited a number this file now records as wrong, and the
  withdrawal stood anyway.** "−1.6% over 73,918" was per-quote counting, and
  the reproducible figure is −0.3% over 25,911 — which spans zero, so it
  demonstrates no edge either. That correction reinstated nothing on its own:
  withdrawal only ever reduces what the card may do, and only Cooper reading
  the evidence and signing a new receipt could move it back, which is the
  step that then happened.
  `data/manual/staging_provider_policy.json` is the state that governs. It
  allowlisted nothing from the withdrawal until Cooper approved twelve
  markets on 2026-09-23, which is what it holds now. **An earlier version of this file also carried a
  bullet saying all eleven markets were allowlisted**, contradicting this one
  forty lines further down, alongside a verbatim duplicate of the quota
  paragraph. Both are gone. **This bullet then carried the mirror-image
  defect**: after the twelve-market approval landed it went on asserting that
  the card "produces no selection, no lean, no pass and no stake", so the file
  again disagreed with itself about whether the card may bet — this time by
  understating what the policy allows. Two bullets disagreeing about that is
  the worst possible thing for this file to be unsure of, in either
  direction.
- **The provider's whole NHL catalogue is either wired or recorded as
  deferred with its reason** (`docs/periphery_markets_decision.md`,
  2026-08-27): the six prop alternate ladders and the anytime scorer land on
  existing approved markets; `team_total` is new, priced off the scoreline
  matrix, settles from the boxscore, and stays card-excluded until a human
  receipt names it while its opinions accumulate forward. Period markets and
  first/last scorer are deferred — no period model, no goal-order data —
  not silently dropped. The per-event fetch is windowed to the day's slate
  (`--horizon-days 1`; an unwindowed 32-event August board starved the
  nearest nine games) and the cap is 640 against the pessimistic bound —
  sixteen events at two regions, the largest night (320, eight events, until
  2026-10-06; the quota bullet above has the measurement); an asked-for market nobody quotes costs
  nothing.
- **2026-09-26 (#237): a future game is not fetched every run, nor cached.**
  `fetch_nhl_data` put the whole season in scope and `fetch_boxscore` served
  only finals from cache, so every scheduled game was requested on every run
  (up to about 600 requests a night in season), spent the `--max-games`
  budget, and had its `FUT` answer written to `data/raw/nhl/boxscore`.
  Gameday Refresh's thin-history check, Experiment Refresh's 500-boxscore
  floor and Historical Props Purchase's "No boxscores were restored" warning
  all counted those files. Now a game whose start is after now, or that a
  live schedule calls `FUT`/`PRE`, is not requested; a cached club
  schedule's state is not believed, and an unconfirmed start is fetched. A
  game rescheduled *earlier* than its cached start is skipped until that
  cached start passes, then fetched: its result arrives late, not lost.
  Only final boxscores are cached, and every workflow count counts only
  those. No dataset row changes: `build_datasets` already skipped non-final
  boxscores.
- **Data**: three seasons cached — 3,936 games, 157,419 player-game rows,
  121 unresolved names (0.08%). A completed boxscore is never refetched, and
  (since 2026-09-26, #237) a game known not to have been played is not
  fetched.
- **Calibration** (can rule out, never in): 2.5M walk-forward prop samples,
  every skater market bent by ice time
  (`docs/why_ice_time_gets_its_own_correction.md`); team model overconfident
  on favourites (its docstring's opposite prediction left on the record in
  `models/team_model.py`).
- **2026-10-07: Cooper's drought rule is an unstaked list on the card, and
  he picks from it.** Cooper's decision, in his words: "Keep trying with
  points/goals/assists for player props. Players who scored 70+ points / 30+
  goals / 30+ assists, and among those, who is on a current 5+ game drought in
  each respective category. IF they fit that criteria then it's a bet. For the
  higher-end producers like McDavid there is no value in 1+ point, but goal
  props for guys like him can be identified with this trend." And, after
  seeing the backtest: "idc, run the rule and i will pick from your selections
  based on my NHL knowledge and from watching games every night." The rule,
  per category: 70+ points, 30+ goals or 30+ assists LAST regular season (the
  prior completed season), and 5+ straight regular-season games dressed for
  without one in that category, carried across the season boundary, entering
  tonight, is the over 0.5 in that category (the anytime scorer folds into
  `goals`). **The backtest headline, read from
  `data/outputs/drought_rule_backtest.json` (2024-25 and 2025-26 bought
  prices, best price, card window, flat stake, 95% interval bootstrapped over
  game nights): points -15.8% over 69 wagers (-35.9% to +6.9%); goals -4.3%
  over 971 (-14.6% to +4.9%); assists -10.4% over 1,804 (-17.1% to -4.3%).
  No category's interval is above zero: no demonstrated edge, and assists is a
  demonstrated deficit.** Cooper has seen it and decided; the card states it
  in one line and does not argue it.
  What shipped: the card's section "Drought rule — Cooper's list", built every
  game day by `drought_rule.build_drought_list` from the player logs, the
  current rosters and the schedule alone, so it publishes with "not posted"
  prices on a night the card is blocked for prices. It is a LIST: no units,
  no tiers, no edge, nothing in the best bets, leans, passes, selection
  fingerprint, stakes or frozen snapshot. Each row: player, team (the roster's,
  not the log's last club), opponent, puck drop, category, line (over 0.5), last
  season's total, current drought, and the best staged price with its book, or
  "not posted" (never filled in). A price shorter than -160 is flagged on the
  row, never hidden. Sorted by category, then longest drought first. The
  puck-drop guard applies (`apply_puck_drop_guard`): a started game, or one
  whose start cannot be confirmed, is not listed. A price name two players
  share resolves to neither and is listed as unresolved. The qualifiers come
  from `prepare_logs`, **moved from `scripts/run_drought_rule_backtest.py` into
  `src/nhl_betting_lab/drought_rule.py`** so the card and the evidence are one
  function (tonight is entered as one more row per player, asked of
  `prepare_logs` itself). It reaches Cooper through the card markdown, the
  operating-home comment (a changed list posts, without the marker phrase),
  `latest_card_comment.md` on card-feed (every run), and the site
  (`data/outputs/drought_list.json`, carried in `gameday-reports`, restored by
  Publish Site, written by `web/build_site_json.py` as `games[].drought` and
  `droughtNote`, the shape `web/SCHEMA.md` names).
  **Gradeable, apart from the registered test.** Each listed row is recorded
  with its price to `data/processed/drought_list/<day>.csv` (first price
  stands; a row listed "not posted" may take one once; a settled day is never
  reopened), settled by `scripts/run_drought_rule_forward.py` using the forward
  ledger's own settlement helpers (a player who never entered is void, the
  14-day patience window, one row per wager at the listed best price) into
  `data/processed/drought_forward.csv`, and restated in
  `data/outputs/drought_rule_forward.md` (listed count, hit rate, flat-stake
  ROI, game-clustered 95% interval, per category and overall, with the
  backtest headline beside it). A row with no posted price is graded for the
  hit rate and is not a wager. It records the RULE's results; Cooper's actual
  picks are his and are not tracked. `tests/test_the_drought_forward_record.py`
  proves `write_snapshot`'s frozen opinions, `forward_evidence.csv` and
  `build_forward_report` are byte for byte what they would have been.
  **Unchanged: the model, the edge bar, the market list, the staking rule
  (`STAKE_EXCLUDED_MARKETS` included), how the model's own selections are
  chosen, the provider policy and the registered 2027-04-25 forward test.**
  This is a list added beside them, not a change to any of them.
- **2026-10-07, evening: the Drought List. The drought bar now scales with
  the player, two ways, and the list is named for what it is.** Cooper's
  framing: the better the player, the shorter the drought that makes him
  worth a look. The flat 5-game bar shipped that morning (#307, above) is
  replaced; the base qualifier is not: 70+ points, 30+ goals or 30+ assists
  LAST regular season, per category, and the current drought is still the
  straight regular-season games he dressed for without one in that category,
  carried across the season boundary, exactly as `prepare_logs` counts it. A
  player is listed when his drought reaches EITHER of two bars:
  1. **The tier bar**, from last season's total in the category (`TIERS`):
     points 100+ -> 3, 85-99 -> 4, 70-84 -> 5; goals 40+ -> 3, 35-39 -> 4,
     30-34 -> 5; assists 60+ -> 3, 45-59 -> 4, 30-44 -> 5.
  2. **The surprise bar** (equal surprise, which Cooper also liked), from his
     own prior-season hit rate p = (prior-season regular-season games with
     one or more in the category) / (prior-season regular-season games
     dressed, never his team's games): the smallest n >= 1 with (1 - p)^n
     <= 0.05 (`SURPRISE_LEVEL`). Undefined when p = 0, so he never qualifies
     on this bar; 1 when p = 1.
  Each listed row carries both bars, which bars his drought has reached
  (`rule`: "tier", "surprise" or "both"), his hit rate, the rarity of a
  streak this long for HIM ((1 - p)^drought, shown as "1 in N for him"), his
  tier band and that band's measured record from the committed backtest
  (`cell_record`, null when the file lacks it, never guessed). Sorted by
  category, then rarest first, then longest drought, then name.
  **The measurement, read from the regenerated
  `data/outputs/drought_rule_backtest.json` (`SHIPPED: either bar`, 2024-25
  and 2025-26 bought prices, best price, card window, flat stake, 95%
  interval bootstrapped over game nights): points -1.6% over 311 wagers
  (-10.8% to +7.1%); goals -7.0% over 1,355 (-14.1% to +0.4%); assists
  -8.4% over 2,135 (-14.4% to -2.3%). No category's interval sits above
  zero: no demonstrated edge, and assists is a demonstrated deficit.** The
  two bars apart, same window: for points the surprise bar lists everyone
  the tier bar does and more (surprise only 311 at -1.6%, tier only 101 at
  -6.9%); for goals the tier bar does (tier only 1,355 at -7.0%, surprise
  only 508 at -11.1%); assists tier only 2,130 at -8.4%, surprise only
  1,068 at -12.9%. Three cells are worth naming, and none is a finding:
  **assists 60+ @3 is +10.5% over 184 (-1.2% to +23.6%)**, the one band
  whose interval nearly clears zero and does not; **goals 40+ @3 is -12.4%
  over 494 (-22.8% to -1.0%)**, a loss whose interval excludes zero, which
  is the best goal scorers on a 3-game drought; and **points 100+ @3 is
  +15.5% over 15 wagers (-25.5% to +46.9%)**, fifteen wagers, which can say
  nothing either way. Cooper has seen the morning's numbers and decided to
  implement the list regardless, as a list he picks from with his own NHL
  knowledge; the card states the headline in one line and does not argue
  it. What shipped: `drought_rule.TIERS`, `SURPRISE_LEVEL`, `tier_bar`,
  `surprise_bar`, `band_label`, `bars_reached` and `cell_records`;
  `prepare_logs` now also carries `prior_gp` and `prior_hit_<market>`;
  `qualifiers_entering` and `build_drought_list` list on either bar and
  carry the new fields; the backtest keeps the flat rule's buckets (`RULE:
  drought 5+` and the control, so the history reads the same) and adds
  `SHIPPED: either bar`, `TIER bars only`, `SURPRISE 5% only` and, per
  band, `TIER <band> @<bar>` and `TIER <band> ==<bar>`, with `tiers`,
  `surprise_level` and `rule` at the top of its JSON; `backtest_headline`
  reads the SHIPPED bucket. The card section is titled "Drought List"
  (`SECTION_TITLE`; it was "Drought rule — Cooper's list") and shows the bar
  reached ("3 (tier)", "4 (both)"), both bars, the rarity and the band's
  record beside the price. The dated lists and their forward record
  (`drought_forward`) keep their columns. **Still an UNSTAKED list: no
  units, no tiers-as-stakes, nothing in the model's selections, the
  selection fingerprint, the stakes, `STAKE_EXCLUDED_MARKETS`,
  `write_snapshot`, `forward_evidence.csv` or `build_forward_report`.
  Unchanged: the model, the edge bar, the market list, the staking rule and
  the registered 2027-04-25 forward test.** The site (`web/`) still renders
  the list from `drought_list.json`; its own sentence about the rule is the
  site's to update.
  **Review fixes (same evening), nothing staked or registered touched.** The
  row also carries `one_in`, N in "1 in N for him" computed once from the
  UNROUNDED (1 - p)^drought (`drought_rule.one_in`): `rarity`'s 4 dp had
  quantised the rarest rows, the ones the sort puts first (0.25^7 printed
  "1 in 10,000" where it is 1 in 16,384, and anything under 0.00005 printed
  "rarer than 1 in 10,000"); `rarity_text` and the page read it, and a row
  without it (written before the field) reads N off the rarity as before.
  The page (`web/Board.dc.html`) had omitted the "for him" line for exactly
  those rows (rarity 0.0 while the card printed "rarer than 1 in 10,000 for
  him"); it now prints the card's spellings, with a thousands separator,
  and skips a row that is not an object instead of throwing on it. The
  cell's "This cell 2024-26" label was hard-coded on a page three labs
  share; the builder now publishes `droughtWindow` ("2024-26", read from
  the backtest JSON's card-window seasons, null without the file) and the
  page prints that. `drought_for_game` no longer dies on an unhashable
  `rule` (a TypeError that took the whole site build down), and `_real` /
  `_whole` refuse an infinity (json.dumps writes `Infinity`, which the
  browser's JSON.parse refuses). `surprise_bar` returns None, not a
  ZeroDivisionError, for a p so small that 1 - p is 1.0; `drought_before`
  refuses a None/NaN stat (it had counted one as a hit) and counts a hit at
  one or more. The tests pin the sort's "then drought descending" tiebreak
  at equal 4-dp rarity, the committed headline's 311 / 1,355 / 2,135 (the
  flat rule's test pinned 69 / 971 / 1,804), and the page's rows rendered
  through its own component under node on the builder's output.
  2026-10-07 (later): renamed to Due List, Cooper's name for it, on every
  page and the card; identifiers keep `drought`.
- **2026-10-09: the Due List is tracked season long as if 0.25u were bet on
  every entry, every night.** Cooper: "I would like for the due list to be
  tracked season long on the website as if we bet .25u on each one every
  night." Nothing is bet, and none of it reaches the card's selections,
  stakes, the props tallies, `forward_evidence` or the registered test. What
  changed: every graded Due List row on results.json carries `units` (0.25u
  at its price; a push 0; a void, an ungraded row or one with no price at all
  None), and `record.dueList` / `dueList.season` carry `stake`, `units`,
  `staked` (and `returnPct`). The season record is read from the lab's own
  ledger (`data/processed/drought_forward.csv`, restored by Publish Site)
  when present, else summed from the frozen boards. Two additions in the lab
  (`drought_forward`, run by `run_drought_rule_forward.py` in Gameday
  Refresh's Due List step): `backfill_lists` rebuilds every regular-season
  night of this season before the first recorded list (2026-10-07) with
  `build_drought_list`, TODAY's either-bar rule, the logs of games before
  that night, and the prices the card froze that morning
  (`priced_snapshots/<day>.csv`, read only); `fill_prices` gives an entry
  recorded with no price the card's frozen price for that morning, in the
  list file and, if the night has settled, in the ledger. Both are named in
  `data/processed/drought_list/sources.json` and on the Results page. An
  entry no frozen price covers stays "not posted": graded for the hit rate,
  no units. `tests/test_due_list_is_never_staked.py` became
  `tests/test_due_list_is_tracked_at_a_quarter_unit.py`, by Cooper's request.
- **2026-10-10: the Due List's goals rule changed, on Cooper's word, after
  the tuning research.** Cooper: "leave assists and move goals to 25+ with a
  10-game drought, i still want the 40+ goals at 5-game drought too tho".
  Goals now qualify at 25+ goals last season (`THRESHOLDS`), listed at a
  drought of 10 (25-39) or 5 (40+) (`TIERS`), and no longer on the surprise
  bar (`SURPRISE_MARKETS` is points and assists). Points and assists are
  unchanged. The research (`scripts/run_due_list_tuning.py`, Due List Tuning
  workflow run 38069590532, two seasons of bought prices, best card-window
  over 0.5): no setting held up on the season it was not picked on; a drought
  does not make the over better value, and for assists makes it worse
  (-0.415 logit per 5 games [-0.616, -0.217] beyond the price); 25+ goals at
  10+ was the one setting both seasons picked, +7.9% over 207 (2024-25) and
  +12.4% over 147 (2025-26), intervals spanning zero, and the same search on
  random data finds one that good about a third of the time: **no
  demonstrated edge.** The committed backtest was regenerated on the new rule
  (Due List Tuning run 38072353385; card window, either bar, best price,
  flat stake, 95% interval bootstrapped over nights): points -1.6% over 311
  (-10.8% to +7.1%), goals +3.6% over 537 (-9.3% to +19.2%), assists -8.6%
  over 2,157 (-14.6% to -2.3%). No category's interval sits above zero: no
  demonstrated edge, and assists is a demonstrated deficit. Goals by band:
  25-39 @10 +10.8% over 325 (-10.3% to +31.4%), 40+ @5 -7.4% over 212
  (-24.8% to +11.2%). The regenerating run graded 678 more card-window
  selections than the committed run it replaced (2025-26 games it could
  match), which moves assists from 2,135 to 2,157 with its rule unchanged,
  and restored a thinner `late` window (74,966 selections against 111,546),
  which the headline does not read. Still an UNSTAKED list: the model, the edge bar, the
  market list, the staking rule and the registered 2027-04-25 test are
  unchanged, and recorded lists and their forward record keep their columns
  (nights already recorded are not rebuilt).

- **2026-10-31: the Due List's assists rule changed, on Cooper's word, and
  every row shows its shots and the card's own chance.** Cooper chose "Yes,
  60+ assists only" on a decision card. Assists now qualify at 60+ last
  season (`THRESHOLDS`), tier bar 3 (`TIERS`), and the surprise bar still
  applies. The list's first three weeks (Oct 8-29, graded from card-feed's
  card history against the forward ledger, best price): 179 entries, 36.3%
  hit against 37.3% implied, -3.2u at 1u each; assists were 121 of them at
  -3.7u. Regenerated backtest (Due List Tuning run 41203596438, card window,
  either bar): points -1.6% over 311 (-10.8% to +7.1%), goals +3.6% over 537
  (-9.3% to +19.2%), assists **+10.5% over 184 (-1.8% to +23.8%)**, where
  30+ assists read -8.6% over 2,157. No category's interval sits above zero:
  **no demonstrated edge**, and the 60+ band was picked after seeing it.
  Every row now also carries `drought_sog` / `usual_sog` (shots on goal a
  game during the drought against his rate in up to 82 games before it,
  `shots_during_drought`) and `model_probability` / `model_edge` (the card's
  own chance of the over and its gap to the best price), as card columns and
  as `droughtShots`, `usualShots`, `modelChance`, `modelEdge` on the site
  JSON. Both are information, never a filter. The backtest's new shots split
  separates nothing: goals with shots up +18.2% over 69 (+61% in 2024-25,
  -15% in 2025-26), shots down +3.1% over 302; on the live list the model
  agreeing made -2.7u over 49. Still an UNSTAKED list: the model, the edge
  bar, the market list, the staking rule, the snapshot, the forward ledger
  and the registered test are unchanged.
  **Round two, same day (Cooper: "yes do all that except 4").** `due_context.annotate`
  runs on the list after it is built:
  - **Not dressing:** a player whose club posted tonight's lines (16+
    skaters, the card's rule) without him is taken off and named in the
    list's notes.
  - **Line tags:** each row carries `line_tonight` / `pp_tonight` (not
    `line`, which is the prop's 0.5), the latest earlier capture's
    `line_before` / `pp_before`, `line_move` (up, down, same, mixed) and
    Daily Faceoff's `status`.
  - **The goalie he faces:** `opp_goalie` and `opp_goalie_status` (Daily
    Faceoff), and `opp_goalie_backup`, true when he is not the goalie with
    the most starts in his club's last 20 games. It also carries
    `opp_goalie_vs_expected`, his regressed GA over xGA minus 1 from the
    ratings file.

  These are card columns "Line tonight" and "Goalie faced" and site
  fields (`web/SCHEMA.md`). The recorded lists and the Due List ledger
  gain `model_probability` / `model_edge` (older files read blank). Every
  Monday the card carries "Due List scorecard": the last full Sunday to
  Saturday and the season, by category, hits, units at 0.25u, and model
  agreed vs disagreed (`drought_forward.build_scorecard`). It is saved
  every run as `due_list_scorecard.md`. None of it is measured against
  prices; apart from the not-dressing removal it filters nothing. Same
  unchanged list as above.

- **2026-10-09: the card's player props are on the public site.** Cooper:
  "player props need to be posting to the website". The pages had rendered a
  `props` block since the 2026-10-07 drop, and `season_record` summed one,
  but nothing wrote it, so every board read "Props are not on this board".
  `web/build_site_json.py::build_props` now writes the card's prop best bets
  and leans for the board's league day, every figure the card's own (price,
  book, model probability, edge, tier, units), joined to a game through the
  provider names the team pick uses; passes are counted in the note, never
  listed; an excluded market is named as excluded. `grade_props` settles the
  frozen rows the next morning on the box-score logs by the forward ledger's
  rules (no row in a boxed game is void, a goalie under 2,400 seconds is
  void, no box score yet waits). Site only: the card, the snapshot, the
  forward ledger, the model, the edge bar, the market list and the staking
  rule are untouched. It publishes the card's best price and book per prop,
  as the board already did for team picks and the Due List; no capture
  store, line history or closing price reaches the site.
  `tests/test_the_site_publishes_the_cards_props.py`.
  Later the same day, Cooper: "Only show the best bets, not the leans for
  player props". `build_props` now lists prop best bets only; leans are
  counted with the passes in the note. Boards frozen before this carry lean
  rows and are graded as before.
- **2026-10-10: stat sides, on the card and the board.** Cooper: "I want to
  make sure were not only looking for edges but looking for sides that the
  stats say should win." The card's best bets are where the model's chance
  beats the price, so a game whose favourite is priced right never said who
  the stats favour. The card now carries a "Stat sides" section
  (`nhl_betting_lab.stat_sides`): every priced game tonight, the moneyline
  side with the larger model win chance (the same xG ratings the card prices
  on), its fair price, the best staged price and book, and how the chance
  compares with that price ("best bet on the card", "N pts long, under the
  bar", "N pts short"). The puck-drop guard applies; a game without an
  opinion on both sides is counted, never guessed. The site already showed
  each team's win % inside the expanded game; each game's row now reads
  "Stats: TOR 58%" too (`web/Board.dc.html`, from `winProb`), and the
  Results strip's "Straight up" record already grades that side. The
  section itself stakes nothing and adds nothing to the snapshot, the
  forward ledger or its report. No measurement here shows that backing the
  stats' side at the market's price makes money, and the section says so.
  **Then, the same day, NOT a defect fix: Cooper changed the staking rule
  before the decision date** ("I want the stats combined into the model",
  then "I still want to bet underdogs but only if the model actually says
  it has a good shot of winning ... via the stats"). A team best bet in
  `moneyline`, `puck_line` or `regulation_3_way` is staked only when it
  clears the edge bar AND the model's moneyline win chance for that team is
  at least `stat_sides.STAT_SIDE_MIN_WIN` (40%, the default picked that day;
  Cooper's to move). A favourite always clears it; an underdog only with a
  real chance. One that fails, or a side with no moneyline opinion, becomes
  a lean at zero units naming why (`stat_side_reason`), under its own
  heading. Totals, team totals, the regulation draw and props are untouched.
  As with the `points` exclusion, `write_snapshot` freezes the unfiltered
  priced frame before `build_card`, so the forward ledger and the registered
  test score the same opinions; only stakes move. Unmeasured against real
  prices: whether it helps is for the team-markets backtest.
  **Then props, the same day and on the same footing** (Cooper: "well i
  still want that to apply for props. i want you the model to [be]
  confident in them hitting relative to their odds bracket"). A prop best
  bet is staked only when the model's hit chance clears what the SHORTEST
  price in its odds bracket would need for a best bet: that price's
  break-even plus `BEST_BET_PROP_EDGE` (`gameday_card.PROP_ODDS_BRACKETS`,
  `prop_confidence_reason`). Brackets, the default picked that day, about
  eight points of break-even wide: -160..-136 needs 73.5%, -135..-111
  69.4%, -110..+110 64.4%, +111..+150 59.4%, +151..+200 51.8%, +201..+300
  45.2%, +301..+400 36.9%, +401..+600 31.9%. A price at the short end of its
  bracket is held to the bar it already cleared; a longer one inside it is
  held to more. One that fails is a zero-unit lean under "Stats check,
  props". On the 2026-10-10 card it would have kept 8 of the 20 prop best
  bets. Snapshot and ledger unchanged, as above. Not measured against real
  prices, and the record says a higher flat bar did not help (the threshold
  sweep is flat); whether a bracket-relative one does is a backtest away.
- **2026-10-11: The Lineup gets the lab's DraftKings projections.** Cooper:
  "Yes do all of that" (five improvements to how the model feeds his DFS app).
  `nhl_betting_lab.dfs_projections` turns the props model's expected counts
  into expected DraftKings points, p10/p90 and the four bonus chances.
  Goalies are projected as if they start (win chance from the
  xG team ratings). Gameday Refresh sends them with
  `scripts/publish_lineup_projections.py` (default branch only,
  `continue-on-error`, token `LINEUP_INGEST_TOKEN`) to the worker's
  `/projections`. Only derived means leave: no price, line, book, player id or
  capture time. `publish_lineup_lines.py` now also sends D pairs and goalies,
  in their own keys beside the lines. The **DFS Projection Test** workflow
  measures the projection walk-forward against DraftKings averages and the
  app's old formula (`data/outputs/dfs_projection_test.md`). First run (CI
  run 38183419740, 133,435 player-games, 2023-24 to 2026-27): MAE 4.790
  against 4.824 for DraftKings' average and 4.833 for the app's formula,
  paired against the average -0.033 [-0.059, -0.012]: measurably closer,
  by a small margin. The books' de-vigged means were measured WORSE than the
  model's on the 83,183 player-games carrying a card-window prop (MAE 4.785
  against 4.665, paired +0.120 [+0.111, +0.129], bias +0.818: a proportional
  de-vig keeps the over's shading), so the send leaves them out unless run
  with `--anchor-on-books`. p90 was beaten 9.8% and p10 undercut 5.2% of the
  time (10% each if right). Site/app only:
  the card, snapshot, forward ledger, model, edge bar, market list and staking
  rule are untouched.
- **2026-10-12, NOT a defect fix: blocked shots, hits and goalie saves can
  reach the card.** Cooper: "How do we get blocked shots, goalie saves, and
  hits on the card". All three were allowlisted and priced and never once
  reached a card. Books post them late: on every 9:40 AM ET card from
  2026-09-29 to 2026-10-12, blocks were priced for 0-3 games of the slate,
  hits for none until 1 of 3 on 2026-10-12, saves for 0-2 (the 18:29 UTC
  dispatch of 2026-10-06 had saves for 8 of 9 and blocks for 6 of 9), so
  `require_full_slate` excluded them every day. And `goalie_saves` was in
  `HARD_GATED_MARKETS` for want of a confirmed starter. Three changes, the
  first two gate changes Cooper made, recorded as his:
  1. **Game by game** (`gameday_card.GAME_BY_GAME_MARKETS`,
     `assess_markets(game_by_game=...)`): the three are eligible for the
     games a book has posted them in, and the card names the games they are
     missing under "Priced game by game". Every other market stays strict.
     Whether the posted games differ from the rest, the measurement
     `market_eligibility`'s docstring asks for, has not been made.
  2. **Saves on the books' goalie.** `HARD_GATED_MARKETS` is empty. Books
     post a saves line only for the goalie they expect to start, and void it
     if he does not play; the model prices him as the backtest did, on real
     starts. A late switch the books have not yet repriced is the risk left.
  3. **An afternoon update.** Gameday Refresh gains a third cron, `30 12 *
     1-4,10-12 *`, held to 20:30 UTC (4:30 PM EDT, 3:30 PM EST), which the
     precheck never stands down. It re-prices the slate at the 640 cap (up to
     646 credits a run, about 52,000 a season against 3.6M remaining) and
     posts the card again when the selections changed. The day's first
     snapshot still stands, so **the forward ledger and the 2027-04-25 test
     are unchanged**: they score the morning's frozen opinions, which already
     carried every one of these markets a book had posted. Only the card's
     selections and stakes move.
  Measured on bought prices, card window: `blocked_shots` +7.9% over 3,026,
  surviving correction; `hits` −1.3% over 5,178 and `goalie_saves` −5.5% over
  114, both spanning zero: no demonstrated edge on either. The model, the
  edge bars, the bracket rule, the market list and the staking rule are
  unchanged.
- **2026-10-14, a defect fix: a saves stake needs tonight's listed
  starter.** The card staked Jake Oettinger over 24.5 saves (-110, Fliff,
  0.25u) in DAL @ COL; Daily Faceoff had confirmed Casey DeSmith at 11:46
  UTC, two hours before the card, and Oettinger did not play. The
  2026-10-12 premise that "books post a saves line only for the goalie they
  expect to start" was false: a book still quoted Oettinger at 20:41 UTC, and
  the same card priced both Colorado goalies. Gameday Refresh now runs
  `scripts/fetch_starting_goalies.py` (free, soft, 2 minutes) before the
  card, writing `data/processed/starting_goalies.csv` (date, teams, goalie,
  strength label, the source's news time, `retrieved_at`; no price). A
  `goalie_saves` best bet is staked only when Daily Faceoff lists that goalie
  as his team's starter marked Confirmed, Likely or Expected
  (`data.starting_goalies.STAKEABLE_STRENGTHS`); otherwise it is a lean at
  zero units under "Saves, starter check" naming who is listed. No listing,
  "Unconfirmed", a file over 12 hours old, or a failed fetch withholds every
  saves stake. Like the stats checks, it changes stakes only: the snapshot is
  frozen before `build_card`, so the forward ledger and the 2027-04-25 test
  are unchanged. The model, the edge bar, the market list and the allowlist
  are unchanged. `tests/test_a_saves_stake_needs_the_listed_starter.py`
  replays the night.
- **2026-10-13: period, extra-prop and scorer markets are shadow models,
  not the card's.** Cooper asked for three groups ("Do 1, 2, and 3"): period
  markets (`h2h_p1..p3`, `h2h_3_way_p1..p3`, `spreads_p1..p3`,
  `totals_p1..p3`), `player_power_play_points`, `player_faceoffs_won` and
  `player_shots`, and `player_goal_scorer_first` / `_last`. Each is built in
  `nhl_betting_lab.new_markets` (`periods.py`, `player_extras.py`,
  `scorers.py`) from the NHL's free play-by-play, which carries what the
  boxscore lacks (goals by period, PP assists, faceoff counts, missed and
  blocked attempts, goal order), and measured walk-forward on outcomes only by
  `scripts/run_period_markets.py`, `run_player_extras.py` and
  `run_scorer_markets.py`, which the **Shadow Stats** workflow now runs (no
  credit). Outcomes can rule a model out and never in. Nothing on the card's
  path may import the package (`tests/test_the_shadow_model_cannot_reach_the_card.py`).
  Stated assumptions to check against a book's rules before any price
  backtest: a tied period grades `h2h_pN` as a push; `player_shots` is shot
  attempts (unblocked attempts are measured too); scorer markets count
  overtime, never the shootout, a player who did not dress is void. None of
  these markets is in the fetch list or has price history, so none can be
  priced, backtested or allowlisted yet; asking for them in the daily fetch,
  and buying history, spend credits and are Cooper's call. The model, the edge
  bar, the market list, the staking rule and the registered test are
  unchanged.
- **2026-10-13: those markets are priced, privately, and nothing reaches the
  card.** Cooper approved both the daily fetch and the historical buy ("do it
  all"). The 17 keys (`new_markets.prices.CORE_KEYS`: the 12 period markets,
  `player_power_play_points`, `player_faceoffs_won`, `player_shots`, first and
  last scorer) are a separate fetch, NOT added to `odds_api`'s lists or
  `markets.py`, so the card, the snapshot, the forward ledger and the
  allowlist never see them. `scripts/capture_new_market_prices.py` asks
  tonight's unstarted regular-season games (the preseason screen and the
  started-game drop before the cap) at 1 credit per market returned per
  region, gated at 17 x 2 = 34 an event; `scripts/buy_new_market_prices.py`
  buys a past window at 10 per market returned per region, gated at 340 an
  event, dry-run by default, with `--probe-events N` to measure the real
  charge on a spread sample and project the full buy. Both enforce the cap on
  measured spend projected one event ahead at the dearest charge seen (#234,
  `prices.gated_buy`), refuse a missing or zero cap, never re-buy a cached
  response, and fall back once to the core keys on a 422 (the alternate
  spellings, `--with-alternates`, have never been seen served for NHL).
  **Budget:** the daily capture runs from the **New Market Prices** workflow
  (cron 10:00 UTC, months 1-4 and 10-12, default branch only) with a cap of
  640, which covers a 16-game night (16 x 34 = 544); at 7.3 games a night
  that is at most about 46,000 credits a season, less whatever is not
  served. A full two-season buy (about 2,700 events at 9.5 hours) is at
  worst 918,000 credits; the probe measures the real figure before any buy,
  and the buy itself is a dispatch with Cooper's cap. **The prices live only
  on branch `new-markets` of the PRIVATE repository
  `cooperross399/nhl-closing-lines`** (`scripts/private_new_market_store.py`,
  gzip, one file per response, add-only; it refuses the public lab, wants
  `"private": true`, and pulls only outside the workspace), and on a runner
  only in `$RUNNER_TEMP/private-new-markets`; no step uploads them.
  `scripts/run_new_market_backtest.py` joins them to the shadow models'
  walk-forward opinions (one bet per wager at the best price, flat stake,
  bars 3.5% period / 6% player, game-clustered intervals corrected across
  every figure, `player_shots` settled as attempts and as unblocked attempts
  with the mean posted line printed beside both) and writes aggregates only
  to `data/outputs/new_market_backtest.md`. The first workflow push needs
  `seed_branch` ticked to create the branch. Moving any market onto the card
  still needs a backtest, an allowlisting receipt and Cooper's decision. The
  model, the edge bar, the market list, the staking rule and the registered
  test are unchanged.
  **Same day, the probe changed the plan.** New Market Prices run
  38470625496 (probe, cap 4,000) bought 11 past events for 2,940 credits,
  **267 an event measured**, projecting about 494,000 for the full buy; its
  quota check read **85,422 remaining of 100,000** before the probe and
  82,462 after, not the 3,635,739 of 5,000,000 the quota bullet above
  records (read 2026-09-02). Cooper then chose **"Daily only"** on a
  decision card: the nightly capture runs (about 27 credits an event
  measured live, roughly 200 a night) and **no historical buy is made**; the
  backtest runs once enough captured games accumulate. The 11 probe events
  are held on the private branch. Every credit figure in this file that
  says a spend "fits the quota" was written against the larger plan; check
  `scripts/check_provider_quota.py` in the latest run before any new spend.

- **2026-10-21, NOT a defect fix: goalie saves are priced on tonight's
  game (Cooper, 2026-10-20: "Re-evaluate and fine-tune the goalie saves
  portion of the model. Factor in the team that is favored to win and home
  ice advantage.").** The old mean was the goalie's career shots against
  per sixty, which follows him across clubs and moves about twice as much
  as saves do; it projected heavy favourites' goalies (65%+) at 23.46 saves
  where they made 22.46 (326 starts), big underdogs' (35% or less) at 25.93
  where they made 27.83 (309). `models/saves_context.py` recalibrates it on
  tonight's two teams' recent shot rates, home ice, the rink's counting
  bias and start minutes (`SHIPPED`, variant `G`); the favourite enters
  through the two teams' shot rates (it projects those two groups at 23.17
  and 26.94). With no shot counts in the games table the card falls back
  to the old mean (`SavesInputs.for_card`). Measured walk-forward by
  `scripts/run_saves_model_study.py` (Saves Model Study run 39536283289)
  under a rule fixed before the run: out of sample +0.0510 log-likelihood
  per start [+0.0417, +0.0604] over 4,024 starts (both seasons alone
  exclude zero), MAE 4.998 against 5.266; on the bought saves prices at the
  6% bar +52.0u over 668 against -47.3u over 1,703 (`late`), -4.2u over 44
  against -6.3u over 114 (`card`). Variants adding the market moneyline
  scored as well on outcomes but lost more than the old model on the
  `card`-window prices, so under the rule they did not ship. No edge is
  claimed: the `late` figure is uncorrected and chosen among seven.
  `docs/goalie_saves_context.md`. **This changes what the forward test
  scores for `goalie_saves`**, as the xG switch did for team markets: saves
  rows frozen before `SAVES_CONTEXT_FROM` (2026-10-21) are set aside
  (`superseded_saves_rows`), and the 2027-04-25 verdict on saves covers the
  new model only (192 saves rows were in the ledger). Every other market,
  the edge bars, the bracket and starter checks, the market list and the
  staking rule are unchanged. **The Lineup's goalie projections**
  (`publish_lineup_projections.py`, `dfs_projections.project_slate(...,
  saves_inputs=)`) read the same model from 2026-10-21, on the DFS
  Projection Test's walk-forward goalie comparison
  (`saves_context.walk_forward_means`, the "Goalies on the card's saves
  model" section of `dfs_projection_test.md`): on 6,187 starts (DFS
  Projection Test run 39549990121) DraftKings-points MAE 7.807 against
  7.871 on the old saves mean, paired -0.065 [-0.100, -0.024], and bias
  -1.012 against -1.239; DraftKings' own average 8.122.
- **2026-10-21, a defect fix recorded as `docs/when_this_ends.md` requires:
  a late market reaches the ledger.** Books post blocked shots, hits and
  goalie saves after the 9:40 AM ET freeze, the card picks them game by game
  (`GAME_BY_GAME_MARKETS`), and the 20:30 UTC re-price staked them while the
  morning snapshot stood untouched: on 2026-10-19 the card staked 13 saves
  bets and 5 blocks the forward ledger never saw. `write_snapshot(...,
  late_markets=GAME_BY_GAME_MARKETS)` now lets a later run add, to the
  standing snapshot, a late market's rows for every game the snapshot holds
  no row of that market for. That is the first opinion on that market in that
  game, so nothing is repriced: a (game, market) already frozen keeps every
  row, other markets keep the first-snapshot rule, a settled day takes
  nothing, and the puck-drop guard applies. The rows are appended, so the
  morning file is a byte prefix of the later one, and
  `restore_state._first_opinions` no longer puts an older carrier's copy back
  over a copy that only extends it. The model, the edge bar, the market list
  and the staking rule are unchanged; the ledger now holds late-market
  opinions it used to miss.

- **2026-10-21: the shadow team variants and per-team home ice were priced,
  and nothing switched.** Cooper said "Yes do all tht" to re-testing them and
  switching on a winner. `run_shadow_stats.py --price-backtest` now prices,
  on identical games and the bought team prices, the old goals ratings, the
  live xG ratings, both PostHockey variants and the live ratings with
  per-team home ice (`team_home_ice`, two years of goals shrunk at 150
  games). The switch rule was committed before any result was read
  (`docs/team_variants_decision_rule.md`): beat the live ratings in units in
  both windows, and lose no more than 5u in any `late` market. Shadow Stats
  run 39550297681, 3,798 games: none passed (context xG worse in both;
  shooter-adjusted xG +55.9u `late` but -22.9u `early`; per-team home ice
  +10.9u `late`, level `early`, and -10.4u on `late` totals). Every interval
  spans zero, live included: no demonstrated edge. The Props Form Test re-run
  repeated -32.9u against long-run. The card, the ledger and the model are
  unchanged.

- **2026-10-21, NOT a defect fix: Cooper switched the card's team markets
  onto PostHockey's shooter-adjusted xG and each team's own home ice, against
  the switch rule.** Hours after the entry above, Cooper: "I dont give a shit
  if you find that it makes more money. I am telling you that i want it to
  affect the model. I know it will", then "We will always be betting picks
  the day of" (the `late` window, where shooter-adjusted xG was +55.9u and
  per-team home ice +10.9u against live; neither passed the committed rule,
  and every interval spans zero: no demonstrated edge). The ratings file
  (`shadow_team_ratings.json`, built by `run_shadow_stats.py --tables-only`
  in Gameday Refresh and Publish Site) is now `xg_shooter_gsax`
  (`measurement.RATINGS_VARIANT_KEY`: recent shooter-adjusted xGF/xGA with
  GSAx(sh)) and carries `home_ice`, each team's log deviation from the
  league's home edge over the two years before the ratings date, shrunk at
  150 games (`measurement.team_home_ice`), which `TeamModel.home_ice` applies
  to every team market. Every run now builds context xG and shooter talent,
  which only the full measurement did. The combined pair was never priced as
  a pair before the switch; `--price-backtest` now prices it
  (`xg_shooter_home`). This changes what the forward test scores for team
  markets, as the 2026-10-05 switch did: rows frozen before
  `TEAM_RATINGS_FROM` (2026-10-22) are set aside (`superseded_team_rows`),
  and the 2027-04-25 verdict on team markets covers the new ratings only.
  Props, the edge bars, the stat-side and bracket checks, the market list
  and the staking rule are unchanged. A missing or stale file still prices
  on goals and says so.
- **2026-10-21, NOT a defect fix: each club's last five games are factored
  into team markets and props (Cooper: "I want to make sure the model is
  learning from itself each night too ... how every team is playing in their
  last five games", then "i dont want to completely rely on the last 5 games
  i just want it to be factored in").** Every model already re-fits on every
  game each run; what was missing was short-term team form. **Team markets:**
  `measurement.team_form` takes each club's venue-adjusted shooter-adjusted
  xGF and xGA over its last `TEAM_FORM_GAMES` (5) against its own
  recent-weighted level, shrunk at `TEAM_FORM_SHRINKAGE_GAMES` (15, so five
  games keep a quarter of the move) and clamped to 0.9-1.1; `xg_team_ratings`
  multiplies it into attack and defence and publishes it as `form`, so the
  card, the site and The Lineup read it with no reader change. **Props:**
  `PlayerPropsModel.team_form` (`team_form_factors`) multiplies a skater's
  expected count by his own club's last-five production and tonight's
  opponent's last-five concession of that stat, each against the club's
  record in the logs, same shrinkage, clamped to 0.85-1.18; the card passes
  the roster's club. Goalie saves are untouched (the saves context model
  already reads both clubs' recent shot rates). Constants are this lab's
  choice, made before any price was read. Measured for information on the
  bought prices (`run_shadow_stats.py --price-backtest`, variant
  `xg_shooter_home_form` against the same re-rated nightly without form;
  `run_props_form_experiment.py --team-form`); the walk-forward prices form
  night by night (`generate_prop_samples(team_form=True)`, default off, so
  every committed measurement is unchanged). Live from the 2026-10-22 card,
  the same day the team-market test restarts (`TEAM_RATINGS_FROM`). **Prop
  ledger rows frozen before 2026-10-22 were priced without form and are NOT
  set aside**, unlike saves and team markets: setting them aside would
  discard every prop opinion so far, and whether to is Cooper's call. The
  edge bars, the bracket and starter checks, the market list and the staking
  rule are unchanged.
- **2026-10-21, NOT a defect fix: rest and travel, the opponent's matchup by
  position, and tonight's posted lines are on the card (Cooper: "Okay do all
  of that and add it n", after a list of factors that included these).** All
  three are live from the 2026-10-22 card; constants are this lab's choice.
  **Rest and travel** (`rest.schedule_state`): a club with 3-10 days off is
  rested, one that crossed two or more time zones since its last rink
  travelled (`RINK_UTC_OFFSET`); `TeamModel` fits a for/against factor for
  each from its training games, shrunk as back-to-backs are, and applies it
  total-preserving, so it moves who scores and never the expected total;
  each factor is clamped to 0.9-1.1, and it applies whatever the
  back-to-back verdict says. The public board prices it the same way.
  **Matchup by position** (`PlayerPropsModel.opponent_group_factors`): a
  prop reads what tonight's opponent allows forwards or defencemen in that
  stat, falling back to the all-skater table, shrunk the same way. **Posted
  lines** (`lineups.tonight_lineups`): Gameday Refresh captures Daily
  Faceoff's lines before the card ("Capture tonight's posted lines",
  soft). For a club with at least 16 skaters posted, a skater not on its
  lines gets no opinion and is named on the card's log; everyone else's
  expected ice time comes from his line and power-play unit through
  `models.role_minutes`, blended with his own last ten, so a promoted player
  takes the higher line's minutes; and half the share of the club's last-20
  points held by recent regulars missing tonight comes off its attack,
  floored at 0.85. A club with no posted lines prices as before. The
  walk-forwards price rest/travel and position only when asked
  (`schedule=True`, `position_matchup=True`), so every committed measurement
  is unchanged; Shadow Stats prices `xg_shooter_home_form_schedule` and
  Props Form Test `--test position_matchup`, for information. The lines
  have no history before 2026-09-29 and are measured forward. The snapshot
  freezes whatever the card priced, so these change what the forward test
  scores from 2026-10-22, as last-five form does; prop rows before then are
  not set aside (Cooper's call). The edge bars, the bracket and starter
  checks, the market list and the staking rule are unchanged.
  **Line movement since the first card** (`price_movement`, same request):
  a later run that day (the 20:30 UTC re-price, a backup) reads the day's
  first priced snapshot as the open and moves each opinion half the median
  change in implied probability over books quoting it both times, at most
  five points. The first card of a day sees none, and the private movement
  chain is not read (no new token holder). Late-market rows the re-price
  adds to the snapshot carry the moved probability.
  **Referee crews** (`referees`, same request): Gameday Refresh's "Record
  tonight's referee crews" (`scripts/fetch_referees.py`, free, soft) reads
  tonight's crews from the NHL right-rail and adds past regular-season games'
  crews to `data/processed/referee_games.csv`, 300 a run newest first, so
  the history fills over the first few days. (Its first version read each
  name from the wrong key, so the first run, 2026-10-21, found no crews and
  every factor was 1.0; #348 reads `fullName.default`, as the NHL serves it.) A referee's factor is his
  games' total goals over the league's, shrunk at 120 games; a crew is the
  mean of its known referees, clamped to 0.95-1.05, and scales both clubs'
  expected goals (the total moves, the split does not) and every skater's
  goals, assists and points in that game. Penalties are read through goals
  because goals are what the bets settle on. A game with no crew posted
  when the card runs moves nothing; the public board does not read crews.
  **The pre-game update** (same request): a fourth Gameday Refresh cron,
  `30 14 * 1-4,10-12 *`, held to 22:30 UTC (6:30 PM EDT, 5:30 PM EST),
  which the precheck never stands down. It re-captures the posted lines,
  crews and starting goalies, re-prices the slate (moved with the books
  since the morning card) and posts the card again when its selections
  changed; games under way are pulled by the puck-drop guard, and the
  day's first snapshot still stands. About 290 credits on an average night
  (up to 646 at the 640 cap), about 9,000 a month; the run of 2026-10-21
  read 61,239 credits remaining.
- **2026-10-25, NOT a defect fix: the hits model is dialled in (Cooper:
  "enhance and improve the hits portion of our model. DIal it in more",
  then "i think overs could be in play a lot more often").** Four parts,
  `player_props.HITS_OPTIONS`, all on the card from the first card after
  this merges; the walk-forward prices any subset (`hits_options`, default
  none, so every committed measurement stands). **Rink:** hits are counted
  by the home club's scorer, so each club's rink factor is total hits in its
  last 82 home games over its last 82 road games (its own style cancels),
  shrunk at 20 home games, rescaled to average 1.0, clamped 0.6-1.6
  (`fit_hits_rink_factors`); every logged hit is divided by its rink's
  factor before any hits rate, baseline, opponent or form table is fitted,
  and tonight's rink's factor is multiplied back in. **Shrinkage:** a
  skater's hit rate is shrunk toward his position by an empirical-Bayes
  amount (noise over the real spread of hit rates, bounded 3,000-70,000
  seconds) instead of the 70,000 every stat shares, which pulled heavy
  hitters toward an average forward (the out-of-sample slope recorded
  above for hits was 1.80). **Recency:** a game's weight in the hit rate
  halves every 60 of the player's games. **Spread:** the negative-binomial
  dispersion for hits is measured inside each player's own games (method
  of moments around his own mean, times the rink); measured on the whole
  column it counted grinder-versus-winger as game-to-game noise, piled
  probability on 0 and 1 hits and under-priced every over. Measured
  walk-forward by `scripts/run_hits_model_study.py` (Hits Model Study
  run 40151716329, 129,419 player-games, 2023-24 to 2026-27); information
  only. Log-likelihood per player-game against the old model: +0.0607
  [+0.0584, +0.0630] for all four; rink alone +0.0005; rink with the
  own-games spread alone -0.0129 (that spread needs the lighter
  shrinkage beside it). Skaters the old model put at 2+ hits (7,382):
  predicted 2.385 old and 2.981 new, actual 2.840. On the bought hits
  prices (`card` window, 6% bar, one bet per wager): old -65.8u over
  5,249 (-1.25%), 13 of them overs; all four +125.7u over 2,621, +4.80%
  [+1.17%, +8.43%], overs -0.11% over 1,151 and unders +8.64% over
  1,470. Uncorrected, four variants tried on one dataset, and the parts
  were chosen on reasoning before this run but checked against it: not
  a demonstrated edge. The edge bars, the bracket check, the market list and
  the staking rule are unchanged; the snapshot freezes what the card
  priced, so hits opinions frozen from the next card are the new model's,
  and earlier ones are not set aside (Cooper's call).
- **2026-10-25, NOT a defect fix: PostHockey's pre-game win probability is
  blended into the team markets (Cooper asked for what PostHockey does that
  the model lacks to be wired into the card).** PostHockey rates a game on
  the players dressed (Estimated Net Rating), the listed goalies' season
  forecasts, home ice and back-to-backs, and publishes P(home wins) free at
  `posthockey.com/api/v1/live`. `scripts/fetch_posthockey_pregame.py`
  ("Record PostHockey's pre-game win probability", soft, free, before the
  card and at the pre-game update) writes it to
  `data/processed/posthockey_tonight/<day>.csv`; `posthockey.tonight_targets`
  reads the latest pre-game read per game (never a live number), and
  `TeamModel` moves goals between the sides, total held, until its moneyline
  is `posthockey.BLEND_WEIGHT` (0.5) of the way to it. Puck line and team
  totals follow; game totals do not move. `TeamModel.pregame_weight`
  defaults to 0, so every walk-forward and measurement is unchanged; the
  public board does not read it. Constants are this lab's choice, not
  measured against prices. The full read of the site and what still differs
  is `docs/posthockey_gap_list.md`.
- **2026-10-25, NOT a defect fix: tonight's listed starter prices the team
  markets (Cooper chose PostHockey's "goalie tonight" as model step 1).** The
  ratings file now also carries `team_goalie` (the GSAx(sh) factor inside
  each team's defence), `goalies` (each goalie's own GA over shooter-adjusted
  xGA, `measurement.goalie_factors` on `xga_adj`, regressed toward
  `unseen_goalie`) and `unseen_goalie` (`measurement.UNSEEN_GOALIE_FACTOR`,
  1.02: PostHockey starts an unseen goalie at -1.40 goals saved per 1,000
  shots). The card (`_listed_starters`, `team_ratings.apply_starters`) reads
  Daily Faceoff's listing for the day, matches each goalie to his NHL id
  through the logs, divides the team's goaltending out of its defence and
  multiplies the starter's in, clamped to 0.85-1.15; a listed goalie with no
  record gets the unseen factor, a club with no listing or a file without
  the goalie tables moves nothing. Attack, defence and form are unchanged
  (checked on the 2026-10-25 state: identical teams, 134 goalies).
  Not measured against prices; constants are this lab's choice.
- **2026-10-25, NOT a defect fix: the team ratings are score-adjusted
  (PostHockey's score & venue adjustment, Cooper's model step 2).** Every
  even-strength attempt is weighted (`metrics.score_weights`) so that in
  each season and score state (5v5: three or more down to three or more up;
  4v4/3v3: trailing, tied, leading) the home side's share of shooter-adjusted
  xG equals the season's home share at that strength, each state's total
  preserved; power play, penalty kill and extra attacker keep weight 1, as
  does a state under 20 xG. The textbook shares (McCurdy 2014), not
  PostHockey's talent-controlled ones; venue stays in, because the ratings
  divide it out themselves. The table gains `xgf_sva`/`xga_sva`, and
  `xg_team_ratings` builds on variant `xg_shooter_sva` whenever the table
  carries them (`score_adjusted: true` in the file; the file's `variant`
  stays `xg_shooter_gsax`, its family); goaltending still compares goals
  with unweighted xGA. Checked on the 2026-10-25 state (4,095 games): total
  xG unchanged to 1e-15, net rating moved -0.069 (OTT) to +0.025 (NYR, SJS),
  leading teams up. `xg_shooter_sva` joins the price backtest for
  information. Not measured against prices before going live.
- **2026-10-25, NOT a defect fix: tonight's dressed lineup sets each
  club's attack on player ratings (PostHockey's model step 3).** Every
  skater carries an offensive rating (`lineups.skater_ratings`): his
  offensive game score per game (0.75 goals, 0.625 assists, the mean of
  Luszczyszyn's 0.7 and 0.55 since the logs do not split them, 0.075 shots),
  over his last three seasons weighted 1/0.5/0.3 by games, with 10 games
  (forwards) or 20 (defencemen) of his position's newcomer average mixed in
  (PostHockey's Estimated Net Rating offence weights; no aging, and no
  defensive half, which needs on-ice shift data). A posted club's attack
  moves by half the gap between tonight's sheet and its usual eighteen
  (most games in its last 20), per skater, clamped 0.85-1.10; a skater with
  no record reads as a newcomer. It replaces the old points-share hole,
  which could only take attack off: a star back from injury now puts it
  on. On the 2026-10-25 logs: McDavid 111.4 per 84, newcomer forward 28.8;
  EDM without him x0.969, with him x1.027. Not measured against prices.
- **2026-10-25, NOT a defect fix: skater ratings and tonight's starting
  goalie are aged (PostHockey's model step 4).** Birth dates come from the
  rosters the card already caches (`nhl_api.current_birth_dates`).
  **Skaters:** `lineups.aging_curves` fits, per forwards and defencemen, a
  season's change in offensive game score per game as linear in age, by
  weighted least squares on consecutive seasons of the same skater (20+
  games each, harmonic-mean weights, at least 150 pairs, ages 19-38);
  `skater_ratings` moves each past season along it to his age this season
  before averaging. On the 2026-10-25 logs both curves peak at 27 (survivors
  only, as PostHockey says of its own). **Goalies:** `team_ratings.apply_starters`
  multiplies a starter's factor by exp(-term x share), term read off
  PostHockey's published goalie age curve (`GOALIE_AGE_CURVE`, logits, peak
  +0.031 at 24, -0.094 at 40) and share his own record's weight
  (`goalie_games` / (+ `goalie_shrinkage_games`) in the ratings file). Not
  built, and why: a scoring-environment term `E` would move every team's
  xG together and the ratings divide by the league mean, so it changes no
  price; an era split is moot because the lab's play-by-play starts in
  2023-24, all in PostHockey's chip era. Not measured against prices.

- **2026-10-26, NOT a defect fix: the defensive half of each skater's
  rating moves the club's defence for tonight's lineup (PostHockey's Net
  Rating has one; Cooper: "Make it perfect like Post Hockey").** Gameday
  Refresh caches the NHL shift charts (`scripts/fetch_shift_charts.py`,
  free, newest first, 800 a run, its own Actions cache), and
  `run_shadow_stats.py --tables-only` rates every skater from them
  (`shadow.defence`): his on-ice 5v5 shooter-adjusted xG against per second
  minus his team's with him off the ice, last three seasons weighted
  1/0.5/0.3, shrunk toward zero by 60,000 seconds of 5v5 ice time, times his
  own 5v5 ice time a game, sign flipped and clamped to +/-0.20 goals a game,
  published as `skater_defence` in the ratings file. `lineups._lineup_defence`
  moves a posted club's defence by half the goals tonight's sheet prevents
  beyond its usual eighteen's, over 3.0 goals a game, clamped 0.90-1.10. A
  skater with no rating counts as zero; no shift charts cached moves nothing.
  No age curve (no defensive history long enough to fit one). Not measured
  against prices; constants are this lab's choice.

- **2026-10-26: game pages, a track record and a methods page on the site
  (Cooper: "Make it perfect like Post Hockey").** Site only, plus one
  descriptive field on the card: `gameday_card.json` carries `team_factors`,
  each priced game's home win chance repriced layer by layer in the card's
  own order (`factor_breakdown.slate_breakdowns`: strength with form divided
  out, home ice, form, rest, lineup, goalies, referees, PostHockey), ending
  at the card's moneyline before line movement. It reads the model and
  changes no price, selection, stake, snapshot or ledger row. The site
  publishes it as `games[].factors` with each side's ratings, and writes
  `record.json` (calibration of published win chances against finals, Brier
  against the frozen no-vig market, and line movement after moneyline picks
  from the board's own line series; accuracy only, never a return) and
  `ratings.json` (team table, top and bottom defenders). New NHL-only pages
  `Game.dc.html`, `Record.dc.html`, `Methods.dc.html` (`web/SCHEMA.md`;
  the design drop of 2026-10-26 replaced the first drafts).

- **2026-10-26: one results page (Cooper: "transform the archive results
  pages into one big page of all our results and tracking for each
  team/player/player prop/market").** Site only. Each settled night now keeps
  its graded best bets (team picks at the card's stake, prop best bets at the
  card's stake, priced Due List entries at 0.25u notional) as `bets`
  (`build_site_json.tracker_rows`); a night kept without them is settled again
  once. `tracker.json` sums them by group, market, prop type, team, player,
  price band and month, and `Tracker.dc.html` ("All results", the design
  drop that replaced the first draft `Tracker.html`) shows them with filters,
  search and every bet; it replaces the Archive tab on the NHL pages (the
  archive is linked from it). Team picks frozen before the board recorded
  their stake count at 1u and are marked. These are the published picks the
  Results page already grades. No card, snapshot, ledger row or stake changed.

- **2026-10-26, Cooper's call: units and return are published.** The third
  page drop states it: units, win–loss records and return for every graded
  best bet are on All results, superseding the 2026-10-05 call that kept any
  return off the site until 2027-04-25 (`docs/when_this_ends.md` records it;
  the registered statistic, date and rule are unchanged).
  `tests/test_site_publishes_no_forward_return.py` was retired; what it also
  held (the schedule fetch's user agent, the empty-state wording, the
  favicon, the nav) moved to `tests/test_site_pages_hold_their_line.py`, with
  a test that the Due List is tracked and never called a bet.
  `test_record_json_has_no_return.py` is `test_record_json_carries_no_units.py`:
  the calibration page still carries no units. `record.json` gains
  `markets.total` (games by the over's published chance, against the over
  coming in), `markets.puckLine` (by the favourite's cover chance), 5-point
  bands merged to at least 10 games with Wilson intervals, and `dueList`
  (priced entries since 2026-10-09, hit rate, the price of their mean decimal
  odds and its flat-stake break-even); the drop's sealed-hash block was
  dropped with the seal. `tests/test_tracker_json_shape.py` and
  `tests/test_tracker_rows_trace_to_archive.py` pin tracker.json.

- **2026-10-26: the shared pages are pinned by tag.** Board, Results,
  Archive, Graphic, `lib/live.js`, `lib/format.js`, `lib/sports.js` and the
  team logos are one set of files in the NHL, EPL and CBB labs (and the hub,
  for the two libraries); `lib/sports.js` had already drifted three ways.
  `web/shared.lock.json` pins a tag of `cooperross399/betting-lab-shared` with
  every file's SHA-256, Publish Site copies that tag in
  (`web/sync_shared.py --from`, failing on any byte that differs, and
  publishing the committed copies with a warning when the clone fails), and
  `tests/test_shared_pages_identical.py` holds the committed copies to the
  lock. NHL stays the editing home for page drops; a drop lands in the shared
  repository, is tagged, and each lab bumps its lock by pull request.
  Logos are 128 px now (`web/fetch_logos.py` shrinks each download; about
  2.2 MB to 0.5 MB here). Pages caches every file for ten minutes and cannot
  be raised, so `web/hash_assets.py` names `support.js` and `lib/*.js` by
  content at publish and points the pages at those names.

- **2026-10-28, NOT a defect fix: the card learns from its own results
  (Cooper: "I just want it to learn from the most information possible.
  Whatever helps it make winning plays more often").** Until now every model
  refit each run on the games, and nothing fed back whether its opinions won
  against the price. `nhl_betting_lab.self_learning` fits, per market, on
  the forward ledger's settled opinions (one per wager at the best price,
  each game counting once; team markets from `TEAM_RATINGS_FROM`, saves from
  `SAVES_CONTEXT_FROM`) `logit P(win) = logit(price) + a + w * (logit(model)
  - logit(price))`, with a ridge prior of 10 toward `(0, 1)` (the card as it
  was), `w` held to 0-1.5 and `a` to +/-0.25. `run_gameday_card.py` applies
  it to the probabilities AFTER `write_snapshot`, so the ledger, what it
  learns from next time, and the 2027-04-25 test are unchanged; only edges,
  selections and stakes move. It writes `data/outputs/self_learning.md` and
  `.json`. Fitted through 2026-10-27: shots on goal w=0.81, points 0.84,
  assists 0.86, hits 0.72, total goals 0.93, the rest 0.94-1.03. Before the
  switch, Cooper's season records from the ledger at the morning best price:
  total-goals leans 87-147-15, -15.6u over 249 (234 overs); team leans
  -26.6u over 987; prop leans +131.2u over 2,927; stats-check props held
  back -3.9u over 239. Walk-forward
  (`scripts/run_self_learning_check.py`, 22 days after a week's warm-up,
  best-bet bars): card as it was +1.2u over 379, learned +17.0u over 237;
  the prior of 10 was picked on that same run (5: +10.9u over 173; 20:
  +7.1u over 303; 40: +3.9u over 338; 150: +5.3u over 369). Three weeks:
  no demonstrated edge. The model, the edge bars, the market list and the
  staking rule are unchanged.

- **2026-11-01: the site refreshes at 7:00 AM New York, and a failed live-score
  poll is quiet.** Cooper asked for both. Publish Site gains two crons (10:55
  and 11:55 UTC) and a `when` job that keeps only the one at 7 AM in New York
  that day; a 7 AM board is built on yesterday's card, so it is shown and not
  frozen. And "Live scores unavailable — retrying in 2 min" no longer shows:
  the Board shows the last update time while it retries, and a prop's live
  tracker hides until its box score loads. That page is shared, so the change
  is on `betting-lab-shared` main, pinned here as `v12.1`, a BRANCH, because
  this session could not push tags; the lock's hashes still hold it byte for
  byte. EPL and CBB stay on `v12` until the next drop fans out. A Claude Design
  drop built on an older Board would bring the message back: the next drop's
  Board should keep this behaviour.

- **2026-11-02: one tab bar on every page, and smoother tab switches.**
  Cooper: the Season tab dropped Tracker and Record and showed an Archive tab
  "which shouldnt even be a thing", and pages "visibly glitch whenever i click
  a different tab". `Season.dc.html` had its own hard-coded tabs; it now draws
  the same list as Tracker, Record and Game. Publish Site runs
  `web/smooth_pages.py` on the published pages (not the committed, pinned
  shared ones): the site's dark on `html`/`body` before anything draws (the
  blank page between tabs was the browser's white), a cross-document view
  transition, and preloads of the React files `support.js` loads. Site only.
  `tests/test_pages_move_smoothly.py`.
  **Later the same day, Props and Results still glitched** (Cooper: "When i
  click the props and results tab it still glitches"). Measured in a browser
  at 390 px: the header's Site links jumped a row when the page's data
  arrived, Board and Results drew their tabs without Props, Season, Record
  or Tracker and with an Archive tab until then, and Board opened on
  `#props` drew Tonight first. `smooth_pages.py` now also starts Board and
  Results with this site's tabs and the address's tab (exact-string
  patches to the published copies, which fail the publish if a page no
  longer holds them), keeps the Site links on their own row on a narrow
  screen, keeps a line for the date above each headline, and sizes every
  tab bar's tabs the same way. Season gained the Methods, EPL and CBB
  links, and Record, Methods and Game the 56 px tab width the others use.
  Shared pages stay pinned; a design drop that changes these strings
  turns the publish red until `PATCHES` is updated.

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
| Required status check | `Full test suite` — the `name:` of the job in `.github/workflows/tests.yml`; branch protection matches it literally |

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
  market and present all along in `alternate_totals`. Before writing off a
  market, read `data/outputs/provider_market_discovery.md`: per book, per line,
  alternate ladders included (`reports/market_discovery.discover_coverage`),
  written by `scripts/run_provider_shadow.py`. **Read the free copy first.**
  Every Gameday Refresh run that fetches a slate uploads it in the
  `gameday-reports` artifact (kept 30 days): that day's slate, props and
  ladders asked, no credit beyond the run's own budgeted fetch. That fetch's
  cap buys 16 events (8 until 2026-10-06), so a market that reads
  incomplete on a full slate is not the budget stopping. Offline,
  `scripts/run_provider_shadow.py` with no flags re-assesses whatever is
  already staged and spends nothing. For the whole posted board, the
  Provider Market Discovery workflow's "Fetch and report coverage" step runs
  `scripts/run_provider_shadow.py --live --overwrite-staging --horizon-days 0 --max-events 20 --props --credit-cap 380`
  (the step's line as run by a dispatch with `include_props` ticked and
  `credit_cap` left at its default). **That run spends up to its per-event
  cap, 380 credits by default (about 10 events at 38 credits an event), plus
  a few for the bulk markets, and like every live fetch outside the Gameday
  Refresh budget it is asked of Cooper first.** Without `--props` no prop or ladder is asked and the
  report says "not asked", which is not "not offered"; without
  `--credit-cap` the script falls back to 190 (5 events); without
  `--overwrite-staging` it stops at the first staged file it would replace.
  (Until 2026-09-26 this rule named `run_provider_market_discovery.py
  --line-coverage`, a script and a flag that have never existed.)
- **Never print, write, compare, or commit an API key.** `tests/test_no_secrets_committed.py`
  enforces this; do not weaken it. The production credential is the GitHub
  secret `NHL_ODDS_API_KEY`; `.env` is local-only. The guard scans every
  tracked path, symlink target and text body, keyed on the shape of a key and
  of an assignment rather than on a spelling, and it names what it still
  cannot see in `test_the_gaps_this_guard_still_has_are_the_ones_written_down`
  rather than claiming to be closed. `tests/test_the_guards_exist.py` and the
  collection hook in `tests/conftest.py` make deleting, renaming or
  deselecting it a red build rather than a smaller green one.
- **Never weaken a gate**, and never sign a human acceptance receipt on
  Cooper's behalf.
- **Never merge with failing CI**, and never force-push. This repository is
  public and branch protection requires the status check **`Full test suite`**
  — the `name:` of the job in `.github/workflows/tests.yml` — so nothing merges
  with it red. `tests/test_workflows.py` pins that job to the whole suite:
  it parses the workflow with `yaml.safe_load`, demands exactly one job with
  that name, no `if:`, no `needs:`, no `strategy:`, no `continue-on-error`,
  no shell override, no `if:` on any OTHER job in that file for a `needs:`
  to point at, an unfiltered `pull_request` trigger, `PYTHONSAFEPATH: "1"` in
  effect on every step of that job that starts an interpreter (not the suite
  step alone: `python -m pyflakes` resolves against the working directory too,
  and a `pyflakes.py` at the root was measured to satisfy the lint step), a
  whitelist of the arguments the suite line may carry (`-q`, `-rs`,
  `--color=no` — because `--version` narrows nothing, is in no blocklist, and
  exits 0 having run no test), and every line in `PINNED_TOOL_LINES` pinned as
  a whole command — and then executes every run block under
  stubs and reads the exit code, which is what catches
  `if ! pytest; then echo; fi`, `: python -m coverage report`, and every
  future rewording. Inside the suite, a skip, an xfail or an xpass exits 1,
  including a skip decided during collection (`tests/conftest.py`); a guard
  module that collected nothing exits 1 before a test runs, and so does a
  single guard TEST that was defined but not collected; and a narrowing flag
  is read back off pytest's own configuration rather than looked for in a
  command line, so `PYTEST_ADDOPTS` assembled from pieces is caught too. (Measured
  2026-09-05: all five labs are public and `main` is protected in every one —
  CBB requires the context `Tests`, with `enforce_admins` on and force-pushes
  and deletions refused. This used to name CBB as the exception while it was
  private; it was one for part of 2026-09-04 and is not one now.)
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
PYTHONPATH=src .venv/bin/python -m compileall -q -f src scripts tests web
.venv/bin/python -m pyflakes src scripts tests web
```

## Provider automation

Provider automation is **not trusted** unless the provider policy
(`data/manual/staging_provider_policy.json`), the acceptance checklist, and the
human acceptance receipt say it is. The shipped policy allowlists
`the_odds_api` for twelve markets under the receipt the operating state
names (the 2026-08-27 receipt for eleven,
`odds_api-20260827T165300-0400-cooperross399`, was withdrawn on 2026-08-29); the PR
gate re-verifies that
paperwork — receipt, coverage, evidence checksums — on every policy change.
Shadow runs still write to `data/staging/`, which the card reads directly
(Gameday Refresh fetches into it and cards from it in one job); eligibility
(allowlist and completeness) and freshness gate what the card may price from
there. Evidence checksums are the PR gate's check, not the card's
(`docs/provider_allowlist_approval.md`).

## What Claude decides, and what Cooper decides

Claude works autonomously on: data, models, measurement, reports, tests,
workflows, docs, and opening PRs with green CI.

Claude stops and asks for: **provider/market allowlisting approvals**, and
**anything spending API credits beyond a small measurement budget**. Those two
are Cooper's alone.

## Design drops

- Branches named design/** come from Claude Design. They may change only page files (see .github/workflows/design-drop-guard.yml) and auto-merge on green. Never rebase or edit them by hand; ask Claude Design for a new drop instead. Design Drop (`.github/workflows/design-drop.yml`) pins a changed shared page to a new tag of `cooperross399/betting-lab-shared`, merges the drop once Tests and the guard pass on its head, and moves the EPL lab, the CBB lab and the hub to that tag through `shared-sync/<tag>` pull requests merged on green. It needs the `DESIGN_DROP_TOKEN` secret. A drop that changes `web/DROP_NOTE.md` is labelled `needs-builder`: the feed change it asks for is made by a Claude Code run, never on the design branch. Claude Design has no push tool, so it uploads each drop zip to one fixed URL per site, which it overwrites: `https://cold-forest-6e14.cooperross399.workers.dev/drop/<nhl|epl|cbb>` (PUT with the drop key, which lives only as the worker secret `DROP_KEY`; GET serves the zip, `/meta` its sha256, bytes and upload time; KV namespace `DROPS`; added 2026-10-29). Design Drop Intake (`.github/workflows/design-drop-intake.yml`) reads each site's `/meta` hourly (and on dispatch), skips a sha already in that lab's `.design-drops/seen.txt`, and turns a new zip into a design/<date>-<slug>-<hash> branch and pull request in that lab (slug from the zip's `MANIFEST.json`), appending the sha to `seen.txt` in the same pull request. It serves the EPL and CBB labs too, because only this lab holds `DESIGN_DROP_TOKEN`: there it never writes a file their lock pins (shared pages reach them by shared-sync), and it merges their pull request itself when every check passes and starts their publish. Dispatched with `zip_url` and `site`, it takes that zip instead. It refuses a drop whose page sits closer to an earlier version on main than to the current one (`design_drop.py stale`): a drop built on old copies would undo newer work, as the first game-pages drop of 2026-10-26 would have.
