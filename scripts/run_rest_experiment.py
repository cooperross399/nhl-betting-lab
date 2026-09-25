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
import sys
from pathlib import Path

import pandas as pd

from nhl_betting_lab.backtest.team_walk_forward import generate_team_samples
from nhl_betting_lab.config import MIN_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_team_games
from nhl_betting_lab.reports.team_markets_measurement import (
    MixedWindowError,
    measure_prices,
    select_price_window,
)


EXPERIMENT_MARKDOWN = "rest_experiment.md"
EXPERIMENT_JSON = "rest_experiment.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-threshold", type=float, default=MIN_EDGE)
    parser.add_argument(
        "--phase",
        default="late",
        help=(
            "Which snapshot window to measure. The team store holds two, and "
            "the best price across both is a price nobody could have taken. "
            "Defaults to `late`, the window the team measurement uses, because "
            "this verdict decides that measurement's `use_rest`."
        ),
    )
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
    # This read every window and every price captured after face-off until
    # 2026-09-24, the defect the team measurement had: the recorded +19.4u
    # included 1,070 bets priced once the game had started and 1,223 that
    # took an early quote over the late one.
    try:
        prices, window = select_price_window(prices, args.phase)
    except MixedWindowError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 2
    window_line = (
        f"Priced in the `{window['phase']}` window, median "
        f"{window['phase_hours']:.1f} hours before face-off. "
        f"{window['excluded_after_face_off']:,} price row(s) captured at or "
        f"after face-off and {window['excluded_other_windows']:,} from other "
        "windows were excluded."
        if window["phase"]
        else "The prices carry no window information."
    )
    print(window_line)

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
                processed_dir=processed,
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

    # A VARIANT THAT PLACED NO BET DECIDES NOTHING. A named window the store
    # does not hold leaves every market `None`, which summed to +0.0u; 0 is
    # not > 0, so this recorded "costs +0.0u on the priced sample" and
    # `ships: []` — withdrawing `team_b2b`, recorded at +5.8u in the `late`
    # window, on a run that priced nothing. The props rest experiment did
    # exactly this on the real four-hour store. A refusal writes nothing, so
    # the drift check reads the untouched verdict as "not re-decided" and the
    # refresh fails instead of opening a pull request.
    unmeasured = [
        name
        for name in variants
        if not any(entry and entry["bets"] for entry in results[name].values())
    ]
    if unmeasured:
        print(
            f"::error::The {' and '.join(unmeasured)} variant(s) placed no bet, "
            f"so this run measured nothing and records no verdict. {window_line}",
            file=sys.stderr,
        )
        return 2

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
        window_line,
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
            {
                # One convention across every experiment: `ships` is the list
                # of policy names in force, read by `verdicts.ships`. The
                # boolean it once was made the shared reader see "off".
                "results": results,
                "delta_units": delta,
                "phase": window["phase"],
                "phase_hours": window["phase_hours"],
                "excluded_after_face_off": window["excluded_after_face_off"],
                "excluded_other_windows": window["excluded_other_windows"],
                "ships": ["team_b2b"] if ships else [],
                "verdict": verdict,
            },
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
