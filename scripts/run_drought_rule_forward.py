#!/usr/bin/env python3
"""Settle the Due List's dated files and restate the rule's own forward record.

    PYTHONPATH=src .venv/bin/python scripts/run_drought_rule_forward.py

Offline: reads `data/processed/drought_list/*.csv`, the player logs and team
games, and writes `data/processed/drought_forward.csv` and
`data/outputs/drought_rule_forward.md`. It fetches nothing, spends nothing,
stakes nothing, and touches none of the registered forward test's files
(`forward_evidence.csv`, `forward_evidence.md`, the priced snapshots).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.drought_forward import (
    build_report,
    load_ledger,
    pending_rows,
    save_report,
    settle_lists,
)
from nhl_betting_lab.providers.team_names import load_team_name_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)
    processed, outputs = Path(args.processed_dir), Path(args.output_dir)

    names = load_team_name_map(processed_dir=processed)
    result = settle_lists(load_player_logs(processed), load_team_games(processed),
                          team_names=names, processed_dir=processed)
    print(result.summary_line())
    payload = build_report(load_ledger(processed), pending_rows=pending_rows(processed), outputs_dir=outputs)
    for name, path in save_report(payload, output_dir=outputs).items():
        print(f"  {name}: {path}")
    print("The Due List is unstaked; no bet was placed and the registered forward test was not touched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
