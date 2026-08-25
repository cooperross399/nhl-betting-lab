# NHL Betting Lab

Gated research tooling for NHL player props and team markets. It produces
measured, calibrated recommendation cards. **It never places a bet, and it
never invents a price.**

Player props are the primary product: shots on goal, points, goals (including
anytime scorer), assists, goalie saves, and blocked shots. Team markets —
moneyline, puck line, totals — are priced and modelled so that an edge
anywhere can be found.

Read [`CLAUDE.md`](CLAUDE.md) for the operating rules and
[`docs/what_we_can_and_cannot_claim.md`](docs/what_we_can_and_cannot_claim.md)
before believing any number this repository produces.

## The current answer to "does this work"

Nothing in this repository has a demonstrated edge, because nothing has been
measured against real prices yet. That is a statement about the evidence, not
about the models. `data/outputs/what_we_can_claim.md` is regenerated from the
measurements every run and always says what they actually support.

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

# What the evidence supports -> data/outputs/what_we_can_claim.md
PYTHONPATH=src .venv/bin/python scripts/run_what_we_can_claim.py
```

### The card — offline, gated

```bash
# With the shipped policy this produces no card and no selections, and says
# why. That is correct behaviour, not a failure.
PYTHONPATH=src .venv/bin/python scripts/run_gameday_card.py

# Decide whether the card is worth an email and write the comment body.
PYTHONPATH=src .venv/bin/python scripts/post_card_to_issue.py --out comment.md
```

### Provider — the two that touch the network

```bash
# Confirm the credential is present. Costs no quota; prints only its length.
PYTHONPATH=src .venv/bin/python scripts/check_provider_credential.py

# Assess whatever is already staged. No credits.
PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py

# Live shadow fetch. Team markets are a handful of credits; props are one
# credit per market per event and the cap is hard.
PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py --live --props \
    --credit-cap 60
```

### Historical prices — the expensive one

```bash
# Free: print what a purchase would cost and stop.
PYTHONPATH=src .venv/bin/python scripts/buy_historical_props.py \
    --from 2025-01-05 --to 2025-01-05

# One event: find out which prop markets the provider retains at all.
PYTHONPATH=src .venv/bin/python scripts/buy_historical_props.py \
    --probe --live --credit-cap 60
```

Ten credits per market per event. Six markets across a twelve-game night is
720 credits, so this is a spending decision rather than a default.

### Gates and tests

```bash
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

| Workflow | Trigger | Spends credits |
|:---------|:--------|:---------------|
| Tests | every PR and push to main | no |
| Provider Policy PR Gate | PRs touching policy or receipts | no |
| Gameday Refresh | daily in season, and on demand | yes, capped |
| Provider Market Discovery | on demand | yes, capped |
| Historical Props Purchase | on demand only, never scheduled | yes, capped, required cap |

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
| [`docs/goalie_props_need_a_confirmed_starter.md`](docs/goalie_props_need_a_confirmed_starter.md) | A measurement that was asking the wrong question |
| [`docs/why_ice_time_gets_its_own_correction.md`](docs/why_ice_time_gets_its_own_correction.md) | The mechanism behind the conditional correction |
| [`docs/provider_allowlist_approval.md`](docs/provider_allowlist_approval.md) | How a market becomes trusted |
| [`docs/claude_autonomy_operating_model.md`](docs/claude_autonomy_operating_model.md) | How Claude works here, and the two hard stops |
