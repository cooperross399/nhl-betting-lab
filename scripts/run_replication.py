#!/usr/bin/env python3
"""Compare two measured windows and say whether a result replicated.

    PYTHONPATH=src .venv/bin/python scripts/run_replication.py \
        --discovery data/outputs/player_props_backtest_2025-26.json \
        --test data/outputs/player_props_backtest_2024-25.json

Offline. Reads two labelled backtest payloads and writes
`data/outputs/replication.md`. It never pools them: pooling asks a different
question and launders a strong first window into a merged average that reads
like confirmation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.reports.replication import (
    compare,
    load_backtest,
    save_replication,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--test", required=True)
    parser.add_argument("--discovery-label", default="")
    parser.add_argument("--test-label", default="")
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    discovery_path = Path(args.discovery)
    test_path = Path(args.test)
    discovery = load_backtest(discovery_path)
    test = load_backtest(test_path)

    missing = [
        str(path)
        for path, payload in ((discovery_path, discovery), (test_path, test))
        if not payload
    ]
    if missing:
        print(
            "Cannot compare: these measured windows are missing or unreadable: "
            + ", ".join(missing)
        )
        return 1

    report = compare(
        discovery,
        test,
        discovery_label=args.discovery_label or discovery_path.stem,
        test_label=args.test_label or test_path.stem,
    )
    paths = save_replication(report, output_dir=Path(args.output_dir))

    print(report.headline())
    for item in report.markets:
        print(f"  {item.market}: {item.state} — {item.reason}")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
