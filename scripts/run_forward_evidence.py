#!/usr/bin/env python3
"""Settle pending priced snapshots and rebuild the forward-evidence report.

Runs after results are fetched: every snapshot day whose games are all final
settles as a unit into `data/processed/forward_evidence.csv`, and
`data/outputs/forward_evidence.md` restates what the ledger supports.

    PYTHONPATH=src .venv/bin/python scripts/run_forward_evidence.py

Offline: reads the archive, the processed tables, and nothing else. It
fetches nothing, spends nothing, and revises no frozen opinion — a snapshot
is evidence, and settlement only ever appends.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.forward_evidence import (
    build_forward_report,
    load_ledger,
    save_forward_report,
    settle_snapshots,
)
from nhl_betting_lab.providers.team_names import load_team_name_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--archive-dir", default="")
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    archive = Path(args.archive_dir) if args.archive_dir else None

    logs = load_player_logs(processed)
    games = load_team_games(processed)
    result = settle_snapshots(
        logs,
        games,
        team_names=load_team_name_map(processed_dir=processed),
        archive_dir=archive,
        processed_dir=processed,
    )
    print(result.summary_line())

    payload = build_forward_report(load_ledger(processed))
    paths = save_forward_report(payload, output_dir=Path(args.output_dir))
    for name, path in paths.items():
        print(f"  {name}: {path}")
    print(
        "Settlement appends; no frozen opinion was revised, no price was "
        "fetched, and no bet was placed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
