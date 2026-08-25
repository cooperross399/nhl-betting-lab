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

- **Props have been measured against real prices on two seasons, and nothing
  survives.** 192 events bought (58 from 2025-26, 134 from 2024-25), 11,418
  credits, 90,594 price rows, 1,268 bets. Pooled: **+2.3% over 1,268 bets,
  95% interval −3.1% to +7.7% — no demonstrated edge**, and nothing survives
  correcting for the number of markets tested.
- **`shots_on_goal` was the one result that survived on the first window, and
  it did not replicate.** +18.1% over 263 bets on 2025-26, surviving
  correction (+2.1% to +34.2%); **−6.0% over 420 bets on 2024-25**, pointing
  the other way on the larger sample. `points` reversed too, −16.4% then
  +1.7%. `data/outputs/replication.md`.
- **That is the system working, not failing.** A single window found a
  survivor; the second window contradicted it. Had the lab shipped on the
  first result it would have staked money on a window property. Nothing is
  allowlisted and nothing should be.
- **92% of every bet is on the Under.** One directional disagreement with the
  market rather than six independent ones, which is why markets flip sign
  between windows: they share the bias.
- **The measured historical rate is ten credits per market returned per
  event.** The documentation was ambiguous between one and ten; the
  pessimistic reading was right. Quota after the purchase: ~96,495 of 100,000.
- **No market is allowlisted.** `data/manual/staging_provider_policy.json`
  allowlists nothing, so the card produces no selection, no lean, no pass and
  no stake. It lists every market with its reason. That is correct behaviour.
- **Data**: three seasons cached — 3,936 games, 157,419 player-game rows,
  121 unresolved names (0.08%). A completed boxscore is never refetched.
- **Props calibration**: 1,889,685 walk-forward samples over 3,658 games
  (2023-11-22 to 2026-04-16), 63 refits. `data/outputs/props_calibration.md`.
- **Every skater market is bent by ice time, and one Platt curve cannot fix
  it.** Shots on goal under twelve minutes: pooled predicts 12.9% against 7.7%
  observed on 74,588 samples. The ice-time-conditional correction predicts
  7.6% and straightens every bucket, on all six markets. The mechanism —
  ice-time quantity without ice-time quality, plus shrinkage toward a baseline
  dominated by well-deployed players — is in
  `docs/why_ice_time_gets_its_own_correction.md`.
- **Neither correction is in force.** The card prices props with the raw
  model. Calibration cannot rule a model in, and the price-based backtest that
  would decide measures nothing yet.
- **`goalie_saves` cannot reach the card at all**, above and beyond policy: a
  saves prop is only bettable on the confirmed starter, and this lab has no
  confirmed-starter source. The card names the market and that reason, and
  says it is not a no-value judgement.
  `docs/goalie_props_need_a_confirmed_starter.md`.
- **Team markets** measured over 51,212 samples across 3,658 games. Moneyline
  Brier 0.2430, puck line 0.2066, totals 0.2136.
  `data/outputs/team_markets_measurement.md`.
- **The team model is overconfident on favourites**, not conservative as its
  docstring originally argued. Puck line: 75.0% predicted against 70.9%
  observed on 3,098 samples; 83.7% against 78.5% on 1,397. Fitted slope 0.792
  on the moneyline. The wrong prediction is left on the record in
  `models/team_model.py` rather than deleted.

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
  scorer), assists, goalie saves, blocked shots.
- Team markets — moneyline, puck line, totals — are priced and modelled so an
  edge anywhere can be found, but they are not the point of the lab.
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
human acceptance receipt say it is. The default policy allowlists nothing.
Shadow runs write to `data/staging/`, which the card cannot read.

## What Claude decides, and what Cooper decides

Claude works autonomously on: data, models, measurement, reports, tests,
workflows, docs, and opening PRs with green CI.

Claude stops and asks for: **provider/market allowlisting approvals**, and
**anything spending API credits beyond a small measurement budget**. Those two
are Cooper's alone.
