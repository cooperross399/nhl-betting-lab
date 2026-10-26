#!/usr/bin/env python3
"""Cache the NHL shift charts the skaters' defensive ratings are built from.

    PYTHONPATH=src .venv/bin/python scripts/fetch_shift_charts.py --budget 800

Free and keyless (`api.nhle.com/stats`). Final games in `team_games.csv` whose
chart is not cached are asked newest first, at most `--budget` a run, so a
cold cache (about four thousand games) fills over a few runs and every later
run asks only last night's games. A chart with no shifts yet is not cached and
is asked again next run. Soft in Gameday Refresh: `run_shadow_stats.py
--tables-only` rates whatever is cached (`shadow.defence`). Exit 0 unless the
team games could not be read.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from nhl_betting_lab.config import PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.data.build_datasets import load_team_games
from nhl_betting_lab.data.nhl_api import NhlApiError
from nhl_betting_lab.shadow.shifts import cache_path, fetch_shift_chart


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--budget", type=int, default=800)
    parser.add_argument("--polite-seconds", type=float, default=0.1)
    args = parser.parse_args(argv)
    games = load_team_games(args.processed_dir)
    if games.empty:
        print("No team games on disk; build the datasets first.", file=sys.stderr)
        return 1
    final = games.dropna(subset=["home_goals", "away_goals"])
    ids = sorted({int(g) for g in final["game_id"] if int(g) > 0}, reverse=True)
    missing = [g for g in ids if not cache_path(g, args.raw_dir).is_file()]
    asked = charted = failed = 0
    for gid in missing[: max(args.budget, 0)]:
        asked += 1
        try:
            if fetch_shift_chart(gid, raw_dir=args.raw_dir).complete:
                charted += 1
        except NhlApiError as exc:
            failed += 1
            print(f"Shift chart {gid}: {exc}", file=sys.stderr)
        time.sleep(args.polite_seconds)
    left = len(missing) - charted
    print(
        f"Shift charts: {len(ids) - len(missing)} of {len(ids)} final games were cached; "
        f"asked {asked}, charted {charted}, failed {failed}; {left} still to fetch."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
