"""Measure the drought rule against bought prop prices.

The rule (Cooper, 2026-10-07): a skater who produced 70+ points, 30+ goals or
30+ assists LAST regular season, and who has gone 5+ straight games without one
in that category, is a bet on the over 0.5 in that category (1+ point, anytime
goal, 1+ assist).

Every figure in the report is generated here. One wager per selection, at the
best price any book offered, in two snapshots per event: the first ("card",
about T-9.6h, the window the Gameday card prices in) and the last ("late").
Intervals are a bootstrap over game dates, because one night's games share a
slate; MDE is the smallest ROI the sample could detect at 80% power.

The bought prices are not in git (data/processed/*.csv is ignored), so this
runs on a machine that holds them:

    python scripts/run_drought_rule_backtest.py --data /path/to/data/processed
"""
from __future__ import annotations

import argparse
import json
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nhl_betting_lab.drought_rule import (  # noqa: E402,F401
    MIN_DROUGHT,
    THRESHOLDS,
    drought_before,
    prepare_logs,
)
from nhl_betting_lab.models.player_props import player_name_aliases  # noqa: E402
from nhl_betting_lab.season import game_date  # noqa: E402

# The drought logic lives in src/ so the Gameday card and this evidence share one function.
__all__ = ["MIN_DROUGHT", "THRESHOLDS", "drought_before", "prepare_logs"]

BUCKETS = (("not in drought (0-4)", 0, 4), ("RULE: drought 5+", 5, 10_000),
           ("drought 5-6", 5, 6), ("drought 7-9", 7, 9), ("drought 10+", 10, 10_000))
GOAL_SWEEP = (30, 35, 40, 45)
BOOTSTRAPS = 1000


def decimal(odds):
    odds = np.asarray(odds, dtype=float)
    return np.where(odds > 0, 1 + odds / 100, 1 + 100 / -odds)


def build_wagers(prices: pd.DataFrame, logs: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    keys: dict[tuple[str, str], set] = {}
    for r in logs[["player_id", "player", "date"]].drop_duplicates().itertuples():
        for alias in player_name_aliases(r.player):
            keys.setdefault((alias, r.date), set()).add(r.player_id)
    by_game = logs.drop_duplicates(["player_id", "date"]).set_index(["player_id", "date"])

    p = prices[prices.market.isin(list(THRESHOLDS)) & (prices.line == 0.5) & (prices.selection == "over")].copy()
    p["gdate"] = p.commence_time.map(game_date)
    p = p[pd.to_datetime(p.snapshot) < pd.to_datetime(p.commence_time)]
    first = p.groupby("provider_event_id").snapshot.transform("min")
    last = p.groupby("provider_event_id").snapshot.transform("max")
    p["dec"] = decimal(p.american_odds)

    rows, counts = [], {}
    for window, mask in (("card", p.snapshot == first), ("late", p.snapshot == last)):
        best = p[mask].sort_values("dec").groupby(["provider_event_id", "market", "player"]).tail(1)
        c = counts[window] = {"selections": int(len(best)), "no_regular_season_game": 0, "ambiguous_name": 0, "graded": 0}
        for r in best.itertuples():
            ids = set().union(*(keys.get((a, r.gdate), set()) for a in player_name_aliases(r.player)))
            if not ids:  # a playoff game, or a game the player did not dress for
                c["no_regular_season_game"] += 1
                continue
            if len(ids) > 1:
                c["ambiguous_name"] += 1
                continue
            g = by_game.loc[(next(iter(ids)), r.gdate)]
            c["graded"] += 1
            rows.append({"window": window, "date": r.gdate, "season": int(g.season_start), "market": r.market,
                         "player": g.player, "odds": float(r.american_odds), "book": r.book, "dec": float(r.dec),
                         "won": bool(g[r.market] >= 1), "prior": g["prior_" + r.market], "drought": int(g["drought_" + r.market])})
    w = pd.DataFrame(rows)
    w["profit"] = np.where(w.won, w.dec - 1, -1.0)
    w["qualifies"] = w.prior >= w.market.map(THRESHOLDS)
    return w, counts


def summarize(x: pd.DataFrame, seed: int) -> dict | None:
    if x.empty:
        return None
    nights = x.groupby("date").profit.agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(nights), size=(BOOTSTRAPS, len(nights)))
    s, n = nights["sum"].to_numpy(), nights["count"].to_numpy()
    boot = s[idx].sum(1) / n[idx].sum(1)
    return {"wagers": int(len(x)), "nights": int(len(nights)), "hit_rate": float(x.won.mean()),
            "implied": float((1 / x.dec).mean()), "median_odds": int(x.odds.median()),
            "roi": float(x.profit.mean()), "units": float(x.profit.sum()),
            "ci_low": float(np.percentile(boot, 2.5)), "ci_high": float(np.percentile(boot, 97.5)),
            "mde": float(2.8 * boot.std())}


def measure(w: pd.DataFrame) -> dict:
    out = {"buckets": [], "goal_sweep": []}
    for window in ("card", "late"):
        for market in THRESHOLDS:
            q = w[(w.window == window) & (w.market == market) & w.qualifies]
            for label, lo, hi in BUCKETS:
                for season in ("both", 2024, 2025):
                    x = q[q.drought.between(lo, hi)]
                    if season != "both":
                        x = x[x.season == season]
                    r = summarize(x, seed=zlib.crc32(repr((window, market, label, season)).encode()))
                    if r:
                        out["buckets"].append({"window": window, "market": market, "bucket": label, "season": str(season), **r})
    g = w[(w.window == "card") & (w.market == "goals") & (w.drought >= MIN_DROUGHT)]
    for th in GOAL_SWEEP:
        x = g[g.prior >= th]
        r = summarize(x, seed=th)
        if r:
            r["by_season"] = {str(s): summarize(x[x.season == s], seed=th + s) for s in (2024, 2025)}
            out["goal_sweep"].append({"prior_goals_at_least": th, **r})
    return out


def pct(v):
    return f"{v * 100:+.1f}%"


def render(result: dict, counts: dict, generated_at: str) -> str:
    L = [
        "# Drought rule backtest",
        "",
        f"Generated {generated_at} by `scripts/run_drought_rule_backtest.py`. Every figure below comes from that script.",
        "",
        "**The rule.** A skater with 70+ points, 30+ goals or 30+ assists last regular season, on a run of "
        f"{MIN_DROUGHT}+ straight games without one in that category, is a bet on the over 0.5 in that category.",
        "",
        "**How it is measured.** 2024-25 and 2025-26 regular seasons. One wager per selection at the best price any book "
        "offered. `card` is each event's first snapshot (the window the Gameday card prices in); `late` is its last. "
        "Interval: 95%, bootstrapped over game nights. MDE: the smallest ROI this sample could detect at 80% power. "
        "Seasons are labelled by their starting year.",
        "",
    ]
    rule = {(b["window"], b["market"], b["season"]): b for b in result["buckets"] if b["bucket"].startswith("RULE")}
    L += ["## Headline (card window)", "", "| Market | Wagers | Hit | Implied | ROI | 95% interval | MDE | 2024-25 | 2025-26 |", "|:--|--:|--:|--:|--:|:--|--:|--:|--:|"]
    for m in THRESHOLDS:
        b, s1, s2 = rule.get(("card", m, "both")), rule.get(("card", m, "2024")), rule.get(("card", m, "2025"))
        if b:
            L.append(f"| {m} | {b['wagers']} | {b['hit_rate']*100:.1f}% | {b['implied']*100:.1f}% | {pct(b['roi'])} | "
                     f"{pct(b['ci_low'])} .. {pct(b['ci_high'])} | {b['mde']*100:.1f}% | "
                     f"{pct(s1['roi']) if s1 else '—'} | {pct(s2['roi']) if s2 else '—'} |")
    L += ["", "## Every bucket", "", "Control is the same qualifying players when they are NOT in a drought.", "",
          "| Window | Market | Bucket | Season | Wagers | Nights | Hit | Implied | Median odds | ROI | 95% interval | MDE | Units |",
          "|:--|:--|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|"]
    for b in result["buckets"]:
        L.append(f"| {b['window']} | {b['market']} | {b['bucket']} | {b['season']} | {b['wagers']} | {b['nights']} | "
                 f"{b['hit_rate']*100:.1f}% | {b['implied']*100:.1f}% | {b['median_odds']:+d} | {pct(b['roi'])} | "
                 f"{pct(b['ci_low'])} .. {pct(b['ci_high'])} | {b['mde']*100:.1f}% | {b['units']:+.1f} |")
    L += ["", "## Goals: does a higher scoring bar help? (card window, drought 5+)", "",
          "| Last season goals | Wagers | Hit | Implied | ROI | 95% interval | 2024-25 | 2025-26 |", "|--:|--:|--:|--:|--:|:--|--:|--:|"]
    for g in result["goal_sweep"]:
        s = g["by_season"]
        L.append(f"| {g['prior_goals_at_least']}+ | {g['wagers']} | {g['hit_rate']*100:.1f}% | {g['implied']*100:.1f}% | "
                 f"{pct(g['roi'])} | {pct(g['ci_low'])} .. {pct(g['ci_high'])} | "
                 + " | ".join(f"{pct(s[k]['roi'])} / {s[k]['wagers']}" if s.get(k) else "—" for k in ("2024", "2025")) + " |")
    L += ["", "## Accounting", "", "Best-price selections read per window, and why any were not graded. "
          "`no_regular_season_game` is a playoff game or a game the player did not dress for.", ""]
    for window, c in counts.items():
        L.append(f"- `{window}`: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "outputs")
    a = ap.parse_args(argv)
    prices_path = a.data / "historical_prop_prices.csv"
    if not prices_path.exists():
        print(f"No bought prices at {prices_path}; nothing measured.", file=sys.stderr)
        return 1
    logs = prepare_logs(pd.read_csv(a.data / "player_game_logs.csv"))
    prices = pd.read_csv(prices_path, usecols=["commence_time", "provider_event_id", "market", "player",
                                               "selection", "line", "american_odds", "book", "snapshot"])
    wagers, counts = build_wagers(prices, logs)
    result = measure(wagers)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "drought_rule_backtest.json").write_text(json.dumps(
        {"generated_at": now, "thresholds": THRESHOLDS, "min_drought": MIN_DROUGHT, "accounting": counts, **result}, indent=1) + "\n")
    (a.out / "drought_rule_backtest.md").write_text(render(result, counts, now))
    print(render(result, counts, now).split("## Every bucket")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
