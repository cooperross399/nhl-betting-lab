#!/usr/bin/env python3
"""Measure the period-market shadow model walk-forward, on outcomes.

    PYTHONPATH=src .venv/bin/python scripts/run_period_markets.py [--fetch]

Reads `team_games.csv` and the cached NHL play-by-play
(`data/raw/nhl/play_by_play/<game>.json`, the cache `run_shadow_stats.py`
fills). `--fetch` downloads the play-by-play of every final game not yet
cached (free, keyless NHL API; the same fetch `run_shadow_stats.py --fetch`
makes). Without it only cached games are read. When
`shadow_team_games.csv` is beside the processed tables, the site's xG
ratings are scored too.

Writes `data/processed/period_goals.csv` (goals by period, per game) and the
report to `data/outputs/period_markets.md` and `.json`. Nothing here fetches
odds or spends a credit, and nothing on the card's path reads any of it
(`nhl_betting_lab.new_markets`).

Exit codes: 0 measured; 1 nothing to measure (no team games, no cached
play-by-play, or too little history for a single window); 2 the parsed goals
rebuild the boxscore score too rarely, or too many fetches failed, to trust.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.data.build_datasets import load_team_games
from nhl_betting_lab.data.nhl_api import NhlApiError, _cache_root, _read_cache, game_is_final
from nhl_betting_lab.new_markets import periods
from nhl_betting_lab.shadow.play_by_play import fetch_play_by_play

#: Below this share of exact boxscore matches the parse is suspect.
MINIMUM_MATCH = 0.95
#: Above this share of failed fetches the coverage is suspect.
MAXIMUM_FETCH_FAILURES = 0.02
SHADOW_TEAM_TABLE = "shadow_team_games.csv"
PERIOD_TABLE = "period_goals.csv"


def _final_game_ids(team_games: pd.DataFrame) -> list[int]:
    frame = team_games.dropna(subset=["home_goals", "away_goals"])
    ids = pd.to_numeric(frame["game_id"], errors="coerce").dropna()
    return sorted({int(g) for g in ids if int(g) > 0})


def _num(value: float | None, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def _interval(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "unbounded"
    return f"[{low:+.2f}, {high:+.2f}]"


def render(payload: dict) -> str:
    v = payload["validation"]
    lines = [
        "# Period markets: a shadow model, measured on outcomes",
        "",
        "Built beside the card, never on it (`nhl_betting_lab.new_markets.periods`). "
        "Nothing on the card's path imports it, and it reaches the card only after a "
        "price backtest and Cooper's decision.",
        "",
        "**Read this first.** These are forecasting comparisons on outcomes, walk-forward: "
        "each game is priced on ratings and period shares fitted only on earlier games. "
        "Beating the baseline means team information helps forecast a period. It says "
        "nothing about beating a price; only a price backtest can, and none has been run.",
        "",
        "## Settlement",
        "",
        "- `h2h_p1..p3`: two-way, **a tied period is a push** (inferred from the provider "
        "serving a separate three-way market; check each book's rule before a price "
        "backtest). Tied periods are counted as void and scored nowhere in those rows.",
        "- `h2h_3_way_p1..p3`: home, draw, away for the period; Brier is the three-class sum.",
        "- `spreads_p1..p3`: home's line at -1.5, -0.5, +0.5, +1.5 (away's is the complement).",
        "- `totals_p1..p3`: over 0.5, 1.5, 2.5 goals in the period.",
        "- Periods 1-3 only; overtime and the shootout settle no period market.",
        "",
        "## Data",
        "",
        f"- Final games in `team_games.csv`: {payload['games_listed']:,} (only regular-season "
        f"games are scored); "
        f"play-by-play read for {payload['games_read']:,}; fetch failures: {payload['fetch_failures']}.",
        f"- Goal events whose scoring side could not be told: {payload['unattributed']:,}.",
        f"- Parsed goals rebuild the boxscore's final score in "
        f"{_num(None if v['match'] != v['match'] else 100 * v['match'], '.1f')}% of {v['games']:,} games.",
        f"- Games scored walk-forward: {payload['games_scored']:,}.",
        "",
        "League goals per period (all games read), and the share of a side's final goals "
        "scored in each period (the last fit):",
        "",
        "| Period | Home goals | Away goals | Home share | Away share | Tied |",
        "|:--|--:|--:|--:|--:|--:|",
    ]
    for row in payload["league_periods"]:
        lines.append(
            f"| {row['period']} | {row['home_rate']:.3f} | {row['away_rate']:.3f} | "
            f"{_num(row['home_share'], '.3f')} | {_num(row['away_share'], '.3f')} | {row['tied']:.1%} |"
        )
    lines += [
        "",
        "## Each model against the baseline",
        "",
        "Gain is the baseline's mean loss minus the model's, per 1,000 rows: positive is "
        "better. Baseline: " + periods.MODEL_LABELS["baseline"] + ". 95% intervals are "
        "clustered on the game; the corrected interval counts every market-line measured "
        "for that model.",
    ]
    for model in [m for m in periods.MODELS if m != "baseline"]:
        rows = [r for r in payload["summary"] if r["model"] == model]
        if not rows:
            continue
        lines += [
            "",
            f"### {periods.MODEL_LABELS[model]}",
            "",
            "| Market | Line | Games | Void | Log loss | Baseline | Gain/1,000 | 95% interval | "
            "Corrected | Brier gain/1,000 | Mean p | Observed | Verdict |",
            "|:--|:--|--:|--:|--:|--:|--:|:--|:--|--:|--:|--:|:--|",
        ]
        for r in rows:
            label = r["market"] if r["scope"] != "line" else f"`{r['market']}`"
            lines.append(
                f"| {label} | {r['line']} | {r['games']:,} | "
                f"{'' if r['void'] is None else r['void']} | {r['log_loss']:.4f} | "
                f"{r['baseline_log_loss']:.4f} | {r['ll_gain_per_1000']:+.2f} | "
                f"{_interval(r['low'], r['high'])} | {_interval(r['adjusted_low'], r['adjusted_high'])} | "
                f"{r['brier_gain_per_1000']:+.2f} | {_num(r['mean_p'], '.3f')} | "
                f"{_num(r['observed'], '.3f')} | {r['verdict']} |"
            )
    if not payload["summary"]:
        lines += ["", "Nothing was scored: too little history for a single walk-forward window."]
    lines += [
        "",
        "## What this cannot see",
        "",
        "- The score after two periods: protecting a lead and pulling the goalie make the "
        "third period the least Poisson of the three.",
        "- The full-game model's overconfidence on favourites carries into every period.",
        "- A period that beats the baseline here has earned a price backtest, nothing more.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Fetch uncached play-by-play (free NHL API).")
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR)
    args = parser.parse_args(argv)

    team_games = load_team_games(args.processed_dir)
    if team_games.empty:
        print("No team games on disk; build the datasets first.", file=sys.stderr)
        return 1
    ids = _final_game_ids(team_games)
    failures = 0
    parsed = []
    for number, gid in enumerate(ids, 1):
        payload = None
        if args.fetch:
            try:
                payload = fetch_play_by_play(gid, raw_dir=args.raw_dir).payload
            except NhlApiError as exc:
                failures += 1
                print(f"Play-by-play {gid}: {exc}", file=sys.stderr)
        else:
            payload = _read_cache(_cache_root(args.raw_dir) / "play_by_play" / f"{gid}.json")
        if payload is not None and game_is_final(payload):
            goals = periods.period_goals(payload)
            if goals is not None:
                parsed.append(goals)
        if number % 500 == 0:
            print(f"Play-by-play: {number} of {len(ids)} games")
    if not parsed:
        print("No play-by-play on disk; run with --fetch.", file=sys.stderr)
        return 1
    table = pd.DataFrame([g.row() for g in parsed])
    validation = periods.validate_against_boxscores(team_games, table)
    fetch_rate = failures / len(ids) if ids else 0.0
    if validation["games"] == 0 or validation["match"] < MINIMUM_MATCH or fetch_rate > MAXIMUM_FETCH_FAILURES:
        print(
            f"::error::Period goals rebuild the boxscore in {validation['match']:.1%} of "
            f"{validation['games']} games (floor {MINIMUM_MATCH:.0%}); {failures} of {len(ids)} "
            "fetches failed. Not measured.",
        )
        return 2
    args.processed_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.processed_dir / PERIOD_TABLE, index=False)

    xg_path = args.processed_dir / SHADOW_TEAM_TABLE
    xg_metrics = pd.read_csv(xg_path) if xg_path.is_file() else None
    scored = periods.walk_forward(team_games, table, xg_metrics=xg_metrics)
    summary = periods.summarise(scored)

    merged = table.merge(
        team_games[["game_id", "home_goals", "away_goals"]].assign(
            game_id=lambda f: pd.to_numeric(f["game_id"], errors="coerce")
        ).dropna(),
        on="game_id",
        how="inner",
    )
    last_fit = periods.fit_period_shares(merged) if not merged.empty else None
    league = []
    for p in periods.PERIODS:
        league.append({
            "period": p,
            "home_rate": float(table[f"home_p{p}"].mean()),
            "away_rate": float(table[f"away_p{p}"].mean()),
            "home_share": last_fit.shares[("home", p)] if last_fit else None,
            "away_share": last_fit.shares[("away", p)] if last_fit else None,
            "tied": float((table[f"home_p{p}"] == table[f"away_p{p}"]).mean()),
        })
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "games_listed": int(len(ids)),
        "games_read": int(len(table)),
        "fetch_failures": failures,
        "unattributed": int(table["unattributed"].sum()),
        "validation": validation,
        "games_scored": int(scored["game_id"].nunique()) if not scored.empty else 0,
        "models": {k: v for k, v in periods.MODEL_LABELS.items() if k == "baseline" or k in set(scored.get("model", []))},
        "tie_rule": "h2h_pN is two-way and a tied period is a push (void); h2h_3_way_pN carries the draw.",
        "league_periods": league,
        "summary": summary,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "period_markets.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (args.output_dir / "period_markets.md").write_text(render(payload), encoding="utf-8")
    print(
        f"Period markets: {payload['games_read']} of {len(ids)} games read, "
        f"{payload['games_scored']} scored walk-forward, boxscore match {validation['match']:.1%}."
    )
    return 0 if summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
