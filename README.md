# NHL Betting Lab

Gated research tooling for NHL player props and team markets. It produces
measured, calibrated recommendation cards. **It never places a bet, and it never
invents a price.**

Player props are the primary product: shots on goal, points, goals (including
anytime scorer), assists, goalie saves, and blocked shots. Team markets —
moneyline, puck line, totals — are priced and modelled so that an edge anywhere
can be found.

Start with [`CLAUDE.md`](CLAUDE.md) for the operating rules and
[`docs/what_we_can_and_cannot_claim.md`](docs/what_we_can_and_cannot_claim.md)
before believing any number this repository produces.

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

## Tests

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

## Where the card comes from

GitHub Actions, not a laptop. The **Gameday Refresh** workflow
(`.github/workflows/gameday-refresh.yml`) runs daily in season and posts each
card to the pinned issue **NHL Betting Lab — Claude Operating Home**.

## Safety boundaries

- No bet is ever placed, and no betting is ever automated.
- A missing price stays missing; an excluded market is never reported as a pass,
  an avoid, or a no-value call.
- A selection whose game has started — or whose start cannot be confirmed — is
  quarantined and its stake removed. See
  [`docs/puck_drop_guard.md`](docs/puck_drop_guard.md).
- No market reaches the card without measurement against real prices and a
  reviewed human approval.
