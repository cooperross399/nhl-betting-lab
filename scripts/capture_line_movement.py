#!/usr/bin/env python3
"""Capture the day's prices repeatedly, so line movement becomes observable.

    PYTHONPATH=src .venv/bin/python scripts/capture_line_movement.py --live \
        --credit-cap 400

Two of the three ideas left after the no-edge finding — a book leaving its
alternate ladder behind when it moves the main line, and a book lagging the
market on lineup news — are untestable for the same reason: this lab has only
ever seen **one** price per game, four hours before puck drop. A single
snapshot cannot show movement, and movement is the whole hypothesis.

So this captures the same board several times a day and keeps every
observation with the moment it was taken. It answers nothing on its own. It
makes two questions answerable that otherwise never are, and like forward
evidence it cannot be collected retroactively: a night not captured is gone.

**It touches nothing the card reads.** It writes only under
`data/processed/line_movement/`, never `data/staging/`, never the forward
ledger, never the policy. It places no bet and it decides nothing.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.closing_lines import append_captures, best_prices
from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.providers.odds_api import EmptySlateError
from nhl_betting_lab.season import LEAGUE_TIMEZONE


MOVEMENT_DIRNAME = "line_movement"


def capture_path(day: str, *, processed_dir: Path | None = None) -> Path:
    """One file per league game date, so a season is many small files.

    A single accumulating file would be rewritten whole on every capture
    several times a day, which is how a long file gets truncated by a run
    that dies halfway.
    """
    root = (processed_dir or PROCESSED_DIR) / MOVEMENT_DIRNAME
    return root / f"{day}.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--credit-cap", type=int, default=0)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument(
        "--horizon-days",
        type=int,
        default=1,
        help="League game dates to capture, starting today.",
    )
    args = parser.parse_args(argv)

    if args.live and args.credit_cap <= 0:
        parser.error("--live requires a positive --credit-cap.")

    processed = Path(args.processed_dir)
    load_provider_env()
    if not args.live:
        print("Dry run: nothing was asked and no credit was spent.")
        return 0

    provider = odds_api.OddsApiProvider()
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(LEAGUE_TIMEZONE).date()
    league_days = [
        (today + timedelta(days=offset)).isoformat()
        for offset in range(max(args.horizon_days, 1))
    ]
    print(f"Capturing {league_days} at {captured_at}.")

    markets = list(odds_api.PER_EVENT_PROVIDER_MARKETS) + list(
        odds_api.ALTERNATE_PROVIDER_MARKETS
    )
    try:
        result = provider.fetch_player_props(
            markets=markets,
            credit_cap=args.credit_cap,
            fetched_at=captured_at,
            league_days=league_days,
        )
    except EmptySlateError as exc:
        # Not a fault, and not a red run: the league does not play every
        # night and does not play in July.
        print(f"Nothing to capture: {exc}")
        return 0
    except odds_api.ProviderError as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        return 2

    if not result.rows:
        print("No rows returned; nothing written.")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        return 0

    frame = pd.DataFrame(result.rows)
    frame["captured_at"] = captured_at
    day = league_days[0]
    path = capture_path(day, processed_dir=processed)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Append. Each capture is its own observation of the same market, and the
    # point of the file is that they differ.
    header = not path.is_file()
    frame.to_csv(path, mode="a", header=header, index=False, lineterminator="\n")

    print(f"{len(frame)} rows appended to {path}.")

    # The same fetch also feeds the closing-line store, which keeps one row
    # per selection at the best price any book showed. It is a strict subset
    # of what was just written, so deriving it here retires a second
    # scheduled fetch that was asking the provider the same question.
    narrow = best_prices(frame, captured_at=captured_at)
    added = append_captures(narrow, processed_dir=processed)
    print(f"{added} best-price row(s) appended to the closing-line store.")
    print(result.summary_line())
    for warning in result.warnings:
        print(f"  warning: {warning}")
    print(
        "This capture wrote no staging file, froze no opinion, edited no "
        "policy, and placed no bet."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
