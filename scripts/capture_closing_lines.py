#!/usr/bin/env python3
"""Capture what the market is showing right now, for closing-line value.

    PYTHONPATH=src .venv/bin/python scripts/capture_closing_lines.py --live \
        --credit-cap 400

Run repeatedly through the evening. Each run records the best price on every
selection at that moment; the closing price for a game is the last capture
strictly before its start, resolved later by
`nhl_betting_lab.closing_lines`.

Why repeatedly rather than once: NHL puck drops are spread from 19:00 to
22:30 Eastern, so a single fetch is a closing line for some games and a
three-hour-early one for others. Capturing hourly and resolving per game is
the only way one job serves a staggered slate.

This writes prices and nothing else. It builds no card, places no bet, edits
no policy, and cannot change a selection — a capture is evidence about the
market, gathered after the card's opinion was already frozen.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from nhl_betting_lab.closing_lines import (
    append_captures,
    best_prices,
    captures_path,
)
from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.season import LEAGUE_TIMEZONE
from nhl_betting_lab.providers.odds_api import EmptySlateError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--credit-cap",
        type=int,
        default=400,
        help="Hard cap on per-event credits for this capture.",
    )
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    args = parser.parse_args(argv)

    if not args.live:
        print("Dry run: nothing was fetched and no credit was spent.")
        return 0

    load_provider_env()
    provider = odds_api.OddsApiProvider()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(LEAGUE_TIMEZONE).date().isoformat()

    try:
        team = provider.fetch_team_markets(
            fetched_at=stamp, league_days=[today]
        )
    except EmptySlateError as exc:
        # Same contract as the card: an off-day is not a fault.
        print(f"No slate: {exc}")
        return 3
    except odds_api.ProviderError as exc:
        print(f"Team-market capture failed: {exc}", file=sys.stderr)
        return 2

    rows = list(team.rows)
    credits = team.credits_spent
    try:
        per_event = provider.fetch_player_props(
            markets=list(odds_api.PER_EVENT_PROVIDER_MARKETS)
            + list(odds_api.ALTERNATE_PROVIDER_MARKETS),
            credit_cap=args.credit_cap,
            fetched_at=stamp,
            league_days=[today],
        )
        rows.extend(per_event.rows)
        credits += per_event.credits_spent
        for warning in per_event.warnings:
            print(f"  warning: {warning}")
    except odds_api.ProviderError as exc:
        # A failed per-event capture still leaves the team markets recorded.
        # Partial evidence about the close beats none, and the rows that are
        # missing are counted rather than imagined.
        print(f"Per-event capture failed: {exc}", file=sys.stderr)

    best = best_prices(_frame(rows), captured_at=stamp)
    written = append_captures(best, processed_dir=Path(args.processed_dir))
    print(
        f"Captured {written} selection(s) at their best price, from "
        f"{len(rows)} raw price rows; about {credits} credit(s) spent."
    )
    print(f"Store: {captures_path(Path(args.processed_dir))}")
    print(
        "This capture placed no bet, built no card, and changed no "
        "selection."
    )
    return 0


def _frame(rows):
    import pandas as pd

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=list(odds_api.PRICE_COLUMNS)
    )


if __name__ == "__main__":
    raise SystemExit(main())
