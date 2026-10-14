#!/usr/bin/env python3
"""Fetch tonight's starting goalies for the card's saves check.

    PYTHONPATH=src .venv/bin/python scripts/fetch_starting_goalies.py

Reads Daily Faceoff's starting-goalies page once and writes
`data/processed/starting_goalies.csv`, replacing the previous run's file, so
the card reads only what this run fetched. It spends no provider credits and
freezes no opinion (`nhl_betting_lab.data.starting_goalies` says what the
card does with it).

A failed fetch removes the old file and exits 1. The card then withholds
every saves stake and says why: an old listing would be yesterday's word on
tonight's goalie, which is the guess the check exists to stop.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.data.starting_goalies import COLUMNS, FILENAME, PAGE, parse_page

USER_AGENT = (
    "nhl-betting-lab/1.0 (private betting-model research; "
    "low volume, game days only)"
)


def _fetch(url: str, *, timeout: float = 25.0) -> str:
    import requests

    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def main(argv: list[str] | None = None, *, fetch=_fetch) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    args = parser.parse_args(argv)

    path = Path(args.processed_dir) / FILENAME
    path.unlink(missing_ok=True)
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        rows = parse_page(fetch(PAGE), retrieved_at=retrieved_at)
    except Exception as exc:  # the site, on a bad day
        print(
            f"::warning::Could not read the starting goalies ({exc}). The card "
            "will withhold every saves stake.",
            file=sys.stderr,
        )
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(COLUMNS)).to_csv(path, index=False)
    for row in rows:
        print(f"{row['date']} {row['team']}: {row['goalie'] or '-'} ({row['strength'] or 'no label'})")
    print(f"Starting goalies: {len(rows)} team listing(s) written to {path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
