#!/usr/bin/env python3
"""Measure the league's scoring drift and fit the PostHockey blend weight.

Cooper, 2026-11-10 ("All"): two model changes, both live on the card
(`scoring_env`, `posthockey.fit_blend_weight`). This is their measurement,
information only; nothing here is read by the card.

1. **Drift.** League per-game skater goals, assists, points, shots, blocks
   and hits, and total goals, for this season's periods (before 2026-10-19,
   10-19 to 10-27, from 10-28) against earlier seasons and against every
   regular-season game in the logs (the window the models are fitted on).
2. **Persistence.** On every week of every season the logs hold: does the
   last `ENV_DAYS` days' deviation from the fitted level carry into the next
   14 days? The slope through the origin is how much of it to keep, and
   gives the shrinkage in games it implies.
3. **The forward ledger.** Settled prop wagers in population B (6% bar),
   by market, side and period: the model's chance against the hit rate.
4. **Price replay of the environment.** Every settled ledger wager in a
   moved market repriced with the night's walk-forward multiplier, against
   the same frozen best price and outcome. Approximate: the frozen chance is
   inverted to a Poisson mean, scaled and re-read (the props model uses a
   negative binomial for some stats), and a total moves by the target over
   the fitted level alone (the card divides by its ratings' own level).
5. **PostHockey blend weight.** From the frozen site boards' factor
   breakdown (the card's own home win chance before the blend, exactly) and
   PostHockey's number the card used, against finals: the log-loss-best
   weight with a bootstrap interval over games, the card's own refit on its
   own sources, and the moneyline repriced at that weight against the
   frozen prices.

Reads the logs, team games, forward ledger, PostHockey reads and frozen
site boards. Writes `data/outputs/scoring_environment_study.md` and
`.json`. Spends nothing.

    PYTHONPATH=src python scripts/run_scoring_environment.py --history-dir dist/data/history
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_layer_scoring as layer  # noqa: E402

from nhl_betting_lab import posthockey, scoring_env  # noqa: E402
from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR  # noqa: E402

SEASON_FROM = "2026-10-07"
PERIODS = (("before 10-19", "", "2026-10-19"), ("10-19 to 10-27", "2026-10-19", "2026-10-28"),
           ("from 10-28", "2026-10-28", "9999"))
NEXT_DAYS = 14
REPORT_MD = "scoring_environment_study.md"
REPORT_JSON = "scoring_environment_study.json"
STATS = (scoring_env.TEAM_GOALS, *scoring_env.MEASURED_STATS)


def drift(table: pd.DataFrame, today: str) -> dict:
    out: dict = {"seasons": {}, "periods": {}, "reference": {}}
    table = table.copy()
    table["date"] = table["date"].astype(str)
    season_of = table["game_id"].astype(str).str[:4]
    for season, rows in table.groupby(season_of):
        out["seasons"][season] = {"games": int(len(rows)), **{s: float(rows[s].mean()) for s in STATS}}
    current = table[table["date"] >= SEASON_FROM]
    for label, start, end in PERIODS:
        rows = current[(current["date"] >= start) & (current["date"] < end)]
        out["periods"][label] = {"games": int(len(rows)), **{s: float(rows[s].mean()) for s in STATS}}
    before = table[table["date"] < today]
    out["reference"] = {"games": int(len(before)), **{s: float(before[s].mean()) for s in STATS}}
    return out


def persistence(table: pd.DataFrame, *, rng: np.random.Generator) -> dict:
    """Slope of the next 14 days' deviation on the last ENV_DAYS days'."""
    table = table.copy()
    table["date"] = table["date"].astype(str)
    dates = sorted(table["date"].unique())
    if not dates:
        return {}
    first = date.fromisoformat(dates[0]) + timedelta(days=200)
    last = date.fromisoformat(dates[-1]) - timedelta(days=NEXT_DAYS)
    points: list[dict] = []
    day = first
    while day <= last:
        night = day.isoformat()
        env = scoring_env.reading(table, night)
        after = table[(table["date"] >= night)
                      & (table["date"] < (day + timedelta(days=NEXT_DAYS)).isoformat())]
        if env.active and len(after) >= 40:
            row = {"night": night, "recent_games": env.recent_games}
            for stat in STATS:
                if stat in env.reference:
                    ref = env.reference[stat]
                    row[f"x_{stat}"] = env.recent[stat] / ref - 1.0
                    row[f"y_{stat}"] = float(after[stat].mean()) / ref - 1.0
            points.append(row)
        day += timedelta(days=7)
    frame = pd.DataFrame(points)
    out: dict = {"weeks": int(len(frame))}
    if frame.empty:
        return out
    n_recent = float(frame["recent_games"].mean())
    out["mean_recent_games"] = n_recent
    for stat in STATS:
        x, y = frame.get(f"x_{stat}"), frame.get(f"y_{stat}")
        if x is None or x.isna().all():
            continue
        mask = x.notna() & y.notna()
        x, y = x[mask].to_numpy(), y[mask].to_numpy()
        slope = float((x * y).sum() / (x * x).sum()) if (x * x).sum() > 0 else 0.0
        boots = []
        for _ in range(1000):
            pick = rng.integers(0, len(x), len(x))
            xx, yy = x[pick], y[pick]
            if (xx * xx).sum() > 0:
                boots.append(float((xx * yy).sum() / (xx * xx).sum()))
        low, high = (np.percentile(boots, [2.5, 97.5]) if boots else (slope, slope))
        clipped = min(max(slope, 1e-6), 0.999999)
        out[stat] = {
            "slope": slope, "low": float(low), "high": float(high),
            "implied_shrinkage_games": float(n_recent * (1 - clipped) / clipped),
            "mean_abs_recent_deviation": float(np.abs(x).mean()),
        }
    return out


def ledger_calibration(wagers: pd.DataFrame) -> list[dict]:
    rows = wagers[wagers["is_prop"].astype(bool)].copy()
    rows["prob"] = rows["model_probability"].astype(float)
    rows = rows[rows["prob"] - rows["implied"] >= layer.MIN_PROP_EDGE - 1e-12]
    rows["period"] = ""
    for label, start, end in PERIODS:
        day = rows["snapshot_date"].astype(str)
        rows.loc[(day >= start) & (day < end), "period"] = label
    out = []
    for (market, side, period), part in rows.groupby(["market", "selection", "period"]):
        decided = part[part["outcome"].isin(["won", "lost"])]
        out.append({
            "market": market, "side": side, "period": period, "wagers": int(len(part)),
            "model": float(part["prob"].mean()),
            "hit_rate": float((decided["outcome"] == "won").mean()) if len(decided) else float("nan"),
            "units": float(part["profit_units"].astype(float).sum()),
        })
    return out


def poisson_over(mean: float, line: float) -> float:
    return layer.poisson_over(mean, line)


def implied_mean(p_over: float, line: float) -> float | None:
    """The Poisson mean whose P(X > line) is `p_over`, by bisection."""
    if not 0.0 < p_over < 1.0:
        return None
    low, high = 1e-6, 60.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if poisson_over(mid, line) < p_over:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def env_replay(wagers: pd.DataFrame, table: pd.DataFrame, logs: pd.DataFrame) -> tuple[dict, dict]:
    from nhl_betting_lab.models.player_props import team_form_factors, team_game_totals

    moved = set(scoring_env.ENV_STATS) | {"total_goals"}
    rows = wagers[wagers["market"].isin(moved)].copy()
    totals = team_game_totals(logs) if not logs.empty else None
    cache: dict[str, dict[str, float]] = {}
    new_p = []
    for row in rows.itertuples():
        night = str(row.snapshot_date)
        if night not in cache:
            env = scoring_env.reading(table, night)
            form = team_form_factors(totals, before=night) if totals is not None else {}
            mult = scoring_env.props_multipliers(env, form)
            mult["total_goals"] = (
                min(max(env.ratio.get(scoring_env.TEAM_GOALS, 1.0), scoring_env.ENV_RANGE[0]),
                    scoring_env.ENV_RANGE[1]) if env.active else 1.0
            )
            cache[night] = mult
        factor = cache[night].get(str(row.market), 1.0)
        prob = float(row.model_probability)
        side = str(row.selection)
        line = float(row.line) if pd.notna(row.line) else float("nan")
        if factor == 1.0 or side not in ("over", "under") or math.isnan(line):
            new_p.append(prob)
            continue
        p_over = prob if side == "over" else 1.0 - prob
        mu = implied_mean(p_over, line)
        if mu is None:
            new_p.append(prob)
            continue
        q = poisson_over(mu * factor, line)
        new_p.append(min(max(q if side == "over" else 1.0 - q, 0.001), 0.999))
    rows["p_env"] = new_p
    results: dict = {}
    for market in sorted(rows["market"].unique()):
        part = rows[rows["market"] == market]
        if len(part) >= 1:
            results[market] = layer.score(part, "p_env", "model_probability")
    props = rows[rows["market"] != "total_goals"]
    if not props.empty:
        results["all moved props"] = layer.score(props, "p_env", "model_probability")
    notes = {"nights": {k: v for k, v in sorted(cache.items())}, "wagers": int(len(rows))}
    return results, notes


def board_blend_rows(history: Path, games: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for path in sorted(history.glob("20??-??-??.json")) if history.is_dir() else []:
        day = path.stem
        if day < posthockey.BLEND_FROM:
            continue
        try:
            board = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for game in board.get("games") or []:
            steps = game.get("factors") or []
            keys = [str(s.get("key")) for s in steps]
            if "posthockey" not in keys:
                continue
            i = keys.index("posthockey")
            delta = float(steps[i].get("delta") or 0.0)
            if i == 0 or abs(delta) < 1e-9:
                continue  # PostHockey had not priced it: nothing was blended
            p_model = float(steps[i - 1]["homeWin"])
            rows.append({
                "date": day, "home": (game.get("home") or {}).get("abbr"),
                "away": (game.get("away") or {}).get("abbr"),
                "p_model": p_model, "target": p_model + delta / posthockey.BLEND_WEIGHT,
                "p_final": float(steps[i]["homeWin"]), "source": "board",
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["target"] = frame["target"].clip(*posthockey.PROBABILITY_RANGE)
    return frame.merge(posthockey.home_results(games), on=["date", "home", "away"], how="inner")


def blend_study(frame: pd.DataFrame, *, rng: np.random.Generator) -> dict:
    if frame.empty:
        return {"games": 0}
    raw = posthockey.best_weight(frame)
    boots = []
    for _ in range(1000):
        boots.append(posthockey.best_weight(frame.iloc[rng.integers(0, len(frame), len(frame))]))
    out = {
        "games": int(len(frame)), "first": str(frame["date"].min()), "last": str(frame["date"].max()),
        "best": raw, "low": float(np.percentile(boots, 2.5)), "high": float(np.percentile(boots, 97.5)),
        "shrunk": posthockey.blend_weight(raw, len(frame)),
        "home_win_rate": float(frame["home_won"].mean()),
        "log_loss": {f"{w:.2f}": posthockey.blend_log_loss(frame, w)
                     for w in sorted({0.0, 0.25, 0.5, 0.75, 1.0, raw})},
    }
    halves = {}
    for label, part in (("before 11-01", frame[frame["date"] < "2026-11-01"]),
                        ("from 11-01", frame[frame["date"] >= "2026-11-01"])):
        if len(part):
            halves[label] = {"games": int(len(part)), "best": posthockey.best_weight(part)}
    out["halves"] = halves
    return out


def blend_replay(wagers: pd.DataFrame, boards: pd.DataFrame, weight: float, team_names: dict) -> dict:
    from nhl_betting_lab.providers.team_names import resolve_team

    ml = wagers[wagers["market"] == "moneyline"].copy()
    if ml.empty or boards.empty:
        return {}
    ml["home"] = ml["home_team"].map(lambda n: resolve_team(n, team_names))
    ml["away"] = ml["away_team"].map(lambda n: resolve_team(n, team_names))
    ml["date"] = ml["snapshot_date"].astype(str)
    ml = ml.merge(boards[["date", "home", "away", "p_model", "target", "p_final"]],
                  on=["date", "home", "away"], how="inner")
    ml = ml[(ml["p_final"] - np.where(ml["selection"] == "home", ml["model_probability"].astype(float),
                                      1 - ml["model_probability"].astype(float))).abs() <= 0.01]
    if ml.empty:
        return {}
    home_new = ml["p_model"] + weight * (ml["target"] - ml["p_model"])
    shift = home_new - ml["p_final"]
    ml["p_fit"] = np.where(ml["selection"] == "home", ml["model_probability"].astype(float) + shift,
                           ml["model_probability"].astype(float) - shift).clip(0.001, 0.999)
    return layer.score(ml.reset_index(drop=True), "p_fit", "model_probability")


def render(payload: dict) -> str:
    d = payload["drift"]
    lines = ["# Scoring environment and PostHockey blend: measurement", "",
             "Information only (Cooper, 2026-11-10, \"All\"); the card reads none of it.", "",
             "## 1. League scoring per game, regular season", "",
             "| Window | Games | " + " | ".join(STATS) + " |", "|:--|--:|" + "--:|" * len(STATS)]
    for label, row in [*d["seasons"].items(), *d["periods"].items(), ("fit window (all before today)", d["reference"])]:
        lines.append(f"| {label} | {row['games']:,} | " + " | ".join(
            f"{row.get(s, float('nan')):.2f}" for s in STATS) + " |")
    env = payload["environment_today"]
    lines += ["", f"Today's reading: {env['describe']}", "",
              "## 2. Does a three-week move persist into the next two weeks?", ""]
    p = payload["persistence"]
    lines.append(f"{p.get('weeks', 0)} weekly readings, mean {p.get('mean_recent_games', 0):.0f} recent games.")
    lines += ["", "| Stat | Slope (kept share) | 95% | Implied shrinkage (games) | Mean abs. recent move |",
              "|:--|--:|:--|--:|--:|"]
    for stat in STATS:
        if stat in p:
            r = p[stat]
            lines.append(f"| {stat} | {r['slope']:.2f} | [{r['low']:.2f}, {r['high']:.2f}] | "
                         f"{r['implied_shrinkage_games']:.0f} | {r['mean_abs_recent_deviation']:.1%} |")
    lines += ["", "## 3. Population B props on the forward ledger", "",
              "| Market | Side | Period | Wagers | Model | Hit rate | Units |", "|:--|:--|:--|--:|--:|--:|--:|"]
    for r in payload["ledger_calibration"]:
        lines.append(f"| {r['market']} | {r['side']} | {r['period']} | {r['wagers']:,} | {r['model']:.1%} | "
                     f"{r['hit_rate']:.1%} | {r['units']:+.1f} |")
    lines += ["", "## 4. Price replay of the environment (approximate)", "",
              "| Market | Pop. B with | Pop. B without | Contribution (B) | Staked with | Staked without | "
              "Contribution (staked) |", "|:--|:--|:--|--:|:--|:--|--:|"]
    for market, r in payload["env_replay"].items():
        b, s = r["population_b"], r["staked"]
        lines.append(f"| {market} | {layer._cell(b['with'])} | {layer._cell(b['without'])} | "
                     f"{b['contribution_units']:+.1f}u ({b['changed_wagers']} changed; halves "
                     f"{b['halves']['before']:+.1f} / {b['halves']['after']:+.1f}) | {layer._cell(s['with'])} | "
                     f"{layer._cell(s['without'])} | {s['contribution_units']:+.1f}u |")
    lines += ["", "## 5. PostHockey blend weight", "", "```",
              json.dumps(payload["blend"], indent=2, sort_keys=True, default=str), "```", "",
              "Every interval spans zero unless it says otherwise: **no demonstrated edge**.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR)
    parser.add_argument("--history-dir", type=Path, default=Path("dist/data/history"))
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args(argv)
    from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
    from nhl_betting_lab.providers.team_names import load_team_name_map

    rng = np.random.default_rng(20261110)
    logs = load_player_logs(args.processed_dir)
    games = load_team_games(args.processed_dir)
    table = scoring_env.league_game_table(logs, games)
    if table.empty:
        print("::error::No player logs or team games to measure.", file=sys.stderr)
        return 1
    env_today = scoring_env.reading(table, args.today)
    payload: dict = {
        "drift": drift(table, args.today),
        "environment_today": {"describe": env_today.describe(), "ratio": env_today.ratio,
                              "recent_games": env_today.recent_games},
        "persistence": persistence(table, rng=rng),
        "constants": {"ENV_DAYS": scoring_env.ENV_DAYS, "ENV_SHRINKAGE_GAMES": scoring_env.ENV_SHRINKAGE_GAMES,
                      "ENV_RANGE": scoring_env.ENV_RANGE, "ENV_STATS": sorted(scoring_env.ENV_STATS)},
    }
    team_names = load_team_name_map(processed_dir=args.processed_dir)
    ledger = layer.load_ledger([], args.processed_dir)
    if ledger.empty:
        payload.update({"ledger_calibration": [], "env_replay": {}, "env_replay_notes": {}})
    else:
        layer.WINDOW_FROM = SEASON_FROM
        wagers = layer.settled_wagers(ledger)
        payload["settled_wagers"] = int(len(wagers))
        payload["ledger_calibration"] = ledger_calibration(wagers)
        payload["env_replay"], payload["env_replay_notes"] = env_replay(wagers, table, logs)
    boards = board_blend_rows(args.history_dir, games)
    blend = {"boards": blend_study(boards, rng=rng)}
    card_fit = posthockey.fit_blend_weight(args.processed_dir, games, team_names, before=args.today,
                                           ledger=None)
    blend["card_refit"] = card_fit
    if not ledger.empty and not boards.empty:
        weight = blend["boards"]["shrunk"]
        blend["moneyline_replay_at_shrunk_weight"] = blend_replay(wagers, boards, weight, team_names)
        blend["moneyline_replay_at_best_weight"] = blend_replay(
            wagers, boards, blend["boards"]["best"], team_names)
    payload["blend"] = blend
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / REPORT_JSON).write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    text = render(payload)
    (args.output_dir / REPORT_MD).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
