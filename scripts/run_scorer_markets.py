#!/usr/bin/env python3
"""First and last goal scorer as a shadow model, measured walk-forward.

    PYTHONPATH=src .venv/bin/python scripts/run_scorer_markets.py --fetch

Reads `team_games.csv` and `player_game_logs.csv` and the NHL play-by-play
for every final game (the goal order the boxscore does not carry), then
scores each regular-season game's realised first and last scorer, "no
scorer" included, against three baselines on the same games, refitting every
14 days on earlier games only. Writes `data/outputs/scorer_markets.md` and
`.json` (`nhl_betting_lab.new_markets.scorers`).

`--fetch` downloads play-by-play not yet cached (free, keyless, the same
cache `run_shadow_stats.py` uses). Without it only cached games are read and
nothing touches the network. It never fetches odds and spends no credit.
Nothing here is read by the card or the forward ledger.

Exit codes: 0 measured; 1 nothing to measure (no datasets, no play-by-play,
or no game past the minimum history); 2 the play-by-play goals disagree with
the boxscores too often, or too many fetches failed, to trust.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.data.nhl_api import NhlApiError, game_is_final
from nhl_betting_lab.new_markets import scorers

#: Below this share of exact boxscore matches the parse is suspect.
MINIMUM_MATCH = 0.95
#: Above this share of failed fetches the coverage is suspect.
MAXIMUM_FETCH_FAILURES = 0.02

LABELS = {
    "uniform": "Same team shares, every dressed skater equal",
    "position": "Same team shares, split by forward/defence league rate",
    "naive": "Coin-flip team share, every dressed skater equal",
}


def _fmt(cell: dict) -> str:
    return f"{cell['per_1000']:+.1f} [{cell['low']:+.1f}, {cell['high']:+.1f}]"


def render(payload: dict) -> str:
    v = payload["validation"]
    s = payload["summary"]
    lines = [
        "# First and last goal scorer: a shadow model, measured on outcomes",
        "",
        "Built beside the card, never on it (`nhl_betting_lab.new_markets.scorers`). "
        "These are forecasting comparisons on outcomes, walk-forward: they can rule "
        "the model out and never in. Only a price backtest against bought "
        "`player_goal_scorer_first` / `player_goal_scorer_last` prices could, and "
        "none has been run; reaching the card also needs Cooper's sign-off.",
        "",
        "## Settlement assumed",
        "",
        "- First scorer: the first goal of the game, overtime included; shootout goals never count.",
        "- Last scorer: the last goal of the game, overtime included, shootout excluded; empty-net goals count.",
        "- A player who does not dress is void. No goal in regulation or overtime: every player loses and "
        "\"no goalscorer\" wins.",
        "- These are typical US-book rules, assumed here, not any book's published terms.",
        "",
        "## Data",
        "",
        f"- Final games listed: {payload['games_listed']:,}; play-by-play read for "
        f"{payload['games_read']:,}; fetch failures: {payload['fetch_failures']:,}.",
        f"- Goals per side against the boxscore (shootout winner allowed for): "
        f"{100 * v['match']:.1f}% of {v['games']:,} games match exactly.",
        f"- Walk-forward windows scored: {s['windows']}, refitting every "
        f"{payload['refit_days']} days, each needing {payload['minimum_history']} "
        "earlier games with play-by-play.",
        f"- Skater weights from the props model: {s['skater_weights'] - s['fallback_weights']:,} of "
        f"{s['skater_weights']:,}; the rest took a position rate times trailing ice time.",
        "- Not scored: " + ", ".join(f"{k.replace('_', ' ')} {n:,}" for k, n in s["skipped"].items()) + ".",
        "",
    ]
    for market, entry in s["markets"].items():
        lines += [
            f"## {market.capitalize()} scorer",
            "",
            f"Game-markets scored: {entry['games']:,} over {entry['dates']:,} dates. "
            f"No-scorer games: {entry['no_scorer_games']:,} observed against "
            f"{entry['predicted_no_scorer']:.1f} predicted.",
            "",
            "Log loss per game (lower is better): "
            + ", ".join(f"{k} {val:.4f}" for k, val in entry["log_loss"].items())
            + ".",
            "",
            "Model minus baseline, log-likelihood per 1,000 games, 95% interval "
            "clustered on the date. Positive is better; an interval that includes "
            "zero is no demonstrated difference.",
            "",
            "| Against | Games | Difference | Verdict |",
            "|:--|--:|--:|:--|",
        ]
        for name, cell in entry["against"].items():
            lines.append(f"| {LABELS[name]} | {cell['games']:,} | {_fmt(cell)} | {cell['verdict']} |")
        team = entry["team"]
        lines += [
            f"| Which side scores it (home / away / none) against a coin flip | "
            f"{team['difference']['games']:,} | {_fmt(team['difference'])} | {team['difference']['verdict']} |",
            "",
            "Calibration of each dressed skater's probability (95% interval clustered on the game):",
            "",
            "| Bucket | Player-games | Games | Predicted | Observed | 95% interval | Inside |",
            "|:--|--:|--:|--:|--:|:--|:--|",
        ]
        for c in entry["calibration"]:
            lines.append(
                f"| {c['bucket']} | {c['player_games']:,} | {c['games']:,} | {100 * c['predicted']:.2f}% | "
                f"{100 * c['observed']:.2f}% | {100 * c['low']:.2f}% .. {100 * c['high']:.2f}% | "
                f"{'yes' if c['inside'] else 'no'} |"
            )
        lines.append("")
    if not s["markets"]:
        lines += ["No game was scored.", ""]
    lines += [
        "## What this cannot say",
        "",
        "- Nothing about prices. A better log-likelihood is the precondition for a price "
        "backtest, not a claim of edge; books price these markets with heavy margins.",
        "- The candidates are the skaters who dressed, known at warm-ups, not when a morning "
        "card is built.",
        "- Team strength is the card's goals `TeamModel`, not the xG ratings, because this "
        "package may not import the shadow stats. Back-to-backs are not applied.",
        "- Empty-net last goals go to the side that leads after regulation, at a share fitted "
        "on earlier games, and are split inside the team like any goal: who is on the ice "
        "late is not modelled.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fetch", action="store_true", help="Fetch play-by-play not yet cached (free).")
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR)
    parser.add_argument("--refit-days", type=int, default=scorers.REFIT_DAYS)
    parser.add_argument("--minimum-history", type=int, default=scorers.MINIMUM_HISTORY_GAMES)
    args = parser.parse_args(argv)

    team_games = load_team_games(args.processed_dir)
    logs = load_player_logs(args.processed_dir)
    if team_games.empty or logs.empty:
        print("No team games or player logs on disk; build the datasets first.", file=sys.stderr)
        return 1
    final = team_games.dropna(subset=["home_goals", "away_goals"])
    ids = sorted({int(g) for g in pd.to_numeric(final["game_id"], errors="coerce").dropna() if int(g) > 0})
    failures = 0
    orders: dict[int, scorers.GoalOrder] = {}
    for number, gid in enumerate(ids, 1):
        payload = None
        if args.fetch:
            try:
                payload = scorers.fetch_play_by_play(gid, raw_dir=args.raw_dir).payload
            except NhlApiError as exc:
                failures += 1
                print(f"Play-by-play {gid}: {exc}", file=sys.stderr)
        else:
            payload = scorers.read_cached_play_by_play(gid, args.raw_dir)
        if isinstance(payload, dict) and game_is_final(payload):
            orders[gid] = scorers.parse_goal_order(payload)
        if number % 500 == 0:
            print(f"Play-by-play: {number} of {len(ids)} games")
    if not orders:
        print("No play-by-play on disk; run with --fetch.", file=sys.stderr)
        return 1

    validation = scorers.validate_against_boxscores(final, orders)
    result = scorers.measure(
        team_games, logs, orders, refit_days=args.refit_days, minimum_history=args.minimum_history
    )
    summary = scorers.summarise(result)
    payload = {
        "games_listed": len(ids),
        "games_read": len(orders),
        "fetch_failures": failures,
        "validation": validation,
        "refit_days": args.refit_days,
        "minimum_history": args.minimum_history,
        "summary": summary,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "scorer_markets.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    report = render(payload)
    (args.output_dir / "scorer_markets.md").write_text(report, encoding="utf-8")
    print(report)

    code = 0
    if failures > MAXIMUM_FETCH_FAILURES * max(len(ids), 1):
        print(f"::error::{failures} of {len(ids)} play-by-play fetches failed.")
        code = 2
    if validation["games"] and validation["match"] < MINIMUM_MATCH:
        print(
            "::error::The play-by-play goals disagree with the boxscores in "
            f"{100 * (1 - validation['match']):.1f}% of games; the goal order is suspect."
        )
        code = 2
    if code == 0 and not summary["markets"]:
        print("No game was past the minimum history; nothing was measured.", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
