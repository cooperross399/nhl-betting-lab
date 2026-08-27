#!/usr/bin/env python3
"""Does the fitted calibration correction make money or lose it?

The house rule this answers, from `CLAUDE.md`:

    Calibration is a precondition, not a goal. Where historical prices exist,
    a price-based backtest decides. A change that improves calibration but
    loses the backtest does not ship.

Both corrections — the pooled Platt and the ice-time-conditional one —
straighten every reliability bucket. Nobody had asked what they do to the
price-tested return, which is the only question that decides whether they
reach the card. The EPL lab learned this the expensive way: a change that
improved calibration on every market cost about 140 units in its backtest.

Three variants of the identical bet-selection policy, on identical prices:

* **raw** — the distribution's own P(over), as the card uses today;
* **pooled** — corrected by the market's walk-forward Platt curve;
* **by-TOI** — corrected by the ice-time bucket's curve, pooled fallback.

Every correction applied to a bet was fitted only on grid samples from
strictly earlier dates. Anything else would leak the season into its own
bets and flatter whichever variant is worse.

    PYTHONPATH=src .venv/bin/python scripts/run_correction_experiment.py

Offline; spends nothing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.backtest.correction_timeline import build_timeline
from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.reports.player_props_backtest import run_backtest
from nhl_betting_lab.reports.props_calibration import expand_to_lines
from nhl_betting_lab.season import game_date


EXPERIMENT_MARKDOWN = "correction_experiment.md"
EXPERIMENT_JSON = "correction_experiment.json"

WINDOWS = (
    ("2024-25", "2024-10-01", "2025-05-01"),
    ("2025-26", "2025-10-01", "2026-05-01"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-threshold", type=float, default=MIN_PROP_EDGE)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    outputs = Path(args.output_dir)
    samples_path = outputs / "prop_calibration_samples.csv"
    prices_path = Path(args.processed_dir) / "historical_prop_prices.csv"
    if not samples_path.is_file() or not prices_path.is_file():
        print(
            "Need both the walk-forward samples and the bought prices on "
            "disk. Run the calibration and a purchase first."
        )
        return 1

    samples = pd.read_csv(samples_path)
    prices = pd.read_csv(prices_path)
    print(f"{len(samples):,} distribution samples, {len(prices):,} price rows.")

    print("Expanding distributions onto the calibration grid for fitting...")
    grid = expand_to_lines(samples)
    print(f"{len(grid):,} grid samples. Fitting walk-forward timelines...")
    timeline = build_timeline(grid)
    print(
        f"Timelines: {sum(len(v) for v in timeline.pooled.values())} pooled "
        f"fits across {len(timeline.pooled)} markets; "
        f"{len(timeline.bucketed)} market-bucket series."
    )

    variants = {
        "raw": None,
        "pooled": lambda market, day, toi, p: timeline.correct_pooled(
            market, day, p
        ),
        "by_toi": lambda market, day, toi, p: timeline.correct_bucketed(
            market, day, toi, p
        ),
    }

    dates = prices["commence_time"].map(game_date)
    results: dict[str, dict[str, dict]] = {}
    for label, start, end in WINDOWS:
        window_prices = prices[(dates >= start) & (dates <= end)]
        results[label] = {}
        for name, correct in variants.items():
            report = run_backtest(
                window_prices,
                samples,
                edge_threshold=args.edge_threshold,
                correct=correct,
            )
            overall = report.overall
            results[label][name] = {
                "bets": overall.bets if overall else 0,
                "profit": overall.profit if overall else 0.0,
                "roi": overall.roi if overall else 0.0,
                "low": overall.low if overall else 0.0,
                "high": overall.high if overall else 0.0,
                "by_market": {
                    market: {
                        "bets": interval.bets,
                        "roi": interval.roi,
                        "profit": interval.profit,
                    }
                    for market, interval in report.by_market.items()
                },
            }
            r = results[label][name]
            print(
                f"  {label} {name:<8} {r['bets']:>5} bets  "
                f"{r['profit']:>+8.1f}u  {r['roi']:>+7.1%}  "
                f"[{r['low']:+.1%} .. {r['high']:+.1%}]"
            )

    # The decision, in the repository's own words.
    def total_profit(name: str) -> float:
        return sum(results[w][name]["profit"] for w, _, _ in WINDOWS)

    raw_profit = total_profit("raw")
    verdicts: list[str] = []
    ships: list[str] = []
    for name in ("pooled", "by_toi"):
        delta = total_profit(name) - raw_profit
        wins_both = all(
            results[w][name]["profit"] >= results[w]["raw"]["profit"]
            for w, _, _ in WINDOWS
        )
        if wins_both and delta > 0:
            verdicts.append(
                f"**{name}** beats raw on both windows "
                f"({delta:+.1f}u across them). That clears the rule's bar — "
                "and it is still an in-sample comparison of three policies, "
                "so it earns a place on the card, not a claim of edge."
            )
            ships.append(name)
        elif delta > 0:
            verdicts.append(
                f"**{name}** is ahead overall ({delta:+.1f}u) but not on both "
                "windows. A variant that wins only where it wins is a "
                "selection; it does not ship."
            )
        else:
            verdicts.append(
                f"**{name}** loses the backtest ({delta:+.1f}u against raw) "
                "despite improving calibration. Exactly the EPL lesson: it "
                "does not ship, and the calibration tables do not overrule "
                "this."
            )

    lines = [
        "# Correction experiment: does better calibration make better bets?",
        "",
        (
            "The rule: where historical prices exist, the price-based "
            "backtest decides. Both corrections straighten every reliability "
            "bucket; this is the question that actually governs."
        ),
        "",
        "| Window | Variant | Bets | Profit | ROI | 95% interval |",
        "|:-------|:--------|-----:|-------:|----:|:-------------|",
    ]
    for label, _, _ in WINDOWS:
        for name in variants:
            r = results[label][name]
            lines.append(
                f"| {label} | {name} | {r['bets']} | {r['profit']:+.1f}u "
                f"| {r['roi']:+.1%} | {r['low']:+.1%} .. {r['high']:+.1%} |"
            )
    lines += ["", "## Verdict", ""]
    lines += [f"- {v}" for v in verdicts]
    lines += [
        "",
        (
            "Every correction applied to a bet was fitted only on samples "
            "from strictly earlier dates, on the same cadence the sample "
            "generator uses. The three variants saw identical prices and "
            "used the identical selection rule; only the stated probability "
            "differed."
        ),
        "",
    ]
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / EXPERIMENT_MARKDOWN).write_text("\n".join(lines), encoding="utf-8")
    (outputs / EXPERIMENT_JSON).write_text(
        json.dumps(
            {"results": results, "ships": ships, "verdicts": verdicts},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print("\n".join(verdicts))
    print(f"Written to {outputs / EXPERIMENT_MARKDOWN}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
