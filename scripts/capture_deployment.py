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

So a night not captured must not look like a captured one. Exit 0 means the
scratch list was read for at least one of tonight's games, or there were no
games; a game that could not be read is named in a `::warning::`. Exit 2 means
the schedule could not be read or no game's list was captured, and the Line
Movement gate turns that run red.
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


def game_info(payload: object) -> dict:
    """The block both scratch lists live in, or ValueError when it is not there.

    This used to read `payload.get("gameInfo") or {}` and `info.get(side) or
    {}`, so a 200 body with no `gameInfo` - `{'message': 'not found'}` in the
    failure-shape audit's replay - wrote, for two games, four rows with no
    player and `scratch_count` 0: exactly the row reserved below for "we
    looked and it was empty". The live endpoint answers a bogus id with a 404
    and has always carried both team blocks, so this is the path a schema
    change would take, and it would take it silently for the whole season. A
    list nobody saw is not an empty list; the game is counted as not captured.
    """
    info = payload.get("gameInfo") if isinstance(payload, dict) else None
    if not isinstance(info, dict):
        raise ValueError("the right-rail answered with no gameInfo block")
    missing = [side for side in ("homeTeam", "awayTeam") if not isinstance(info.get(side), dict)]
    if missing:
        raise ValueError(f"the right-rail's gameInfo has no {' or '.join(missing)} block")
    return info


def rows_for_game(payload: dict, *, game_id: str, captured_at: str) -> list[dict]:
    """Long-form rows: one per scratched player, plus the officials.

    A game with an empty scratch list is recorded as a row with no player, so
    "we looked and it was empty" is distinguishable from "we never looked" —
    which is the whole point of capturing a timestamp. A body without the
    lists raises ValueError (see `game_info`) rather than writing that row.
    """
    info = game_info(payload)
    officials = {
        "referees": [r.get("default", "") for r in (info.get("referees") or [])],
        "linesmen": [r.get("default", "") for r in (info.get("linesmen") or [])],
    }
    rows: list[dict] = []
    for side in ("homeTeam", "awayTeam"):
        team = info[side]
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

    # Every game tonight is either captured or named as lost. This loop used
    # to print a failed fetch and move on, then answer "No deployment rows
    # returned; nothing written." with exit 0 - so in the failure-shape
    # audit's replay two games whose right-rail fetches all failed (HTTP 403,
    # 503 past the retries, or unreachable) exited 0 with no file, and a
    # partial night (one game 429 past the retries) printed "2 game(s)" with
    # one game in the file. The workflow step had no id either, so nothing
    # could have read the exit anyway. Now: no game captured is exit 2, which
    # the Line Movement gate turns red; a partial capture keeps what came back
    # and warns with the games it lost, which is the rule fetch_nhl_data.py
    # and capture_line_combinations.py already follow - one blip is not a red
    # run, a source that answered nothing is.
    rows: list[dict] = []
    captured: list[str] = []
    lost: list[str] = []
    reasons: list[str] = []
    for game in games:
        raw_id = game.get("id")
        game_id = "" if raw_id in (None, "") else str(raw_id)
        if not game_id:
            lost.append("a game with no id")
            reasons.append("a scheduled game had no id")
            continue
        try:
            payload = fetch(f"/v1/gamecenter/{game_id}/right-rail")
            game_rows = rows_for_game(payload, game_id=game_id, captured_at=captured_at)
        except Exception as exc:  # one game's loss must not cost the others
            lost.append(game_id)
            reasons.append(f"game {game_id}: {exc}")
            continue
        rows.extend(game_rows)
        captured.append(game_id)

    if reasons:
        print(
            f"{len(lost)} of {len(games)} game(s) could not be read:", file=sys.stderr
        )
        for line in reasons:
            print(f"  {line}", file=sys.stderr)
    if not captured:
        # Loud, because silence here looks exactly like a quiet night.
        print(
            f"No scratch list was captured for any of {len(games)} game(s) on "
            f"{today}; nothing written.",
            file=sys.stderr,
        )
        return 2

    path = capture_path(today, processed_dir=Path(args.processed_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(
        path, mode="a", header=not path.is_file(), index=False, lineterminator="\n"
    )
    named = int((frame["player"].astype(str) != "").sum())
    if lost:
        print(
            f"::warning::The scratch list was NOT captured for {len(lost)} of "
            f"{len(games)} game(s) this run ({', '.join(lost)}); the rest were "
            "kept. The instant a list became public cannot be collected later."
        )
    print(
        f"{len(captured)} of {len(games)} game(s) captured, {named} scratch "
        f"row(s) at {captured_at} -> {path}"
    )
    print(
        "This capture spent no provider credits, touched no card, and froze "
        "no opinion."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
