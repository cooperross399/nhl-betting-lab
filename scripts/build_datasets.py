#!/usr/bin/env python3
"""Rebuild the processed player-game and team-game tables from the cache.

Reads only what `scripts/fetch_nhl_data.py` has already cached, so it needs no
network and produces the same tables every time it runs.

    PYTHONPATH=src .venv/bin/python scripts/build_datasets.py
"""

from __future__ import annotations

import argparse

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import build_datasets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be built without writing the CSVs.",
    )
    args = parser.parse_args(argv)

    players, teams, result = build_datasets(write=not args.dry_run)
    print(result.summary_line())
    if result.games_not_final:
        preview = ", ".join(str(item) for item in result.games_not_final[:10])
        print(f"Not final (no rows produced): {preview}")
    if result.games_malformed:
        preview = ", ".join(str(item) for item in result.games_malformed[:10])
        print(f"Malformed or missing stats: {preview}")
    if result.names_unresolved:
        print(
            f"{result.names_unresolved} player-game rows have no full name. "
            "Run the fetch with the registry enabled; a row without a full "
            "name cannot be joined to a prop price."
        )
    if args.dry_run:
        print("Dry run: nothing was written.")
    else:
        print(
            f"Wrote {len(players)} player rows and {len(teams)} team rows "
            f"to {PROCESSED_DIR}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
