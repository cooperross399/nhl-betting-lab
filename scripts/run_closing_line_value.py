#!/usr/bin/env python3
"""Report closing-line value from the frozen opinions and the captures.

    PYTHONPATH=src .venv/bin/python scripts/run_closing_line_value.py

Offline. Reads the forward ledger (or the raw snapshots when the ledger has
not settled anything yet) and the closing-price store, and writes
`data/outputs/closing_line_value.md`. Spends nothing, fetches nothing, and
places no bet.

Exits 2 when the capture store holds rows it cannot read, or when a priced
snapshot cannot be read. It still writes the report either way, and the
report names what could not be read instead of calling it the pre-season
state or leaving the day out without a word.
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
from nhl_betting_lab.forward_evidence import load_ledger, read_snapshot, snapshots_dir


def _opinions(
    processed_dir: Path,
    archive_dir: Path | None,
    *,
    unreadable: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Every frozen opinion, settled or not.

    CLV does not need a result — that is the point of it. So the snapshots
    are read directly rather than waiting for games to finish, and the ledger
    is used only to fill in anything the archive has since lost.

    `unreadable`, when given, receives every snapshot file that could not be
    read, by file name, with the reason.

    ## A damaged snapshot is named; it no longer stops or thins the report

    Each file used to be read with a bare `pd.read_csv`, catching only
    `OSError`, `EmptyDataError` and `ParserError`. Half of a multi-byte
    character, or a file re-saved as Latin-1, raised `UnicodeDecodeError`
    straight out of the runner: the failure-shape audit froze two days of 64
    rows and cut one inside a character, and the runner exited 1 with no
    `closing_line_value.md`. An unclosed quote, zero bytes or half a header
    were caught and skipped without a word: the run printed "64 frozen
    opinion(s)" of the 128, exited 0, and the report named nothing, while
    settlement named the same file and exited 2. On a day that had already settled, settlement never
    reads the file again, so this report is the only reader that can say it
    is damaged, and it crashed.

    Every file now goes through `forward_evidence.read_snapshot`, the reader
    settlement uses, so the two agree on what is a day's opinion. `OSError`
    (a file that cannot be opened at all) is still caught, and now named too.
    The rows the ledger holds for a damaged day are still read below.
    """
    frames = []
    directory = snapshots_dir(archive_dir)
    if directory.is_dir():
        for path in sorted(directory.glob("*.csv")):
            try:
                frame, problem = read_snapshot(path)
            except OSError as error:
                frame = None
                problem = f"{type(error).__name__}: {error.strerror or error}"
            if frame is None:
                if unreadable is not None:
                    unreadable[path.name] = problem
                continue
            frames.append(frame)
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


def _unreadable_snapshots(
    opinions: pd.DataFrame, unreadable: dict[str, str]
) -> list[dict[str, object]]:
    """Each snapshot file that could not be read, why, and how many rows
    frozen that day are counted anyway — which can only be rows the forward
    ledger settled from that day, since its own file was not read."""
    days = (
        opinions["snapshot_date"].astype(str)
        if "snapshot_date" in opinions.columns
        else pd.Series(dtype=str)
    )
    return [
        {
            "name": name,
            "reason": reason,
            "ledger_rows": int((days == Path(name).stem).sum()),
        }
        for name, reason in sorted(unreadable.items())
    ]


def _say_unreadable_snapshots(damaged: list[dict[str, object]]) -> None:
    if not damaged:
        return
    listed = "; ".join(
        f"{entry['name']} ({entry['reason']})" for entry in damaged
    )
    print(
        f"::error::{len(damaged)} priced snapshot file(s) could not be read, "
        f"so no opinion frozen only in them is scored: {listed}. The report "
        "names each one and says what the forward ledger still holds of its "
        "day. A snapshot is written whole or not at all, so the file was "
        "damaged after it was written, or was written before that rule "
        "existed. Restore it from the gameday-state artifact that froze it."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--archive-dir", default="")
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    archive = Path(args.archive_dir) if args.archive_dir else None

    unreadable: dict[str, str] = {}
    opinions = _opinions(processed, archive, unreadable=unreadable)
    damaged = _unreadable_snapshots(opinions, unreadable)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        captures = load_captures(processed)
    except UnreadableCaptureStore as exc:
        # A damaged store was read as an empty one, and the report said
        # "Nothing to measure yet ... the correct state and not a fault".
        # The report is still written, so the page that gets published says
        # what happened. The run is then marked failed rather than clean.
        report = unreadable_store_report(opinions, exc)
        report["unreadable_snapshots"] = damaged
        path = save_clv_report(
            report,
            output_dir=Path(args.output_dir),
            generated=generated,
        )
        print(f"::error::{exc}")
        if exc.__cause__ is not None:
            print(f"  cause: {str(exc.__cause__).strip()}")
        _say_unreadable_snapshots(damaged)
        print(f"  report: {path}")
        return 2
    print(
        f"{len(opinions)} frozen opinion(s); {len(captures)} captured "
        "price(s) in the store."
    )

    report = build_clv_report(opinions, captures)
    report["unreadable_snapshots"] = damaged
    path = save_clv_report(
        report, output_dir=Path(args.output_dir), generated=generated
    )
    counts = report.get("counts", {})
    print(
        f"Matched {counts.get('matched', 0)} of {counts.get('opinions', 0)} "
        f"opinion(s) to a closing price; {counts.get('no_close', 0)} had none, "
        f"of which {counts.get('no_close_not_near_face_off', 0)} were priced "
        "before face-off but not near it."
    )
    _say_unreadable_snapshots(damaged)
    print(f"  report: {path}")
    # The report above is written and names each damaged file; the exit says
    # the run was not clean, as it does for a damaged capture store.
    return 2 if damaged else 0


if __name__ == "__main__":
    raise SystemExit(main())
