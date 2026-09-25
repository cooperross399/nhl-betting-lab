#!/usr/bin/env python3
"""Report closing-line value from the frozen opinions and the captures.

    PYTHONPATH=src .venv/bin/python scripts/run_closing_line_value.py

Offline. Reads the forward ledger (or the raw snapshots when the ledger has
not settled anything yet) and the closing-price store, and writes
`data/outputs/closing_line_value.md`. Spends nothing, fetches nothing, and
places no bet.

Exits 2 when the capture store holds rows it cannot read. It still writes
the report, and the report says so instead of calling it the pre-season
state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.closing_lines import (
    UnreadableCaptureStore,
    build_clv_report,
    load_captures,
    save_clv_report,
    unreadable_store_report,
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
    # A ledger row repeats its snapshot row, so exact repeats go. The key
    # includes the BOOK and the PRICE. It used to stop at `line`, so each
    # selection kept whichever book's row came first (the alphabetically
    # first, in staging order) before `collapse_to_best` ever saw the rest.
    # The opinion was then scored at that book's price against a best-of-N
    # close. On a market that did not move, a refuter measured mean CLV
    # -1.36% with 25,504 losses against 150 beats on the store CI reads.
    # Every book's row now reaches the collapse, which keeps the best price.
    keys = [
        column
        for column in (
            "snapshot_date", "commence_time", "home_team", "away_team",
            "market", "player", "selection", "line", "book", "american_odds",
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
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        captures = load_captures(processed)
    except UnreadableCaptureStore as exc:
        # A damaged store was read as an empty one, and the report said
        # "Nothing to measure yet ... the correct state and not a fault".
        # The report is still written, so the page that gets published says
        # what happened. The run is then marked failed rather than clean.
        path = save_clv_report(
            unreadable_store_report(opinions, exc),
            output_dir=Path(args.output_dir),
            generated=generated,
        )
        print(f"::error::{exc}")
        if exc.__cause__ is not None:
            print(f"  cause: {str(exc.__cause__).strip()}")
        print(f"  report: {path}")
        return 2
    print(
        f"{len(opinions)} frozen opinion(s); {len(captures)} captured "
        "price(s) in the store."
    )

    report = build_clv_report(opinions, captures)
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
