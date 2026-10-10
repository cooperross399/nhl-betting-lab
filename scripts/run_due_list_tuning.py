#!/usr/bin/env python3
"""Which Due List settings are best? Searched, and checked on a season they were not chosen on.

Cooper asked on 2026-10-10 for "the best possible parameters for the due
list". Searching settings on two seasons and quoting the winner would only
find the settings that fitted the noise best, so this does four things:

1. **Does a drought tell the price anything?** Among good producers, it
   compares each drought length with the same players when they are not in a
   drought (ROI difference, interval bootstrapped over game nights), and fits
   `won ~ logit(implied) + drought` so a drought is judged against the price
   it was offered at. If a drought carries nothing the book has not priced,
   no setting can beat the vig except by luck.
2. **The search.** Per category, every combination of last season's total
   (the qualifier), the drought bar (a flat bar, or the surprise bar at a
   level), and a price window. The best setting on 2024-25 is scored on
   2025-26, and the other way round, beside the shipped rule on the same
   season.
3. **What a search finds in noise.** The same search on simulated seasons in
   which every bet is priced exactly as it was and the drought carries
   nothing (each over wins at its implied probability, scaled so the bets
   lose the vig they really lost). The best in-sample ROI the real search
   found is placed in that distribution.
4. **The other side.** The best under 0.5 on the same players, by drought,
   since a market that over-reacts to a drought would make the under the
   value side.

One wager per selection at the best price any book offered, in each event's
first snapshot (`card`, the window the list is published in), strictly
before face-off. Seasons are labelled by their starting year. Every figure is
an aggregate (wagers, hit rates, ROI, intervals); no price, line or book is
printed.

It records nothing the card or the list reads, changes no setting, and
spends nothing. The bought prices are not in git, so it runs where they are
(the Due List Tuning workflow restores them onto its runner):

    PYTHONPATH=src python scripts/run_due_list_tuning.py --data data/processed
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nhl_betting_lab.drought_rule import SURPRISE_MARKETS, THRESHOLDS, prepare_logs, surprise_bar, tier_bar  # noqa: E402
from nhl_betting_lab.models.player_props import player_name_aliases  # noqa: E402
from nhl_betting_lab.season import game_date  # noqa: E402

MARKETS = tuple(THRESHOLDS)
SEASONS = (2024, 2025)
#: The population every analysis starts from: well below the shipped
#: qualifier, so the search can move it down as well as up.
FLOORS = {"points": 40, "goals": 15, "assists": 25}
QUALIFIERS = {
    "points": (40, 50, 60, 70, 80, 90, 100),
    "goals": (15, 20, 25, 30, 35, 40),
    "assists": (25, 30, 40, 50, 60),
}
FLAT_BARS = tuple(range(1, 11))
SURPRISE_LEVELS = (0.5, 0.35, 0.25, 0.15, 0.10, 0.05, 0.025)
#: Price window, American odds: the shortest price allowed, then the longest.
SHORTEST = (None, -160, -130, 100)
LONGEST = (None, 300, 200)
MIN_TRAIN_WAGERS = 100
DROUGHT_BUCKETS = (("0 (control)", 0, 0), ("1-2", 1, 2), ("3-4", 3, 4), ("5-6", 5, 6), ("7-9", 7, 9), ("10+", 10, 10_000))
BOOTSTRAPS = 1000
NULL_SIMS = 200


def decimal(odds):
    odds = np.asarray(odds, dtype=float)
    return np.where(odds > 0, 1 + odds / 100, 1 + 100 / -odds)


def build(prices: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    """One row per (event, market, player, side): the best card-window price, joined to his game."""
    keys: dict[tuple[str, str], set] = {}
    for r in logs[["player_id", "player", "date"]].drop_duplicates().itertuples():
        for alias in player_name_aliases(r.player):
            keys.setdefault((alias, r.date), set()).add(r.player_id)
    by_game = logs.drop_duplicates(["player_id", "date"]).set_index(["player_id", "date"])

    p = prices[prices.market.isin(MARKETS) & (prices.line == 0.5) & prices.selection.isin(["over", "under"])].copy()
    p = p[pd.to_datetime(p.snapshot) < pd.to_datetime(p.commence_time)]
    p = p[p.snapshot == p.groupby("provider_event_id").snapshot.transform("min")]
    p["gdate"] = p.commence_time.map(game_date)
    p["dec"] = decimal(p.american_odds)
    best = p.sort_values("dec").groupby(["provider_event_id", "market", "player", "selection"]).tail(1)

    rows = []
    for r in best.itertuples():
        ids = set().union(*(keys.get((a, r.gdate), set()) for a in player_name_aliases(r.player)))
        if len(ids) != 1:
            continue
        g = by_game.loc[(next(iter(ids)), r.gdate)]
        prior_gp = g["prior_gp"]
        if pd.isna(prior_gp) or prior_gp <= 0:
            continue
        hit = g[r.market] >= 1
        rows.append({
            "side": r.selection, "date": r.gdate, "season": int(g.season_start), "market": r.market,
            "player_id": int(next(iter(ids))), "odds": float(r.american_odds), "dec": float(r.dec),
            "won": bool(hit if r.selection == "over" else not hit),
            "prior": float(g["prior_" + r.market]), "drought": int(g["drought_" + r.market]),
            "hit_rate": float(g["prior_hit_" + r.market]) / float(prior_gp),
        })
    w = pd.DataFrame(rows)
    w["profit"] = np.where(w.won, w.dec - 1, -1.0)
    w["implied"] = 1 / w.dec
    w["shipped_bar"] = [min(b for b in (tier_bar(m, t), surprise_bar(h) if m in SURPRISE_MARKETS else None)
                            if b is not None)
                        if tier_bar(m, t) is not None else np.nan
                        for m, t, h in zip(w.market, w.prior, w.hit_rate)]
    return w


def night_boot(x: pd.DataFrame, seed: int, column: str = "profit") -> tuple[float, float]:
    nights = x.groupby("date")[column].agg(["sum", "count"])
    if len(nights) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(nights), size=(BOOTSTRAPS, len(nights)))
    s, n = nights["sum"].to_numpy(), nights["count"].to_numpy()
    boot = s[idx].sum(1) / n[idx].sum(1)
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def summary(x: pd.DataFrame, seed: int) -> dict:
    if x.empty:
        return {"wagers": 0}
    lo, hi = night_boot(x, seed)
    return {"wagers": int(len(x)), "hit_rate": float(x.won.mean()), "implied": float(x.implied.mean()),
            "roi": float(x.profit.mean()), "units": float(x.profit.sum()), "ci_low": lo, "ci_high": hi}


def diff_vs_control(x: pd.DataFrame, control: pd.DataFrame, seed: int) -> tuple[float, float, float]:
    """ROI(x) - ROI(control), bootstrapped over the nights both share."""
    a = x.groupby("date").profit.agg(["sum", "count"])
    b = control.groupby("date").profit.agg(["sum", "count"])
    nights = a.index.union(b.index)
    a, b = a.reindex(nights, fill_value=0), b.reindex(nights, fill_value=0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(nights), size=(BOOTSTRAPS, len(nights)))
    with np.errstate(invalid="ignore", divide="ignore"):
        d = a["sum"].to_numpy()[idx].sum(1) / a["count"].to_numpy()[idx].sum(1) \
            - b["sum"].to_numpy()[idx].sum(1) / b["count"].to_numpy()[idx].sum(1)
    d = d[np.isfinite(d)]
    point = x.profit.mean() - control.profit.mean()
    return float(point), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 50) -> np.ndarray:
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        mu = 1 / (1 + np.exp(-(X @ beta)))
        W = mu * (1 - mu)
        H = X.T @ (X * W[:, None]) + 1e-9 * np.eye(X.shape[1])
        step = np.linalg.solve(H, X.T @ (y - mu))
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    return beta


def information_test(x: pd.DataFrame, seed: int) -> dict:
    """won ~ 1 + logit(implied) + min(drought, 10)/5 + log-rarity, bootstrapped over nights.

    `rarity_log` is drought x log(1 - p): how unlikely the streak is for him.
    The price's own coefficient soaks up the vig and any favourite-longshot
    bias, so the drought terms are what the price did not already say.
    """
    y = x.won.to_numpy(float)
    drought = np.minimum(x.drought.to_numpy(float), 10) / 5
    rarity = -x.drought.to_numpy(float) * np.log(np.clip(1 - x.hit_rate.to_numpy(float), 1e-6, 1))
    X = np.column_stack([np.ones(len(x)), logit(x.implied), drought, np.minimum(rarity, 6)])
    beta = fit_logistic(X, y)
    dates = x.date.to_numpy()
    uniq, inv = np.unique(dates, return_inverse=True)
    groups = [np.flatnonzero(inv == i) for i in range(len(uniq))]
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(200):
        pick = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        boots.append(fit_logistic(X[pick], y[pick]))
    boots = np.array(boots)
    out = {"n": int(len(x))}
    for i, name in ((2, "drought_per_5_games"), (3, "rarity_log")):
        out[name] = {"coef": float(beta[i]), "low": float(np.percentile(boots[:, i], 2.5)),
                     "high": float(np.percentile(boots[:, i], 97.5))}
    return out


def grid(market: str) -> list[dict]:
    bars = [("flat", d) for d in FLAT_BARS] + [("surprise", a) for a in SURPRISE_LEVELS]
    return [{"qualifier": q, "bar": b, "level": v, "shortest": s, "longest": lg}
            for q, (b, v), s, lg in itertools.product(QUALIFIERS[market], bars, SHORTEST, LONGEST)]


def surprise_bars(hit_rate: np.ndarray, level: float) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        n = np.ceil(np.log(level) / np.log(1 - hit_rate))
    n = np.where(hit_rate >= 1, 1, n)
    return np.where((hit_rate <= 0) | ~np.isfinite(n), np.inf, np.maximum(n, 1))


def masks(x: pd.DataFrame, settings: list[dict]) -> np.ndarray:
    prior, drought, odds, hr = (x[c].to_numpy(float) for c in ("prior", "drought", "odds", "hit_rate"))
    out = np.zeros((len(settings), len(x)), dtype=np.float32)
    for i, s in enumerate(settings):
        bar = s["level"] if s["bar"] == "flat" else surprise_bars(hr, s["level"])
        m = (prior >= s["qualifier"]) & (drought >= bar)
        # American odds: every plus price is >= +100 and every minus price <= -100,
        # so ">= -130" keeps -130 .. -101 and every plus price, and ">= +100" keeps plus prices only.
        if s["shortest"] is not None:
            m &= odds >= s["shortest"]
        if s["longest"] is not None:
            m &= odds <= s["longest"]
        out[i] = m
    return out


def setting_text(s: dict) -> str:
    bar = f"drought {s['level']}+" if s["bar"] == "flat" else f"surprise bar at {s['level']:g}"
    price = []
    if s["shortest"] is not None:
        price.append(f"no shorter than {s['shortest']:+d}")
    if s["longest"] is not None:
        price.append(f"no longer than {s['longest']:+d}")
    return f"last season {s['qualifier']}+, {bar}" + (f", {', '.join(price)}" if price else "")


def best_setting(M: np.ndarray, profit: np.ndarray) -> tuple[int, float]:
    n = M.sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        roi = (M @ profit) / n
    roi = np.where(n >= MIN_TRAIN_WAGERS, roi, -np.inf)
    i = int(np.argmax(roi))
    return i, float(roi[i])


def search(over: pd.DataFrame) -> dict:
    out = {"folds": [], "null": {}}
    rng = np.random.default_rng(20261010)
    for market in MARKETS:
        x = over[over.market == market]
        settings = grid(market)
        for train, test in ((2024, 2025), (2025, 2024)):
            tr, te = x[x.season == train], x[x.season == test]
            Mtr, Mte = masks(tr, settings), masks(te, settings)
            i, train_roi = best_setting(Mtr, tr.profit.to_numpy(np.float32))
            chosen = te[Mte[i].astype(bool)]
            shipped = te[te.drought >= te.shipped_bar]
            out["folds"].append({
                "market": market, "train": train, "setting": settings[i],
                "setting_text": setting_text(settings[i]), "settings_searched": len(settings),
                "train_wagers": int(Mtr[i].sum()), "train_roi": train_roi,
                "test_result": summary(chosen, seed=train * 7 + len(market)),
                "shipped_on_test": summary(shipped, seed=test * 11 + len(market)),
                "test_season": test,
            })
            # The same search where the drought carries nothing: each over wins at
            # its implied probability, scaled to lose exactly the vig it lost.
            imp = tr.implied.to_numpy()
            dec = tr.dec.to_numpy()
            scale = (tr.profit.mean() + 1) / (imp * dec).mean()
            q = np.clip(imp * scale, 0, 1)
            null_best, null_test, null_both = [], [], []
            n_tr, n_te = Mtr.sum(1), Mte.sum(1)
            enough = (n_tr >= MIN_TRAIN_WAGERS) & (n_te >= MIN_TRAIN_WAGERS)

            def positive_in_both(p_tr, p_te):
                with np.errstate(invalid="ignore", divide="ignore"):
                    return int((enough & (Mtr @ p_tr > 0) & (Mte @ p_te > 0)).sum())

            real_both = positive_in_both(tr.profit.to_numpy(np.float32), te.profit.to_numpy(np.float32))
            imp_te, dec_te = te.implied.to_numpy(), te.dec.to_numpy()
            q_te = np.clip(imp_te * (te.profit.mean() + 1) / (imp_te * dec_te).mean(), 0, 1)
            for _ in range(NULL_SIMS):
                won = rng.random(len(tr)) < q
                prof = np.where(won, dec - 1, -1.0).astype(np.float32)
                j, b = best_setting(Mtr, prof)
                null_best.append(b)
                won_te = rng.random(len(te)) < q_te
                sel = Mte[j].astype(bool)
                prof_te = np.where(won_te, dec_te - 1, -1.0).astype(np.float32)
                null_test.append(float(prof_te[sel].mean()) if sel.any() else np.nan)
                null_both.append(positive_in_both(prof, prof_te))
            null_best = np.array(null_best)
            out["null"][f"{market}:{train}"] = {
                "real_best_train_roi": train_roi,
                "null_best_train_roi_median": float(np.median(null_best)),
                "null_best_train_roi_95th": float(np.percentile(null_best, 95)),
                "share_of_null_at_least_real": float((null_best >= train_roi).mean()),
                "null_test_roi_median": float(np.nanmedian(null_test)),
                "settings_with_both_seasons": int(enough.sum()),
                "real_positive_in_both": real_both,
                "null_positive_in_both_median": float(np.median(null_both)),
                "null_positive_in_both_95th": float(np.percentile(null_both, 95)),
                "share_of_null_both_at_least_real": float((np.array(null_both) >= real_both).mean()),
            }
    return out


def measure(w: pd.DataFrame) -> dict:
    over = w[(w.side == "over") & (w.prior >= w.market.map(FLOORS))]
    under = w[(w.side == "under") & (w.prior >= w.market.map(FLOORS))]
    res = {"population": {}, "by_drought": [], "under_by_drought": [], "information": {}}
    for market in MARKETS:
        x = over[over.market == market]
        u = under[under.market == market]
        res["population"][market] = {"over": summary(x, 1), "under": summary(u, 2),
                                     "floor": FLOORS[market]}
        control = x[x.drought == 0]
        for label, lo, hi in DROUGHT_BUCKETS:
            b = x[x.drought.between(lo, hi)]
            entry = {"market": market, "bucket": label, **summary(b, lo * 13 + len(market))}
            if lo > 0 and len(b):
                d, dl, dh = diff_vs_control(b, control, seed=lo * 17 + len(market))
                entry.update({"vs_control": d, "vs_control_low": dl, "vs_control_high": dh})
                entry["by_season"] = {str(s): summary(b[b.season == s], s + lo) for s in SEASONS}
            res["by_drought"].append(entry)
            ub = u[u.drought.between(lo, hi)]
            res["under_by_drought"].append({"market": market, "bucket": label, **summary(ub, lo * 19 + len(market))})
        res["information"][market] = information_test(x, seed=len(market))
    res["search"] = search(over)
    return res


def pct(v):
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:+.1f}%"


def cell(s: dict) -> str:
    if not s.get("wagers"):
        return "0 wagers"
    return f"{pct(s['roi'])} over {s['wagers']:,} [{pct(s['ci_low'])} .. {pct(s['ci_high'])}]"


def render(res: dict, generated_at: str) -> str:
    L = ["# Due List tuning", "",
         f"Generated {generated_at} by `scripts/run_due_list_tuning.py`. 2024-25 and 2025-26 regular seasons, "
         "best price per wager in the `card` window, over 0.5 unless a table says under. Intervals are 95%, "
         "bootstrapped over game nights.", "",
         "## Who is in the population", "",
         "| Category | Last season at least | Overs | Over ROI | Unders | Under ROI |", "|:--|--:|--:|:--|--:|:--|"]
    for m, p in res["population"].items():
        L.append(f"| {m} | {p['floor']} | {p['over'].get('wagers', 0):,} | {cell(p['over'])} | "
                 f"{p['under'].get('wagers', 0):,} | {cell(p['under'])} |")
    L += ["", "## 1. Does a drought tell the price anything?", "",
          "Overs on the population above, by the drought entering the game, against the same players with no "
          "drought (drought 0). `vs control` is the ROI difference.", "",
          "| Category | Drought | Wagers | Hit | Implied | ROI | 95% interval | vs control | 95% interval | 2024-25 | 2025-26 |",
          "|:--|:--|--:|--:|--:|--:|:--|--:|:--|--:|--:|"]
    for b in res["by_drought"]:
        if not b.get("wagers"):
            continue
        vs = (f"{pct(b['vs_control'])} | {pct(b['vs_control_low'])} .. {pct(b['vs_control_high'])}"
              if "vs_control" in b else "— | —")
        seasons = " | ".join(f"{pct(s['roi'])} / {s['wagers']}" if s.get("wagers") else "—"
                             for s in b.get("by_season", {}).values()) or "— | —"
        L.append(f"| {b['market']} | {b['bucket']} | {b['wagers']:,} | {b['hit_rate']*100:.1f}% | {b['implied']*100:.1f}% | "
                 f"{pct(b['roi'])} | {pct(b['ci_low'])} .. {pct(b['ci_high'])} | {vs} | {seasons} |")
    L += ["", "Judged against the price: `won ~ logit(implied) + drought + rarity`. A coefficient whose interval "
          "spans zero means the drought adds nothing the price had not already said.", "",
          "| Category | Wagers | Drought (per 5 games) | 95% interval | Rarity for him | 95% interval |", "|:--|--:|--:|:--|--:|:--|"]
    for m, r in res["information"].items():
        d, k = r["drought_per_5_games"], r["rarity_log"]
        L.append(f"| {m} | {r['n']:,} | {d['coef']:+.3f} | {d['low']:+.3f} .. {d['high']:+.3f} | "
                 f"{k['coef']:+.3f} | {k['low']:+.3f} .. {k['high']:+.3f} |")
    L += ["", "## 2. The search, checked on the other season", "",
          f"Per category: every last-season qualifier x every drought bar (flat 1-10, or the surprise bar at "
          f"{', '.join(f'{a:g}' for a in SURPRISE_LEVELS)}) x a price window. The setting with the best ROI on one "
          f"season (at least {MIN_TRAIN_WAGERS} wagers) is scored on the other, beside the shipped rule there.", "",
          "| Category | Chosen on | Best setting | Settings searched | ROI where chosen | Scored on | Its ROI there | Shipped rule there |",
          "|:--|--:|:--|--:|:--|--:|:--|:--|"]
    for f in res["search"]["folds"]:
        L.append(f"| {f['market']} | {f['train']} | {f['setting_text']} | {f['settings_searched']:,} | "
                 f"{pct(f['train_roi'])} over {f['train_wagers']:,} | {f['test_season']} | {cell(f['test_result'])} | {cell(f['shipped_on_test'])} |")
    L += ["", "## 3. What the same search finds when the drought means nothing", "",
          f"{NULL_SIMS} simulated seasons, every bet at its real price, each over winning at its implied "
          "probability scaled to lose the vig it really lost. `Share` is how often noise alone found a best "
          "setting at least as good as the real search did.", "",
          "| Category:season | Real best ROI | Noise: median best | Noise: 95th pct best | Share | Noise: chosen setting's ROI on the other season |",
          "|:--|--:|--:|--:|--:|--:|"]
    for k, n in res["search"]["null"].items():
        L.append(f"| {k} | {pct(n['real_best_train_roi'])} | {pct(n['null_best_train_roi_median'])} | "
                 f"{pct(n['null_best_train_roi_95th'])} | {n['share_of_null_at_least_real']:.2f} | {pct(n['null_test_roi_median'])} |")
    L += ["", f"Settings that made money in BOTH seasons (at least {MIN_TRAIN_WAGERS} wagers in each), against how many "
          "noise alone produces. A real effect shows as many more than noise.", "",
          "| Category | Settings with enough wagers | Positive in both, real | Noise: median | Noise: 95th pct | Share of noise at least real |",
          "|:--|--:|--:|--:|--:|--:|"]
    for k, n in res["search"]["null"].items():
        if k.endswith(":2024"):
            L.append(f"| {k.split(':')[0]} | {n['settings_with_both_seasons']:,} | {n['real_positive_in_both']:,} | "
                     f"{n['null_positive_in_both_median']:.0f} | {n['null_positive_in_both_95th']:.0f} | "
                     f"{n['share_of_null_both_at_least_real']:.2f} |")
    L += ["", "## 4. The other side: unders 0.5 by drought", "",
          "| Category | Drought | Wagers | Hit | Implied | ROI | 95% interval |", "|:--|:--|--:|--:|--:|--:|:--|"]
    for b in res["under_by_drought"]:
        if b.get("wagers"):
            L.append(f"| {b['market']} | {b['bucket']} | {b['wagers']:,} | {b['hit_rate']*100:.1f}% | "
                     f"{b['implied']*100:.1f}% | {pct(b['roi'])} | {pct(b['ci_low'])} .. {pct(b['ci_high'])} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
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
    w = build(prices, logs)
    res = measure(w)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "due_list_tuning.json").write_text(json.dumps({"generated_at": now, **res}, indent=1, default=float) + "\n")
    text = render(res, now)
    (a.out / "due_list_tuning.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
