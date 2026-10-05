#!/usr/bin/env python3
"""Build the modern-stats shadow model and measure it against the card's.

    PYTHONPATH=src .venv/bin/python scripts/run_shadow_stats.py --fetch

`--fetch` downloads the NHL play-by-play for every final game in
`team_games.csv` that is not already cached (free, keyless; a cold cache is
about four thousand requests). Without it, only cached games are read.

Writes the per-game tables to `data/processed/shadow_*.csv` and the report to
`data/outputs/shadow_stats.md` and `.json`. Nothing here is read by the card
or the forward ledger (`nhl_betting_lab.shadow`). Spends no odds credits.

Exit codes: 0 measured; 1 nothing to measure; 2 measured, but the
play-by-play disagrees with the boxscores too often, or too many fetches
failed, to trust it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.data.nhl_api import NhlApiError, _cache_root, _read_cache, game_is_final
from nhl_betting_lab.shadow import measurement
from nhl_betting_lab.shadow.metrics import build_tables
from nhl_betting_lab.shadow.play_by_play import fetch_play_by_play, game_events
from nhl_betting_lab.shadow.xg import add_expected_goals

#: Below this share of exact boxscore matches the parse is suspect.
MINIMUM_MATCH = 0.95
#: Above this share of failed fetches the coverage is suspect.
MAXIMUM_FETCH_FAILURES = 0.02


def _final_game_ids(team_games: pd.DataFrame) -> list[int]:
    frame = team_games.dropna(subset=["home_goals", "away_goals"])
    return sorted({int(g) for g in frame["game_id"] if int(g) > 0})


def _fmt(cell: dict) -> str:
    return f"{cell['per_1000']:+.2f} [{cell['low']:+.2f}, {cell['high']:+.2f}]"


def render(payload: dict, table: pd.DataFrame, goalies: pd.DataFrame, shooters: pd.DataFrame) -> str:
    v = payload["validation"]
    lines = [
        "# Shadow model: modern stats against the card's model",
        "",
        "Built beside the card, never on it. The card's model is frozen until "
        "2027-04-25 (`docs/when_this_ends.md`), and nothing in "
        "`nhl_betting_lab.shadow` can reach the card or the forward ledger.",
        "",
        "**Read this first.** These are forecasting comparisons on outcomes, "
        "walk-forward. A stat that forecasts worse is ruled out. A stat that "
        "forecasts better has earned a price backtest, nothing more: the market "
        "already sees most of what these stats see, and only a price backtest "
        "decides (`CLAUDE.md`).",
        "",
        "## Data",
        "",
        f"- Games in `team_games.csv`: {payload['games_listed']}; play-by-play read for "
        f"{payload['games_read']}; fetch failures: {payload['fetch_failures']}.",
        f"- Shot attempts parsed: {payload['attempts']:,}; attempts whose shooting team "
        f"could not be told, and so dropped: {payload['unattributed']:,}.",
        f"- Check against the boxscore, {v['games']:,} games: shots on goal match exactly "
        f"in {100 * v['shots_match']:.1f}%, goals in {100 * v['goals_match']:.1f}%.",
        "",
        "Expected goals, each season fitted only on earlier seasons:",
        "",
        "| Season | Fitted on | Unblocked attempts | Goals | xG | Out of sample |",
        "|:--|:--|--:|--:|--:|:--|",
    ]
    for s in payload["xg_seasons"]:
        lines.append(
            f"| {s['season']} | {', '.join(map(str, s['fitted_on']))} | {s['attempts']:,} | "
            f"{s['goals']:,} | {s['expected']:,.0f} | {'no (not compared)' if s['in_sample'] else 'yes'} |"
        )
    lines += [
        "",
        "## Team strength: rated on each stat instead of goals",
        "",
        "Difference in log-likelihood per 1,000 games against the card's goals-based "
        "`TeamModel`, same structure, same games, same back-to-back adjustment. "
        "Positive is better. 95% intervals resample whole dates.",
        "",
        f"Games compared: {payload['team_games_scored']:,}.",
        "",
        "| Rated on | Goals scored | Moneyline | Total 5.5 | Verdict (moneyline) |",
        "|:--|--:|--:|--:|:--|",
    ]
    for e in payload["team"]:
        lines.append(
            f"| {e['label']} | {_fmt(e['goals_ll'])} | {_fmt(e['moneyline_ll'])} | "
            f"{_fmt(e['total_ll'])} | {e['moneyline_ll']['verdict']} |"
        )
    lines += [
        "",
        "## Prop rates: shot attempts and ixG instead of box-score counts",
        "",
        "Difference in Poisson log-likelihood per 1,000 player-games against the "
        "card's construction (shrunk box-score rate per 60 times trailing-10 ice "
        "time). Positive is better.",
        "",
        "| Market | Rate built on | Player-games | Difference | Verdict |",
        "|:--|:--|--:|--:|:--|",
    ]
    for stat, entries in payload["props"].items():
        for e in entries:
            lines.append(
                f"| {stat} | {e['label']} | {e['rows']:,} | {_fmt(e['ll'])} | {e['ll']['verdict']} |"
            )
    lines += ["", "## What it says", ""]
    lines += [f"- {s}" for s in payload["findings"]]
    if not table.empty:
        lines += [
            "",
            f"## {table.attrs.get('season', '')} team table",
            "",
            "All situations unless named. PDO is 5v5 on-ice shooting plus save "
            "percentage; GSAx is the team's goalies, empty nets excluded; "
            "high danger is within 25 ft and 45 degrees of the net (an "
            "approximation of the inner slot).",
            "",
            table.to_markdown(),
        ]
    if not goalies.empty:
        lines += ["", "## Goals saved above expected, latest season (min. 20 games)", "", goalies.to_markdown(index=False)]
    if not shooters.empty:
        lines += ["", "## Individual expected goals per 60, latest season (min. 500 minutes)", "", shooters.to_markdown(index=False)]
    lines += [
        "",
        "## Not built, and why",
        "",
        "- WAR, GAR, xGAR, RAPM: Evolving-Hockey, paid.",
        "- Zone entries, exits, forecheck and passing microstats: All Three Zones, paid.",
        "- MoneyPuck's xG, flurry adjustment and deserve-to-win: licence required.",
        "- NHL EDGE skating and shot speed: no per-game archive to fit on game by game.",
        "- Confirmed-starter GSAx: the card runs before starters are confirmed, so "
        "goaltending here is the team's goalies together.",
        "- Score-adjusted 5v5 and a separate 5v5-plus-special-teams scoreline: not "
        "built yet; all-situations xG already carries the power play.",
    ]
    return "\n".join(lines) + "\n"


def findings(team: list[dict], props: dict[str, list[dict]]) -> list[str]:
    out: list[str] = []
    better = [e["label"] for e in team if e["moneyline_ll"]["verdict"].startswith("better")]
    worse = [e["label"] for e in team if e["moneyline_ll"]["verdict"].startswith("worse")]
    out.append(
        "Team strength on the moneyline: "
        + (f"better than goals for {', '.join(better)}. " if better else "no stat beat goals. ")
        + (f"Worse for {', '.join(worse)}." if worse else "")
    )
    for stat, entries in props.items():
        wins = [e["label"] for e in entries if e["ll"]["verdict"].startswith("better")]
        out.append(
            f"{stat}: " + (f"better than the box-score rate with {', '.join(wins)}." if wins
                           else "no shadow rate beat the box-score rate.")
        )
    out.append(
        "Anything better here is a candidate for a price backtest, and any change "
        "to the card waits for 2027-04-25 and Cooper's decision."
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
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
    events = []
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
            events.append(game_events(payload))
        if number % 500 == 0:
            print(f"Play-by-play: {number} of {len(ids)} games")
    shots = pd.DataFrame([s for e in events for s in e.shots])
    if shots.empty:
        print("No play-by-play on disk; run with --fetch.", file=sys.stderr)
        return 1
    scored, seasons = add_expected_goals(shots)
    team_table, player_table, goalie_table = build_tables(events, scored)
    args.processed_dir.mkdir(parents=True, exist_ok=True)
    team_table.to_csv(args.processed_dir / "shadow_team_games.csv", index=False)
    player_table.to_csv(args.processed_dir / "shadow_player_games.csv", index=False)
    goalie_table.to_csv(args.processed_dir / "shadow_goalie_games.csv", index=False)

    out_of_sample = {s.season for s in seasons if not s.in_sample}
    validation = measurement.validate_against_boxscores(team_games, team_table)
    team_rows, team_summary = measurement.compare_team_models(
        team_games, team_table, scored_seasons=out_of_sample
    )
    logs = load_player_logs(args.processed_dir)
    _, prop_summary = measurement.compare_prop_rates(
        logs,
        player_table,
        scored_seasons=out_of_sample,
        covered_games={e.game_id for e in events},
    )

    names = (
        logs.drop_duplicates("player_id", keep="last").set_index("player_id")["player"].to_dict()
        if not logs.empty
        else {}
    )
    latest = int(team_table["season"].max())
    regular = lambda f: f[f["game_id"].astype(str).str[4:6] == "02"]  # noqa: E731
    g = regular(goalie_table[goalie_table["season"] == latest])
    g = g.groupby("goalie_id").agg(GP=("game_id", "nunique"), xGA=("xga", "sum"), GA=("ga", "sum"))
    g = g[g["GP"] >= 20]
    g["GSAx"] = g["xGA"] - g["GA"]
    g.insert(0, "Goalie", [names.get(i, str(i)) for i in g.index])
    goalies = pd.concat([g.nlargest(5, "GSAx"), g.nsmallest(5, "GSAx")]).round(1)
    toi = regular(logs[pd.to_numeric(logs["season"], errors="coerce") == latest]) if not logs.empty else logs
    p = regular(player_table[player_table["season"] == latest]).groupby("player_id")[["ixg", "igoals", "icf"]].sum()
    if not toi.empty:
        p = p.join(toi.groupby("player_id")["toi_seconds"].sum(), how="inner")
        p = p[p["toi_seconds"] >= 500 * 60]
        p["ixG/60"] = p["ixg"] / p["toi_seconds"] * 3600
        p["iCF/60"] = p["icf"] / p["toi_seconds"] * 3600
        p.insert(0, "Player", [names.get(i, str(i)) for i in p.index])
        shooters = p.nlargest(10, "ixG/60")[["Player", "ixg", "igoals", "ixG/60", "iCF/60"]].round(2)
    else:
        shooters = pd.DataFrame()

    payload = {
        "games_listed": len(ids),
        "games_read": len(events),
        "fetch_failures": failures,
        "attempts": int(len(shots)),
        "unattributed": int(sum(e.unattributed for e in events)),
        "validation": validation,
        "xg_seasons": [s.__dict__ for s in seasons],
        "team_games_scored": int(team_rows["game_id"].nunique()) if not team_rows.empty else 0,
        "team": team_summary,
        "props": prop_summary,
        "findings": findings(team_summary, prop_summary),
    }
    table = measurement.latest_season_table(team_table)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "shadow_stats.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    report = render(payload, table, goalies, shooters)
    (args.output_dir / "shadow_stats.md").write_text(report, encoding="utf-8")
    print(report)

    if failures > MAXIMUM_FETCH_FAILURES * max(len(ids), 1):
        print(f"::error::{failures} of {len(ids)} play-by-play fetches failed.")
        return 2
    if validation["games"] and min(validation["shots_match"], validation["goals_match"]) < MINIMUM_MATCH:
        print(
            "::error::The play-by-play disagrees with the boxscores too often "
            f"(shots {validation['shots_match']:.1%}, goals {validation['goals_match']:.1%}); "
            "the parse is suspect and the comparison should not be trusted."
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
