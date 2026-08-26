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

    PYTHONPATH=src .venv/bin/python scripts/rebuild_price_files.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.providers.odds_api import normalize_event


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
    args = parser.parse_args(argv)

    raw = Path(args.raw_dir)
    processed = Path(args.processed_dir)
    processed.mkdir(parents=True, exist_ok=True)

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
        frame.to_csv(target, index=False, lineterminator="\n")
        print(f"{cache_name}: {len(frame):,} rows rebuilt into {target_name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
