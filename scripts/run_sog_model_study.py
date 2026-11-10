#!/usr/bin/env python3
"""Does shots on goal's own-games spread price shots better? Walk-forward on
outcomes, on the bought card-window prices, and replayed on the forward ledger.

The rule was fixed before this ran: `docs/sog_dispersion_decision_rule.md`.
The candidate is `player_props.SOG_OPTIONS` (the spread measured inside each
player's own games, with the shrinkage measured against it); the baseline is
the model as it prices shots today. `dispersion` alone is shown for
information.

1. Outcomes: the negative-binomial log-likelihood of each player-game's shots,
   paired against the baseline, 95% bootstrap over games; and calibration by
   line (`DEFAULT_LINES`): mean predicted over against the share that went
   over.
2. Bought prices: `card` window, one bet per wager at the best price, 6% bar,
   overs and unders separately.
3. Forward ledger: the settled `shots_on_goal` wagers from 2026-09-29, one per
   wager at the best frozen price, re-priced by each walk-forward model (refit
   every 7 days), population B at the 6% bar.

Writes `data/outputs/sog_model_study.md` and `.json`: aggregates only, no
price, line-level price or book. Offline; spends nothing.

    PYTHONPATH=src .venv/bin/python scripts/run_sog_model_study.py
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
from nhl_betting_lab.models.player_props import HITS_OPTIONS, SOG_OPTIONS, player_key
from nhl_betting_lab.providers.team_names import (
    UnresolvedTeamsError,
    load_team_name_map,
)
from nhl_betting_lab.reports.player_props_backtest import run_backtest
from nhl_betting_lab.stats import roi_interval

REPORT_MARKDOWN = "sog_model_study.md"
REPORT_JSON = "sog_model_study.json"
MARKET = "shots_on_goal"
LEDGER_FROM = "2026-09-29"

VARIANTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("old", frozenset()),
    ("dispersion", frozenset({"dispersion"})),
    ("candidate", frozenset(SOG_OPTIONS)),
)
LABELS = {
    "old": "Baseline (shots as priced today)",
    "dispersion": "Own-games spread only (information)",
    "candidate": "Own-games spread + measured shrinkage (candidate)",
}
KEY = ["game_id", "player_id"]


def _log_likelihood(samples: pd.DataFrame) -> pd.Series:
    values = []
    for mean, r, actual in zip(samples["mean"], samples["dispersion_r"], samples["actual"]):
        r_value = None if r is None or (isinstance(r, float) and math.isnan(r)) else float(r)
        p = distribution_from(float(mean), r_value).pmf(int(round(float(actual))))
        values.append(math.log(max(p, 1e-12)))
    return pd.Series(values, index=samples.index)


def _over(mean: float, r: object, line: float) -> float:
    r_value = None if r is None or (isinstance(r, float) and math.isnan(r)) else float(r)
    return float(distribution_from(float(mean), r_value).over_probability(float(line)))


def _clustered_mean(diff: pd.Series, clusters: pd.Series, draws: int = 1000) -> tuple[float, float, float]:
    by = pd.DataFrame({"d": diff.to_numpy(), "c": clusters.to_numpy()}).groupby("c")["d"]
    sums = by.sum().to_numpy()
    counts = by.size().to_numpy()
    rng = np.random.default_rng(20261110)
    stats = []
    for _ in range(draws):
        pick = rng.integers(0, len(sums), len(sums))
        stats.append(sums[pick].sum() / counts[pick].sum())
    return float(sums.sum() / counts.sum()), float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def _summary(profits: list[float]) -> dict:
    if not profits:
        return {"bets": 0, "profit": 0.0, "roi": 0.0, "low": 0.0, "high": 0.0}
    interval = roi_interval(profits)
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


def _implied(american: float) -> float:
    a = float(american)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def ledger_replay(processed: Path, logs: pd.DataFrame, team_names: dict, use_rest: bool,
                  threshold: float) -> tuple[dict, dict]:
    """Population B of the settled shots wagers, re-priced by each variant."""
    from nhl_betting_lab.closing_lines import collapse_to_best

    note: dict = {}
    path = processed / "forward_evidence.csv"
    if not path.is_file():
        note["skipped"] = "no forward ledger on disk"
        return {}, note
    ledger = pd.read_csv(path, dtype={"player": str})
    ledger = ledger[(ledger["market"] == MARKET) & (ledger["snapshot_date"].astype(str) >= LEDGER_FROM)]
    if ledger.empty:
        note["skipped"] = "no shots rows in the ledger"
        return {}, note
    wagers = collapse_to_best(ledger)
    wagers = wagers[wagers["outcome"].isin(["won", "lost", "push"])].copy()
    wagers["pkey"] = wagers["player"].map(player_key)
    wagers["line"] = wagers["line"].astype(float)
    wagers["date"] = wagers["snapshot_date"].astype(str)
    wagers["selection"] = wagers["selection"].astype(str)
    wagers["implied"] = wagers["american_odds"].map(_implied)
    note["settled_wagers"] = int(len(wagers))
    lines = {MARKET: tuple(sorted(float(x) for x in wagers["line"].dropna().unique()))}
    prices = ledger.assign(date=ledger["snapshot_date"].astype(str))[
        ["date", "commence_time", "home_team", "away_team", "market", "player", "selection", "line",
         "american_odds", "book"]]
    key = ["date", "pkey", "line", "selection"]
    for name, options in VARIANTS:
        print(f"Ledger replay, walk-forward shots ({name}) ...", flush=True)
        samples, walk = generate_prop_samples(
            logs, lines=lines, start_date=LEDGER_FROM, refit_days=7, use_rest=use_rest,
            hits_options=HITS_OPTIONS, team_form=True, position_matchup=True, sog_options=options,
        )
        print(f"  {walk.summary_line()}", flush=True)
        report = run_backtest(prices, samples, edge_threshold=-1.0, phase="", team_names=team_names)
        bets = pd.DataFrame([{
            "date": b.date, "pkey": player_key(b.player), "line": float(b.line),
            "selection": b.selection, f"p_{name}": b.model_probability,
        } for b in report.bets if b.market == MARKET])
        if bets.empty:
            note["skipped"] = f"{name}: no wager re-priced"
            return {}, note
        wagers = wagers.merge(bets.drop_duplicates(key), on=key, how="left")
    wagers = wagers.dropna(subset=[f"p_{n}" for n, _ in VARIANTS])
    note["matched_wagers"] = int(len(wagers))
    if wagers.empty:
        return {}, note
    note["corr_old_to_frozen"] = float(np.corrcoef(wagers["p_old"], wagers["model_probability"].astype(float))[0, 1])
    results: dict = {}
    for name, _ in VARIANTS:
        edge = wagers[f"p_{name}"] - wagers["implied"]
        chosen = wagers[edge >= threshold]
        entry = {"all": _summary(chosen["profit_units"].astype(float).tolist())}
        for side in ("over", "under"):
            part = chosen[chosen["selection"] == side]
            entry[side] = _summary(part["profit_units"].astype(float).tolist())
            entry[side]["hit"] = float((part["outcome"] == "won").mean()) if len(part) else 0.0
            entry[side]["modelled"] = float(part[f"p_{name}"].mean()) if len(part) else 0.0
        results[name] = entry
    return results, note


def verdict(results: dict, replay: dict) -> tuple[bool, list[str]]:
    reasons = []
    ll = results["candidate"]["log_likelihood"]
    c1 = ll["low"] > 0
    reasons.append(f"1. log-likelihood {ll['paired_vs_old']:+.4f} [{ll['low']:+.4f}, {ll['high']:+.4f}]: "
                   + ("passes" if c1 else "fails"))
    cand, old = results["candidate"]["prices"]["all"]["profit"], results["old"]["prices"]["all"]["profit"]
    c2 = cand >= 0 and cand >= old
    reasons.append(f"2. bought card-window prices {cand:+.1f}u against baseline {old:+.1f}u: "
                   + ("passes" if c2 else "fails"))
    if replay:
        rc, ro = replay["candidate"]["all"]["profit"], replay["old"]["all"]["profit"]
        c3 = rc >= 0 and rc >= ro
        reasons.append(f"3. ledger replay {rc:+.1f}u against baseline {ro:+.1f}u: "
                       + ("passes" if c3 else "fails"))
    else:
        c3 = False
        reasons.append("3. ledger replay: not measured, so fails")
    return c1 and c2 and c3, reasons


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
        only = prices[prices["market"].astype(str) == MARKET]
        prices = only if not only.empty else prices
    team_names = load_team_name_map(processed_dir=processed)
    use_rest = verdicts.ships("props_b2b", output_dir=outputs)
    lines = {MARKET: DEFAULT_LINES[MARKET]}

    samples: dict[str, pd.DataFrame] = {}
    results: dict[str, dict] = {}
    for name, options in VARIANTS:
        print(f"Generating walk-forward shots samples ({name}: {sorted(options) or 'none'})...", flush=True)
        frame, walk = generate_prop_samples(logs, lines=lines, use_rest=use_rest, sog_options=options)
        print(f"  {walk.summary_line()}", flush=True)
        frame = frame[frame["market"] == MARKET].copy()
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
        bets = [b for b in report.bets if b.market == MARKET]
        r_values = frame["dispersion_r"].astype(float)
        results[name] = {
            "options": sorted(options),
            "phase": report.phase,
            "phase_hours": report.phase_hours,
            "prices": {
                "all": _summary([b.profit for b in bets]),
                "over": _summary([b.profit for b in bets if str(b.selection).lower() == "over"]),
                "under": _summary([b.profit for b in bets if str(b.selection).lower() == "under"]),
            },
            "median_r": float(r_values.median()) if r_values.notna().any() else None,
            "mean_predicted": float(frame["mean"].mean()),
            "mean_actual": float(frame["actual"].mean()),
            "samples": int(len(frame)),
            "calibration": {},
        }
        for line in DEFAULT_LINES[MARKET]:
            predicted = [
                _over(m, r, line) for m, r in zip(frame["mean"], frame["dispersion_r"])
            ]
            results[name]["calibration"][str(line)] = {
                "predicted": float(np.mean(predicted)),
                "observed": float((frame["actual"].astype(float) > line).mean()),
            }

    base = samples["old"]
    for name, frame in samples.items():
        joined = base[KEY + ["ll"]].merge(frame[KEY + ["ll"]], on=KEY, suffixes=("_old", ""))
        mean, low, high = _clustered_mean(joined["ll"] - joined["ll_old"], joined["game_id"])
        results[name]["log_likelihood"] = {
            "paired_vs_old": mean, "low": low, "high": high, "n": int(len(joined)),
            "per_game": float(joined["ll"].mean()),
        }

    replay, replay_note = ledger_replay(processed, logs, team_names, use_rest, args.edge_threshold)
    passed, reasons = verdict(results, replay)

    payload = {
        "edge_threshold": args.edge_threshold,
        "use_rest": use_rest,
        "results": results,
        "ledger_replay": replay,
        "ledger_note": replay_note,
        "passes": passed,
        "reasons": reasons,
        "rule": "docs/sog_dispersion_decision_rule.md",
    }
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / REPORT_JSON).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    phase = results["old"]["phase"]
    hours = results["old"]["phase_hours"]
    out = [
        "# Shots on goal spread study",
        "",
        f"**Verdict under `docs/sog_dispersion_decision_rule.md`: {'PASSES' if passed else 'FAILS'}.**",
        "",
        *[f"- {line}" for line in reasons],
        "",
        "## On outcomes (walk-forward, cached history)",
        "",
        "| Variant | Log-likelihood per player-game vs baseline (95%, games) | Median r | Mean predicted / actual |",
        "|:--|:--|--:|:--|",
    ]
    for name, _ in VARIANTS:
        r = results[name]
        ll = r["log_likelihood"]
        med = "Poisson" if r["median_r"] is None or not math.isfinite(r["median_r"]) else f"{r['median_r']:.1f}"
        out.append(
            f"| {LABELS[name]} | {ll['paired_vs_old']:+.4f} [{ll['low']:+.4f}, {ll['high']:+.4f}] over "
            f"{ll['n']:,} | {med} | {r['mean_predicted']:.3f} / {r['mean_actual']:.3f} |"
        )
    out += ["", "### Calibration by line: mean predicted over / share over", "",
            "| Variant | " + " | ".join(f"over {line}" for line in DEFAULT_LINES[MARKET]) + " |",
            "|:--|" + "--:|" * len(DEFAULT_LINES[MARKET])]
    for name, _ in VARIANTS:
        cal = results[name]["calibration"]
        out.append(f"| {LABELS[name]} | " + " | ".join(
            f"{cal[str(line)]['predicted']:.3f} / {cal[str(line)]['observed']:.3f}" for line in DEFAULT_LINES[MARKET]
        ) + " |")
    out += [
        "",
        f"## On the bought shots prices (`{phase}` window"
        + (f", median {hours:.1f} hours before face-off" if hours is not None else "")
        + f", {args.edge_threshold:.0%} bar, one bet per wager)",
        "",
        "| Variant | All | Overs | Unders |",
        "|:--|:--|:--|:--|",
    ]
    for name, _ in VARIANTS:
        p = results[name]["prices"]
        out.append(f"| {LABELS[name]} | {_cell(p['all'])} | {_cell(p['over'])} | {_cell(p['under'])} |")
    out += ["", f"## Forward-ledger replay (settled shots wagers from {LEDGER_FROM}, best frozen price, "
            f"population B at {args.edge_threshold:.0%})", ""]
    if replay:
        out += [
            f"Settled wagers {replay_note.get('settled_wagers', 0):,}, re-priced by every variant "
            f"{replay_note.get('matched_wagers', 0):,}; baseline's correlation with the frozen "
            f"probability {replay_note.get('corr_old_to_frozen', float('nan')):.3f}.",
            "",
            "| Variant | All | Overs (hit / modelled) | Unders (hit / modelled) |",
            "|:--|:--|:--|:--|",
        ]
        for name, _ in VARIANTS:
            e = replay[name]
            out.append(
                f"| {LABELS[name]} | {_cell(e['all'])} | {_cell(e['over'])} "
                f"({e['over']['hit']:.1%} / {e['over']['modelled']:.1%}) | {_cell(e['under'])} "
                f"({e['under']['hit']:.1%} / {e['under']['modelled']:.1%}) |"
            )
    else:
        out.append(f"Not measured: {replay_note}")
    out += [
        "",
        "Intervals are 95% and uncorrected; three variants were measured on one dataset. "
        "An interval that includes zero is no demonstrated edge.",
        "",
    ]
    text = "\n".join(out)
    (outputs / REPORT_MARKDOWN).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
