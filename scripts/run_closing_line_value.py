#!/usr/bin/env python3
"""Report closing-line value from the frozen opinions and the captures.

    PYTHONPATH=src .venv/bin/python scripts/run_closing_line_value.py

Offline. Reads the forward ledger (or the raw snapshots when the ledger has
not settled anything yet) and the closing-price store, and writes
`data/outputs/closing_line_value.md`. Spends nothing, fetches nothing, and
places no bet.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.closing_lines import (
    build_clv_report,
    load_captures,
    save_clv_report,
)
from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.forward_evidence import load_ledger, snapshots_dir


def _opinions(processed_dir: Path, archive_dir: Path | None) -> pd.DataFrame:
    """Every frozen opinion, settled or not.

    CLV does not need a result — that is the point of it. So the snapshots
    are read directly rather than waiting for games to finish, and the ledger
    is used only to fill in anything the archive has since lost.
    """
    frames = []
    directory = snapshots_dir(archive_dir)
    if directory.is_dir():
        for path in sorted(directory.glob("*.csv")):
            try:
                frames.append(pd.read_csv(path))
            except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
                continue
    ledger = load_ledger(processed_dir)
    if not ledger.empty:
        frames.append(ledger[[c for c in ledger.columns if c != "outcome"]])
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    keys = [
        column
        for column in (
            "snapshot_date", "commence_time", "home_team", "away_team",
            "market", "player", "selection", "line",
        )
        if column in combined.columns
    ]
    return combined.drop_duplicates(subset=keys) if keys else combined


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--archive-dir", default="")
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    archive = Path(args.archive_dir) if args.archive_dir else None

    opinions = _opinions(processed, archive)
    captures = load_captures(processed)
    print(
        f"{len(opinions)} frozen opinion(s); {len(captures)} captured "
        "price(s) in the store."
    )

    report = build_clv_report(opinions, captures)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = save_clv_report(
        report, output_dir=Path(args.output_dir), generated=generated
    )
    counts = report.get("counts", {})
    print(
        f"Matched {counts.get('matched', 0)} of {counts.get('opinions', 0)} "
        f"opinion(s) to a closing price; {counts.get('no_close', 0)} had none."
    )
    print(f"  report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
