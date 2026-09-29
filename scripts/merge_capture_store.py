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
import sys
from pathlib import Path

import pandas as pd

from nhl_betting_lab.closing_lines import CAPTURE_COLUMNS
from nhl_betting_lab.stores import CorruptStoreError, existing_row_count, read_store


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


def _refuse_a_short_read(frame: pd.DataFrame, rows_on_disk: int | None, which: str) -> None:
    """Refuse a store whose parse came back shorter than its file.

    One stray quote need not make pandas raise: two of them fold rows into
    one field, and a 4-row file reads as 2 garbled rows with no error. The
    count comes from the file, as in `closing_lines.append_captures` and the
    forward ledger's `_read_ledger` (#266), because a floor taken from the
    read it guards can never fire.
    """
    if rows_on_disk is not None and len(frame) < rows_on_disk:
        raise ValueError(
            f"Refusing a merge: the {which} store holds {rows_on_disk} row(s) "
            f"and parses to only {len(frame)} of its {rows_on_disk}, without "
            "an error (a stray quote folds rows into one field). Writing now "
            "would publish the rows that parsed in place of the ones it holds. "
            "Restore it from the closing-lines branch, then re-run."
        )


def merge(
    mine: pd.DataFrame,
    theirs: pd.DataFrame,
    *,
    remote_rows: int | None = None,
    local_rows: int | None = None,
) -> pd.DataFrame:
    """Every row either side holds, once. Never fewer than the remote had.

    The store is append-only evidence about a market that no longer exists:
    once a game has started, a capture that was dropped cannot be taken
    again.

    `remote_rows` and `local_rows` are the row counts of the two FILES,
    counted before they were parsed. A file-count that runs ahead of the
    parse (a stray blank line is not one: `existing_row_count` skips those as
    pandas does) refuses the merge — fail-closed.

    ## The floor is compared with the remote PART, not the total

    It was `max(len(theirs), remote_rows)` compared with `len(merged)`, which
    is `theirs + mine`. So the local rows made up for the remote rows a short
    read lost: a 4-row remote parsed as 2, plus 4 local rows, merged to 6,
    cleared the floor of 4, and a store missing two remote captures was
    written and pushed. `closing_lines.append_captures` had the same masked
    floor until #266. A short parse on either side is now refused before
    anything is merged; the total is then held only to the rows the remote
    parse returned, which a merge can never legitimately undercut.
    """
    _refuse_a_short_read(theirs, remote_rows, "remote")
    _refuse_a_short_read(mine, local_rows, "local")
    merged = pd.concat([theirs, mine], ignore_index=True).drop_duplicates()
    if len(merged) < len(theirs):
        raise ValueError(
            f"Refusing a merge that would leave {len(merged)} rows where the "
            f"remote store holds {len(theirs)}."
        )
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mine", required=True)
    parser.add_argument("--theirs", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    theirs_path, mine_path = Path(args.theirs), Path(args.mine)
    # Counted from the files BEFORE the parse, so the floor cannot be the
    # product of a read that failed.
    remote_rows = existing_row_count(theirs_path)
    local_rows = existing_row_count(mine_path)
    try:
        mine = _read(mine_path)
        theirs = _read(theirs_path)
        merged = merge(mine, theirs, remote_rows=remote_rows, local_rows=local_rows)
    except (CorruptStoreError, ValueError) as exc:
        # Refused before anything is written: the publish step's
        # `|| exit 1` then stops the push, and the annotation says why
        # rather than leaving a traceback to be read for it.
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    merged.to_csv(Path(args.out), index=False, lineterminator="\n")
    print(
        f"Merged {len(mine)} local row(s) into {len(theirs)} remote -> "
        f"{len(merged)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
