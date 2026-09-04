#!/usr/bin/env python3
"""Merge two copies of the closing-line capture store, refusing to lose rows.

    PYTHONPATH=src .venv/bin/python scripts/merge_capture_store.py \
        --mine mine.csv --theirs theirs.csv --out store.csv

Used by the Closing Lines workflow when a push is rejected because another
capture landed first. The retry has to merge rather than re-offer what it
hashed before it fetched — otherwise the retry silently discards the capture
it collided with, which is the one thing a retry exists to prevent.

Lives here rather than inside the workflow because a merge that can drop a
row deserves a test, and shell embedded in YAML cannot have one.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from nhl_betting_lab.closing_lines import CAPTURE_COLUMNS
from nhl_betting_lab.stores import existing_row_count, read_store


def _read(path: Path) -> pd.DataFrame:
    """The store's rows, or a loud refusal. Never an empty frame from a damaged file.

    This used to catch ParserError and return an empty frame. That made the
    shrink guard below compare the merge against the ZERO it had just failed
    to read: a 500-row remote store with one ragged row merged to one row,
    printed "Merged 1 local row(s) into 0 remote -> 1.", and exited 0 — and the
    workflow pushed it. `read_store(for_append=True)` is the reader the
    restore path already used; the publish path simply was not using it.

    A missing or genuinely empty file still reads as empty. There is nothing
    in it to lose.
    """
    return read_store(path, columns=CAPTURE_COLUMNS, for_append=True)


def merge(
    mine: pd.DataFrame,
    theirs: pd.DataFrame,
    *,
    remote_rows: int | None = None,
) -> pd.DataFrame:
    """Every row either side holds, once. Never fewer than the remote had.

    The store is append-only evidence about a market that no longer exists:
    once a game has started, a capture that was dropped cannot be taken
    again.

    `remote_rows` is the row count of the remote FILE, counted before it was
    parsed. The floor is the larger of that and the parsed length, because
    the parse is exactly the thing that failed last time: a shrink guard whose
    floor comes from the read it is guarding can never fire. A file-count that
    runs ahead of the parse (a stray blank line) refuses a merge that would
    have been fine — fail-closed, and a blank line in an append-only store is
    itself worth a look.
    """
    floor = max(len(theirs), remote_rows or 0)
    merged = pd.concat([theirs, mine], ignore_index=True).drop_duplicates()
    if len(merged) < floor:
        raise ValueError(
            f"Refusing a merge that would leave {len(merged)} rows where the "
            f"remote store holds {floor}."
        )
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mine", required=True)
    parser.add_argument("--theirs", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    theirs_path = Path(args.theirs)
    # Counted from the file BEFORE the parse, so the floor cannot be the
    # product of a read that failed.
    remote_rows = existing_row_count(theirs_path)
    mine = _read(Path(args.mine))
    theirs = _read(theirs_path)
    merged = merge(mine, theirs, remote_rows=remote_rows)
    merged.to_csv(Path(args.out), index=False, lineterminator="\n")
    print(
        f"Merged {len(mine)} local row(s) into {len(theirs)} remote -> "
        f"{len(merged)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
