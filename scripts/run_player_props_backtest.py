#!/usr/bin/env python3
"""Measure the props model against historically-bought prices.

Writes `data/outputs/player_props_backtest.md` — one of the three measurement
outputs the operating contract names.

    PYTHONPATH=src .venv/bin/python scripts/run_player_props_backtest.py

Offline by default: it reads whatever historical prices have already been
bought into `data/processed/historical_prop_prices.csv` and the cached
walk-forward samples. It buys nothing. Buying historical prices costs ten
credits per market per event and is a separate, deliberate command.

When no historical prices exist, the report says so plainly and measures
nothing, rather than presenting a calibration number as though it were a
backtest.

When prices exist and the walk-forward samples do not, or either file exists
and cannot be read, it refuses: `::error::`, exit 1, and nothing written, so
the previous report stays where it is rather than being replaced by one that
says nothing was bought.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.providers.team_names import (
    UnresolvedTeamsError,
    load_team_name_map,
)
from nhl_betting_lab.reports.player_props_backtest import run_backtest, save_backtest
from nhl_betting_lab.season import game_date


HISTORICAL_PRICES_FILENAME = "historical_prop_prices.csv"
RETENTION_FILENAME = "historical_props_retention.json"
SAMPLES_FILENAME = "prop_calibration_samples.csv"


class UnreadableInputError(Exception):
    """A file that exists and cannot be parsed, which is not no file."""


def _load(path: Path, columns: list[str]) -> pd.DataFrame:
    """The frame at `path`; an empty one when there is no file.

    A file that exists and cannot be parsed used to come back empty too,
    exactly as though it were absent. A damaged samples file then printed "No
    walk-forward samples are on disk" and overwrote the contract report with
    one measuring nothing — a copy of the real one went from the `late`
    window and 550,225 priced outcomes to no window and 0 — and a damaged
    price store read as "no prices", so every summary said none had been
    bought. Absent is a fact a report can state; unreadable is a fault it
    cannot, so it refuses.
    """
    if not path.is_file():
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_csv(path)
    except (
        OSError,
        UnicodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as error:
        # One line: a GitHub annotation ends at the first newline, and the
        # parser's own message carries one.
        reason = " ".join(str(error).split())
        raise UnreadableInputError(
            f"{path} exists but could not be read ({type(error).__name__}: "
            f"{reason}). An unreadable file is not an empty one, so nothing "
            "was measured and no report was written."
        ) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-threshold", type=float, default=MIN_PROP_EDGE)
    parser.add_argument(
        "--from",
        dest="start",
        default="",
        help=(
            "Measure only prices on or after this ISO date. Use it to score "
            "one window at a time: pooling two windows makes a bigger sample, "
            "which is a different question from whether a result replicates."
        ),
    )
    parser.add_argument("--to", dest="end", default="", help="ISO end date.")
    parser.add_argument(
        "--label",
        default="",
        help="Name for this window, written into the report and its filenames.",
    )
    parser.add_argument(
        "--phase",
        default="auto",
        choices=("auto", "card", "late", "early", "all"),
        help=(
            "Which snapshot window to measure. `auto` refuses when the store "
            "holds more than one, which is what it is for. The guard used to "
            "say 'name the window explicitly' and this flag did not exist, so "
            "the only way to follow the instruction was to edit the source."
        ),
    )
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    outputs = Path(args.output_dir)

    try:
        prices = _load(
            processed / HISTORICAL_PRICES_FILENAME,
            ["date", "market", "player", "selection", "line", "american_odds", "book"],
        )
        samples = _load(
            outputs / SAMPLES_FILENAME,
            ["date", "market", "player", "line", "model_probability", "actual"],
        )
    except UnreadableInputError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1

    # PRICES WITH NO MODEL TO MEASURE THEM AGAINST ARE A REFUSAL, NOT A
    # REPORT. This used to print one stdout line and write the report anyway:
    # with 20,000 price rows and `--phase late` it read "No snapshot window
    # was filtered" and "Priced outcomes seen: 0", exited 0, and the claims
    # summary built on it said no prices had been bought for any market. It
    # happens in a worktree (the samples file is gitignored and read from
    # --output-dir) and in a purchase probe, which skips the step that builds
    # them. The calibration and team measurements already refuse in the same
    # position; a report with no model that looks like a report is worse
    # than none. No prices at all is still reported, because "nothing has
    # been bought" is then true.
    if samples.empty and not prices.empty:
        print(
            f"::error::{len(prices):,} historical price row(s) are on disk in "
            f"{processed / HISTORICAL_PRICES_FILENAME} and there are no "
            f"walk-forward samples at {outputs / SAMPLES_FILENAME} to measure "
            "them against. Run scripts/run_props_calibration.py with the same "
            "--output-dir first. Nothing was measured and no report was "
            "written, so the previous one is untouched.",
            file=sys.stderr,
        )
        return 1

    retention_note = ""
    unmeasurable: dict[str, str] = {}
    retention_path = outputs / RETENTION_FILENAME
    if retention_path.is_file():
        try:
            payload = json.loads(retention_path.read_text(encoding="utf-8"))
            retention_note = str(payload.get("table", ""))
            unmeasurable = dict(payload.get("unmeasurable", {}) or {})
        except (OSError, UnicodeError, json.JSONDecodeError):
            retention_note = (
                "A retention probe file exists but could not be read, so "
                "retention is treated as unknown."
            )

    if args.start or args.end:
        before = len(prices)
        if not prices.empty:
            # Filter on the league game date, not the UTC commence date, so a
            # window boundary does not cut an evening slate in half.
            source = (
                prices["commence_time"]
                if "commence_time" in prices.columns
                else prices["date"]
            )
            dates = source.map(game_date)
            keep = pd.Series(True, index=prices.index)
            if args.start:
                keep &= dates >= args.start
            if args.end:
                keep &= dates <= args.end
            prices = prices[keep]
        print(
            f"Window {args.start or 'start'} .. {args.end or 'end'}: "
            f"{len(prices):,} of {before:,} price rows."
        )

    if prices.empty:
        print(
            "No historical prop prices are on disk, so nothing can be "
            "measured against a real price. The report will say that."
        )
    if samples.empty:
        print(
            "No walk-forward samples are on disk. Run "
            "scripts/run_props_calibration.py first."
        )

    try:
        report = run_backtest(
            prices,
            samples,
            edge_threshold=args.edge_threshold,
            phase="" if args.phase == "all" else args.phase,
            retention_note=retention_note,
            unmeasurable_markets=unmeasurable,
            window_label=args.label
            or (
                f"{args.start or 'start'} to {args.end or 'end'}"
                if args.start or args.end
                else ""
            ),
            # From the same directory as the prices, as the team measurement
            # and forward settlement read it; rebuilt from the boxscore cache
            # when the file is absent.
            team_names=load_team_name_map(processed_dir=processed),
        )
    except UnresolvedTeamsError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 2
    paths = save_backtest(report, output_dir=outputs, label=args.label)
    print(report.summary_line())
    for market, interval in report.by_market.items():
        print(f"  {market}: {interval.verdict()}")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
