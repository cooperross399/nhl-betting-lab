"""Measure the Due List rule against bought prop prices.

The rule (Cooper, 2026-10-07 evening; goals changed 2026-10-10): a skater who
produced 70+ points, 25+ goals or 30+ assists LAST regular season is listed in
that category when his current drought (straight regular-season games dressed
without one in it) reaches EITHER bar: the TIER bar from last season's total
(points 100+ -> 3, 85-99 -> 4, 70-84 -> 5; goals 40+ -> 5, 25-39 -> 10;
assists 60+ -> 3, 45-59 -> 4, 30-44 -> 5) or, for points and assists only,
the SURPRISE bar from his own prior-season hit rate p (the smallest n with
(1 - p)^n <= 0.05). The wager measured
is the over 0.5 in that category (1+ point, anytime goal, 1+ assist). The flat
5-game rule it replaced (#307, the same morning) is kept as its own buckets so
history reads the same.

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
    SHIPPED_BUCKET,
    SURPRISE_LEVEL,
    SURPRISE_MARKETS,
    THRESHOLDS,
    TIERS,
    band_label,
    drought_before,
    prepare_logs,
    surprise_bar,
    tier_bar,
    tier_bucket,
)
from nhl_betting_lab.models.player_props import player_name_aliases  # noqa: E402
from nhl_betting_lab.season import game_date  # noqa: E402

# The drought logic lives in src/ so the Gameday card and this evidence share one function.
__all__ = ["SHIPPED_BUCKET", "SURPRISE_LEVEL", "THRESHOLDS", "TIERS", "band_label", "drought_before",
           "prepare_logs", "surprise_bar", "tier_bar", "tier_bucket"]

#: The flat bar of the rule #307 shipped (every qualifier at 5+). Its buckets
#: stay in the report so the history reads the same; the card no longer uses it.
FLAT_DROUGHT = 5
BUCKETS = (("not in drought (0-4)", 0, 4), (f"RULE: drought {FLAT_DROUGHT}+", FLAT_DROUGHT, 10_000),
           ("drought 5-6", 5, 6), ("drought 7-9", 7, 9), ("drought 10+", 10, 10_000))
TIER_ONLY_BUCKET = "TIER bars only"
SURPRISE_ONLY_BUCKET = f"SURPRISE {SURPRISE_LEVEL:.0%} only"
GOAL_SWEEP = (30, 35, 40, 45)
BOOTSTRAPS = 1000
RULE_SENTENCE = (
    "A skater with 70+ points, 25+ goals or 30+ assists last regular season is listed in that category when "
    "his drought reaches either the tier bar from last season's total (points 100+ -> 3, 85-99 -> 4, 70-84 -> 5; "
    "goals 40+ -> 5, 25-39 -> 10; assists 60+ -> 3, 45-59 -> 4, 30-44 -> 5) or, for points and assists, the "
    f"surprise bar from his own prior-season hit rate p, the smallest n with (1 - p)^n <= {SURPRISE_LEVEL}; "
    "the wager is the over 0.5."
)


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
                         "won": bool(g[r.market] >= 1), "prior": g["prior_" + r.market], "drought": int(g["drought_" + r.market]),
                         "prior_gp": g["prior_gp"], "prior_hits": g["prior_hit_" + r.market]})
    return label_bars(pd.DataFrame(rows)), counts


def label_bars(w: pd.DataFrame) -> pd.DataFrame:
    """Each wager's bars: whether he qualifies, his band and tier bar, his hit rate and surprise bar."""
    w = w.copy()
    w["profit"] = np.where(w.won, w.dec - 1, -1.0)
    w["qualifies"] = w.prior >= w.market.map(THRESHOLDS)
    gp = pd.to_numeric(w.prior_gp, errors="coerce")
    w["hit_rate"] = pd.to_numeric(w.prior_hits, errors="coerce") / gp.where(gp > 0)
    w["band"] = [band_label(m, t) for m, t in zip(w.market, w.prior)]
    w["tier_bar"] = pd.to_numeric(pd.Series([tier_bar(m, t) for m, t in zip(w.market, w.prior)], index=w.index), errors="coerce")
    w["surprise_bar"] = pd.to_numeric(pd.Series([surprise_bar(p) if m in SURPRISE_MARKETS else None
                                                 for m, p in zip(w.market, w.hit_rate)], index=w.index), errors="coerce")
    w["either_bar"] = w[["tier_bar", "surprise_bar"]].min(axis=1)
    return w


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


def bucket_masks(q: pd.DataFrame, market: str) -> list[tuple[str, pd.Series]]:
    """Every bucket of one market's qualifiers, in report order: the flat rule's, then the shipped rule's."""
    masks = [(label, q.drought.between(lo, hi)) for label, lo, hi in BUCKETS]
    masks += [
        (SHIPPED_BUCKET, q.drought >= q.either_bar),
        (TIER_ONLY_BUCKET, q.drought >= q.tier_bar),
        (SURPRISE_ONLY_BUCKET, q.surprise_bar.notna() & (q.drought >= q.surprise_bar)),
    ]
    for floor, bar in TIERS[market]:
        band = band_label(market, floor)
        masks.append((tier_bucket(band, bar), (q.band == band) & (q.drought >= bar)))
        masks.append((tier_bucket(band, bar, exactly=True), (q.band == band) & (q.drought == bar)))
    return masks


def measure(w: pd.DataFrame) -> dict:
    out = {"buckets": [], "goal_sweep": []}
    for window in ("card", "late"):
        for market in THRESHOLDS:
            q = w[(w.window == window) & (w.market == market) & w.qualifies]
            for label, mask in bucket_masks(q, market):
                for season in ("both", 2024, 2025):
                    x = q[mask.fillna(False).astype(bool)]
                    if season != "both":
                        x = x[x.season == season]
                    r = summarize(x, seed=zlib.crc32(repr((window, market, label, season)).encode()))
                    if r:
                        out["buckets"].append({"window": window, "market": market, "bucket": label, "season": str(season), **r})
    g = w[(w.window == "card") & (w.market == "goals") & (w.drought >= FLAT_DROUGHT)]
    for th in GOAL_SWEEP:
        x = g[g.prior >= th]
        r = summarize(x, seed=th)
        if r:
            r["by_season"] = {str(s): summarize(x[x.season == s], seed=th + s) for s in (2024, 2025)}
            out["goal_sweep"].append({"prior_goals_at_least": th, **r})
    return out


def pct(v):
    return f"{v * 100:+.1f}%"


def _tiers_sentence() -> str:
    return "; ".join(f"{m} " + ", ".join(f"{band_label(m, floor)} -> {bar}" for floor, bar in tiers) for m, tiers in TIERS.items())


def render(result: dict, counts: dict, generated_at: str) -> str:
    L = [
        "# Due List backtest",
        "",
        f"Generated {generated_at} by `scripts/run_drought_rule_backtest.py`. Every figure below comes from that script.",
        "",
        f"**The rule.** {RULE_SENTENCE}",
        "",
        f"**The bars.** Tier bar, from last season's total: {_tiers_sentence()}. Surprise bar, from his own "
        f"prior-season hit rate p (games with one or more / games dressed): the smallest n with (1 - p)^n <= "
        f"{SURPRISE_LEVEL} (undefined when p is 0; 1 when p is 1). A player is listed when his drought reaches "
        f"either. The flat rule shipped that morning (#307: every qualifier at {FLAT_DROUGHT}+) is kept below as "
        f"`RULE: drought {FLAT_DROUGHT}+` so the history reads the same.",
        "",
        "**How it is measured.** 2024-25 and 2025-26 regular seasons. One wager per selection at the best price any book "
        "offered. `card` is each event's first snapshot (the window the Gameday card prices in); `late` is its last. "
        "Interval: 95%, bootstrapped over game nights. MDE: the smallest ROI this sample could detect at 80% power. "
        "Seasons are labelled by their starting year.",
        "",
    ]
    by = {(b["window"], b["market"], b["bucket"], b["season"]): b for b in result["buckets"]}
    L += ["## Headline (card window, the shipped rule: either bar)", "",
          "| Market | Wagers | Nights | Hit | Implied | ROI | 95% interval | MDE | 2024-25 | 2025-26 |",
          "|:--|--:|--:|--:|--:|--:|:--|--:|--:|--:|"]
    for m in THRESHOLDS:
        b, s1, s2 = by.get(("card", m, SHIPPED_BUCKET, "both")), by.get(("card", m, SHIPPED_BUCKET, "2024")), by.get(("card", m, SHIPPED_BUCKET, "2025"))
        if b:
            L.append(f"| {m} | {b['wagers']} | {b['nights']} | {b['hit_rate']*100:.1f}% | {b['implied']*100:.1f}% | {pct(b['roi'])} | "
                     f"{pct(b['ci_low'])} .. {pct(b['ci_high'])} | {b['mde']*100:.1f}% | "
                     f"{pct(s1['roi']) + ' / ' + str(s1['wagers']) if s1 else '—'} | {pct(s2['roi']) + ' / ' + str(s2['wagers']) if s2 else '—'} |")
        else:
            L.append(f"| {m} | 0 | 0 | — | — | — | — | — | — | — |")
    L += ["", "## The two bars apart (card window)", "",
          "`SHIPPED` is either bar; `TIER bars only` and `SURPRISE 5% only` are each bar on its own, over the same qualifiers.", "",
          "| Market | Bucket | Wagers | Nights | Hit | Implied | ROI | 95% interval | MDE | 2024-25 | 2025-26 |",
          "|:--|:--|--:|--:|--:|--:|--:|:--|--:|--:|--:|"]
    for m in THRESHOLDS:
        for label in (SHIPPED_BUCKET, TIER_ONLY_BUCKET, SURPRISE_ONLY_BUCKET):
            b, s1, s2 = by.get(("card", m, label, "both")), by.get(("card", m, label, "2024")), by.get(("card", m, label, "2025"))
            if b:
                L.append(f"| {m} | {label} | {b['wagers']} | {b['nights']} | {b['hit_rate']*100:.1f}% | {b['implied']*100:.1f}% | "
                         f"{pct(b['roi'])} | {pct(b['ci_low'])} .. {pct(b['ci_high'])} | {b['mde']*100:.1f}% | "
                         f"{pct(s1['roi']) + ' / ' + str(s1['wagers']) if s1 else '—'} | {pct(s2['roi']) + ' / ' + str(s2['wagers']) if s2 else '—'} |")
            else:
                L.append(f"| {m} | {label} | 0 | 0 | — | — | — | — | — | — | — |")
    L += ["", "## Per band (card window)", "",
          "`@bar` is the band's players with a drought at or past the band's bar (what the tier bar lists); "
          "`==bar` is the same players exactly at the bar (the night the tier bar first lists them).", "",
          "| Market | Band | Bar | @bar wagers | Hit | Implied | ROI | 95% interval | MDE | 2024-25 | 2025-26 | ==bar wagers | ROI | 95% interval |",
          "|:--|:--|--:|--:|--:|--:|--:|:--|--:|--:|--:|--:|--:|:--|"]
    for m, tiers in TIERS.items():
        for floor, bar in tiers:
            band = band_label(m, floor)
            b = by.get(("card", m, tier_bucket(band, bar), "both"))
            s1, s2 = by.get(("card", m, tier_bucket(band, bar), "2024")), by.get(("card", m, tier_bucket(band, bar), "2025"))
            e = by.get(("card", m, tier_bucket(band, bar, exactly=True), "both"))
            at = (f"{b['wagers']} | {b['hit_rate']*100:.1f}% | {b['implied']*100:.1f}% | {pct(b['roi'])} | "
                  f"{pct(b['ci_low'])} .. {pct(b['ci_high'])} | {b['mde']*100:.1f}% | "
                  f"{pct(s1['roi']) + ' / ' + str(s1['wagers']) if s1 else '—'} | {pct(s2['roi']) + ' / ' + str(s2['wagers']) if s2 else '—'}"
                  if b else "0 | — | — | — | — | — | — | —")
            exactly = f"{e['wagers']} | {pct(e['roi'])} | {pct(e['ci_low'])} .. {pct(e['ci_high'])}" if e else "0 | — | —"
            L.append(f"| {m} | {band} | {bar} | {at} | {exactly} |")
    L += ["", "## Every bucket", "", "Control is the same qualifying players when they are NOT in a drought (flat rule's buckets first).", "",
          "| Window | Market | Bucket | Season | Wagers | Nights | Hit | Implied | Median odds | ROI | 95% interval | MDE | Units |",
          "|:--|:--|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|"]
    for b in result["buckets"]:
        L.append(f"| {b['window']} | {b['market']} | {b['bucket']} | {b['season']} | {b['wagers']} | {b['nights']} | "
                 f"{b['hit_rate']*100:.1f}% | {b['implied']*100:.1f}% | {b['median_odds']:+d} | {pct(b['roi'])} | "
                 f"{pct(b['ci_low'])} .. {pct(b['ci_high'])} | {b['mde']*100:.1f}% | {b['units']:+.1f} |")
    L += ["", f"## Goals: does a higher scoring bar help? (card window, flat drought {FLAT_DROUGHT}+)", "",
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


def payload(result: dict, counts: dict, generated_at: str) -> dict:
    """The JSON: the keys the first report had, plus the tiers, the level and the rule in one sentence."""
    return {"generated_at": generated_at, "thresholds": THRESHOLDS, "min_drought": FLAT_DROUGHT,
            "tiers": {m: [list(t) for t in tiers] for m, tiers in TIERS.items()},
            "surprise_level": SURPRISE_LEVEL, "rule": RULE_SENTENCE, "accounting": counts, **result}


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
    (a.out / "drought_rule_backtest.json").write_text(json.dumps(payload(result, counts, now), indent=1) + "\n")
    (a.out / "drought_rule_backtest.md").write_text(render(result, counts, now))
    print(render(result, counts, now).split("## Every bucket")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
