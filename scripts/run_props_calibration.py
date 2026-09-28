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

from nhl_betting_lab.backtest import samples_are_current
from nhl_betting_lab.backtest.walk_forward import generate_prop_samples
from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs
from nhl_betting_lab.markets import prop_market_keys
from nhl_betting_lab.reports.props_calibration import (
    build_calibration_report,
    save_calibration_report,
)
from nhl_betting_lab.verdicts import ships


#: What a cached samples file must carry to be reused. expected_toi_seconds is
#: here because a cache without it gives the ice-time correction nothing it can
#: index on honestly; regenerating is the only right answer.
REUSABLE_SAMPLE_COLUMNS = ("mean", "dispersion_r", "actual", "expected_toi_seconds")


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

    # The default measurement describes the shipped policy, and what ships is
    # the recorded verdict's call, not this script's.
    use_rest = ships("props_b2b", output_dir=outputs)
    # Read before the cache is judged, because the cache is judged against
    # them: which games exist is half of whether it is current.
    logs = load_player_logs(processed)

    samples = None
    if args.reuse_samples and samples_path.is_file():
        import pandas as pd

        cached = pd.read_csv(samples_path)
        # The policy and the games are checked as well as the schema. This
        # checked the schema alone, so after a verdict flipped the old
        # policy's cache was reused (194,707 of 749,115 fitted means differ
        # between the two), and a cache the logs had outgrown was reused
        # forever — Gameday Refresh restores it every run. Either one
        # regenerates here.
        current, reason = samples_are_current(
            cached,
            known_markets=prop_market_keys(),
            required_columns=REUSABLE_SAMPLE_COLUMNS,
            required_policy={"use_rest": use_rest},
            source_games=logs,
        )
        if current:
            samples = cached
            print(f"Reusing {len(samples):,} cached samples from {samples_path}.")
        else:
            print(f"Not reusing the cached samples: {reason}")
            # Removed before regenerating, not overwritten after. The file
            # used to stay put until the rebuild replaced it, so a rebuild
            # that never happened — no logs, or a crash — left the refused
            # samples on disk looking exactly like fresh ones. Experiment
            # Refresh runs this under `|| true` and then only asks whether
            # the file is there, and the correction experiment went on to
            # re-decide `by_toi` on the samples this had just refused.
            samples_path.unlink()
    if samples is None:
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
            use_rest=use_rest,
        )
        print(walk.summary_line())
        outputs.mkdir(parents=True, exist_ok=True)
        samples.to_csv(samples_path, index=False, lineterminator="\n")

    report = build_calibration_report(samples)
    paths = save_calibration_report(report, output_dir=outputs)

    # Refresh the live by-TOI correction curves, fitted on everything to
    # date — which for live pricing is exactly walk-forward: today's games
    # are not in the fit. Whether the card *applies* them is a separate,
    # recorded decision; see scripts/run_correction_experiment.py.
    from datetime import datetime, timezone

    from nhl_betting_lab.models.toi_corrections import (
        fit_current_corrections,
        save_current_corrections,
    )
    from nhl_betting_lab.reports.props_calibration import expand_to_lines

    grid = (
        samples
        if "model_probability" in samples.columns
        else expand_to_lines(samples)
    )
    current = fit_current_corrections(
        grid,
        fitted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    corrections_path = save_current_corrections(
        current, processed_dir=Path(args.processed_dir)
    )
    print(f"Live corrections refreshed: {current.describe()} -> {corrections_path}")
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
