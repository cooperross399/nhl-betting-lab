#!/usr/bin/env python3
"""Rebuild the price CSVs from the raw cached responses.

The CSVs are derived data. Every response ever bought is cached under
`data/raw/historical_props/` and `data/raw/historical_team_prices/`, and those
files never change — so the CSVs can always be reconstructed from them without
spending a credit.

This exists because a purchase that bought nothing once overwrote the
accumulated price file with an empty frame. The raw cache made that a
five-minute recovery instead of an 11,000-credit one, which is the whole
argument for caching raw evidence rather than only derived tables.

**The rebuild is only as complete as the cache it reads**, and that is the
sharp edge. This script wrote whatever it produced, unconditionally: pointed
at a partial cache it replaced a 2,675,428-row store with 90,594 rows and
printed success, which is the same silent shortfall it exists to repair,
running the other way. `build_datasets` has refused a shrink below half since
a one-game build nearly replaced a season; this now does the same, per file,
on rows rather than existence, with `--allow-shrink` as the deliberate
override.

    PYTHONPATH=src .venv/bin/python scripts/rebuild_price_files.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.providers.odds_api import normalize_event
from nhl_betting_lab.stores import existing_row_count


def _rows_from_cache(directory: Path) -> list[dict]:
    rows: list[dict] = []
    if not directory.is_dir():
        return rows
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("events_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        data = payload.get("data") if isinstance(payload, dict) else payload
        events = data if isinstance(data, list) else [data]
        snapshot = str((payload or {}).get("timestamp", "")) if isinstance(payload, dict) else ""
        for event in events:
            if not isinstance(event, dict):
                continue
            found = normalize_event(event, fetched_at=snapshot or path.stem)
            for row in found:
                row["snapshot"] = snapshot or path.stem
            rows.extend(found)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help=(
            "Permit replacing an accumulated price file with a much smaller "
            "rebuild. Off by default, because a partial raw cache produces a "
            "small rebuild without an error — and the prices it would drop "
            "cost credits that are already spent."
        ),
    )
    args = parser.parse_args(argv)

    raw = Path(args.raw_dir)
    processed = Path(args.processed_dir)
    processed.mkdir(parents=True, exist_ok=True)
    refused = False

    for cache_name, target_name, keep in (
        ("historical_props", "historical_prop_prices.csv", "prop"),
        ("historical_team_prices", "historical_team_prices.csv", "team"),
    ):
        rows = _rows_from_cache(raw / cache_name)
        frame = pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()
        if keep == "prop" and not frame.empty:
            from nhl_betting_lab.markets import PROP_MARKETS

            wanted = {market.key for market in PROP_MARKETS}
            frame = frame[frame["market"].isin(wanted)]
        if keep == "team" and not frame.empty:
            from nhl_betting_lab.markets import TEAM_MARKETS

            wanted = {market.key for market in TEAM_MARKETS}
            frame = frame[frame["market"].isin(wanted)]
        target = processed / target_name
        if frame.empty:
            print(f"{cache_name}: no cached responses; {target_name} untouched.")
            continue
        existing = existing_row_count(target)
        if existing and len(frame) < max(1, existing // 2) and not args.allow_shrink:
            # Refusing beats writing. The rows on the losing side of this
            # comparison were bought with credits that cannot be spent twice,
            # and the usual cause is a raw cache that is present but partial —
            # which looks exactly like a successful rebuild.
            print(
                f"Refused: rebuilding {target_name} from {raw / cache_name} "
                f"produced {len(frame):,} row(s) where the file already holds "
                f"{existing:,}. Refusing to shrink an accumulated price file "
                "by more than half — check that the raw cache is complete "
                "(restore the `historical-props` artifact if it is not), or "
                "pass --allow-shrink if the shrink is deliberate.",
                file=sys.stderr,
            )
            refused = True
            continue
        frame.to_csv(target, index=False, lineterminator="\n")
        print(f"{cache_name}: {len(frame):,} rows rebuilt into {target_name}.")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
