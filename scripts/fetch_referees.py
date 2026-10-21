#!/usr/bin/env python3
"""Record who referees tonight, and who refereed the games already played.

    PYTHONPATH=src .venv/bin/python scripts/fetch_referees.py

Free (the NHL's right-rail), and soft in Gameday Refresh: the card reads what
is here and moves nothing for a game with no crew or a referee with no
history (`nhl_betting_lab.referees`). Past games are added newest first, at
most `--budget` a run, appended as they arrive, so a run cut short keeps what
it read and the next run carries on. Exit 0 unless the schedule could not be
read at all.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from nhl_betting_lab import referees as rf
from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_team_games
from nhl_betting_lab.data.nhl_api import API_BASE_URL, _default_requester, _get_json
from nhl_betting_lab.season import LEAGUE_TIMEZONE, game_date

REGULAR_SEASON = "2"
FLUSH_EVERY = 25


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--budget", type=int, default=300)
    parser.add_argument("--polite-seconds", type=float, default=0.2)
    args = parser.parse_args(argv)
    processed = Path(args.processed_dir)

    def fetch(path: str):
        return _get_json(f"{API_BASE_URL}{path}", requester=_default_requester)

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(LEAGUE_TIMEZONE).date().isoformat()

    # Tonight's crews first: they are what the card reads today.
    status = 0
    try:
        schedule = fetch("/v1/schedule/now")
    except Exception as exc:  # the public API, on a bad day
        print(f"::warning::Could not read the schedule: {exc}", file=sys.stderr)
        schedule, status = {}, 2
    tonight = []
    for week in schedule.get("gameWeek") or []:
        for game in week.get("games") or []:
            if game_date(str(game.get("startTimeUTC", ""))) != today:
                continue
            game_id = str(game.get("id") or "")
            if not game_id:
                continue
            try:
                names = rf.referees_of(fetch(f"/v1/gamecenter/{game_id}/right-rail"))
            except Exception as exc:
                print(f"Game {game_id}: no crew read ({exc}).", file=sys.stderr)
                continue
            tonight.append({
                "date": today, "game_id": game_id,
                "home_team": (game.get("homeTeam") or {}).get("abbrev", ""),
                "away_team": (game.get("awayTeam") or {}).get("abbrev", ""),
                "referees": json.dumps(names), "retrieved_at": retrieved_at,
            })
            time.sleep(args.polite_seconds)
    rf.append_rows(processed / rf.TONIGHT_DIRNAME / f"{today}.csv", tonight, rf.TONIGHT_COLUMNS)
    posted = sum(1 for row in tonight if row["referees"] != "[]")
    print(f"Tonight ({today}): crews posted for {posted} of {len(tonight)} game(s) read.")

    # Then the games already played that the history lacks, newest first.
    games = load_team_games(processed)
    history = rf.load_history(processed)
    have = set(history["game_id"].astype(str))
    if games.empty:
        print("No team games on disk; no referee history added.")
        return status
    played = games[games["game_type"].astype(str) == REGULAR_SEASON]
    played = played[~played["game_id"].astype(str).isin(have)].sort_values("date", ascending=False)
    todo = played.head(max(0, args.budget))
    path = processed / rf.HISTORY_FILENAME
    batch, added, lost = [], 0, 0
    for row in todo.itertuples():
        try:
            names = rf.referees_of(fetch(f"/v1/gamecenter/{row.game_id}/right-rail"))
        except Exception:
            lost += 1
            continue
        if names:
            batch.append({
                "game_id": str(row.game_id), "date": str(row.date)[:10],
                "home_team": row.home_team, "away_team": row.away_team,
                "referees": json.dumps(names),
            })
        if len(batch) >= FLUSH_EVERY:
            added += rf.append_rows(path, batch, rf.HISTORY_COLUMNS)
            batch = []
        time.sleep(args.polite_seconds)
    added += rf.append_rows(path, batch, rf.HISTORY_COLUMNS)
    print(
        f"Referee history: {added} game(s) added ({lost} could not be read); "
        f"{len(have) + added} held, {max(0, len(played) - len(todo))} still to add."
    )
    print("This spent no provider credits.")
    return status


if __name__ == "__main__":
    # Line-buffered, so a step cut off by its timeout still shows what it read.
    sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())
