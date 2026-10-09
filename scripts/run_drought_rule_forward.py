#!/usr/bin/env python3
"""Settle the Due List's dated files and restate the rule's own forward record.

    PYTHONPATH=src .venv/bin/python scripts/run_drought_rule_forward.py

Offline: reads `data/processed/drought_list/*.csv`, the player logs and team
games, and writes `data/processed/drought_forward.csv` and
`data/outputs/drought_rule_forward.md`. First it rebuilds any night of this
season before the first recorded list, and gives an entry recorded with no
price the price the card froze that morning, naming both in
`data/processed/drought_list/sources.json` (Cooper, 2026-10-09: the list is
tracked season long as if 0.25u were bet on every entry). It fetches nothing, spends nothing,
stakes nothing, and touches none of the registered forward test's files
(`forward_evidence.csv`, `forward_evidence.md`, the priced snapshots).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from datetime import datetime
from zoneinfo import ZoneInfo

from nhl_betting_lab.config import DATA_DIR, OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.data.nhl_api import current_rosters
from nhl_betting_lab.drought_forward import (
    backfill_lists,
    build_report,
    fill_prices,
    load_ledger,
    load_sources,
    pending_rows,
    save_report,
    settle_lists,
)
from nhl_betting_lab.drought_rule import cell_records
from nhl_betting_lab.forward_evidence import snapshots_dir
from nhl_betting_lab.providers.team_names import load_team_name_map
from nhl_betting_lab.season import scheduled_regular_season_starts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--raw-dir", default="", help=f"Where the cached schedules and rosters are (default {RAW_DIR}).")
    parser.add_argument("--archive-dir", default=str(DATA_DIR / "archive"),
                        help="Where the card's frozen prices (priced_snapshots/<day>.csv) are.")
    parser.add_argument("--today", default="", help="League day (default: today in New York).")
    args = parser.parse_args(argv)
    processed, outputs = Path(args.processed_dir), Path(args.output_dir)
    today = args.today or datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    names = load_team_name_map(processed_dir=processed)
    logs = load_player_logs(processed)
    raw = Path(args.raw_dir) if args.raw_dir else None
    rosters = current_rosters(raw_dir=raw)
    snapshots = snapshots_dir(Path(args.archive_dir))
    # Neither may stop the night's settlement: a backfill or a price fill that
    # fails is named and the ledger settles as it would have without it.
    try:
        for note in backfill_lists(logs=logs, rosters=rosters, starts=scheduled_regular_season_starts(raw),
                                   team_names=names, today=today, snapshots=snapshots, processed_dir=processed,
                                   records=cell_records(outputs, fallback=OUTPUTS_DIR)):
            print(f"Due List backfill: {note}")
    except (KeyError, ValueError, OSError) as exc:
        print(f"::warning::The Due List's earlier nights could not be rebuilt: {exc}")
    try:
        for note in fill_prices(logs=logs, rosters=rosters, team_names=names, snapshots=snapshots,
                                processed_dir=processed):
            print(f"Due List price: {note}")
    except (KeyError, ValueError, OSError) as exc:
        print(f"::warning::The Due List's unpriced entries could not take the card's prices: {exc}")
    result = settle_lists(logs, load_team_games(processed), team_names=names, processed_dir=processed)
    print(result.summary_line())
    payload = build_report(load_ledger(processed), pending_rows=pending_rows(processed), outputs_dir=outputs,
                           sources=load_sources(processed))
    for name, path in save_report(payload, output_dir=outputs).items():
        print(f"  {name}: {path}")
    print("The Due List is unstaked; no bet was placed and the registered forward test was not touched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
