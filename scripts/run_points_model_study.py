#!/usr/bin/env python3
"""Why does the props model hold the points and assists unders too likely?
Walk-forward, on outcomes, on the bought prices and on the live ledger.

Cooper, 2026-11-10: the forward ledger's population B had the points under at
a model 0.666 against a 0.551 hit rate (price 0.574), and assists 0.722
against 0.617 (price 0.633). Read off the ledger's own frozen opinions (every
settled points and assists opinion, both sides, before any bar), the model's
points mean ran 7.6% below what landed over 6,454 player-games and assists
12.3% below over 5,126, with assists' shortfall growing with the prediction
(actual = 1.20 x predicted); goals sat within 2%. Every one of those is
priced as a Poisson, and once the mean is scaled to what landed the Pearson
dispersion is 1.02 (points) and 0.99 (assists): the shape is right and the
level is low. So the candidates are the inputs to the mean
(`player_props.SCORING_OPTIONS`):

* ``pp_centred``: the power-play proxy, 1 + 1.4 x (share - 0.12) clamped to
  0.88-1.18, averages well under 1.0 because most skaters take far less than
  12% of their club's power-play goals, while the rate it multiplies already
  holds every power-play point.
* ``shrinkage``: every stat shrinks toward its position at 70,000 seconds;
  the measured out-of-sample slopes (1.32 assists, 1.21 points) say it is
  too much.

Each variant is priced walk-forward (`generate_prop_samples`, refit every 14
days, as the card prices: the back-to-back verdict in force, last-five team
form, matchup by position and the scoring environment), points and assists
only, and scored:

1. Outcomes: the Poisson log-likelihood of each player-game, paired against
   the old model on the same player-games with a 95% interval clustered on
   the game, over every season and over 2026-27 alone; mean predicted
   against actual; the slope of actual on predicted; and, at over 0.5, the
   side the model leans (its chance above 50%) against how often that side
   landed, for the over and the under apart.
2. Prices: the bought prices (`card` window) and the forward ledger's frozen
   prices, one bet per wager at the best price, flat stakes, at the 6% prop
   bar, by side: bets, the model's mean chance, the hit rate, the price's
   implied chance and the ROI with its 95% interval clustered on the night.

**The rule, fixed before this ran.** A variant ships only if, for BOTH
points and assists: (a) its paired log-likelihood gain over the old model is
positive with the interval excluding zero, pooled and in 2026-27 alone; and
(b) at over 0.5 the gap between the model's chance of its leaned side and
that side's hit rate is no larger than the old model's for the over AND for
the under (pooled). Among those that pass, the largest pooled points gain
ships. Prices are reported, never a gate: an interval spanning zero is no
demonstrated edge.

Writes `data/outputs/points_model_study.md` and `.json`: aggregates only, no
price, line or book. Offline; spends nothing.

    PYTHONPATH=src .venv/bin/python scripts/run_points_model_study.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import gammaln

from nhl_betting_lab import verdicts
from nhl_betting_lab.backtest.walk_forward import generate_prop_samples
from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs
from nhl_betting_lab.providers.team_names import (
    UnresolvedTeamsError,
    load_team_name_map,
)
from nhl_betting_lab.reports.player_props_backtest import run_backtest
from nhl_betting_lab.stats import clustered_mean_interval

REPORT_MARKDOWN = "points_model_study.md"
REPORT_JSON = "points_model_study.json"
MARKETS = ("points", "assists")
SEASON_FROM = "2026-10-01"
LEDGER_FROM = "2026-10-07"
VARIANTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("old", frozenset()),
    ("pp_centred", frozenset({"pp_centred"})),
    ("shrinkage", frozenset({"shrinkage"})),
    ("both", frozenset({"pp_centred", "shrinkage"})),
)
LABELS = {
    "old": "Old model",
    "pp_centred": "Power-play proxy centred",
    "shrinkage": "Measured shrinkage",
    "both": "Both",
}
KEY = ["game_id", "player_id", "market"]


def _poisson_ll(mean: pd.Series, actual: pd.Series) -> pd.Series:
    m = mean.astype(float).clip(lower=1e-9).to_numpy()
    k = actual.astype(float).round().to_numpy()
    return pd.Series(-m + k * np.log(m) - gammaln(k + 1.0), index=mean.index)


def _interval(values: pd.Series, clusters: pd.Series) -> dict:
    if len(values) < 2:
        return {"mean": float(values.mean()) if len(values) else 0.0, "low": 0.0, "high": 0.0, "n": int(len(values))}
    iv = clustered_mean_interval(values.astype(float).tolist(), list(clusters))
    return {"mean": iv.roi, "low": iv.low, "high": iv.high, "n": int(len(values))}


def _lean_sides(frame: pd.DataFrame, line: float) -> dict:
    """At `line`, the side the model leans against how often it landed."""
    p_over = 1.0 - np.exp(-frame["mean"].astype(float))
    if line > 1.0:
        m = frame["mean"].astype(float)
        p_over = 1.0 - np.exp(-m) * (1.0 + m)
    over = frame["actual"].astype(float) > line
    out = {}
    for side, leans, chance, landed in (
        ("over", p_over > 0.5, p_over, over),
        ("under", p_over < 0.5, 1.0 - p_over, ~over),
    ):
        n = int(leans.sum())
        pred = float(chance[leans].mean()) if n else 0.0
        hit = float(landed[leans].mean()) if n else 0.0
        out[side] = {"n": n, "model": pred, "hit": hit, "gap": pred - hit}
    return out


def _reliability(frame: pd.DataFrame) -> list[dict]:
    table = pd.DataFrame({
        "p": 1.0 - np.exp(-frame["mean"].astype(float).to_numpy()),
        "hit": (frame["actual"].astype(float).to_numpy() > 0.5).astype(float),
    })
    table["bucket"] = pd.cut(table["p"], [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0])
    rows = []
    for interval, group in table.groupby("bucket", observed=True):
        rows.append({
            "bucket": f"{interval.left:.0%}-{interval.right:.0%}",
            "n": int(len(group)),
            "model": float(group["p"].mean()),
            "hit": float(group["hit"].mean()),
        })
    return rows


def _outcomes(samples: dict[str, pd.DataFrame], market: str, since: str = "") -> dict:
    base = samples["old"]
    base = base[base["market"] == market]
    if since:
        base = base[base["date"] >= since]
    out = {}
    for name, frame in samples.items():
        frame = frame[frame["market"] == market]
        if since:
            frame = frame[frame["date"] >= since]
        joined = base[KEY + ["ll"]].merge(
            frame[KEY + ["ll", "mean", "actual"]], on=KEY, suffixes=("_old", "")
        )
        diff = joined["ll"] - joined["ll_old"]
        slope = float(np.polyfit(joined["mean"], joined["actual"], 1)[0]) if len(joined) > 2 else 0.0
        out[name] = {
            "ll_vs_old": _interval(diff, joined["game_id"]),
            "ll_per_player_game": float(joined["ll"].mean()) if len(joined) else 0.0,
            "mean_predicted": float(joined["mean"].mean()) if len(joined) else 0.0,
            "mean_actual": float(joined["actual"].mean()) if len(joined) else 0.0,
            "slope": slope,
            "lean_0_5": _lean_sides(joined, 0.5),
            "lean_1_5": _lean_sides(joined, 1.5),
            "reliability_0_5": _reliability(joined),
        }
    return out


def _price_sides(bets, market: str, edge: float) -> dict:
    out = {}
    for side in ("over", "under"):
        chosen = [
            b for b in bets
            if b.market == market and str(b.selection).lower() == side and b.edge >= edge - 1e-12
        ]
        if not chosen:
            out[side] = {"bets": 0}
            continue
        settled = [b for b in chosen if not b.push]
        profits = pd.Series([b.profit for b in chosen], dtype=float)
        iv = _interval(profits, pd.Series([b.date for b in chosen]))
        out[side] = {
            "bets": len(chosen),
            "units": float(profits.sum()),
            "roi": iv["mean"], "low": iv["low"], "high": iv["high"],
            "model": float(np.mean([b.model_probability for b in chosen])),
            "implied": float(np.mean([b.implied_probability for b in chosen])),
            "hit": float(np.mean([b.won for b in settled])) if settled else 0.0,
        }
    return out


def _price_cell(entry: dict) -> str:
    if not entry.get("bets"):
        return "no bets"
    return (
        f"{entry['bets']:,}: model {entry['model']:.3f} / hit {entry['hit']:.3f} / price "
        f"{entry['implied']:.3f}; {entry['units']:+.1f}u, {entry['roi']:+.1%} "
        f"[{entry['low']:+.1%}, {entry['high']:+.1%}]"
    )


def _passes(results: dict, name: str) -> tuple[bool, list[str]]:
    reasons = []
    for market in MARKETS:
        pooled = results["outcomes"][market][name]
        season = results["outcomes_2026_27"][market][name]
        old = results["outcomes"][market]["old"]
        for label, block in (("pooled", pooled), ("2026-27", season)):
            ll = block["ll_vs_old"]
            if not (ll["mean"] > 0 and ll["low"] > 0):
                reasons.append(f"{market} {label} log-likelihood {ll['mean']:+.4f} [{ll['low']:+.4f}, {ll['high']:+.4f}]")
        for side in ("over", "under"):
            new_gap = abs(pooled["lean_0_5"][side]["gap"])
            old_gap = abs(old["lean_0_5"][side]["gap"])
            if new_gap > old_gap + 1e-9:
                reasons.append(f"{market} {side} gap {new_gap:.3f} > old {old_gap:.3f}")
    return (not reasons), reasons


def render(results: dict) -> str:
    lines = [
        "# Points and assists model study",
        "",
        "Every variant priced walk-forward on the same player-games, as the card "
        f"prices (back-to-back adjustment {'on' if results['use_rest'] else 'off'}, "
        "last-five team form, matchup by position, scoring environment), refit "
        "every 14 days. Poisson throughout, as the model prices both markets.",
        "",
    ]
    for block, title in (("outcomes", "every season"), ("outcomes_2026_27", "2026-27 alone")):
        lines += [f"## On outcomes, {title}", ""]
        for market in MARKETS:
            lines += [
                f"### {market}",
                "",
                "| Variant | Log-likelihood per player-game vs old (95%, clustered on game) | "
                "Mean predicted / actual | Slope of actual on predicted | "
                "Leans over 0.5: model / hit (n) | Leans under 0.5: model / hit (n) | "
                "Leans over 1.5: model / hit (n) |",
                "|:--|:--|:--|:--|:--|:--|:--|",
            ]
            for name, _ in VARIANTS:
                r = results[block][market][name]
                ll = r["ll_vs_old"]
                lo, lu, lo15 = r["lean_0_5"]["over"], r["lean_0_5"]["under"], r["lean_1_5"]["over"]
                lines.append(
                    f"| {LABELS[name]} | {ll['mean']:+.4f} [{ll['low']:+.4f}, {ll['high']:+.4f}] over {ll['n']:,} | "
                    f"{r['mean_predicted']:.3f} / {r['mean_actual']:.3f} | {r['slope']:.2f} | "
                    f"{lo['model']:.3f} / {lo['hit']:.3f} ({lo['n']:,}) | "
                    f"{lu['model']:.3f} / {lu['hit']:.3f} ({lu['n']:,}) | "
                    f"{lo15['model']:.3f} / {lo15['hit']:.3f} ({lo15['n']:,}) |"
                )
            lines.append("")
    lines += ["## Over 0.5 reliability, every season", ""]
    for market in MARKETS:
        lines += [f"### {market}", "", "| Model's chance of the over | " + " | ".join(LABELS[n] for n, _ in VARIANTS) + " |",
                  "|:--|" + ":--|" * len(VARIANTS)]
        buckets = sorted({row["bucket"] for n, _ in VARIANTS for row in results["outcomes"][market][n]["reliability_0_5"]},
                         key=lambda b: float(b.split("%")[0]))
        for bucket in buckets:
            cells = []
            for name, _ in VARIANTS:
                row = next((x for x in results["outcomes"][market][name]["reliability_0_5"] if x["bucket"] == bucket), None)
                cells.append(f"{row['model']:.3f} / {row['hit']:.3f} ({row['n']:,})" if row else "")
            lines.append(f"| {bucket} | " + " | ".join(cells) + " |")
        lines.append("")
    for block, title in (("bought", "bought prices (`card` window)"), ("ledger", "the forward ledger's frozen prices")):
        if not results.get(block):
            lines += [f"## On {title}", "", results.get(f"{block}_note", "Not measured."), ""]
            continue
        lines += [
            f"## On {title}, {results['edge_threshold']:.0%} bar, one bet per wager at the best price",
            "",
            "Each cell: bets: the model's mean chance / hit rate / price's implied chance; units, ROI [95%, clustered on the night].",
            "",
            "| Variant | Market | Overs | Unders |",
            "|:--|:--|:--|:--|",
        ]
        for name, _ in VARIANTS:
            for market in MARKETS:
                r = results[block][name][market]
                lines.append(f"| {LABELS[name]} | {market} | {_price_cell(r['over'])} | {_price_cell(r['under'])} |")
        lines.append("")
    lines += ["## The rule, fixed before the run", ""]
    for name, _ in VARIANTS[1:]:
        ok, reasons = results["rule"][name]
        lines.append(f"- {LABELS[name]}: {'passes' if ok else 'fails: ' + '; '.join(reasons)}")
    lines += [
        "",
        f"Ships: **{LABELS.get(results['ships'], 'nothing')}**." if results["ships"] else "Ships: **nothing**.",
        "",
        "Intervals are 95% and uncorrected; three variants were tried on one "
        "dataset. An interval that includes zero is no demonstrated edge.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-threshold", type=float, default=MIN_PROP_EDGE)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--ledger", type=Path, default=None)
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    outputs = Path(args.output_dir)
    logs = load_player_logs(processed)
    if logs.empty:
        print("Need player logs on disk first.", file=sys.stderr)
        return 1
    team_names = load_team_name_map(processed_dir=processed)
    use_rest = verdicts.ships("props_b2b", output_dir=outputs)

    ledger_path = args.ledger or processed / "forward_evidence.csv"
    ledger = pd.read_csv(ledger_path, dtype={"player": str}) if ledger_path.is_file() else pd.DataFrame()
    if not ledger.empty:
        ledger = ledger[
            ledger["market"].isin(MARKETS)
            & ledger["outcome"].isin(["won", "lost", "push"])
            & (ledger["snapshot_date"].astype(str) >= LEDGER_FROM)
        ]
    ledger_lines = (
        {m: tuple(sorted(float(x) for x in ledger.loc[ledger["market"] == m, "line"].dropna().unique())) for m in MARKETS}
        if not ledger.empty else {}
    )
    lines = {m: tuple(sorted({0.5, 1.5, 2.5} | set(ledger_lines.get(m, ())))) for m in MARKETS}

    prices_path = processed / "historical_prop_prices.csv"
    bought = pd.read_csv(prices_path) if prices_path.is_file() else pd.DataFrame()
    if not bought.empty and "market" in bought:
        bought = bought[bought["market"].astype(str).str.contains("points|assists")]

    samples: dict[str, pd.DataFrame] = {}
    results: dict = {"use_rest": use_rest, "edge_threshold": args.edge_threshold,
                     "bought": {}, "ledger": {}}
    for name, options in VARIANTS:
        print(f"Walk-forward points and assists ({name}: {sorted(options) or 'none'})...", flush=True)
        frame, walk = generate_prop_samples(
            logs, lines=lines, use_rest=use_rest, team_form=True, position_matchup=True,
            scoring_env=True, scoring_options=options,
        )
        print(f"  {walk.summary_line()}", flush=True)
        frame = frame[frame["market"].isin(MARKETS)].copy()
        frame["ll"] = _poisson_ll(frame["mean"], frame["actual"])
        samples[name] = frame
        bare = frame.drop(columns=["ll"])
        try:
            if not bought.empty:
                report = run_backtest(bought, bare, edge_threshold=args.edge_threshold,
                                      phase="card", team_names=team_names)
                results["bought"][name] = {m: _price_sides(report.bets, m, args.edge_threshold) for m in MARKETS}
                results["bought_phase_hours"] = report.phase_hours
            if not ledger.empty:
                prices = ledger.assign(date=ledger["snapshot_date"].astype(str))[
                    ["date", "commence_time", "home_team", "away_team", "market", "player",
                     "selection", "line", "american_odds", "book"]]
                report = run_backtest(prices, bare, edge_threshold=-1.0, phase="", team_names=team_names)
                results["ledger"][name] = {m: _price_sides(report.bets, m, args.edge_threshold) for m in MARKETS}
        except UnresolvedTeamsError as error:
            print(f"::error::{error}", file=sys.stderr)
            return 2
    if bought.empty:
        results["bought_note"] = "No bought prices on disk."
    if ledger.empty:
        results["ledger_note"] = "No forward ledger on disk."

    results["outcomes"] = {m: _outcomes(samples, m) for m in MARKETS}
    results["outcomes_2026_27"] = {m: _outcomes(samples, m, SEASON_FROM) for m in MARKETS}
    results["rule"] = {name: _passes(results, name) for name, _ in VARIANTS[1:]}
    passing = [name for name, _ in VARIANTS[1:] if results["rule"][name][0]]
    results["ships"] = max(
        passing,
        key=lambda n: results["outcomes"]["points"][n]["ll_vs_old"]["mean"],
        default="",
    )

    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / REPORT_JSON).write_text(
        json.dumps(results, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    text = render(results)
    (outputs / REPORT_MARKDOWN).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
