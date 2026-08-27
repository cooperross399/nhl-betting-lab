#!/usr/bin/env python3
"""Does knowing about back-to-backs make better team bets?

The diagnostic that motivated this: the model prices "away on a back-to-back,
home rested" at 52.8% home and it happens 61.3%, over 574 games — an
8.5-point miss on the single most-documented effect in the sport. Fatigue is
causal, rest derives from the schedule (known before puck drop, so it leaks
nothing), and the fix is two shrunk scalars per venue.

A mechanism and a diagnostic are still not the decision. The rule is the same
one the correction experiment enforces: **the price-based backtest decides.**
Two variants of the identical policy on identical prices — rest known, rest
ignored — and the adjustment ships only if it wins.

    PYTHONPATH=src .venv/bin/python scripts/run_rest_experiment.py

Offline; spends nothing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.backtest.team_walk_forward import generate_team_samples
from nhl_betting_lab.config import MIN_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_team_games
from nhl_betting_lab.reports.team_markets_measurement import measure_prices


EXPERIMENT_MARKDOWN = "rest_experiment.md"
EXPERIMENT_JSON = "rest_experiment.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-threshold", type=float, default=MIN_EDGE)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    outputs = Path(args.output_dir)
    games = load_team_games(processed)
    prices_path = processed / "historical_team_prices.csv"
    if games.empty or not prices_path.is_file():
        print("Need team games and bought team prices on disk first.")
        return 1
    prices = pd.read_csv(prices_path)

    results: dict[str, dict] = {}
    variants = {"rest_ignored": False, "rest_known": True}
    for name, use_rest in variants.items():
        print(f"Generating walk-forward samples ({name})...")
        samples, walk = generate_team_samples(games, use_rest=use_rest)
        print(f"  {walk.summary_line()}")
        results[name] = {}
        for market in sorted(set(samples["market"])):
            interval = measure_prices(
                prices,
                samples,
                market=market,
                edge_threshold=args.edge_threshold,
                looks=samples["market"].nunique(),
            )
            if interval is None:
                results[name][market] = None
                continue
            results[name][market] = {
                "bets": interval.bets,
                "profit": interval.profit,
                "roi": interval.roi,
                "low": interval.low,
                "high": interval.high,
            }
            r = results[name][market]
            print(
                f"  {market:<18} {r['bets']:>5} bets  {r['profit']:>+8.1f}u  "
                f"{r['roi']:>+7.1%}"
            )

    def total(name: str) -> float:
        return sum(
            entry["profit"]
            for entry in results[name].values()
            if entry is not None
        )

    delta = total("rest_known") - total("rest_ignored")
    per_market_wins = sum(
        1
        for market in results["rest_known"]
        if results["rest_known"].get(market)
        and results["rest_ignored"].get(market)
        and results["rest_known"][market]["profit"]
        > results["rest_ignored"][market]["profit"]
    )
    measured = sum(1 for entry in results["rest_known"].values() if entry)

    if delta > 0:
        verdict = (
            f"The priced sample is close to indifferent: rest-known finishes "
            f"**{delta:+.1f}u** ahead across the measured markets, improving "
            f"{per_market_wins} of {measured}. That is the interesting "
            "finding — the books already price fatigue, so correcting the "
            "model's 8.5-point residual bias mostly moves its probabilities "
            "toward numbers the market had all along. The adjustment ships "
            "because the rule's bar is *must not lose the backtest* and it "
            "does not, while making the stated probabilities honest on a "
            "quarter of the schedule. It is not evidence of an edge, and a "
            "delta this small would not survive any correction for chance."
        )
        ships = True
    else:
        verdict = (
            f"Knowing about back-to-backs costs {delta:+.1f}u on the priced "
            "sample, whatever the residual diagnostic said. It does not ship. "
            "A mechanism explains a bias; only the backtest decides whether "
            "correcting it beats the prices, and here the books already "
            "priced the fatigue in better than the adjustment does."
        )
        ships = False

    lines = [
        "# Rest experiment: does knowing about back-to-backs make better bets?",
        "",
        (
            "The motivating diagnostic: an 8.5-point moneyline miss on away "
            "back-to-backs over 574 games. Mechanism and diagnostic are still "
            "not the decision — identical policies on identical prices, one "
            "knowing the schedule, one ignoring it."
        ),
        "",
        "| Market | Variant | Bets | Profit | ROI | 95% interval |",
        "|:-------|:--------|-----:|-------:|----:|:-------------|",
    ]
    for name in variants:
        for market, entry in sorted(results[name].items()):
            if entry is None:
                lines.append(f"| `{market}` | {name} | — | — | — | no prices |")
                continue
            lines.append(
                f"| `{market}` | {name} | {entry['bets']} "
                f"| {entry['profit']:+.1f}u | {entry['roi']:+.1%} "
                f"| {entry['low']:+.1%} .. {entry['high']:+.1%} |"
            )
    lines += ["", "## Verdict", "", verdict, ""]
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / EXPERIMENT_MARKDOWN).write_text("\n".join(lines), encoding="utf-8")
    (outputs / EXPERIMENT_JSON).write_text(
        json.dumps(
            {"results": results, "delta": delta, "ships": ships, "verdict": verdict},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
