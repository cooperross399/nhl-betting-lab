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
every retained event rather than a sample took the measurement to 1,261,440
prices over **25,949 distinct wagers**: **−0.3%, 95% interval −1.5% to
+0.9%**, which includes zero. The earlier +1.4% was a small sample and a
duplicated store; a later **−1.6% over 73,918** counted each of the ~2.8 book
quotes on one selection as its own bet, which measured a strategy the card
would never run and narrowed every interval by about √2.8. One wager is now
one bet at the best price the card could have taken. Best-of-N is
optimistically biased the other way, so those two numbers bracket the truth;
both ends are at or below zero.

The one result that survives correction *and* replicates is a **loss**:
`points` at −4.4% over 6,202 wagers. `blocked_shots` is the only positive
and it failed replication.

The mechanism is understood rather than merely observed. The model is
**overconfident by 9 to 12 points on exactly the bets it selects** — it says
65%, the truth is 53% — while being calibrated overall, which is the
signature of a selection effect rather than a broken model. Regressing the
outcome on both views gives the market a coefficient of 0.97 and the model
0.03 with an interval spanning zero: **when the two disagree, the market is
right and the model's disagreement carries no information.** Line shopping
across eight books was tested too and there is nothing to harvest.

`data/manual/staging_provider_policy.json` therefore allowlists nothing, the
card produces no selection, and re-enabling anything needs a fresh human
receipt signed against the evidence as it now reads. The full account is in
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
# credit per market per event and the cap is hard.
PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py --live --props \
    --credit-cap 190

# Record the market's current best price on every selection, for closing-line
# value. Run repeatedly through the evening; the closing price for a game is
# the last capture strictly before its start.
PYTHONPATH=src .venv/bin/python scripts/capture_closing_lines.py --live \
    --credit-cap 400

# Merge two copies of the capture store without losing a row. Used by the
# workflow when a push collides with a capture that landed first.
PYTHONPATH=src .venv/bin/python scripts/merge_capture_store.py \
    --mine mine.csv --theirs theirs.csv --out store.csv
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

### Historical prices — the expensive one

```bash
# Free: print what a purchase would cost and stop.
PYTHONPATH=src .venv/bin/python scripts/buy_historical_props.py \
    --from 2025-01-05 --to 2025-01-05

# One event: find out which prop markets the provider retains at all.
PYTHONPATH=src .venv/bin/python scripts/buy_historical_props.py \
    --probe --live --credit-cap 60
```

# Team markets, from the bulk endpoint — far cheaper, per snapshot not per event
PYTHONPATH=src .venv/bin/python scripts/buy_historical_team_prices.py \
    --from 2024-10-08 --to 2026-04-15
```

Props: between one and ten credits per market per event. The provider documents ten
for its bulk historical endpoint and is ambiguous about the per-event one, so
the real rate is read from `x-requests-last` as it is spent and the cap is
enforced against the pessimistic reading. Team markets come from the bulk
historical endpoint at `10 x markets x regions` **per snapshot**, so a whole
slate costs thirty credits whether it holds four games or fourteen. Either way
this is a spending decision rather than a default.

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

PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m compileall -q src scripts
```

## Where the card comes from

GitHub Actions, not a laptop. **Gameday Refresh**
(`.github/workflows/gameday-refresh.yml`) runs daily in season and posts each
card to the pinned issue **NHL Betting Lab — Claude Operating Home**. When the
selections differ from the previous card, the comment's first paragraph
contains the phrase `Selections changed`.

**Closing Lines** (`.github/workflows/closing-lines.yml`) runs hourly through
the puck-drop window and records the best price on every selection into its
own **`closing-lines` branch**. Gameday Refresh reads that store and writes
`data/outputs/closing_line_value.md`: beat-the-close rate, CLV%, and the
de-vigged expected value at the closing line, for opinions and for bets
separately. It is the earliest honest signal that the model is finding
something — and it is not profit, which the report says out loud.

Every run — including a "skip" run — also publishes the rendered comment, a
one-object status file, and the forward-evidence report to the **`card-feed`
branch** (`latest_card_comment.md`, `latest_status.json`,
`latest_forward_evidence.md`). That branch is how the scheduled cloud
routines read the card and track the season without any GitHub API
credential: a cloud session cloning this repository sees it over plain git.
A day with no new `card-feed` commit means the workflow itself did not
finish.

| Workflow | Trigger | Spends credits |
|:---------|:--------|:---------------|
| Tests | every PR and push to main | no |
| Provider Policy PR Gate | PRs touching policy or receipts | no |
| Gameday Refresh | daily in season, and on demand | yes, capped |
| Closing Lines | hourly through the evening in season | yes, capped |
| Provider Market Discovery | on demand | yes, capped |
| Historical Props Purchase | on demand only, never scheduled | yes, capped, required cap |
| Line Movement Capture | several times daily in season | yes, capped |

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
| [`docs/goalie_props_need_a_confirmed_starter.md`](docs/goalie_props_need_a_confirmed_starter.md) | A measurement that was asking the wrong question |
| [`docs/why_ice_time_gets_its_own_correction.md`](docs/why_ice_time_gets_its_own_correction.md) | The mechanism behind the conditional correction |
| [`docs/provider_allowlist_approval.md`](docs/provider_allowlist_approval.md) | How a market becomes trusted |
| [`docs/claude_autonomy_operating_model.md`](docs/claude_autonomy_operating_model.md) | How Claude works here, and the two hard stops |
