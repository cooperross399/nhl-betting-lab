#!/usr/bin/env python3
"""Where the Due List can make money, and whether a Hot List would.

Cooper asked on 2026-11-18: "where can we gain profit on the DUE list and could
we investigate the possibility of adding a HOT list like guys who are playing
super well or on point/goal/assist streaks". This measures both, three ways:

1. **This season's Due List record** (`drought_forward.csv`, the graded
   entries the site tracks) sliced by category, band, price, home or away,
   drought length, the card's own opinion and month: hit rate against the
   price's implied chance, units at 1u and at the tracked stake.
2. **The shipped Due List on the two bought seasons** (best `card`-window over
   0.5, strictly before face-off, one wager per player-market-game) sliced the
   same way where the history allows: price, home or away, forward or
   defenceman, and how far past its bar the drought is.
3. **A Hot List on the two bought seasons**: the over 0.5 in points, goals or
   assists for a player on a streak of N straight games with one (2 to 8), or
   with a big last five games, at several floors of last season's total. Each
   setting is ranked by its worse season (both seasons must agree), beside the
   same players at any streak as the control.
4. **Both on this season**, out of sample: the forward ledger's frozen morning
   best price for every over 0.5 in points, goals and assists the card priced
   (`forward_evidence.csv`), settled as the ledger settled it, sliced by the
   same streak and drought.

ROI is per 1u flat at the price; intervals are 95%, bootstrapped over game
nights. Every figure is an aggregate: no price, line or book is printed. It
records nothing the card reads and spends nothing. Run where the bought prices
and the lab's state are (Due List Tuning restores both):

    PYTHONPATH=src python scripts/run_due_hot_research.py --data data/processed
"""
from __future__ import annotations

import argparse
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nhl_betting_lab.drought_rule import (  # noqa: E402
    SURPRISE_MARKETS,
    THRESHOLDS,
    band_label,
    drought_before,
    surprise_bar,
    tier_bar,
)
from nhl_betting_lab.models.player_props import player_name_aliases  # noqa: E402
from nhl_betting_lab.season import game_date  # noqa: E402

MARKETS = ("points", "goals", "assists")
BOOTSTRAPS = 1000
STREAK_BARS = (0, 2, 3, 4, 5, 6, 8)
HOT_FLOORS = {"points": (0, 40, 60, 80), "goals": (0, 20, 30, 40), "assists": (0, 30, 45, 60)}
FORM_BARS = {"points": (4, 5, 6, 7, 8), "goals": (2, 3, 4, 5), "assists": (3, 4, 5, 6)}
FORM_GAMES = 5
RANK_MIN_WAGERS = 150
RANK_MIN_SEASON = 50
PRICE_BRACKETS = ((-10_000, -151, "-150 or shorter"), (-150, -111, "-150 to -111"), (-110, 110, "-110 to +110"),
                  (111, 150, "+111 to +150"), (151, 200, "+151 to +200"), (201, 300, "+201 to +300"),
                  (301, 500, "+301 to +500"), (501, 100_000, "+501 or longer"))


def decimal(odds):
    odds = np.asarray(odds, dtype=float)
    return np.where(odds > 0, 1 + odds / 100, 1 + 100 / -odds)


def bracket(odds: float) -> str:
    for lo, hi, label in PRICE_BRACKETS:
        if lo <= odds <= hi:
            return label
    return "unknown"


def streak_before(values) -> list[int]:
    """Games in a row WITH the stat, entering each game (the game itself excluded)."""
    out, run = [], 0
    for v in values:
        out.append(run)
        run = run + 1 if v >= 1 else 0
    return out


def skater_frame(logs: pd.DataFrame) -> pd.DataFrame:
    s = logs[(logs.role == "skater") & (logs.game_type == 2)].sort_values(["player_id", "date", "game_id"]).copy()
    s["season_start"] = s.season // 10000
    for m in MARKETS:
        s[m] = pd.to_numeric(s[m], errors="coerce").fillna(0)
        by = s.groupby("player_id")[m]
        s["drought_" + m] = by.transform(lambda v: pd.Series(drought_before(v.values), index=v.index))
        s["streak_" + m] = by.transform(lambda v: pd.Series(streak_before(v.values), index=v.index))
        s["last5_" + m] = by.transform(lambda v: v.shift(1).rolling(FORM_GAMES, min_periods=FORM_GAMES).sum())
    per = s[["player_id", "season_start", *MARKETS]].copy()
    for m in MARKETS:
        per["hit_" + m] = (per[m] >= 1).astype(int)
    per["gp"] = 1
    prior = per.groupby(["player_id", "season_start"]).sum().reset_index()
    prior["season_start"] += 1
    prior = prior.rename(columns={**{m: "prior_" + m for m in MARKETS},
                                  **{"hit_" + m: "prior_hit_" + m for m in MARKETS}, "gp": "prior_gp"})
    return s.merge(prior, on=["player_id", "season_start"], how="left")


def name_index(s: pd.DataFrame) -> dict[tuple[str, str], set]:
    keys: dict[tuple[str, str], set] = {}
    for r in s[["player_id", "player", "date"]].drop_duplicates().itertuples():
        for alias in player_name_aliases(r.player):
            keys.setdefault((alias, r.date), set()).add(r.player_id)
    return keys


def attach(rows: pd.DataFrame, s: pd.DataFrame) -> pd.DataFrame:
    """Each wager row (player, gdate, market, odds, won) joined to its player-game's features."""
    keys = name_index(s)
    idx = s.drop_duplicates(["player_id", "date"]).set_index(["player_id", "date"])
    out = []
    for r in rows.itertuples():
        ids = set().union(*(keys.get((a, r.gdate), set()) for a in player_name_aliases(r.player)))
        if len(ids) != 1:
            continue
        pid = next(iter(ids))
        g = idx.loc[(pid, r.gdate)]
        m = r.market
        won = getattr(r, "won", None)
        if won is None or won != won:
            won = bool(g[m] >= 1)
        out.append({"date": r.gdate, "season": int(g.season_start), "player_id": pid, "market": m,
                    "odds": float(r.odds), "dec": float(decimal(r.odds)), "won": bool(won),
                    "push": bool(getattr(r, "push", False)),
                    "venue": g.get("venue", ""), "position": "D" if str(g.get("position", "")).upper() == "D" else "F",
                    "prior": g["prior_" + m], "prior_gp": g["prior_gp"], "prior_hits": g["prior_hit_" + m],
                    "drought": int(g["drought_" + m]), "streak": int(g["streak_" + m]), "last5": g["last5_" + m],
                    "model_edge": getattr(r, "model_edge", np.nan)})
    w = pd.DataFrame(out)
    if w.empty:
        return w
    w["profit"] = np.where(w.push, 0.0, np.where(w.won, w.dec - 1, -1.0))
    w["bracket"] = w.odds.map(bracket)
    w["qualifies"] = w.prior >= w.market.map(THRESHOLDS)
    gp = pd.to_numeric(w.prior_gp, errors="coerce")
    hit_rate = pd.to_numeric(w.prior_hits, errors="coerce") / gp.where(gp > 0)
    w["band"] = [band_label(m, t) if t == t else "" for m, t in zip(w.market, w.prior)]
    tb = pd.to_numeric(pd.Series([tier_bar(m, t) if t == t else None for m, t in zip(w.market, w.prior)], index=w.index),
                       errors="coerce")
    sb = pd.to_numeric(pd.Series([surprise_bar(p) if m in SURPRISE_MARKETS and p == p else None
                                  for m, p in zip(w.market, hit_rate)], index=w.index), errors="coerce")
    w["either_bar"] = pd.concat([tb, sb], axis=1).min(axis=1)
    w["due"] = w.qualifies & (w.drought >= w.either_bar)
    return w


def bought_rows(prices: pd.DataFrame) -> pd.DataFrame:
    p = prices[prices.market.isin(MARKETS) & (prices.line == 0.5) & (prices.selection == "over")].copy()
    p["gdate"] = p.commence_time.map(game_date)
    p = p[pd.to_datetime(p.snapshot, utc=True) < pd.to_datetime(p.commence_time, utc=True)]
    first = p.groupby("provider_event_id").snapshot.transform("min")
    p = p[p.snapshot == first]
    p["dec"] = decimal(p.american_odds)
    best = p.sort_values("dec").groupby(["provider_event_id", "market", "player"]).tail(1)
    return best.rename(columns={"american_odds": "odds"})[["gdate", "market", "player", "odds"]]


def live_rows(ledger: pd.DataFrame) -> pd.DataFrame:
    p = ledger[ledger.market.isin(MARKETS) & (pd.to_numeric(ledger.line, errors="coerce") == 0.5)
               & (ledger.selection == "over") & ledger.outcome.isin(["won", "lost", "push"])].copy()
    p["gdate"] = p.commence_time.map(game_date)
    p["dec"] = decimal(p.american_odds)
    best = p.sort_values("dec").groupby(["snapshot_date", "market", "player"]).tail(1)
    best = best.rename(columns={"american_odds": "odds", "edge": "model_edge"})
    best["won"] = best.outcome == "won"
    best["push"] = best.outcome == "push"
    return best[["gdate", "market", "player", "odds", "won", "push", "model_edge"]]


def summary(x: pd.DataFrame, seed: int, profit: str = "profit") -> dict | None:
    if x.empty:
        return None
    nights = x.groupby("date")[profit].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(nights), size=(BOOTSTRAPS, len(nights)))
    s, n = nights["sum"].to_numpy(), nights["count"].to_numpy()
    boot = s[i].sum(1) / n[i].sum(1)
    graded = x[~x.get("push", pd.Series(False, index=x.index)).astype(bool)]
    return {"n": int(len(x)), "hit": float(graded.won.mean()) if len(graded) else float("nan"),
            "implied": float((1 / x.dec).mean()), "roi": float(x[profit].mean()), "units": float(x[profit].sum()),
            "lo": float(np.percentile(boot, 2.5)), "hi": float(np.percentile(boot, 97.5))}


def pct(v):
    return "—" if v is None or v != v else f"{v * 100:+.1f}%"


def row(label: str, r: dict | None) -> str:
    if r is None:
        return f"| {label} | 0 | — | — | — | — | — |"
    return (f"| {label} | {r['n']:,} | {r['hit'] * 100:.1f}% | {r['implied'] * 100:.1f}% | {r['units']:+.1f}u | "
            f"{pct(r['roi'])} | {pct(r['lo'])} .. {pct(r['hi'])} |")


HEAD = ["| Slice | Wagers | Hit | Implied | Units (1u) | ROI | 95% interval |", "|:--|--:|--:|--:|--:|--:|:--|"]


def table(title: str, x: pd.DataFrame, slices: list[tuple[str, pd.Series]], salt: str) -> list[str]:
    L = ["", f"### {title}", "", *HEAD]
    for label, mask in slices:
        L.append(row(label, summary(x[mask.fillna(False).astype(bool)], zlib.crc32((salt + label).encode()))))
    return L


def drought_past(x: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    past = x.drought - x.either_bar
    return [("at the bar", past == 0), ("1-2 past", past.between(1, 2)), ("3-5 past", past.between(3, 5)),
            ("6+ past", past >= 6)]


def standard_slices(x: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    sl = [("all", pd.Series(True, index=x.index))]
    sl += [(f"market {m}", x.market == m) for m in MARKETS]
    sl += [(f"price {label}", x.bracket == label) for _, _, label in PRICE_BRACKETS]
    sl += [("home", x.venue == "home"), ("away", x.venue == "away"), ("forward", x.position == "F"),
           ("defenceman", x.position == "D")]
    return sl


# ---------------------------------------------------------------- Part 1: this season's Due List record

CATEGORY = {("points", 0.5): "1+ point", ("goals", 0.5): "1+ goal", ("assists", 0.5): "1+ assist",
            ("goals", 1.5): "2+ goals", ("goals", 2.5): "hat trick", ("points", 1.5): "2+ points"}


def tracked_profit(odds: float, outcome: str) -> float:
    from nhl_betting_lab.drought_forward import tracked_stake
    if outcome not in ("won", "lost") or odds != odds:
        return 0.0
    if odds < 0:
        risk, win = 0.25 * -odds / 100, 0.25
    else:
        stake = tracked_stake(None, odds)
        risk, win = stake, stake * odds / 100
    return win if outcome == "won" else -risk


def due_live(ledger: pd.DataFrame) -> list[str]:
    L = ["", "## 1. This season's Due List record", ""]
    d = ledger[ledger.outcome.isin(["won", "lost", "push"])].copy()
    d["odds"] = pd.to_numeric(d.american_odds, errors="coerce")
    graded_all = d.copy()
    d = d[d.odds.notna()].copy()
    if d.empty:
        return L + ["No priced, graded Due List entries."]
    d["line"] = pd.to_numeric(d.line, errors="coerce")
    d["dec"] = decimal(d.odds)
    d["won"] = d.outcome == "won"
    d["push"] = d.outcome == "push"
    d["profit"] = np.where(d.push, 0.0, np.where(d.won, d.dec - 1, -1.0))
    d["tracked"] = [tracked_profit(o, oc) for o, oc in zip(d.odds, d.outcome)]
    d["category"] = [CATEGORY.get((m, ln), f"{m} {ln}") for m, ln in zip(d.market, d.line)]
    d["bracket"] = d.odds.map(bracket)
    d["home"] = d.team == d.home_team
    d["band"] = [band_label(m, t) if m in THRESHOLDS and t == t else c
                 for m, t, c in zip(d.market, pd.to_numeric(d.last_season, errors="coerce"), d.category)]
    d["date"] = d["date"].astype(str)
    edge = pd.to_numeric(d.model_edge, errors="coerce")
    dr = pd.to_numeric(d.drought, errors="coerce")
    L.append(f"{len(graded_all):,} graded entries, {len(d):,} with a price ({d.date.min()} to {d.date.max()}); "
             f"tracked units {d.tracked.sum():+.2f}u.")
    sl = [("all", pd.Series(True, index=d.index))]
    sl += [(f"category {c}", d.category == c) for c in sorted(d.category.unique())]
    sl += [(f"band {b}", d.band == b) for b in sorted(d.band.unique()) if b not in set(d.category)]
    sl += [(f"price {label}", d.bracket == label) for _, _, label in PRICE_BRACKETS]
    sl += [("home", d.home), ("away", ~d.home)]
    sl += [("drought 0-4", dr <= 4), ("drought 5-9", dr.between(5, 9)), ("drought 10-19", dr.between(10, 19)),
           ("drought 20+", dr >= 20)]
    sl += [("card agrees (edge > 0)", edge > 0), ("card edge 5%+", edge >= 0.05), ("card disagrees (edge <= 0)", edge <= 0),
           ("no card opinion", edge.isna())]
    sl += [(f"month {m}", d.date.str[:7] == m) for m in sorted(d.date.str[:7].unique())]
    L += table("Every slice (1u flat at the listed price)", d, sl, "live-due")
    L += ["", "### Tracked units (the site's sizes) by category", "", "| Category | Entries | Tracked units |", "|:--|--:|--:|"]
    for c, g in d.groupby("category"):
        L.append(f"| {c} | {len(g):,} | {g.tracked.sum():+.2f}u |")
    return L


# ---------------------------------------------------------------- Part 2 and 3: bought seasons

def due_history(w: pd.DataFrame) -> list[str]:
    L = ["", "## 2. The shipped Due List on the bought seasons (card window)", ""]
    x = w[w.due].copy()
    sl = standard_slices(x) + drought_past(x)
    sl += [(f"season {s}", x.season == s) for s in (2024, 2025)]
    L += table("Shipped rule, every slice", x, sl, "hist-due")
    for m in MARKETS:
        y = x[x.market == m]
        L += table(f"Shipped rule, {m}, by price and venue", y,
                   [(f"price {label}", y.bracket == label) for _, _, label in PRICE_BRACKETS]
                   + [("home", y.venue == "home"), ("away", y.venue == "away")] + drought_past(y), "hist-due-" + m)
    return L


def hot_cells(w: pd.DataFrame) -> list[dict]:
    out = []
    for m in MARKETS:
        for floor in HOT_FLOORS[m]:
            q = w[(w.market == m) & (w.prior.fillna(0) >= floor)]
            defs = [(f"streak {b}+", q.streak >= b, b) for b in STREAK_BARS]
            defs += [(f"last {FORM_GAMES} >= {k}", q.last5 >= k, k) for k in FORM_BARS[m]]
            for label, mask, bar in defs:
                x = q[mask.fillna(False).astype(bool)]
                seed = zlib.crc32(repr((m, floor, label)).encode())
                out.append({"market": m, "floor": floor, "rule": label, "bar": bar,
                            "all": summary(x, seed), "s2024": summary(x[x.season == 2024], seed + 1),
                            "s2025": summary(x[x.season == 2025], seed + 2)})
    return out


def ranked(cs: list[dict]) -> list[dict]:
    ok = [c for c in cs if c["bar"] > 0 and c["all"] and c["all"]["n"] >= RANK_MIN_WAGERS and c["s2024"] and c["s2025"]
          and c["s2024"]["n"] >= RANK_MIN_SEASON and c["s2025"]["n"] >= RANK_MIN_SEASON]
    return sorted(ok, key=lambda c: (min(c["s2024"]["roi"], c["s2025"]["roi"]), c["all"]["roi"]), reverse=True)


def hot_history(w: pd.DataFrame) -> tuple[list[str], list[dict]]:
    cs = hot_cells(w)
    L = ["", "## 3. A Hot List on the bought seasons (card window)", "",
         f"Streak N+ = N or more straight games with one entering tonight; last {FORM_GAMES} >= k = k or more in "
         "the last five games. Floor = last season's total in that stat. Control = streak 0+ at the same floor.", "",
         "### Best settings, ranked by their worse season", "",
         "| Market | Floor | Rule | Wagers | Hit | Implied | ROI | 95% interval | 2024-25 | 2025-26 | Control ROI |",
         "|:--|--:|:--|--:|--:|--:|--:|:--|--:|--:|--:|"]
    control = {(c["market"], c["floor"]): c["all"] for c in cs if c["rule"] == "streak 0+"}
    for c in ranked(cs)[:25]:
        a, ctl = c["all"], control.get((c["market"], c["floor"]))
        L.append(f"| {c['market']} | {c['floor']}+ | {c['rule']} | {a['n']:,} | {a['hit'] * 100:.1f}% | "
                 f"{a['implied'] * 100:.1f}% | {pct(a['roi'])} | {pct(a['lo'])} .. {pct(a['hi'])} | "
                 f"{pct(c['s2024']['roi'])} / {c['s2024']['n']} | {pct(c['s2025']['roi'])} / {c['s2025']['n']} | "
                 f"{pct(ctl['roi']) if ctl else '—'} |")
    L += ["", "### Every streak cell, all floors", "",
          "| Market | Floor | Rule | Wagers | Hit | Implied | ROI | 95% interval |", "|:--|--:|:--|--:|--:|--:|--:|:--|"]
    for c in cs:
        a = c["all"]
        if a:
            L.append(f"| {c['market']} | {c['floor']}+ | {c['rule']} | {a['n']:,} | {a['hit'] * 100:.1f}% | "
                     f"{a['implied'] * 100:.1f}% | {pct(a['roi'])} | {pct(a['lo'])} .. {pct(a['hi'])} |")
    return L, cs


# ---------------------------------------------------------------- Part 4: this season, out of sample

def live_test(v: pd.DataFrame, cs: list[dict]) -> list[str]:
    L = ["", "## 4. This season, out of sample (forward ledger, morning best price)", ""]
    if v.empty:
        return L + ["No settled over 0.5 opinions in points, goals or assists matched a player."]
    L.append(f"{len(v):,} settled overs at 0.5 ({v.date.min()} to {v.date.max()}).")
    sl = [("all overs 0.5", pd.Series(True, index=v.index)), ("Due List rule", v.due)]
    sl += [(f"Due {m}", v.due & (v.market == m)) for m in MARKETS]
    L += table("The Due List rule this season", v, sl, "live-due-rule")
    top = ranked(cs)[:10]
    rows = []
    for c in top:
        q = v[(v.market == c["market"]) & (v.prior.fillna(0) >= c["floor"])]
        if c["rule"].startswith("streak"):
            mask = q.streak >= c["bar"]
        else:
            mask = q.last5 >= c["bar"]
        rows.append((f"{c['market']} {c['floor']}+ {c['rule']}", q[mask.fillna(False).astype(bool)]))
    L += ["", "### The bought seasons' ten best Hot settings, this season", "", *HEAD]
    for label, x in rows:
        L.append(row(label, summary(x, zlib.crc32(("live-hot" + label).encode()))))
    sl = [(f"{m} streak {b}+", (v.market == m) & (v.streak >= b)) for m in MARKETS for b in STREAK_BARS if b]
    L += table("Every streak length this season, any player", v, sl, "live-streak")
    return L


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "outputs")
    ap.add_argument("--ledger-dir", type=Path, default=None,
                    help="a folder of the forward ledger's day files (card-feed's forward_evidence/)")
    a = ap.parse_args(argv)
    logs = pd.read_csv(a.data / "player_game_logs.csv")
    s = skater_frame(logs)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    L = ["# Due List profit and a Hot List: research", "", f"Generated {now}. 1u flat at the price; "
         "95% intervals bootstrapped over game nights. An interval that includes zero is no demonstrated edge."]
    ledger_path = a.data / "drought_forward.csv"
    if ledger_path.exists():
        L += due_live(pd.read_csv(ledger_path))
    else:
        L += ["", "## 1. This season's Due List record", "", "No Due List ledger on disk."]
    prices_path = a.data / "historical_prop_prices.csv"
    cs: list[dict] = []
    if prices_path.exists():
        prices = pd.read_csv(prices_path, usecols=["commence_time", "provider_event_id", "market", "player",
                                                   "selection", "line", "american_odds", "snapshot"])
        w = attach(bought_rows(prices), s)
        del prices
        L += due_history(w)
        hot, cs = hot_history(w)
        L += hot
    else:
        L += ["", "No bought prices on disk; parts 2 and 3 not measured."]
    fe = a.data / "forward_evidence.csv"
    days = sorted(a.ledger_dir.glob("*.csv")) if a.ledger_dir else []
    if days or fe.exists():
        frames = [pd.read_csv(f, low_memory=False) for f in days] if days else [pd.read_csv(fe, low_memory=False)]
        v = attach(live_rows(pd.concat(frames, ignore_index=True)), s)
        L += live_test(v, cs)
    else:
        L += ["", "## 4. This season", "", "No forward ledger on disk."]
    text = "\n".join(L) + "\n"
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "due_hot_research.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
