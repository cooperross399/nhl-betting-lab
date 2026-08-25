#!/usr/bin/env python3
"""Fetch NHL schedules, boxscores and the player-name registry into the cache.

Public API, no credential, no quota. Safe to run repeatedly: a game that is
already final is never refetched, so a second run over the same window costs
almost nothing and produces exactly the same dataset.

    PYTHONPATH=src .venv/bin/python scripts/fetch_nhl_data.py
    PYTHONPATH=src .venv/bin/python scripts/fetch_nhl_data.py --seasons 20242025
    PYTHONPATH=src .venv/bin/python scripts/fetch_nhl_data.py --from 2026-10-07 --to 2026-10-14

This fetches results only. It fetches no odds, spends no credits, places no
bet, and writes nothing outside `data/raw/nhl/`.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta, timezone

from nhl_betting_lab.config import DEFAULT_SEASONS, REGULAR_SEASON_GAME_TYPE
from nhl_betting_lab.data.nhl_api import (
    NhlApiError,
    fetch_boxscore,
    fetch_club_season_schedule,
    fetch_player_registry,
    fetch_schedule_day,
)


#: Every current NHL club. Hardcoded because the API has no "list all teams"
#: endpoint that is stable across seasons, and a missing club would silently
#: shrink the dataset rather than fail.
TEAMS = (
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET",
    "EDM", "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT",
    "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK",
    "WPG", "WSH",
)


def _game_ids_for_season(season_id: int, *, polite_seconds: float) -> set[int]:
    ids: set[int] = set()
    for team in TEAMS:
        try:
            entry = fetch_club_season_schedule(team, season_id)
        except NhlApiError as exc:
            print(f"  {team}: {exc}", file=sys.stderr)
            continue
        if not entry.from_cache:
            time.sleep(polite_seconds)
        payload = entry.payload
        games = payload.get("games", []) if isinstance(payload, dict) else []
        for game in games:
            if not isinstance(game, dict):
                continue
            if int(game.get("gameType", 0) or 0) != REGULAR_SEASON_GAME_TYPE:
                continue
            game_id = game.get("id")
            if game_id:
                ids.add(int(game_id))
    return ids


def _game_ids_for_dates(start: date, end: date, *, polite_seconds: float) -> set[int]:
    ids: set[int] = set()
    cursor = start
    while cursor <= end:
        try:
            entry = fetch_schedule_day(cursor, refresh=True)
        except NhlApiError as exc:
            print(f"  {cursor}: {exc}", file=sys.stderr)
            cursor += timedelta(days=7)
            continue
        time.sleep(polite_seconds)
        payload = entry.payload
        week = payload.get("gameWeek", []) if isinstance(payload, dict) else []
        for day in week:
            if not isinstance(day, dict):
                continue
            for game in day.get("games", []) or []:
                if not isinstance(game, dict):
                    continue
                if int(game.get("gameType", 0) or 0) != REGULAR_SEASON_GAME_TYPE:
                    continue
                game_id = game.get("id")
                if game_id:
                    ids.add(int(game_id))
        # The endpoint answers with a whole week, so step a week at a time.
        cursor += timedelta(days=7)
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        nargs="*",
        type=int,
        default=None,
        help="Season ids, e.g. 20242025. Defaults to the configured history.",
    )
    parser.add_argument("--from", dest="start", default="", help="ISO start date.")
    parser.add_argument("--to", dest="end", default="", help="ISO end date.")
    parser.add_argument(
        "--skip-registry",
        action="store_true",
        help="Do not refresh the playerId to full-name registry.",
    )
    parser.add_argument(
        "--polite-seconds",
        type=float,
        default=0.25,
        help=(
            "Pause between live requests. The API is free and it rate-limits: "
            "a cold cache is about four thousand requests, and 0.05 earned an "
            "HTTP 429 that thinned every report downstream with nothing "
            "saying so."
        ),
    )
    parser.add_argument(
        "--max-games",
        type=int,
        default=0,
        help="Stop after this many new boxscore fetches. 0 means no limit.",
    )
    args = parser.parse_args(argv)

    seasons = args.seasons if args.seasons else list(DEFAULT_SEASONS)

    ids: set[int] = set()
    if args.start or args.end:
        if not (args.start and args.end):
            parser.error("--from and --to must be given together.")
        try:
            start = date.fromisoformat(args.start)
            end = date.fromisoformat(args.end)
        except ValueError:
            parser.error("--from and --to must be ISO dates (YYYY-MM-DD).")
        print(f"Schedule window {start} .. {end}")
        ids |= _game_ids_for_dates(start, end, polite_seconds=args.polite_seconds)
    else:
        for season in seasons:
            print(f"Season {season}: reading club schedules")
            ids |= _game_ids_for_season(season, polite_seconds=args.polite_seconds)

    print(f"{len(ids)} regular-season game ids in scope.")

    if not args.skip_registry:
        for season in seasons:
            try:
                entry = fetch_player_registry(season)
            except NhlApiError as exc:
                print(f"Registry {season}: {exc}", file=sys.stderr)
                continue
            payload = entry.payload
            count = len(payload.get("skaters", [])) + len(payload.get("goalies", []))
            source = "cache" if entry.from_cache else "fetched"
            print(f"Registry {season}: {count} players ({source}).")

    fetched = 0
    cached = 0
    unfinished = 0
    failures = 0
    for game_id in sorted(ids):
        if args.max_games and fetched >= args.max_games:
            print(f"Stopping at --max-games {args.max_games}.")
            break
        try:
            entry = fetch_boxscore(game_id)
        except NhlApiError as exc:
            failures += 1
            print(f"  {game_id}: {exc}", file=sys.stderr)
            continue
        if entry.from_cache:
            cached += 1
            continue
        fetched += 1
        if not entry.complete:
            unfinished += 1
        time.sleep(args.polite_seconds)

    print(
        f"Boxscores: {cached} already cached, {fetched} fetched "
        f"({unfinished} not yet final), {failures} failed."
    )
    print(
        "Fetched results only. No odds were requested, no credit was spent, "
        "and no bet was placed."
    )
    print(f"Finished at {datetime.now(timezone.utc).isoformat(timespec='seconds')}.")
    return 1 if failures and not (cached or fetched) else 0


if __name__ == "__main__":
    raise SystemExit(main())
