# NHL Betting Lab

Gated research tooling for NHL player props and team markets. It produces
measured, calibrated recommendation cards. **It never places a bet, and it
never invents a price.**

Player props are the primary product: shots on goal, points, goals (including
anytime scorer), assists, goalie saves, blocked shots, and hits — with the
alternate ladders riding the same markets. Team markets — moneyline, puck
line, totals, the regulation 3-way, and team totals — are priced and
modelled so that an edge anywhere can be found. What is deliberately *not*
wired, and why, is recorded in
[`docs/periphery_markets_decision.md`](docs/periphery_markets_decision.md).

Read [`CLAUDE.md`](CLAUDE.md) for the operating rules and
[`docs/what_we_can_and_cannot_claim.md`](docs/what_we_can_and_cannot_claim.md)
before believing any number this repository produces.

## The current answer to "does this work"

**No demonstrated edge, at full population, in either direction.** Buying
every retained event rather than a sample took the measurement to
**25,911 distinct wagers** in the four-hour window: **−0.3%, 95% interval
−1.5% to +1.0%**, which includes zero. (This line has quoted 25,949, from a
local store that no longer exists, and 25,009, from a rebuild on an
incomplete team-name map that dropped one side of every Utah game; see
`CLAUDE.md`.) The earlier +1.4% was a small sample and a
duplicated store; a later **−1.6% over 73,918** counted each of the ~2.8 book
quotes on one selection as its own bet, which measured a strategy the card
would never run and narrowed every interval by about √2.8. One wager is now
one bet at the best price the card could have taken. Best-of-N is
optimistically biased the other way, so those two numbers bracket the truth;
both ends are at or below zero.

Nothing survives correction *and* replicates. `points` (−4.4% over 6,194
wagers) and `blocked_shots` (+4.9% over 4,286) both survive correction on
the pooled window. `points` also survives within 2025-26 alone and is not
confirmed on 2024-25; `blocked_shots` survives within neither season. So
neither survives correction and then replicates. This line used to call
`points` a replicated loss; that came from a replication record built by
counting every book's quote as a bet.

The mechanism is understood rather than merely observed. The model is
**overconfident by 9 to 12 points on exactly the bets it selects** — it says
65%, the truth is 53% — while being calibrated overall, which is the
signature of a selection effect rather than a broken model. Regressing the
outcome on both views gives the market a coefficient of 0.97 and the model
0.03 with an interval spanning zero: **when the two disagree, the market is
right and the model's disagreement carries no information.** Line shopping
across eight books was tested too and there is nothing to harvest.

`data/manual/staging_provider_policy.json` nevertheless allowlists twelve
markets, at Cooper's decision and against the evidence bundle's own
recommendation, so the card does post selections: recommendations from a
model with no demonstrated edge, and every report says so. The full account is in
[`docs/why_the_model_has_no_edge.md`](docs/why_the_model_has_no_edge.md);
`data/outputs/what_we_can_claim.md` is regenerated every run and always says
what the measurements actually support.

## Setup

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e .
```

The production credential is the GitHub secret `NHL_ODDS_API_KEY`. For local
work only, copy `.env.example` to `.env`, fill it in, and `chmod 600 .env`. The
key is never printed, written, compared, or committed;
`tests/test_no_secrets_committed.py` enforces that.

## Commands

Every command below is read-only with respect to bets, policy, and receipts.
The two that spend credits say so and require an explicit flag.

### Data — free, public, no credential

```bash
# Fetch schedules, boxscores and the player-name registry. A completed game is
# never refetched, so a second run over the same window costs almost nothing.
PYTHONPATH=src .venv/bin/python scripts/fetch_nhl_data.py

# Rebuild the processed tables from the cache. No network access at all.
PYTHONPATH=src .venv/bin/python scripts/build_datasets.py
```

### Measurement — offline, no credits

```bash
# Walk-forward calibration -> data/outputs/props_calibration.md
PYTHONPATH=src .venv/bin/python scripts/run_props_calibration.py

# Price-based backtest -> data/outputs/player_props_backtest.md
PYTHONPATH=src .venv/bin/python scripts/run_player_props_backtest.py

# Did a result on one window hold on another? -> data/outputs/replication.md
PYTHONPATH=src .venv/bin/python scripts/run_replication.py \
    --discovery data/outputs/player_props_backtest_2025-26.json \
    --test data/outputs/player_props_backtest_2024-25.json

# Team markets, calibrated and priced -> data/outputs/team_markets_measurement.md
PYTHONPATH=src .venv/bin/python scripts/run_team_markets_measurement.py

# What the evidence supports -> data/outputs/what_we_can_claim.md
PYTHONPATH=src .venv/bin/python scripts/run_what_we_can_claim.py

# Modern stats (Corsi, Fenwick, xG, PDO, GSAx, iCF/ixG) as a shadow model,
# never on the card -> data/outputs/shadow_stats.md. --fetch downloads the
# free NHL play-by-play for every game not yet cached.
PYTHONPATH=src .venv/bin/python scripts/run_shadow_stats.py --fetch
```

### The card — offline, gated

```bash
# Prices whatever the policy allows and recommends only where the measured
# bars clear; a slate with no qualifying edge yields a card with no
# selections that says why. Every priced opinion is also frozen into
# data/archive/priced_snapshots/ — the day's first opinion stands, never
# repriced.
PYTHONPATH=src .venv/bin/python scripts/run_gameday_card.py

# Settle pending snapshots against final boxscores and rebuild the
# accumulating forward-evidence report. Offline; only ever appends.
PYTHONPATH=src .venv/bin/python scripts/run_forward_evidence.py

# Score every frozen opinion against the market's last word before puck drop.
# Offline: it reads the capture store, fetches nothing, spends nothing.
PYTHONPATH=src .venv/bin/python scripts/run_closing_line_value.py

# Decide whether the card is worth an email and write the comment body.
PYTHONPATH=src .venv/bin/python scripts/post_card_to_issue.py --out comment.md
```

### Provider — the two that touch the network

```bash
# Confirm the credential is present. Costs no quota; prints only its length.
PYTHONPATH=src .venv/bin/python scripts/check_provider_credential.py

# How many credits are left. The /v4/sports listing is documented as free.
PYTHONPATH=src .venv/bin/python scripts/check_provider_quota.py

# Which NHL markets does the provider actually serve? Probes each candidate
# individually, so one bad name cannot hide the others.
PYTHONPATH=src .venv/bin/python scripts/discover_nhl_markets.py --live \
    --credit-cap 120

# Assess whatever is already staged. No credits.
PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py

# Live shadow fetch. Team markets are a handful of credits; props are one
# credit per market per region per event and the cap is hard: 19 markets at
# the default two regions count 38 credits an event, so 190 buys 5 events.
# The card reads what this stages, through the policy's gates.
PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py --live --props \
    --credit-cap 190

# Record the market's current best price on every selection, for closing-line
# value. Run repeatedly through the evening; the closing price for a game is
# the last capture strictly before its start.
PYTHONPATH=src .venv/bin/python scripts/capture_closing_lines.py --live \
    --credit-cap 400

# Merge two copies of the capture store without losing a row. Used by the
# private store's push on every day file it writes.
PYTHONPATH=src .venv/bin/python scripts/merge_capture_store.py \
    --mine mine.csv --theirs theirs.csv --out store.csv

# Push this run's closing prices to the PRIVATE store
# (cooperross399/nhl-closing-lines), or pull the whole store into a file
# outside the workspace for the CLV report. Needs NHL_CLOSING_LINES_TOKEN.
# A push refuses this public repository as a target, and any target the
# GitHub API does not call private; a pull refuses to write inside the
# workspace. Closing Lines and Gameday Refresh run it.
PYTHONPATH=src .venv/bin/python scripts/private_closing_store.py push \
    --processed-dir data/processed
PYTHONPATH=src .venv/bin/python scripts/private_closing_store.py pull \
    --out "$RUNNER_TEMP/private-closing-store/closing_line_captures.csv"

# Line Movement's capture chain, kept on branch `movement` of the same private
# repository (stage one of the move, 2026-10-02). Every Line Movement round
# folds the private copy into what it restored; from the default branch it
# also pushes its three stores and checks the private tip holds every row it
# uploaded publicly (a feature-branch dispatch only reads). Needs
# NHL_CLOSING_LINES_TOKEN.
PYTHONPATH=src .venv/bin/python scripts/private_movement_chain.py pull --dest data/processed
PYTHONPATH=src .venv/bin/python scripts/private_movement_chain.py push --processed-dir data/processed
PYTHONPATH=src .venv/bin/python scripts/private_movement_chain.py verify --processed-dir data/processed
```

# Rebuild the price CSVs from the raw cached responses. Free, and the reason
# a clobbered file is a five-minute recovery rather than a re-purchase.
PYTHONPATH=src .venv/bin/python scripts/rebuild_price_files.py

# Capture today's board again, so line MOVEMENT becomes observable. Every
# price this lab ever held was taken once, four hours before puck drop, and
# a single observation cannot show a line moving. Writes only under
# data/processed/line_movement/ — never staging, never the ledger.
PYTHONPATH=src .venv/bin/python scripts/capture_line_movement.py --live \
    --credit-cap 600

# Capture who is NOT playing, and when that became knowable. Free: the NHL's
# own API, no provider credits. Runs in the same job as the price capture so
# the two share an instant and can be joined — which is what makes "was the
# scratch public before the market moved?" answerable a season from now.
PYTHONPATH=src .venv/bin/python scripts/capture_deployment.py

# Capture who was PROMOTED, and when that became knowable. The other half of
# the deployment signal: scratches say who is out, this says who moved up to
# the first line or the top power-play unit — the "usage about to rise" event
# that costs the model -6.44% over 5,661 bets. Free, no provider credits,
# game days only, polite delay. CANNOT be collected retroactively.
PYTHONPATH=src .venv/bin/python scripts/capture_line_combinations.py

# Scan the captured ladders for a book contradicting ITSELF: quoting a harder
# threshold as likelier than an easier one, which no view about hockey is
# needed to see. Free, reads only what is already captured. Counts occurrences
# and states the denominator; it settles nothing and reports no return. The
# return test is registered in docs/pre_registered_ladder_coherence.md.
PYTHONPATH=src .venv/bin/python scripts/run_ladder_coherence.py

### Historical prices — the expensive one

```bash
# Free: print what a purchase would cost and stop.
PYTHONPATH=src .venv/bin/python scripts/buy_historical_props.py \
    --from 2025-01-05 --to 2025-01-05

# Which prop markets does the provider retain at all? Probes --probe-events
# events (five by default) spread across the window. Each one not already
# bought is gated at up to 10 x markets x regions (140 at the defaults) before
# it is asked, and the day listings come out of the same cap, so a cap of 60
# probes only what the cache already holds.
PYTHONPATH=src .venv/bin/python scripts/buy_historical_props.py \
    --probe --live --from 2026-01-10 --to 2026-01-10 --credit-cap 60

# Free: which (event, snapshot) pairs the raw cache holds. Pick one the
# store has, so the venues are compared at the same moment.
PYTHONPATH=src .venv/bin/python scripts/probe_low_vig_venues.py --list-events

# Free: print what the venue probe would ask, and its worst case, and stop.
PYTHONPATH=src .venv/bin/python scripts/probe_low_vig_venues.py

# One event, one snapshot, capped: do Pinnacle, Novig, ProphetX and Betfair
# quote NHL player props at all, and at what margin? The venues outside
# `us,us2`. Also runnable as the manual-dispatch Venue Probe workflow.
PYTHONPATH=src .venv/bin/python scripts/probe_low_vig_venues.py \
    --live --credit-cap 400
```

# Team markets, from the bulk endpoint — far cheaper, per snapshot not per event
PYTHONPATH=src .venv/bin/python scripts/buy_historical_team_prices.py \
    --from 2024-10-08 --to 2026-04-15
```

Props: between one and ten credits per market per event, per region, and the
lab asks two regions (`us,us2`). The provider documents ten for its bulk
historical endpoint and is ambiguous about the per-event one, so the real rate
is read from `x-requests-last` as it is spent and the cap is enforced against
the pessimistic reading; measured, it is ten per market returned, per region.
Team markets come from the bulk historical endpoint at `10 x markets x regions`
**per snapshot**, so a whole slate costs sixty credits at the lab's two regions
(`us,us2`) whether it holds four games or fourteen. Either way this is a
spending decision rather than a default.

### Gates and tests

```bash
# Assemble everything a human needs to decide on allowlisting a market.
# Read-only: it writes no receipt and approves nothing.
PYTHONPATH=src .venv/bin/python scripts/run_allowlist_evidence.py

# Decide whether a calibration correction ships, against real prices, with
# the verdict recorded to disk for the card's gate to read.
PYTHONPATH=src .venv/bin/python scripts/run_correction_experiment.py

# Decide whether the back-to-back rest adjustment ships, the same way.
PYTHONPATH=src .venv/bin/python scripts/run_rest_experiment.py

# The same decision for the props side of rest.
PYTHONPATH=src .venv/bin/python scripts/run_props_rest_experiment.py

# The provider policy PR gate. Exits non-zero when the paperwork does not hold.
PYTHONPATH=src .venv/bin/python scripts/run_policy_pr_gate.py

# Do the experiments still decide what the repository says they decided?
# Compares the verdicts produced now against the ones committed. Reads and
# reports; never edits a live verdict. Exit 1 means something moved.
PYTHONPATH=src .venv/bin/python scripts/check_verdict_drift.py

PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m compileall -q -f src scripts tests web
```

`pytest -q` over the whole suite is the only run there is. A subset run — a
path, `-k`, `-m`, `--ignore`, `--ignore-glob`, `--deselect`, an `addopts` in
`pyproject.toml`, or the same through `PYTEST_ADDOPTS` — exits 1 before a test
runs. The narrowing flags are read back off pytest's own configuration rather
than looked for in a command line, so they read the same however they were
assembled; a positional path is caught by its effect, when a hard-rule guard
collects nothing. Losing one test of a guard is caught too: the floor is per
TEST, comparing what each guard module defines on disk against what the run
collected (`tests/conftest.py`, `tests/test_the_guards_exist.py`).

A run with a skip, an xfail or an xpass in it exits 1 as well — including a
skip decided during COLLECTION, which is the shape a module-level
`pytest.skip(allow_module_level=True)` or `pytest.importorskip` takes and
which the run-time hook alone was measured not to see. There is no exemption
list.

CI's required status check is the job named **`Full test suite`**, and
`tests/test_workflows.py` pins that job to this same invocation by parsing the
workflow and executing its run blocks under stubs: the suite line may carry
only `-q`, `-rs` or `--color=no` and must be launched by `python -m coverage
run -m pytest`; the job may carry no `if:`, `needs:` or `strategy:`, and no
other job in that file may carry an `if:` for a `needs:` to point at; every
line in that file's `PINNED_TOOL_LINES` is pinned as a whole command and
observed under stubs to be reached; and every step of the job that starts an
interpreter must have `PYTHONSAFEPATH: "1"` in effect, which keeps the checkout
ROOT off `sys.path` so a `coverage.py` or `pyflakes.py` sitting there is not
the tool that runs. It does not touch the explicit `PYTHONPATH: src`.
`tests/test_the_guards_exist.py` refuses the TRACKED half of both places; an
untracked file on the `PYTHONPATH` entry is reached by neither, and is executed
as a known gap there rather than described as covered.

## Where the card comes from

GitHub Actions, not a laptop. **Gameday Refresh**
(`.github/workflows/gameday-refresh.yml`) runs daily in season and posts each
card to the pinned issue **NHL Betting Lab — Claude Operating Home**. When the
selections differ from the previous card, the comment's first paragraph
contains the phrase `Selections changed`.

**Closing Lines** (`.github/workflows/closing-lines.yml`) keeps the best price
on every selection in a **private repository, `cooperross399/nhl-closing-lines`**,
one file per UTC day. This repository is public, and a store here (a branch, a
release, a Pages site or an artifact) would be a downloadable odds file, which
the provider's terms forbid. Closing Lines buys nothing on its own schedule:
Line Movement Capture's fetch already carries the prices, so Closing Lines runs
each time Line Movement completes, reads the `line-movement` artifact that run
kept, derives the best price per selection per round from every day it
carries, and pushes those rows to the private store, the bulk moneyline, puck
line and total included (each Line Movement round asks for them beside the
per-event markets). An opinion in a market no round priced before face-off,
such as a day captured before the bulk request was added or a round whose bulk
request failed, is named as uncaptured rather than as a price the books pulled.
It can still be dispatched by hand to force a paid capture. The push and
Gameday Refresh's read both use the Actions secret
**`NHL_CLOSING_LINES_TOKEN`**: a fine-grained token limited to
`cooperross399/nhl-closing-lines` with Contents read and write. Closing Lines
stays disabled until that secret exists.

**Not yet private, moving in two stages:** the `line-movement` artifact the store
is derived from is itself a public artifact holding every captured price. Since
2026-10-02 (stage one) each Line Movement round also keeps its three stores in
the private repository's `movement` branch and checks the private copy holds
every row it uploads publicly, and the public copies are kept 7 days instead of
90. Stage two drops the public upload once rounds verify clean. CLAUDE.md
records both.

Gameday Refresh pulls the private store into the runner's temp directory
(never into `data/processed`, which it uploads publicly as `gameday-state`),
restores the `line-movement` chain beside it, and scores the union of the two
into `data/outputs/closing_line_value.md`: beat-the-close rate, CLV%, and the
de-vigged expected value at the closing line, for opinions and for bets
separately (a "bet" there, as in the forward-evidence report, is an opinion
clearing the 6% prop / 3.5% team measurement bar, not a bet the card staked), with every interval clustered by game (one game's sides, rungs
and players are not independent trials). The report is aggregate: counts,
rates and intervals, never a price, a line or a book. It is the earliest honest
signal that the model is finding something — and it is not profit, which the
report says out loud.

Every run — including a "skip" run — also publishes the rendered comment, a
one-object status file, and the forward-evidence report to the **`card-feed`
branch** (`latest_card_comment.md`, `latest_status.json`,
`latest_forward_evidence.md`). That branch is how the scheduled cloud
routines read the card and track the season without any GitHub API
credential: a cloud session cloning this repository sees it over plain git.
A day with no new `card-feed` commit means the workflow itself did not
finish.
Only runs on the default branch post to the operating home or publish to
`card-feed`: a run dispatched on a feature branch builds and gates the card
as a rehearsal and publishes nothing, and the status line names the ref that
wrote it so the backup's precheck counts only a card `main` published.

Each run starts from the previous run's state, restored by
`scripts/restore_state.py` from the newest run on `main` that actually carries
the `gameday-state` artifact — whatever its conclusion, with the newest
successful state laid underneath a red one. A listing or download GitHub does
not answer is tried three times, and one that still fails makes the run
degraded rather than reading as "nothing to restore": one HTTP 502 used to
restore the purchase's state instead, which has no snapshot archive, so the
day's frozen snapshot never settled and the green run passed the gap on for
good. A red run is what makes the next restore lay the last good state
underneath it. A run dispatched on a feature
branch is never a source: it ran code nobody reviewed, and Line Movement's
only unexpired artifact on 2026-09-25 was such a rehearsal, which would have
seeded the season's capture chain. Choosing "the newest successful run" picked a
skipped backup run (a success with no artifact) and threw away every degraded
run's cache and frozen snapshot. Line Movement Capture restores its captures
the same way, and then unions every day file, row by row, with the two
carriers before the newest (`--union 3`): a red run's scratch list and line
units used to fall out of the chain, and a run whose own restore found nothing
must not become the base the season is lost from. Historical Props Purchase
restores its bought prices and its state with `--refuse-unreachable`. If
GitHub cannot be asked, the run stops before it spends a credit or uploads
anything. Only an answer that no run carries them starts it without them: one
HTTP 502 used to read as "no purchase carries bought prices", and the run
bought the window again and uploaded a thin copy as the newest carrier.

| Workflow | Trigger | Spends credits |
|:---------|:--------|:---------------|
| Tests | every PR and push to main | no |
| Provider Policy PR Gate | PRs touching policy or receipts | no |
| Gameday Refresh | daily in season at 13:30 UTC, backup 15:00 (each cron fires eight hours early and `scripts/wait_for_round.py` holds the run until its slot); on demand, at once | yes, capped |
| Closing Lines | disabled until `NHL_CLOSING_LINES_TOKEN` exists; then after every Line Movement run, and by hand | only when dispatched by hand, capped |
| Provider Market Discovery | on demand; once on 15 October, which asks the three bulk markets only (props, ladders and candidates need a dispatch) | yes, capped |
| Historical Props Purchase | on demand only, never scheduled | yes, capped, required cap |
| Venue Probe | on demand only, never scheduled | yes, capped, required cap |
| Line Movement Capture | five rounds daily in season (14:00, 18:00, 21:00, 23:00, 01:00 UTC): each cron fires eight hours early and `scripts/wait_for_round.py` holds the run until its round, because GitHub starts scheduled runs hours late; by hand, now or at a set `at` time | yes, capped |
| Experiment Refresh | weekly; after the bought prices expire from CI (2026-11-29), it skips the experiments with a notice | no |
| Publish Site | daily, and after each Gameday Refresh | no |
| Season Sim | daily at 13:05 UTC, before the site builds; on demand | no |
| Shadow Stats | on demand, and on PRs that change `src/nhl_betting_lab/shadow/` | no |

The site's **Season** page (`web/Season.dc.html`) is fed by **Season Sim**, which plays the rest of the regular season 10,000 times every morning from public data only — the NHL API for standings, rosters, club schedules and season-to-date skater and goalie stats, MoneyPuck for expected goals — plus the hand-kept availability list in `data/season_sim/roster_notes.json` (injured regulars expected back, opening goalie depth charts, rookies' ice time). `python web/build_season_json.py --out DIR` builds it locally (`--cache` keeps the fetched inputs, `--sims` sets the count); the model is under `web/season_sim/` and the file it writes is described in `web/SCHEMA.md` under `season.json`. The workflow uploads that file as the `season-sim` artifact, and Publish Site lays the newest successful run's copy over the committed baseline at `web/data/season.json`; when none can be restored the page keeps the baseline and labels its age, and the board is published regardless. It is a projection of the standings, published as one: no price is read, no credit is spent, and nothing on it is a pick.

The public site is deployed from `web/` by **Publish Site**, which reads the lab's own outputs and the NHL's free schedule API, and deploys through the Pages API without pushing to any branch. Its history (each day's frozen board, which Results settles against, and the line series) comes from the newest successful publish's `site-history` artifact through `scripts/restore_state.py --success-only --require-newest`, and `scripts/site_history_floor.py` refuses to keep or deploy a history holding less than the one restored. A run that cannot restore the history fails without deploying, and the site keeps its last build: a failed API call used to read as "the history starts today" and truncate the public archive for good. Only a dispatch with `start_history_afresh` starts it over deliberately. It joins market lines and the card's picks through the staged prices, which since 2026-09-29 travel in `gameday-state` (PR #275): the day's live quotes — hundreds of team rows and thousands of prop rows, per book — in a public 90-day artifact, under the same stance as the rest of that state; that provider prices appear on the public page was decided there. The board reads only the rows whose `commence_time` falls on its own league day (`todays_rows`), so a build that restores an earlier day's state publishes those games unpriced rather than under that day's quotes, and a game the build holds no price for says "Not priced" rather than being called a pass. The forward ledger shows its size in wagers and never its return; no season accuracy record is tallied, so none is shown. The lab's state comes from the newest Gameday Refresh run that carries `gameday-state`, through `--require-listing --listing-attempts 3`: a listing that never answers stops the run before anything is built or frozen, where one HTTP 502 used to read as "no run carries the state" and freeze the schedule alone as the day's board. A listing that answers with no carrier still builds the schedule, and the next morning's Results says that board had no projection to settle.

**Experiment Refresh** re-runs the three experiments every Monday and opens a pull request when a verdict moves. Every experiment reads the bought prices, which exist in CI only in Historical Props Purchase's artifacts (newest carrier run 33450963332, expiring 2026-11-29); on 2026-09-25 the owner decided to let them expire rather than give them another home, because this repository is public and the provider's terms forbid redistributing bought prices as downloadable files. From then on, when GitHub answers and no run on main still carries `historical-props` or the purchase's `gameday-state`, the refresh restores the boxscores, builds the tables and samples, skips the experiments and the drift check with a `::notice::`, uploads no evidence artifact, and finishes green; the committed `data/outputs/*_experiment.json` and `*_experiment.md` stand as they were committed, and `verdicts.ships()` reads them unchanged. A listing that fails, a carrier whose download fails, or a carrier that restores and brings no prices still fails the run. To re-decide after the expiry, run the same commands locally in a checkout whose `data/processed` holds `historical_prop_prices.csv` and `historical_team_prices.csv`: `PYTHONPATH=src .venv/bin/python scripts/build_datasets.py`, `scripts/run_props_calibration.py --reuse-samples`, `scripts/run_correction_experiment.py`, `scripts/run_rest_experiment.py`, `scripts/run_props_rest_experiment.py`, then `scripts/check_verdict_drift.py`.

## Safety boundaries

- No bet is ever placed, and no betting is ever automated.
- A missing price stays missing; an excluded market is never reported as a
  pass, an avoid, or a no-value call.
- A selection whose game has started — or whose start cannot be confirmed — is
  quarantined and its stake removed. See
  [`docs/puck_drop_guard.md`](docs/puck_drop_guard.md).
- No market reaches the card without measurement against real prices and a
  reviewed human approval. Claude prepares the evidence and stops.
- Every measured number is printed with its sample size, and an interval that
  includes zero is reported as *no demonstrated edge*.

## Documents worth reading

| Document | What it is for |
|:---------|:---------------|
| [`CLAUDE.md`](CLAUDE.md) | The hard rules, and the contract strings |
| [`docs/project_status_for_claude.md`](docs/project_status_for_claude.md) | Where the lab is and what to do next |
| [`docs/what_we_can_and_cannot_claim.md`](docs/what_we_can_and_cannot_claim.md) | The rules for reading any number here |
| [`docs/nhl_data_sources.md`](docs/nhl_data_sources.md) | Every source, and what it cannot tell us |
| [`docs/puck_drop_guard.md`](docs/puck_drop_guard.md) | Why a started game can never be a play |
| [`docs/when_this_ends.md`](docs/when_this_ends.md) | The pre-registered stopping rule, and the date |
| [`docs/the_venue_route_is_closed.md`](docs/the_venue_route_is_closed.md) | Pinnacle and the exchanges, priced: dearer, or no props at all |
| [`docs/pre_registered_over_side_drop.md`](docs/pre_registered_over_side_drop.md) | A hypothesis registered before the season, and what would settle it |
| [`docs/why_a_lineup_feed_cannot_fix_the_cell.md`](docs/why_a_lineup_feed_cannot_fix_the_cell.md) | The deployment route, priced before it was bought: no detector specification exists |
| [`docs/pre_registered_ladder_coherence.md`](docs/pre_registered_ladder_coherence.md) | The last open route, registered before it could be fitted: books that contradict their own ladders |
| [`docs/goalie_props_need_a_confirmed_starter.md`](docs/goalie_props_need_a_confirmed_starter.md) | A measurement that was asking the wrong question |
| [`docs/why_ice_time_gets_its_own_correction.md`](docs/why_ice_time_gets_its_own_correction.md) | The mechanism behind the conditional correction |
| [`docs/provider_allowlist_approval.md`](docs/provider_allowlist_approval.md) | How a market becomes trusted |
| [`docs/claude_autonomy_operating_model.md`](docs/claude_autonomy_operating_model.md) | How Claude works here, and the two hard stops |
