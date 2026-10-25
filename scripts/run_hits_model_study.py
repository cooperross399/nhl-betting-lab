#!/usr/bin/env python3
"""Does the dialled-in hits model price hits better? Walk-forward, on outcomes
and on the bought hits prices.

Cooper asked on 2026-10-25 to "enhance and improve the hits portion of our
model. Dial it in more", and added "i think overs could be in play a lot more
often". The parts (`player_props.HITS_OPTIONS`): the rink's hits scorer, a
shrinkage measured from the real spread of hit rates, recency weighting, and
a spread measured inside each player's own games. They are on the card from
the first card after this merges, on Cooper's standing rule that a factor he
asks for is wired in; this measures them, it does not gate them.

Each variant is priced walk-forward (`generate_prop_samples`, the back-to-back
policy in force, hits only) and scored two ways:

1. Outcomes: the negative-binomial log-likelihood of each player-game's actual
   hits, paired against the old model on the same player-games, with a 95%
   interval clustered on the game; and the mean predicted against actual for
   skaters the old model priced at 2 or more hits a game (the players books
   post hits lines on).
2. Prices: the bought hits prices (the `card` window; the four-hour buy holds
   no hits), one bet per wager at the best price, flat stakes, at the card's
   prop bar, split into overs and unders.

Writes `data/outputs/hits_model_study.md` and `.json`: aggregates only, no
price, line or book. Offline; spends nothing.

    PYTHONPATH=src .venv/bin/python scripts/run_hits_model_study.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nhl_betting_lab import verdicts
from nhl_betting_lab.backtest.walk_forward import (
    DEFAULT_LINES,
    distribution_from,
    generate_prop_samples,
)
from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs
from nhl_betting_lab.models.player_props import HITS_OPTIONS
from nhl_betting_lab.providers.team_names import (
    UnresolvedTeamsError,
    load_team_name_map,
)
from nhl_betting_lab.reports.player_props_backtest import run_backtest
from nhl_betting_lab.stats import roi_interval

REPORT_MARKDOWN = "hits_model_study.md"
REPORT_JSON = "hits_model_study.json"

VARIANTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("old", frozenset()),
    ("rink", frozenset({"rink"})),
    ("rink_dispersion", frozenset({"rink", "dispersion"})),
    ("shipped", frozenset(HITS_OPTIONS)),
)
LABELS = {
    "old": "Old hits model",
    "rink": "Rink scorer only",
    "rink_dispersion": "Rink + own-games spread",
    "shipped": "All four (on the card)",
}
KEY = ["game_id", "player_id"]


def _log_likelihood(samples: pd.DataFrame) -> pd.Series:
    values = []
    for mean, r, actual in zip(samples["mean"], samples["dispersion_r"], samples["actual"]):
        r_value = None if r is None or (isinstance(r, float) and math.isnan(r)) else float(r)
        p = distribution_from(float(mean), r_value).pmf(int(round(float(actual))))
        values.append(math.log(max(p, 1e-12)))
    return pd.Series(values, index=samples.index)


def _clustered_mean(diff: pd.Series, clusters: pd.Series, draws: int = 1000) -> tuple[float, float, float]:
    by = pd.DataFrame({"d": diff.to_numpy(), "c": clusters.to_numpy()}).groupby("c")["d"]
    sums = by.sum().to_numpy()
    counts = by.size().to_numpy()
    rng = np.random.default_rng(20261025)
    stats = []
    for _ in range(draws):
        pick = rng.integers(0, len(sums), len(sums))
        stats.append(sums[pick].sum() / counts[pick].sum())
    return float(sums.sum() / counts.sum()), float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def _side(bets, side: str) -> dict:
    chosen = [b for b in bets if str(b.selection).lower() == side]
    if not chosen:
        return {"bets": 0, "profit": 0.0, "roi": 0.0, "low": 0.0, "high": 0.0}
    interval = roi_interval([b.profit for b in chosen])
    return {
        "bets": interval.bets, "profit": interval.profit, "roi": interval.roi,
        "low": interval.low, "high": interval.high,
    }


def _cell(entry: dict) -> str:
    if not entry["bets"]:
        return "no bets"
    return (
        f"{entry['profit']:+.1f}u over {entry['bets']:,}, "
        f"{entry['roi']:+.2%} [{entry['low']:+.2%}, {entry['high']:+.2%}]"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-threshold", type=float, default=MIN_PROP_EDGE)
    parser.add_argument("--phase", default="card", choices=("card", "late", "early"))
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
    if "market" in prices:
        only_hits = prices[prices["market"].astype(str).str.contains("hits")]
        prices = only_hits if not only_hits.empty else prices
    team_names = load_team_name_map(processed_dir=processed)
    use_rest = verdicts.ships("props_b2b", output_dir=outputs)

    samples: dict[str, pd.DataFrame] = {}
    results: dict[str, dict] = {}
    for name, options in VARIANTS:
        print(f"Generating walk-forward hits samples ({name}: {sorted(options) or 'none'})...")
        frame, walk = generate_prop_samples(
            logs, lines={"hits": DEFAULT_LINES["hits"]}, use_rest=use_rest,
            hits_options=options,
        )
        print(f"  {walk.summary_line()}")
        frame = frame[frame["market"] == "hits"].copy()
        frame["ll"] = _log_likelihood(frame)
        samples[name] = frame
        try:
            report = run_backtest(
                prices, frame.drop(columns=["ll"]), edge_threshold=args.edge_threshold,
                phase=args.phase, team_names=team_names,
            )
        except UnresolvedTeamsError as error:
            print(f"::error::{error}", file=sys.stderr)
            return 2
        hits_bets = [b for b in report.bets if b.market == "hits"]
        over = _side(hits_bets, "over")
        under = _side(hits_bets, "under")
        everything = roi_interval([b.profit for b in hits_bets]) if hits_bets else None
        results[name] = {
            "options": sorted(options),
            "phase": report.phase,
            "phase_hours": report.phase_hours,
            "all": {
                "bets": everything.bets if everything else 0,
                "profit": everything.profit if everything else 0.0,
                "roi": everything.roi if everything else 0.0,
                "low": everything.low if everything else 0.0,
                "high": everything.high if everything else 0.0,
            },
            "over": over,
            "under": under,
            "mean_predicted": float(frame["mean"].mean()),
            "mean_actual": float(frame["actual"].mean()),
            "samples": int(len(frame)),
        }

    base = samples["old"]
    heavy_keys = base[base["mean"] >= 2.0][KEY]
    for name, frame in samples.items():
        joined = base[KEY + ["ll"]].merge(frame[KEY + ["ll", "mean", "actual"]], on=KEY, suffixes=("_old", ""))
        mean, low, high = _clustered_mean(joined["ll"] - joined["ll_old"], joined["game_id"])
        heavy = frame.merge(heavy_keys, on=KEY)
        results[name]["log_likelihood"] = {
            "paired_vs_old": mean, "low": low, "high": high, "n": int(len(joined)),
            "per_game": float(joined["ll"].mean()),
        }
        results[name]["heavy_hitters"] = {
            "n": int(len(heavy)),
            "mean_predicted": float(heavy["mean"].mean()) if len(heavy) else 0.0,
            "mean_actual": float(heavy["actual"].mean()) if len(heavy) else 0.0,
        }

    payload = {
        "edge_threshold": args.edge_threshold,
        "use_rest": use_rest,
        "results": results,
    }
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / REPORT_JSON).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    phase = results["old"]["phase"]
    hours = results["old"]["phase_hours"]
    lines = [
        "# Hits model study",
        "",
        "Every variant priced walk-forward on the same games (back-to-back "
        f"adjustment {'on' if use_rest else 'off'}, as the verdict in force says).",
        "",
        "## On outcomes",
        "",
        "| Variant | Log-likelihood per player-game vs old (95%, clustered on game) | "
        "Mean predicted / actual, all | Skaters the old model put at 2+ hits: predicted / actual |",
        "|:--|:--|:--|:--|",
    ]
    for name, _ in VARIANTS:
        r = results[name]
        ll = r["log_likelihood"]
        hv = r["heavy_hitters"]
        lines.append(
            f"| {LABELS[name]} | {ll['paired_vs_old']:+.4f} [{ll['low']:+.4f}, {ll['high']:+.4f}] "
            f"over {ll['n']:,} | {r['mean_predicted']:.3f} / {r['mean_actual']:.3f} | "
            f"{hv['mean_predicted']:.3f} / {hv['mean_actual']:.3f} over {hv['n']:,} |"
        )
    lines += [
        "",
        f"## On the bought hits prices (`{phase}` window"
        + (f", median {hours:.1f} hours before face-off" if hours is not None else "")
        + f", {args.edge_threshold:.0%} bar)",
        "",
        "| Variant | All hits bets | Overs | Unders |",
        "|:--|:--|:--|:--|",
    ]
    for name, _ in VARIANTS:
        r = results[name]
        lines.append(f"| {LABELS[name]} | {_cell(r['all'])} | {_cell(r['over'])} | {_cell(r['under'])} |")
    lines += [
        "",
        "Intervals are 95%, uncorrected, and four variants were tried on one "
        "dataset. An interval that includes zero is no demonstrated edge.",
        "",
        "All four parts are on the card (Cooper, 2026-10-25); this measures "
        "them, it does not gate them.",
        "",
    ]
    text = "\n".join(lines)
    (outputs / REPORT_MARKDOWN).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
