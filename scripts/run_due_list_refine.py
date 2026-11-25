#!/usr/bin/env python3
"""Refine the Due List's 1+ assist and 1+ point bars to where they pay.

Cooper, 2026-11-25: "dont drop either just refine the bar to or expand it to
where it is profitable". This season the Due List's 1+ assist rows lost
-12.4u over 159 and its 1+ point rows -6.0u over 33 (1u ladder, Oct 8 to
Nov 23). This sweeps, per category, last season's total (the floor), the
drought bar and a price window (the shortest and longest price listed), and
scores every setting on three samples at the best `card`-window price (bought
seasons) or the best frozen morning price (this season), 1u flat, one wager
per player-game:

- 2024-25 and 2025-26 (the bought prices), and
- this season (the forward ledger's settled over 0.5 opinions).

The rule for choosing, fixed before reading: a setting needs 120+ bought
wagers (40+ in each bought season) and 20+ this season; settings are ranked by
the worst of the three ROIs, then by total units. The top setting is the
candidate. Picking it after seeing it flatters it: a setting is a demonstrated
edge only if its pooled 95% interval sits above zero.

Aggregates only; nothing the card reads, no credit. Run where the bought
prices are (Due List Tuning restores them):

    PYTHONPATH=src python scripts/run_due_list_refine.py --ledger-dir <card-feed forward_evidence/>
"""
from __future__ import annotations

import argparse
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_due_hot_research import (  # noqa: E402
    attach,
    bought_rows,
    live_rows,
    pct,
    skater_frame,
    summary,
)

FLOORS = {"assists": (30, 40, 45, 50, 55, 60, 70), "points": (50, 60, 70, 80, 90, 100)}
#: Drought bars; "rule" is today's either bar (tier or surprise).
BARS = ("rule", 1, 2, 3, 4, 5, 6, 8, 10)
#: The shortest price listed (today -130) and the longest (None: no cap).
MIN_ODDS = (-130, -110, 100, 120, 150)
MAX_ODDS = (None, 400, 300, 250, 200, 150)
MIN_BOUGHT, MIN_SEASON, MIN_LIVE = 120, 40, 20
TOP = 10


def mask_for(x: pd.DataFrame, market: str, floor: int, bar, lo: int, hi) -> pd.Series:
    m = (x.market == market) & (x.prior.fillna(-1) >= floor) & (x.odds >= lo)
    if hi is not None:
        m &= x.odds <= hi
    if bar == "rule":
        m &= x.drought >= x.either_bar
    else:
        m &= x.drought >= bar
    return m.fillna(False).astype(bool)


def quick(x: pd.DataFrame) -> tuple[int, float, float]:
    if x.empty:
        return 0, float("nan"), 0.0
    return len(x), float(x.profit.mean()), float(x.profit.sum())


def label(market: str, floor: int, bar, lo: int, hi) -> str:
    b = "today's bar" if bar == "rule" else f"drought {bar}+"
    p = f"{lo:+d} to {'any' if hi is None else f'{hi:+d}'}"
    return f"{market} {floor}+ · {b} · {p}"


def sweep(w: pd.DataFrame, v: pd.DataFrame, market: str) -> list[dict]:
    out = []
    for floor in FLOORS[market]:
        for bar in BARS:
            for lo in MIN_ODDS:
                for hi in MAX_ODDS:
                    if hi is not None and hi <= lo:
                        continue
                    x = w[mask_for(w, market, floor, bar, lo, hi)]
                    y = v[mask_for(v, market, floor, bar, lo, hi)] if len(v) else v
                    a = quick(x[x.season == 2024])
                    b = quick(x[x.season == 2025])
                    c = quick(y)
                    out.append({"market": market, "floor": floor, "bar": bar, "lo": lo, "hi": hi,
                                "n": len(x), "units": float(x.profit.sum()) if len(x) else 0.0,
                                "s24": a, "s25": b, "live": c})
    return out


def eligible(c: dict) -> bool:
    return (c["n"] >= MIN_BOUGHT and c["s24"][0] >= MIN_SEASON and c["s25"][0] >= MIN_SEASON
            and c["live"][0] >= MIN_LIVE)


def worst(c: dict) -> float:
    return min(c["s24"][1], c["s25"][1], c["live"][1])


def render(w: pd.DataFrame, v: pd.DataFrame) -> list[str]:
    L = []
    for market, title in (("assists", "1+ assist"), ("points", "1+ point")):
        cs = sweep(w, v, market)
        ok = sorted((c for c in cs if eligible(c)), key=lambda c: (worst(c), c["units"] + c["live"][2]), reverse=True)
        L += ["", f"## {title}", "",
              f"{len(cs):,} settings tried, {len(ok):,} with {MIN_BOUGHT}+ bought wagers ({MIN_SEASON}+ a season) "
              f"and {MIN_LIVE}+ this season. Ranked by the worst of the three ROIs.", "",
              "| Setting | 2024-25 | 2025-26 | This season | Worst | Bought pooled (95%) | Live units |",
              "|:--|--:|--:|--:|--:|:--|--:|"]
        today = [c for c in cs if c["bar"] == "rule" and c["floor"] == (55 if market == "assists" else 60)
                 and c["lo"] == -130 and c["hi"] is None]
        for tag, c in [("**today** ", t) for t in today] + [("", c) for c in ok[:TOP]]:
            x = w[mask_for(w, market, c["floor"], c["bar"], c["lo"], c["hi"])]
            r = summary(x, zlib.crc32(repr((market, c["floor"], c["bar"], c["lo"], c["hi"])).encode()))
            pooled = "—" if r is None else f"{pct(r['roi'])} / {r['n']} ({pct(r['lo'])} .. {pct(r['hi'])})"
            cell = lambda t: f"{pct(t[1])} / {t[0]}"  # noqa: E731
            L.append(f"| {tag}{label(market, c['floor'], c['bar'], c['lo'], c['hi'])} | {cell(c['s24'])} | "
                     f"{cell(c['s25'])} | {cell(c['live'])} | {pct(worst(c))} | {pooled} | {c['live'][2]:+.1f}u |")
        if ok:
            best = ok[0]
            y = v[mask_for(v, market, best["floor"], best["bar"], best["lo"], best["hi"])]
            r = summary(y, 7)
            L += ["", f"Candidate: **{label(market, best['floor'], best['bar'], best['lo'], best['hi'])}**. "
                  f"This season: {'—' if r is None else f'{pct(r['roi'])} over {r['n']} ({pct(r['lo'])} .. {pct(r['hi'])})'}."]
    return L


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "outputs")
    ap.add_argument("--ledger-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    s = skater_frame(pd.read_csv(a.data / "player_game_logs.csv"))
    prices = pd.read_csv(a.data / "historical_prop_prices.csv",
                         usecols=["commence_time", "provider_event_id", "market", "player", "selection", "line",
                                  "american_odds", "snapshot"])
    w = attach(bought_rows(prices), s)
    del prices
    days = sorted(a.ledger_dir.glob("*.csv")) if a.ledger_dir else []
    v = attach(live_rows(pd.concat([pd.read_csv(f, low_memory=False) for f in days], ignore_index=True)), s) \
        if days else pd.DataFrame(columns=w.columns)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    L = ["# Due List: refining 1+ assist and 1+ point", "",
         f"Generated {now}. 1u flat at the best price, one wager per player-game; ROI / wagers. "
         f"Bought: {len(w):,} over 0.5 wagers; this season: {len(v):,} settled. An interval that includes zero is "
         "no demonstrated edge, and the top setting is chosen after seeing it."]
    L += render(w, v)
    text = "\n".join(L) + "\n"
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "due_list_refine.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
