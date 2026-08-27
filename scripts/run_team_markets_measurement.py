#!/usr/bin/env python3
"""Measure the team model: calibration walk-forward, and prices where bought.

Writes `data/outputs/team_markets_measurement.md`.

    PYTHONPATH=src .venv/bin/python scripts/run_team_markets_measurement.py

Offline: it reads the processed team games and any historical team prices
already on disk. It fetches nothing and spends no credits.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from nhl_betting_lab.backtest import samples_are_current
from nhl_betting_lab.backtest.team_walk_forward import (
    DEFAULT_TOTAL_LINES,
    PUCK_LINES,
    generate_team_samples,
)
from nhl_betting_lab.config import MIN_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_team_games
from nhl_betting_lab.markets import team_market_keys
from nhl_betting_lab.verdicts import ships
from nhl_betting_lab.reports.team_markets_measurement import (
    build_team_measurement,
    save_team_measurement,
)


SAMPLES_FILENAME = "team_market_samples.csv"
HISTORICAL_PRICES_FILENAME = "historical_team_prices.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refit-days", type=int, default=14)
    parser.add_argument("--minimum-history-games", type=int, default=200)
    parser.add_argument("--edge-threshold", type=float, default=MIN_EDGE)
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

    samples = None
    if args.reuse_samples and samples_path.is_file():
        cached = pd.read_csv(samples_path)
        current, reason = samples_are_current(
            cached,
            known_markets=team_market_keys(),
            required_columns=("model_probability", "outcome", "push"),
            required_lines={
                "total_goals": DEFAULT_TOTAL_LINES,
                "puck_line": PUCK_LINES,
            },
        )
        if current:
            samples = cached
            print(f"Reusing {len(samples):,} cached samples from {samples_path}.")
        else:
            print(f"Not reusing the cached samples: {reason}")
    if samples is None:
        games = load_team_games(processed)
        if games.empty:
            print(
                "No team games. Run scripts/fetch_nhl_data.py and "
                "scripts/build_datasets.py first. No report was written."
            )
            return 1
        samples, walk = generate_team_samples(
            games,
            refit_days=args.refit_days,
            minimum_history_games=args.minimum_history_games,
            # What the default measurement describes is the shipped policy,
            # and what ships is the recorded verdict's call.
            use_rest=ships("team_b2b"),
        )
        print(walk.summary_line())
        outputs.mkdir(parents=True, exist_ok=True)
        samples.to_csv(samples_path, index=False, lineterminator="\n")

    prices_path = processed / HISTORICAL_PRICES_FILENAME
    prices = (
        pd.read_csv(prices_path)
        if prices_path.is_file()
        else pd.DataFrame(columns=["market"])
    )
    if prices.empty:
        print(
            "No historical team prices on disk, so nothing can be measured "
            "against a real price. The report will say that."
        )

    report = build_team_measurement(
        samples, prices, edge_threshold=args.edge_threshold
    )
    paths = save_team_measurement(report, output_dir=outputs)
    print(report.summary_line())
    for item in report.markets:
        print(f"  {item.market}: {item.verdict}")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
