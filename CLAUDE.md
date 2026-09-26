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
  **measured running total** read from `x-requests-last`, which is the gate
  that cannot be mis-specified. The test that asserted the false promise was
  replaced rather than satisfied.
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
  granularity every measurement here already slices on: over-collapsing inside
  a window costs nothing the backtest can see, under-collapsing across windows
  costs a window.
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
  line, book) and never on when it was fetched.
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
  with the 23:00 round in EST, an hour out; in EDT that round lands at or
  after a 19:00 face-off and the strictly-before rule excludes it, so the
  close is the 21:00 round, two hours out. A second job
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
  nothing. Now each Line Movement run hands its closing prices over as the
  `closing-line-captures` artifact, and Closing Lines, triggered when Line
  Movement completes, merges them into that branch. That path fetches nothing
  and spends no credit. **Except the bulk team markets (found 2026-09-25):**
  the retired capture also bought `h2h`, `spreads` and `totals`, and Line
  Movement asks only for the per-event markets and their ladders, so no
  moneyline opinion can ever meet a close, and a featured puck line or total
  only when an alternate ladder repeats its line. The CLV report now names
  those opinions as uncaptured rather than as selections the books pulled;
  capturing them (3 markets x 2 regions = 6 credits a run) is Cooper's call.
- **Closing Lines is DISABLED as of 2026-09-25, pending Cooper's decision —
  do not re-enable it as a fix.** This repository is public, so the
  `closing-lines` branch would be a permanent, downloadable file of captured
  odds (book, price, line, capture time), and The Odds API's terms forbid
  redistributing their data as downloadable files that serve as raw data.
  Nothing more is lost while it is held: the per-event closing prices are a
  strict subset of Line Movement's own captures (`line_movement/<day>.csv`;
  the bulk team markets are captured nowhere — see above), which keep flowing
  through the `line-movement` artifact chain, so the store can be rebuilt from
  them. The cost is that the CLV report in Gameday Refresh reads nothing and
  says "No capture store yet". Re-enabling is one click (Actions → Closing
  Lines → Enable workflow) once Cooper decides where that file may live.
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
  Refresh fetches in the same job and never restores `data/staging/`, so no
  CI card, snapshot or ledger row changes.
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
  policy, and Experiment Refresh sends restored samples through the check.
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
  3,635,739 remaining read on 2026-09-02; at today's cap one fetch a day is
  at most 42,530. (This line said 26,091 for one fetch and 52,182 for two
  until 2026-09-25, one region's arithmetic, and "88,527 remaining" until
  2026-09-02, a figure from before the plan changed. The conclusion held
  both times.) **The Gameday Refresh per-event cap of 320 buys 8 events,
  not a full slate.** Until 2026-09-25 this line said it clipped none of the
  185 nights, as 16 games x 19 = 304 — the region factor left out, since the
  cap was set on 2026-08-28 and `us2` was added the same day. Measured
  (read-only) on the real 2026-27 club schedules, it clips **72 of the 185
  nights** and leaves **254 games** unpriced; the fetch takes the first eight
  by face-off, and on those nights every market only the per-event fetch
  prices — the seven props, the regulation three-way, team totals, 9 of the
  12 allowlisted markets — is INCOMPLETE and excluded from the card. 608 is
  the smallest cap that clips no night (16 x 38); 640 clips 0. **Raising the
  cap spends more credits and is Cooper's decision, still pending**; nothing
  here changed it. Provider Market Discovery has the same gap: its 380 buys
  10 events against a `--max-events 20`. `tests/test_periphery_markets.py`
  divides both caps by the markets asked, not by markets x regions, which is
  how it stayed green; the region-aware check fails at today's caps, so it
  waits on the same decision. The second scheduled trigger now stands down
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
  nearest nine games) and the cap is 320 against the pessimistic bound —
  eight events at two regions, short of the largest nights (the quota bullet
  above has the measurement); an asked-for market nobody quotes costs
  nothing.
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
  market and present all along in `alternate_totals`. Use
  `scripts/run_provider_market_discovery.py --line-coverage` before writing off
  a market.
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
