#!/usr/bin/env python3
"""Measure the shadow power-play points, faceoffs won and shot-attempt models.

    PYTHONPATH=src .venv/bin/python scripts/run_player_extras.py [--fetch]

Reads the NHL play-by-play for every final game in `team_games.csv` from the
cache `run_shadow_stats.py` shares (`data/raw/nhl/play_by_play`); `--fetch`
downloads what is missing (free and keyless; never odds, never a credit).
Joins each skater to his boxscore line for ice time, checks the parse
against the boxscore's goals, shots on goal and power-play goals, prices
every player-game walk-forward (`nhl_betting_lab.new_markets.player_extras`)
and writes:

* `data/processed/player_extras_counts.csv`, the per player-game counts;
* `data/outputs/player_extras.md` and `.json`, log loss, Brier and
  calibration per market and line against a naive trailing-ten Poisson.

Outcomes only: this can rule a model out and never in. Nothing here is read
by the card or the forward ledger.

Exit codes: 0 measured; 1 nothing to measure (no team games, or no
play-by-play on disk); 2 the play-by-play disagrees with the boxscores too
often, or too many fetches failed, to trust it (the counts are not written,
the report says why).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.data.nhl_api import NhlApiError, game_is_final
from nhl_betting_lab.new_markets.player_extras import (
    MARKETS,
    attach_ice_time,
    build_counts,
    fetch_play_by_play,
    measure,
    read_cached_play_by_play,
    validate,
    walk_forward,
)

COUNTS_FILE = "player_extras_counts.csv"
REPORT_STEM = "player_extras"
#: Below this share of exact boxscore matches the parse is suspect.
MINIMUM_MATCH = 0.95
#: Above this share of failed fetches the coverage is suspect.
MAXIMUM_FETCH_FAILURES = 0.02


def _final_game_ids(team_games: pd.DataFrame) -> list[int]:
    frame = team_games.dropna(subset=["home_goals", "away_goals"])
    ids = pd.to_numeric(frame["game_id"], errors="coerce").dropna().astype(int)
    # Regular season and playoffs; preseason is not priced.
    return sorted({g for g in ids if g > 0 and str(g)[4:6] in {"02", "03"}})


def _pct(value: float) -> str:
    return "n/a" if value != value else f"{value:.1%}"


def _gain(cell: dict) -> str:
    def f(x: float) -> str:
        return "inf" if math.isinf(x) else f"{x * 1000:+.1f}"

    return f"{f(cell['mean'])} [{f(cell['low'])}, {f(cell['high'])}]"


def render(payload: dict) -> str:
    out = [
        "# Shadow player props: power-play points, faceoffs won, shot attempts",
        "",
        f"Generated {payload['generated_at']}. Outcomes only, walk-forward: every "
        "player-game is priced from games strictly before its date. **This can "
        "rule a model out and never in**: nothing here has met a price, and "
        "reaching the card needs a price backtest and Cooper's sign-off. "
        "Nothing on the card's path imports this model.",
        "",
        "## What was read",
        "",
        f"- Games with play-by-play: {payload['games_read']} of "
        f"{payload['games_final']} final games; fetch failures: "
        f"{payload['fetch_failures']}.",
        f"- Player-games counted: {payload['join']['counted_rows']}; joined to a "
        f"boxscore line: {payload['join']['matched_rows']} "
        f"({payload['join']['counted_without_boxscore']} counted with no "
        f"boxscore line, {payload['join']['boxscore_without_count']} boxscore "
        "lines the play-by-play roster does not list).",
        f"- Agreement with the boxscore, per player-game: goals "
        f"{_pct(payload['validation']['goals_match'])}, shots on goal "
        f"{_pct(payload['validation']['shots_on_goal_match'])}, power-play "
        f"goals {_pct(payload['validation']['power_play_goals_match'])}. The "
        "last checks the power-play rule on goals; power-play assists use the "
        "same rule on the same events and have no boxscore to check against.",
        f"- Goals whose strength could not be read: "
        f"{payload['parse']['goals_without_strength']}; events naming a player "
        f"the roster does not list: {payload['parse']['unknown_players']}.",
        "",
        "## Definitions, and one assumption to verify",
        "",
        "- `player_power_play_points` = power-play goals + power-play assists. "
        "A goal is on the power play when the scoring side has more skaters "
        "than the other, an empty net's extra attacker taken off each side.",
        "- `player_faceoffs_won` = faceoffs won, measured on players averaging "
        "5 or more faceoffs taken over their last ten games.",
        "- **`player_shots` is ASSUMED to be shot attempts** (goals + shots on "
        "goal + missed + attempts the opponent blocked). The provider's "
        "definition is not confirmed: before settling anything, compare a "
        "book's posted `player_shots` line with a player's attempts and "
        "unblocked attempts. Both readings are measured below "
        "(`shot_attempts`, `unblocked_attempts`); a posted line near shots on "
        "goal would mean neither.",
        "",
        "## Results",
        "",
        "Gain is naive log loss (or Brier) minus the model's, x1000, so "
        "positive means the model forecast better; 95% intervals are "
        f"clustered on the game. {payload['measurement']['looks']} lines are "
        "measured, and the JSON carries the corrected interval for each. "
        "Probabilities are held inside [0.001, 0.999] for both before a log "
        "loss.",
        "",
    ]
    for name, entry in payload["measurement"].get("markets", {}).items():
        out += [
            f"### `{name}` (provider key `{entry['provider_key']}`)",
            "",
            f"{entry['player_games']} player-games over {entry['games']} games. "
            f"Mean count {entry['mean_count']:.3f}; model mean "
            f"{entry['mean_model']:.3f}; naive mean {entry['mean_naive']:.3f}. "
            f"Variance / model mean = {entry['variance_ratio']:.2f} (1 is "
            f"Poisson); priced as a negative binomial on "
            f"{entry['negative_binomial_share']:.0%} of rows.",
            "",
            "| Line | Player-games | Games | Over observed [95%] | Model | Naive "
            "| Log loss model / naive | Log-loss gain x1000 [95%] | Brier model / "
            "naive | Brier gain x1000 [95%] | Reading |",
            "|---:|---:|---:|:--|---:|---:|:--|:--|:--|:--|:--|",
        ]
        for line in entry["lines"]:
            if "observed" not in line:
                out.append(f"| {line['line']} | 0 | 0 | | | | | | | | too few to read |")
                continue
            out.append(
                f"| {line['line']} | {line['samples']} | {line['games']} | "
                f"{line['observed']:.1%} [{line['observed_low']:.1%}, "
                f"{line['observed_high']:.1%}] | {line['predicted_model']:.1%} | "
                f"{line['predicted_naive']:.1%} | {line['log_loss_model']:.4f} / "
                f"{line['log_loss_naive']:.4f} | {_gain(line['log_loss_gain'])} | "
                f"{line['brier_model']:.4f} / {line['brier_naive']:.4f} | "
                f"{_gain(line['brier_gain'])} | {line['verdict']} |"
            )
        if entry["calibration"]:
            out += [
                "",
                "Calibration, every line pooled (95% interval clustered on the game):",
                "",
                "| Predicted | Samples | Games | Mean predicted | Observed [95%] |",
                "|:--|---:|---:|---:|:--|",
            ]
            for b in entry["calibration"]:
                out.append(
                    f"| {b['bucket']} | {b['samples']} | {b['games']} | "
                    f"{b['predicted']:.1%} | {b['observed']:.1%} [{b['low']:.1%}, "
                    f"{b['high']:.1%}] |"
                )
        out.append("")
    out += [
        "## What this does not say",
        "",
        "A model that forecasts outcomes better than a trailing mean has not "
        "shown it beats a book's price, which already holds far more than a "
        "trailing mean. No market here has price history in this lab, so "
        "every line is **no demonstrated edge** against the market until a "
        "price backtest says otherwise.",
        "",
    ]
    return "\n".join(out)


def _clean(value):
    """JSON-safe: an infinity or NaN becomes null."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fetch", action="store_true", help="Download missing play-by-play (free; no odds).")
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
    payloads = []
    for number, gid in enumerate(ids, 1):
        payload = None
        if args.fetch:
            try:
                payload = fetch_play_by_play(gid, raw_dir=args.raw_dir).payload
            except NhlApiError as exc:
                failures += 1
                print(f"Play-by-play {gid}: {exc}", file=sys.stderr)
        else:
            payload = read_cached_play_by_play(gid, raw_dir=args.raw_dir)
        if payload is not None and game_is_final(payload):
            payloads.append(payload)
        if number % 500 == 0:
            print(f"Play-by-play: {number} of {len(ids)} games")
    counts, parse = build_counts(payloads)
    if counts.empty:
        print("No play-by-play on disk; run with --fetch.", file=sys.stderr)
        return 1
    logs = load_player_logs(args.processed_dir)
    table, join = attach_ice_time(counts, logs)
    checks = validate(table)
    print(
        f"Play-by-play: {parse['games']} games, {join['matched_rows']} player-games "
        f"joined; goals match {_pct(checks['goals_match'])}, shots on goal "
        f"{_pct(checks['shots_on_goal_match'])}, power-play goals "
        f"{_pct(checks['power_play_goals_match'])}; {failures} fetch failure(s)."
    )
    problems = []
    if failures > MAXIMUM_FETCH_FAILURES * max(len(ids), 1):
        problems.append(f"{failures} of {len(ids)} play-by-play fetches failed.")
    for key in ("goals_match", "shots_on_goal_match", "power_play_goals_match"):
        value = checks[key]
        if value == value and value < MINIMUM_MATCH:
            problems.append(f"{key} is {value:.1%}, below {MINIMUM_MATCH:.0%}.")
    if table.empty:
        problems.append("No counted player-game joins a boxscore line.")

    predictions = walk_forward(table) if not table.empty else pd.DataFrame()
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "games_final": len(ids),
        "games_read": parse["games"],
        "fetch_failures": failures,
        "parse": parse,
        "join": join,
        "validation": checks,
        "problems": problems,
        "markets": {m.name: {"provider_key": m.provider_key, "lines": list(m.lines)} for m in MARKETS},
        "measurement": measure(predictions) if not problems else {"looks": 0, "markets": {}},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f"{REPORT_STEM}.json").write_text(
        json.dumps(_clean(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = render(payload)
    if problems:
        report += "\n## Not measured\n\n" + "\n".join(f"- {p}" for p in problems) + "\n"
    (args.output_dir / f"{REPORT_STEM}.md").write_text(report, encoding="utf-8")
    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        return 2
    args.processed_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.processed_dir / COUNTS_FILE, index=False)
    print(f"Wrote {args.output_dir / (REPORT_STEM + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
