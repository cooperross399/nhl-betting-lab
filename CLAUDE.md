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
- **The lab measures one thing and ships another, by five and a half hours.**
  Every historical price was bought at a median **4.0 hours** before face-off
  (p10 4.0, p90 4.0). The production card runs **9.5 hours** before a 19:00
  ET face-off, its backup 8.0. So every number here describes a window the
  card does not operate in. It is the stale-minutes finding in structural
  form: at four hours the lineup is largely known, at nine and a half it is
  guessed, and the card is priced in the poorer window while the measurement
  was taken in the richer one. Being bought and measured, not argued about.
- **A store holding two windows now refuses to be measured as one.**
  `stores.label_phases` derives hours-before-face-off from the snapshot, the
  backtest auto-detects the window and **raises** if the store holds more
  than one, and every report states the window it describes. Without it the
  best-price collapse would take the better of a four-hour and a nine-hour
  quote for one wager — a price nobody could have taken. The first version of
  this guard hardcoded a window that matched nothing and fell through
  silently, measuring the mixture it was written to prevent; it now
  auto-detects.
- **The model is 0.34 points from break-even, and the remaining loss is one
  cell.** Betting every wager it has an opinion on returns −2.70% over
  100,805; its own selection returns −0.34% over 26,091, so the selection is
  worth **+2.35 points**. An earlier version of this file said the model
  carried no information — that was true of the *magnitude* of its
  disagreement and false of the model, and the two were conflated.
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
  demonstrated edge on it — in either direction.** 2,710 events, 1,261,440
  price rows collapsing to **25,949 distinct wagers** at the shipped bar:
  **−0.3%, 95% interval −1.5% to +0.9%**, which includes zero. The earlier
  +1.4% came from a 192-event sample thirty times smaller and was noise.
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
  Per market at one bet per wager: `points` **−4.4% (6,202)** still excludes
  zero and still survives correction; `goalie_saves` −2.5% (1,733) now
  **spans zero**, where per-quote counting had it as a demonstrated loss;
  `shots_on_goal` +1.3% (9,395, spans zero); `assists` −1.4% (3,762, spans
  zero); `goals` −6.8% (564, spans zero). `blocked_shots` is the only
  positive at +5.0% over 4,293 — and it **failed replication**: same
  direction on the unseen window but its own interval includes zero, and a
  window that merely fails to contradict is not confirmation. The only
  result that survives correction *and* replicates is `points`, a
  demonstrated deficit rather than an edge.
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
  one bet per wager: moneyline **+0.0% over 1,366** (−8.2% to +8.2%), puck
  line **−1.3% over 1,762** (−5.7% to +3.2%), totals **−2.5% over 2,201**
  (−6.5% to +1.6%). Every interval includes zero. Match rate is 96% on all
  three after the line grid was widened to every line the full buy actually
  holds — totals from 2.0 to 13.5, puck lines to 6.5 — because a line the
  grid does not carry is a price the measurement silently discards, which is
  how a third of the bought totals once vanished.
- **The thin sample's +9.1% totals was noise, and the full buy proves it.**
  On 217 wagers totals read +9.1%; on 2,201 it reads −2.5%. That is what a
  small sample does when repriced, and it is the reason a number is never a
  finding until the sample can carry it.
- **The same data counted per QUOTE says all three are demonstrated losses.**
  Run without the collapse, the full store gives moneyline −7.3% over 17,937,
  puck line −5.4% over 19,418, totals −5.0% over 14,971 — every interval
  excluding zero and surviving the family correction. Per wager, all three
  span zero. Twenty-one books quoting one game is not twenty-one bets, and
  the distortion is large enough to manufacture three demonstrated losses out
  of three null results. It is the clearest demonstration in this repository
  of why `stores.best_price_per_wager` exists.
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
  trusting its silence. `closing-lines.yml` has **no cron at all** — it works
  when dispatched and would never capture on its own, so the CLV machinery is
  dormant until Cooper decides whether a standing ~24,600-credit season is
  worth a diagnostic.
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
