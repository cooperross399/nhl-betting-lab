#!/usr/bin/env python3
"""Does knowing about back-to-backs make better prop bets?

The diagnostic that motivated this: on a back-to-back, scoring production
runs about six percent below the model's expectation (goals 0.963, assists
0.982, points 0.975 act/pred against rested baselines of 1.02-1.04), the
opponent-tired mirror runs the same amount *above*, the both-tired cell
cancels to baseline, and the tired team's goalie faces more shots — every
direction fatigue predicts, in seven independent settlement columns.

A mechanism and a diagnostic are still not the decision. The rule is the one
every adjustment in this repository answers to: **the price-based backtest
decides.** Two variants of the identical policy on identical prices — rest
known, rest ignored — and the adjustment ships only if it does not lose.

The verdict is recorded to `props_rest_experiment.json`, and two things obey
it rather than asserting their own: the card passes schedule history to the
props pricer only while the verdict ships, and the default walk-forward
sample generation follows it the same way.

    PYTHONPATH=src .venv/bin/python scripts/run_props_rest_experiment.py

Offline; spends nothing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.backtest.walk_forward import generate_prop_samples
from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs
from nhl_betting_lab.reports.player_props_backtest import run_backtest


EXPERIMENT_MARKDOWN = "props_rest_experiment.md"
EXPERIMENT_JSON = "props_rest_experiment.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-threshold", type=float, default=MIN_PROP_EDGE)
    parser.add_argument(
        "--phase",
        default="card",
        help=(
            "Which snapshot window to measure. The store holds more than "
            "one and mixing them takes the better of two moments, which "
            "is a price nobody could have taken. Defaults to the window "
            "the card actually runs in."
        ),
    )
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    outputs = Path(args.output_dir)
    logs = load_player_logs(processed)
    prices_path = processed / "historical_prop_prices.csv"
    if logs.empty or not prices_path.is_file():
        print("Need player logs and bought prop prices on disk first.")
        return 1
    prices = pd.read_csv(prices_path)

    results: dict[str, dict] = {}
    reports: dict[str, object] = {}
    for name, use_rest in (("rest_ignored", False), ("rest_known", True)):
        print(f"Generating walk-forward samples ({name})...")
        samples, walk = generate_prop_samples(logs, use_rest=use_rest)
        print(f"  {walk.summary_line()}")
        # The window is named rather than inferred. The store now holds
        # the card's own hour (T-9.5h) beside the originally bought
        # T-4h, and `phase="auto"` refuses to choose — correctly, since
        # the better of two moments is a price nobody could have taken.
        # `card` is the right basis because these verdicts govern the
        # card, and the two windows were measured as equivalent
        # (-0.23 points, inside noise) before this was changed.
        report = run_backtest(
            prices, samples, edge_threshold=args.edge_threshold,
            phase=args.phase,
        )
        reports[name] = report
        results[name] = {
            market: {
                "bets": interval.bets,
                "profit": interval.profit,
                "roi": interval.roi,
            }
            for market, interval in report.by_market.items()
        }
        for market, entry in sorted(results[name].items()):
            print(
                f"  {market:<18} {entry['bets']:>5} bets  "
                f"{entry['profit']:>+8.1f}u  {entry['roi']:>+7.1%}"
            )

    def total(name: str) -> float:
        return sum(entry["profit"] for entry in results[name].values())

    delta = total("rest_known") - total("rest_ignored")
    both = set(results["rest_known"]) & set(results["rest_ignored"])
    wins = sum(
        1
        for market in both
        if results["rest_known"][market]["profit"]
        > results["rest_ignored"][market]["profit"]
    )

    ships = delta > 0
    if ships:
        verdict = (
            f"Rest-known finishes **{delta:+.1f}u** ahead across the measured "
            f"markets, improving {wins} of {len(both)}. The adjustment ships "
            "because the bar is *must not lose the backtest* and it does not, "
            "while making the stated probabilities honest on the quarter of "
            "the schedule that is a back-to-back. It is not evidence of an "
            "edge, and a delta this size would not survive any correction "
            "for chance."
        )
    else:
        verdict = (
            f"Knowing about back-to-backs costs {delta:+.1f}u on the priced "
            "sample, whatever the diagnostic said. It does not ship: a "
            "mechanism explains a bias, and only the backtest decides "
            "whether correcting it beats the prices."
        )

    payload = {
        "ships": ["props_b2b"] if ships else [],
        "delta_units": delta,
        "markets_improved": wins,
        "markets_measured": len(both),
        "edge_threshold": args.edge_threshold,
        "verdict": verdict,
        "results": results,
    }
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / EXPERIMENT_JSON).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# Props rest experiment: does knowing about back-to-backs make better bets?",
        "",
        (
            "Two variants of the identical policy on identical prices. The "
            "diagnostic (own-side scoring −6%, opponent-side +5%, both-tired "
            "cancelling, the tired team's goalie busier) said the model "
            "misses fatigue; this decides whether correcting it beats the "
            "prices that were actually for sale."
        ),
        "",
        "| Market | Rest ignored | Rest known | Delta |",
        "|:-------|-------------:|-----------:|------:|",
    ]
    for market in sorted(both):
        a = results["rest_ignored"][market]
        b = results["rest_known"][market]
        lines.append(
            f"| `{market}` | {a['profit']:+.1f}u ({a['bets']}) "
            f"| {b['profit']:+.1f}u ({b['bets']}) "
            f"| {b['profit'] - a['profit']:+.1f}u |"
        )
    lines += [
        (
            f"| **Total** | {total('rest_ignored'):+.1f}u "
            f"| {total('rest_known'):+.1f}u | **{delta:+.1f}u** |"
        ),
        "",
        "## Verdict",
        "",
        verdict,
        "",
        (
            "Recorded to `props_rest_experiment.json`. The card and the "
            "default sample generation read the verdict rather than assert "
            "their own — the configuration stays auditable against the "
            "measurement that made it."
        ),
        "",
    ]
    (outputs / EXPERIMENT_MARKDOWN).write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{verdict}")
    print(f"Recorded: {outputs / EXPERIMENT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
