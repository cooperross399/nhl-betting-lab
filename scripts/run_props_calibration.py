#!/usr/bin/env python3
"""Measure the props model's calibration, walk-forward, and write the report.

Writes `data/outputs/props_calibration.md` — one of the three measurement
outputs the operating contract names.

    PYTHONPATH=src .venv/bin/python scripts/run_props_calibration.py

Offline: it reads the processed player logs and nothing else. It fetches no
prices, spends no credits, and produces no picks.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nhl_betting_lab.backtest.walk_forward import generate_prop_samples
from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs
from nhl_betting_lab.reports.props_calibration import (
    build_calibration_report,
    save_calibration_report,
)


SAMPLES_FILENAME = "prop_calibration_samples.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refit-days", type=int, default=14)
    parser.add_argument("--minimum-history-games", type=int, default=200)
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument(
        "--reuse-samples",
        action="store_true",
        help="Reuse the cached walk-forward samples instead of regenerating.",
    )
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    outputs = Path(args.output_dir)
    samples_path = outputs / SAMPLES_FILENAME

    if args.reuse_samples and samples_path.is_file():
        import pandas as pd

        samples = pd.read_csv(samples_path)
        print(f"Reusing {len(samples):,} cached samples from {samples_path}.")
    else:
        logs = load_player_logs(processed)
        if logs.empty:
            print(
                "No player logs. Run scripts/fetch_nhl_data.py and "
                "scripts/build_datasets.py first. No report was written, "
                "because a report with no samples that looked like a report "
                "would be worse than none."
            )
            return 1
        samples, walk = generate_prop_samples(
            logs,
            refit_days=args.refit_days,
            minimum_history_games=args.minimum_history_games,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(walk.summary_line())
        outputs.mkdir(parents=True, exist_ok=True)
        samples.to_csv(samples_path, index=False, lineterminator="\n")

    report = build_calibration_report(samples)
    paths = save_calibration_report(report, output_dir=outputs)
    print(report.summary_line())
    for item in report.markets:
        print(f"  {item.market}: {item.verdict}")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    print(
        "Calibration can rule this model out; it cannot rule it in. Whether "
        "it beats a price is measured separately, against real prices."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
