#!/usr/bin/env python3
"""Does a player's recent form make better prop bets? The price test.

Cooper asked on 2026-10-09 for the model to factor in how individual players
are playing. The Shadow Stats measurement found recent form (a game's weight
halving every 10 of a player's games, regressed toward his long-run rate)
forecasts shots, goals, assists and points better than the card's long-run
rate on outcomes. That can rule a change out, never in: the price backtest
decides (`CLAUDE.md`).

So this prices the identical policy twice on identical bought prices: the
card's long-run rates, and the same model with each refit's skater rates
moved toward recent form (`walk_forward.apply_recent_form`). Both use the
back-to-back policy in force. The constants were fixed before this ran.

It records nothing the card reads. It writes `props_form_test.md` and
`.json` (not an `_experiment` file, so neither `verdicts.ships()` nor
Experiment Refresh's drift check sees it), and moving the card onto form is
Cooper's decision after 2027-04-25's freeze, or his explicit say-so before.

    PYTHONPATH=src .venv/bin/python scripts/run_props_form_experiment.py

Offline; spends nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from nhl_betting_lab import verdicts
from nhl_betting_lab.backtest.walk_forward import (
    FORM_HALF_LIFE_GAMES,
    FORM_STATS,
    generate_prop_samples,
)
from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs
from nhl_betting_lab.providers.team_names import (
    UnresolvedTeamsError,
    load_team_name_map,
)
from nhl_betting_lab.reports.player_props_backtest import run_backtest

REPORT_MARKDOWN = "props_form_test.md"
REPORT_JSON = "props_form_test.json"
WINDOWS = ("card", "late", "early")
VARIANTS = (("long_run", False), ("recent_form", True))


def _interval(interval) -> dict:
    return {
        "bets": interval.bets,
        "profit": interval.profit,
        "roi": interval.roi,
        "low": interval.low,
        "high": interval.high,
        "adjusted_low": interval.adjusted_low,
        "adjusted_high": interval.adjusted_high,
    }


def _cell(entry: dict) -> str:
    return (
        f"{entry['profit']:+.1f}u over {entry['bets']:,}, "
        f"{entry['roi']:+.2%} [{entry['low']:+.2%}, {entry['high']:+.2%}]"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-threshold", type=float, default=MIN_PROP_EDGE)
    parser.add_argument("--phase", default="card", choices=WINDOWS)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    outputs = Path(args.output_dir)
    logs = load_player_logs(processed)
    prices_path = processed / "historical_prop_prices.csv"
    if logs.empty or not prices_path.is_file():
        print("Need player logs and bought prop prices on disk first.", file=sys.stderr)
        return 1
    prices = pd.read_csv(prices_path)
    team_names = load_team_name_map(processed_dir=processed)
    use_rest = verdicts.ships("props_b2b", output_dir=outputs)

    results: dict[str, dict] = {}
    measured = None
    for name, form in VARIANTS:
        print(f"Generating walk-forward samples ({name})...")
        samples, walk = generate_prop_samples(logs, use_rest=use_rest, recent_form=form)
        print(f"  {walk.summary_line()}")
        try:
            report = run_backtest(
                prices, samples, edge_threshold=args.edge_threshold,
                phase=args.phase, team_names=team_names,
            )
        except UnresolvedTeamsError as error:
            print(f"::error::{error}", file=sys.stderr)
            return 2
        if report.overall is None or not report.overall.bets:
            print(
                f"::error::The {name} variant placed no bet in the `{args.phase}` "
                "window, so this run measured nothing. " + " ".join(report.notes),
                file=sys.stderr,
            )
            return 2
        measured = report
        results[name] = {
            "overall": _interval(report.overall),
            "by_market": {m: _interval(i) for m, i in report.by_market.items()},
        }

    base, form = results["long_run"], results["recent_form"]
    delta = form["overall"]["profit"] - base["overall"]["profit"]
    markets = sorted(set(base["by_market"]) & set(form["by_market"]))
    form_delta = sum(
        form["by_market"][m]["profit"] - base["by_market"][m]["profit"]
        for m in markets
        if m in FORM_STATS
    )
    zero = form["overall"]["low"] <= 0 <= form["overall"]["high"]
    verdict = (
        f"Recent form finishes {delta:+.1f}u against the long-run rates "
        f"({form_delta:+.1f}u of it in the four form markets). With form the "
        f"card-bar population returns {form['overall']['roi']:+.2%} over "
        f"{form['overall']['bets']:,} bets, against "
        f"{base['overall']['roi']:+.2%} over {base['overall']['bets']:,}. "
        + (
            "Its interval includes zero: no demonstrated edge."
            if zero
            else "Its interval excludes zero."
        )
    )

    payload = {
        "phase": measured.phase,
        "phase_hours": measured.phase_hours,
        "edge_threshold": args.edge_threshold,
        "use_rest": use_rest,
        "form_half_life_games": FORM_HALF_LIFE_GAMES,
        "form_stats": list(FORM_STATS),
        "delta_units": delta,
        "delta_units_form_markets": form_delta,
        "verdict": verdict,
        "results": results,
    }
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / REPORT_JSON).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Props price test: does recent form make better bets?",
        "",
        "The identical policy priced twice on identical bought prices: the "
        "card's long-run player rates, and the same model with shots, goals, "
        "assists and points moved toward each player's recent form (a game's "
        f"weight halving every {FORM_HALF_LIFE_GAMES} of his games, regressed "
        "toward his long-run rate, fixed in advance). One bet per wager at the "
        "best price, flat stakes, at the card's edge bar.",
        "",
        f"Priced in the `{measured.phase}` window, median "
        f"{measured.phase_hours:.1f} hours before face-off. Back-to-back "
        f"adjustment: {'on' if use_rest else 'off'}, as the verdict in force says.",
        "",
        "| Market | Long-run rates | Recent form | Delta |",
        "|:--|:--|:--|--:|",
    ]
    for m in markets:
        a, b = base["by_market"][m], form["by_market"][m]
        lines.append(f"| `{m}` | {_cell(a)} | {_cell(b)} | {b['profit'] - a['profit']:+.1f}u |")
    lines += [
        f"| **All props** | {_cell(base['overall'])} | {_cell(form['overall'])} | **{delta:+.1f}u** |",
        "",
        "Intervals are 95%, uncorrected; each variant's own report applies the "
        "family correction.",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "Nothing here reaches the card. Moving the card onto recent form is "
        "Cooper's decision (the model is frozen until 2027-04-25, "
        "`docs/when_this_ends.md`).",
        "",
    ]
    report_text = "\n".join(lines)
    (outputs / REPORT_MARKDOWN).write_text(report_text, encoding="utf-8")
    print(report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
