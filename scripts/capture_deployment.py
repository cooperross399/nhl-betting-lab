#!/usr/bin/env python3
"""Capture who is NOT playing, and when that became knowable.

    PYTHONPATH=src .venv/bin/python scripts/capture_deployment.py

The model's remaining loss is one cell: it bets unders on players whose ice
time is about to rise, because it prices them on the minutes they used to
play. `docs/where_the_remaining_error_lives.md` measures that cell at -6.44%
over 5,661 bets and shows an oracle on future ice time is worth about five
points. It also shows that **nothing this lab can currently see predicts the
shift** - not the player's own history, not his teammates' absences as
recorded in past box scores, not his ice-time volatility.

The missing thing is a pre-game statement of who is out. The NHL's own API
publishes one: `gameInfo.{home,away}Team.scratches`, free and inside the
licence this lab already relies on. What is NOT known is **when** it
populates. If the scratch list appears an hour before puck drop it is far too
late for a card built at 09:30, but it is still the ground truth a later card
could use - and whether a later card is worth building is exactly what this
capture exists to answer.

So each run records the deployment picture WITH THE INSTANT IT WAS TAKEN, and
runs on the same schedule as the price capture, so the two are joinable. A
year from now these two questions become answerable and today they are not:

* how long before puck drop does the scratch list become public?
* had the market already moved by then?

It answers nothing on its own, spends no provider credits, touches no card,
and cannot be collected retroactively - a night not captured is gone.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.data.nhl_api import (
    API_BASE_URL,
    _default_requester,
    _get_json,
)
from nhl_betting_lab.season import LEAGUE_TIMEZONE, game_date


DEPLOYMENT_DIRNAME = "deployment"


def capture_path(day: str, *, processed_dir: Path | None = None) -> Path:
    """One file per league game date, appended to through the day."""
    return (processed_dir or PROCESSED_DIR) / DEPLOYMENT_DIRNAME / f"{day}.csv"


def rows_for_game(payload: dict, *, game_id: str, captured_at: str) -> list[dict]:
    """Long-form rows: one per scratched player, plus the officials.

    A game with an empty scratch list is recorded as a row with no player, so
    "we looked and it was empty" is distinguishable from "we never looked" —
    which is the whole point of capturing a timestamp.
    """
    info = payload.get("gameInfo") or {}
    officials = {
        "referees": [r.get("default", "") for r in (info.get("referees") or [])],
        "linesmen": [r.get("default", "") for r in (info.get("linesmen") or [])],
    }
    rows: list[dict] = []
    for side in ("homeTeam", "awayTeam"):
        team = info.get(side) or {}
        coach = ((team.get("headCoach") or {}).get("default", "")) or ""
        scratches = team.get("scratches") or []
        if not scratches:
            rows.append({
                "game_id": game_id, "side": side, "player_id": "",
                "player": "", "head_coach": coach,
                "scratch_count": 0, "captured_at": captured_at,
                "referees": json.dumps(officials["referees"]),
                "linesmen": json.dumps(officials["linesmen"]),
            })
            continue
        for entry in scratches:
            name = " ".join(
                part for part in (
                    (entry.get("firstName") or {}).get("default", ""),
                    (entry.get("lastName") or {}).get("default", ""),
                ) if part
            ).strip()
            rows.append({
                "game_id": game_id, "side": side,
                "player_id": entry.get("id", ""), "player": name,
                "head_coach": coach, "scratch_count": len(scratches),
                "captured_at": captured_at,
                "referees": json.dumps(officials["referees"]),
                "linesmen": json.dumps(officials["linesmen"]),
            })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--polite-seconds", type=float, default=0.3)
    args = parser.parse_args(argv)

    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(LEAGUE_TIMEZONE).date().isoformat()

    def fetch(path: str):
        return _get_json(f"{API_BASE_URL}{path}", requester=_default_requester)

    try:
        schedule = fetch("/v1/schedule/now")
    except Exception as exc:  # the public API, on a bad day
        print(f"Could not read the schedule: {exc}", file=sys.stderr)
        return 2

    games = [
        game
        for week in (schedule.get("gameWeek") or [])
        for game in (week.get("games") or [])
        if game_date(str(game.get("startTimeUTC", ""))) == today
    ]
    if not games:
        print(f"No NHL games on {today}; nothing to capture. Not a fault.")
        return 0

    rows: list[dict] = []
    for game in games:
        game_id = str(game.get("id", ""))
        if not game_id:
            continue
        try:
            payload = fetch(f"/v1/gamecenter/{game_id}/right-rail")
        except Exception as exc:
            print(f"  game {game_id}: {exc}", file=sys.stderr)
            continue
        rows.extend(rows_for_game(payload, game_id=game_id, captured_at=captured_at))

    if not rows:
        print("No deployment rows returned; nothing written.")
        return 0

    path = capture_path(today, processed_dir=Path(args.processed_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(
        path, mode="a", header=not path.is_file(), index=False, lineterminator="\n"
    )
    named = int((frame["player"].astype(str) != "").sum())
    print(
        f"{len(games)} game(s), {named} scratch row(s) at {captured_at} "
        f"-> {path}"
    )
    print(
        "This capture spent no provider credits, touched no card, and froze "
        "no opinion."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
