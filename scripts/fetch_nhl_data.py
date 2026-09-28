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
    fetch_club_roster,
    fetch_club_season_schedule,
    fetch_player_registry,
    fetch_schedule_day,
    schedule_lists_the_season,
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


#: Live requests per source this run: ok, served from cache, failed.
Tally = dict[str, dict[str, int]]


def _count(tally: Tally, source: str, outcome: str) -> None:
    tally.setdefault(source, {"ok": 0, "cached": 0, "failed": 0})[outcome] += 1


def _game_ids_for_season(
    season_id: int, *, polite_seconds: float, tally: Tally
) -> set[int]:
    ids: set[int] = set()
    for team in TEAMS:
        try:
            entry = fetch_club_season_schedule(team, season_id)
        except NhlApiError as exc:
            _count(tally, "club schedules", "failed")
            print(f"  {team}: {exc}", file=sys.stderr)
            continue
        _count(tally, "club schedules", "cached" if entry.from_cache else "ok")
        if not entry.from_cache:
            time.sleep(polite_seconds)
        payload = entry.payload
        if not schedule_lists_the_season(payload):
            # Not cached (`fetch_club_season_schedule`), so the next run asks
            # again. This used to be written and served on every run after,
            # and the club had no games all season.
            print(
                f"  {team}: the NHL API lists no regular-season game for "
                f"{season_id} yet, so nothing was cached; the next run asks again."
            )
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


def _game_ids_for_dates(
    start: date, end: date, *, polite_seconds: float, tally: Tally
) -> set[int]:
    ids: set[int] = set()
    cursor = start
    while cursor <= end:
        try:
            entry = fetch_schedule_day(cursor, refresh=True)
        except NhlApiError as exc:
            _count(tally, "schedule days", "failed")
            print(f"  {cursor}: {exc}", file=sys.stderr)
            cursor += timedelta(days=7)
            continue
        _count(tally, "schedule days", "ok")
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
        "--skip-rosters",
        action="store_true",
        help="Do not refresh club rosters (which decide each player's side).",
    )
    parser.add_argument(
        "--skip-registry",
        action="store_true",
        help=(
            "Do not refresh the playerId to full-name registry. Without this "
            "flag the registry of a season still being played is asked for "
            "again on every run; a closed season's is read from cache."
        ),
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

    tally: Tally = {}
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
        ids |= _game_ids_for_dates(
            start, end, polite_seconds=args.polite_seconds, tally=tally
        )
    else:
        for season in seasons:
            print(f"Season {season}: reading club schedules")
            ids |= _game_ids_for_season(
                season, polite_seconds=args.polite_seconds, tally=tally
            )

    print(f"{len(ids)} regular-season game ids in scope.")

    if not args.skip_rosters:
        # Refreshed every run, never served from cache: the card reads these
        # to decide which side of tonight's game each player is on, and in
        # October the game logs still have every mover on the club he left.
        # Thirty-two free requests to keep opening night from silently
        # dropping every traded player's props.
        season = max(seasons)
        fetched = failed = 0
        for team in TEAMS:
            try:
                fetch_club_roster(team, season, refresh=True)
            except NhlApiError as exc:
                failed += 1
                _count(tally, "rosters", "failed")
                print(f"  roster {team}: {exc}", file=sys.stderr)
                continue
            fetched += 1
            _count(tally, "rosters", "ok")
            time.sleep(args.polite_seconds)
        print(f"Rosters {season}: {fetched} clubs refreshed, {failed} failed.")

    if not args.skip_registry:
        # A season still being played is asked for again on every run; only a
        # closed season's registry is read from cache (`registry_is_settled`).
        # This used to serve whatever was cached, so 2026-27's August answer,
        # which named nobody, stood as the season's registry: "Registry
        # 20262027: 0 players (cache)." on every Gameday Refresh run, and
        # every player new this season would have gone unpriced. A failed
        # refresh is counted, so a stats-API outage makes the run degraded
        # rather than quietly serving stale names.
        for season in seasons:
            try:
                entry = fetch_player_registry(
                    season, polite_seconds=args.polite_seconds
                )
            except NhlApiError as exc:
                _count(tally, "registry", "failed")
                print(f"Registry {season}: {exc}", file=sys.stderr)
                continue
            _count(tally, "registry", "cached" if entry.from_cache else "ok")
            payload = entry.payload
            count = len(payload.get("skaters", [])) + len(payload.get("goalies", []))
            source = "cache" if entry.from_cache else "fetched"
            print(f"Registry {season}: {count} players ({source}).")
            if not count and not entry.from_cache:
                print(
                    f"  The stats API lists nobody for {season} yet, so "
                    "nothing was cached; any names already cached stand, and "
                    "the next run asks again."
                )

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
            _count(tally, "boxscores", "failed")
            print(f"  {game_id}: {exc}", file=sys.stderr)
            continue
        if entry.from_cache:
            cached += 1
            _count(tally, "boxscores", "cached")
            continue
        fetched += 1
        _count(tally, "boxscores", "ok")
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
    return _verdict(tally)


def _verdict(tally: Tally) -> int:
    """1 when a source this run asked for was unreachable, else 0.

    This used to return 1 only when boxscores failed and nothing was cached
    or fetched. With the API down, every schedule request fails, no game id
    is in scope, the boxscore loop never runs, and "failures" stays 0; on a
    restored runner "cached" is in the thousands anyway. So a complete outage
    exited 0, the Fetch results step was green, and Gameday Refresh's
    "Results could not be refreshed" could never be written. A cache hit
    proves nothing about whether the API answered.

    A source is DOWN when it made live requests and none succeeded; that is
    a failed refresh. A source that lost some requests and not all is named
    and warned about, and does not fail the run — one roster blip should
    not turn a run red and summon the backup.
    """
    down = sorted(s for s, c in tally.items() if c["failed"] and not c["ok"])
    partial = sorted(s for s, c in tally.items() if c["failed"] and c["ok"])
    for source, c in sorted(tally.items()):
        print(
            f"Live requests, {source}: {c['ok']} ok, {c['cached']} from cache, "
            f"{c['failed']} failed."
        )
    if partial:
        print(
            "::warning::Some NHL API requests failed ("
            + ", ".join(f"{s}: {tally[s]['failed']}" for s in partial)
            + "); the rest were refreshed."
        )
    if down:
        print(
            "::error::The NHL API could not be reached for "
            f"{', '.join(down)}: every live request failed, so results were "
            "not refreshed. The cached results stand, and this run is "
            "degraded.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
