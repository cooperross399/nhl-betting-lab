#!/usr/bin/env python3
"""Would a stricter rule for shots on goal overs have helped? On the bought
card-window prices and on the forward ledger, under the rule fixed before
this ran: `docs/sog_over_rule_decision_rule.md`.

Three candidates, each acting on `shots_on_goal` overs only: `bar` (list an
over only from a 12% edge), `cap` (no over priced longer than +200) and
`exclude` (no over at all). For each, R is the set of population-B overs it
removes and its improvement is D = -(units of R), 1u flat at the best price,
one bet per wager, intervals clustered on the game.

1. Bought prices: the `card` window, priced by the walk-forward props model
   with the layers the card prices shots with (last-five form, matchup by
   position, the scoring environment, the back-to-back verdict in force),
   population B at the 6% bar, pooled and by season.
2. Forward ledger: settled `shots_on_goal` overs frozen from 2026-10-22,
   best frozen price, population B on the frozen edge, pooled and by half.

Writes `data/outputs/sog_over_rule_study.md` and `.json`: aggregates only, no
price, line or book. Offline; spends nothing.

    PYTHONPATH=src .venv/bin/python scripts/run_sog_over_rule_study.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Callable

import pandas as pd

from nhl_betting_lab import verdicts
from nhl_betting_lab.backtest.walk_forward import DEFAULT_LINES, generate_prop_samples
from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs
from nhl_betting_lab.models.player_props import HITS_OPTIONS
from nhl_betting_lab.providers.team_names import UnresolvedTeamsError, load_team_name_map
from nhl_betting_lab.reports.player_props_backtest import run_backtest
from nhl_betting_lab.stats import clustered_mean_interval

REPORT_MARKDOWN = "sog_over_rule_study.md"
REPORT_JSON = "sog_over_rule_study.json"
MARKET = "shots_on_goal"
LEDGER_FROM = "2026-10-22"
SEASON_SPLIT = "2025-08-01"
MIN_REMOVED = 30
RULE = "docs/sog_over_rule_decision_rule.md"

#: The three candidates, fixed in the rule before any result was read. Each
#: answers: does this candidate REMOVE this over (edge, American price)?
CANDIDATES: dict[str, tuple[str, Callable[[float, float], bool]]] = {
    "bar": ("Higher edge bar: shots overs need 12%", lambda edge, price: edge < 0.12),
    "cap": ("Price cap: no shots over longer than +200", lambda edge, price: price > 200.0),
    "exclude": ("Exclude the side: no shots overs", lambda edge, price: True),
}
LOOKS = len(CANDIDATES)


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def summarise(frame: pd.DataFrame) -> dict:
    """Units, return and its game-clustered interval (plain 95% and
    Bonferroni across the candidates) of `frame` (`profit`, `game`, `won`)."""
    if frame.empty:
        return {"bets": 0, "units": 0.0, "roi": None, "low": None, "high": None,
                "adjusted_low": None, "adjusted_high": None, "hit": None}
    interval = clustered_mean_interval(
        frame["profit"].astype(float).tolist(), frame["game"].tolist(),
        wins=int(frame["won"].sum()), looks=LOOKS,
        family=f"{LOOKS} candidate rules for shots overs",
    )
    return {
        "bets": int(interval.bets), "units": float(interval.profit), "roi": float(interval.roi),
        "low": _finite(interval.low), "high": _finite(interval.high),
        "adjusted_low": _finite(interval.adjusted_low), "adjusted_high": _finite(interval.adjusted_high),
        "hit": float(frame["won"].mean()),
    }


def removed_by(frame: pd.DataFrame, name: str) -> pd.Series:
    rule = CANDIDATES[name][1]
    return pd.Series(
        [bool(rule(float(e), float(p))) for e, p in zip(frame["edge"], frame["price"])],
        index=frame.index, dtype=bool,
    )


def measure(overs: pd.DataFrame, splits: dict[str, pd.Series]) -> dict:
    """For each candidate: R (removed) and the overs kept, pooled and split."""
    out: dict = {"all_overs": summarise(overs), "splits_all": {}}
    for label, mask in splits.items():
        out["splits_all"][label] = summarise(overs[mask])
    out["candidates"] = {}
    for name in CANDIDATES:
        gone = removed_by(overs, name)
        entry = {"removed": summarise(overs[gone]), "kept": summarise(overs[~gone]), "splits": {}}
        entry["improvement"] = -entry["removed"]["units"]
        for label, mask in splits.items():
            part = overs[mask & gone]
            entry["splits"][label] = {"removed": summarise(part), "improvement": -float(part["profit"].sum())}
        out["candidates"][name] = entry
    return out


def history(processed: Path, outputs: Path, threshold: float) -> tuple[pd.DataFrame, dict]:
    logs = load_player_logs(processed)
    prices_path = processed / "historical_prop_prices.csv"
    if logs.empty or not prices_path.is_file():
        raise FileNotFoundError("Need player logs and bought prop prices on disk first.")
    prices = pd.read_csv(prices_path)
    if "market" in prices:
        only = prices[prices["market"].astype(str) == MARKET]
        prices = only if not only.empty else prices
    team_names = load_team_name_map(processed_dir=processed)
    use_rest = verdicts.ships("props_b2b", output_dir=outputs)
    print("Generating walk-forward shots samples (the card's layers)...", flush=True)
    samples, walk = generate_prop_samples(
        logs, lines={MARKET: DEFAULT_LINES[MARKET]}, use_rest=use_rest, hits_options=HITS_OPTIONS,
        team_form=True, position_matchup=True, scoring_env=True,
    )
    print(f"  {walk.summary_line()}", flush=True)
    samples = samples[samples["market"] == MARKET]
    report = run_backtest(prices, samples, edge_threshold=threshold, phase="card", team_names=team_names)
    rows = []
    for index, bet in enumerate(report.bets):
        if bet.market != MARKET:
            continue
        day = str(bet.game[2]) if bet.game else str(bet.date)
        rows.append({
            "selection": str(bet.selection).lower(), "edge": float(bet.edge),
            "price": float(bet.american_odds), "profit": float(bet.profit), "won": bool(bet.won),
            "game": bet.game if bet.game else ("bet", index), "day": day[:10],
        })
    bets = pd.DataFrame(rows, columns=["selection", "edge", "price", "profit", "won", "game", "day"])
    note = {
        "phase": report.phase, "phase_hours": report.phase_hours, "use_rest": use_rest,
        "shots_bets": int(len(bets)), "unders": summarise(bets[bets["selection"] == "under"]),
    }
    return bets[bets["selection"] == "over"].reset_index(drop=True), note


def ledger(processed: Path, threshold: float) -> tuple[pd.DataFrame, dict]:
    from nhl_betting_lab.closing_lines import collapse_to_best
    from nhl_betting_lab.forward_evidence import _game_of

    path = processed / "forward_evidence.csv"
    if not path.is_file():
        raise FileNotFoundError("No forward ledger on disk.")
    frame = pd.read_csv(path, dtype={"player": str})
    frame = frame[(frame["market"].astype(str) == MARKET) & (frame["snapshot_date"].astype(str) >= LEDGER_FROM)]
    wagers = collapse_to_best(frame)
    wagers = wagers[wagers["outcome"].isin(["won", "lost", "push"])]
    wagers = wagers[wagers["edge"].astype(float) >= threshold].reset_index(drop=True)
    note = {"population_b_shots": int(len(wagers))}
    out = pd.DataFrame({
        "selection": wagers["selection"].astype(str).str.lower(),
        "edge": wagers["edge"].astype(float),
        "price": wagers["american_odds"].astype(float),
        "profit": wagers["profit_units"].astype(float),
        "won": wagers["outcome"] == "won",
        "game": _game_of(wagers),
        "day": wagers["snapshot_date"].astype(str),
        "modelled": wagers["model_probability"].astype(float),
    })
    note["unders"] = summarise(out[out["selection"] == "under"])
    overs = out[out["selection"] == "over"].reset_index(drop=True)
    note["overs_modelled"] = float(overs["modelled"].mean()) if len(overs) else None
    return overs, note


def ledger_halves(overs: pd.DataFrame) -> dict[str, pd.Series]:
    days = sorted(overs["day"].unique())
    if not days:
        return {}
    cut = days[math.ceil(len(days) / 2) - 1]
    return {
        f"first half ({days[0]} to {cut})": overs["day"] <= cut,
        f"second half (after {cut})": overs["day"] > cut,
    }


def history_seasons(overs: pd.DataFrame) -> dict[str, pd.Series]:
    return {"2024-25": overs["day"] < SEASON_SPLIT, "2025-26": overs["day"] >= SEASON_SPLIT}


def verdict(hist: dict, led: dict) -> tuple[dict, str | None]:
    decisions: dict = {}
    for name in CANDIDATES:
        h, f = hist["candidates"][name], led["candidates"][name]
        reasons = []
        c1 = h["improvement"] > 0 and all(s["improvement"] > 0 for s in h["splits"].values())
        reasons.append("1. history improves pooled and in both seasons: " + ("yes" if c1 else "no"))
        c2 = f["improvement"] > 0 and all(s["improvement"] > 0 for s in f["splits"].values())
        reasons.append("2. ledger improves pooled and in both halves: " + ("yes" if c2 else "no"))
        high = f["removed"]["adjusted_high"]
        c3 = high is not None and high < 0
        reasons.append("3. removed overs' ledger return, corrected for 3, wholly below zero: "
                       + ("yes" if c3 else "no"))
        c4 = h["removed"]["bets"] >= MIN_REMOVED and f["removed"]["bets"] >= MIN_REMOVED
        reasons.append(f"4. at least {MIN_REMOVED} removed on each source: " + ("yes" if c4 else "no"))
        decisions[name] = {"passes": c1 and c2 and c3 and c4, "reasons": reasons}
    passing = [n for n in CANDIDATES if decisions[n]["passes"]]
    chosen = min(passing, key=lambda n: led["candidates"][n]["removed"]["bets"]) if passing else None
    return decisions, chosen


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1%}"


def _cell(entry: dict) -> str:
    if not entry["bets"]:
        return "none"
    return (f"{entry['units']:+.1f}u over {entry['bets']:,}, {_pct(entry['roi'])} "
            f"[{_pct(entry['low'])}, {_pct(entry['high'])}]; corrected "
            f"[{_pct(entry['adjusted_low'])}, {_pct(entry['adjusted_high'])}]; hit {entry['hit']:.1%}")


def _section(title: str, data: dict) -> list[str]:
    out = [f"## {title}", "", f"All population-B overs: {_cell(data['all_overs'])}", ""]
    for label, entry in data["splits_all"].items():
        out.append(f"- {label}: {_cell(entry)}")
    out += ["", "| Candidate | Removed (R) | Improvement D | Kept | By split: D (removed) |",
            "|:--|:--|--:|:--|:--|"]
    for name, (label, _) in CANDIDATES.items():
        c = data["candidates"][name]
        splits = "; ".join(f"{k}: {v['improvement']:+.1f}u ({v['removed']['bets']:,})" for k, v in c["splits"].items())
        out.append(f"| {label} | {_cell(c['removed'])} | {c['improvement']:+.1f}u | {_cell(c['kept'])} | {splits} |")
    return out + [""]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-threshold", type=float, default=MIN_PROP_EDGE)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)
    processed, outputs = Path(args.processed_dir), Path(args.output_dir)
    try:
        hist_overs, hist_note = history(processed, outputs, args.edge_threshold)
        led_overs, led_note = ledger(processed, args.edge_threshold)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 1
    except UnresolvedTeamsError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 2
    hist = measure(hist_overs, history_seasons(hist_overs))
    led = measure(led_overs, ledger_halves(led_overs))
    decisions, chosen = verdict(hist, led)
    payload = {"rule": RULE, "edge_threshold": args.edge_threshold, "history": hist,
               "history_note": hist_note, "ledger": led, "ledger_note": led_note,
               "decisions": decisions, "ships": chosen}
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / REPORT_JSON).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                                       encoding="utf-8")
    hours = hist_note.get("phase_hours")
    out = ["# A stricter rule for shots on goal overs", "",
           f"**Under `{RULE}`: " + (f"`{chosen}` PASSES and ships.**" if chosen else "no candidate passes.**"), ""]
    for name, (label, _) in CANDIDATES.items():
        out.append(f"- **{label}**: {'PASSES' if decisions[name]['passes'] else 'fails'}")
        out += [f"  - {r}" for r in decisions[name]["reasons"]]
    out.append("")
    out += _section(
        f"Bought prices (`{hist_note['phase']}` window"
        + (f", median {hours:.1f} hours before face-off" if hours is not None else "")
        + f", {args.edge_threshold:.0%} bar, one bet per wager; {hist_note['shots_bets']:,} shots bets, "
        f"unders {_cell(hist_note['unders'])})", hist)
    out += _section(
        f"Forward ledger (settled shots wagers frozen from {LEDGER_FROM}, best frozen price, population B "
        f"{led_note['population_b_shots']:,}; overs modelled {_pct(led_note['overs_modelled'])}"
        f" on average; unders {_cell(led_note['unders'])})", led)
    out += ["Units at 1u flat. Intervals are game-clustered; 'corrected' is Bonferroni across the "
            f"{LOOKS} candidates. An interval that includes zero is no demonstrated edge.", ""]
    text = "\n".join(out)
    (outputs / REPORT_MARKDOWN).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
