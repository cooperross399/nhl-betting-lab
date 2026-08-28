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


def _read(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame(columns=list(CAPTURE_COLUMNS))
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=list(CAPTURE_COLUMNS))


def merge(mine: pd.DataFrame, theirs: pd.DataFrame) -> pd.DataFrame:
    """Every row either side holds, once. Never fewer than the remote had.

    The store is append-only evidence about a market that no longer exists:
    once a game has started, a capture that was dropped cannot be taken
    again.
    """
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

    mine = _read(Path(args.mine))
    theirs = _read(Path(args.theirs))
    merged = merge(mine, theirs)
    merged.to_csv(Path(args.out), index=False, lineterminator="\n")
    print(
        f"Merged {len(mine)} local row(s) into {len(theirs)} remote -> "
        f"{len(merged)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
