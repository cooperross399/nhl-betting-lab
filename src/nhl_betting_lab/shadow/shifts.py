"""Fetch and read the NHL shift charts: who was on the ice, second by second.

`api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={id}` is the same
free, keyless API the lab already reads. It lists every shift of every player
(period, start and end in elapsed period time) and, mixed in, one row per goal
(`typeCode` 505). The play-by-play says what happened and the shift chart says
who was there, which is what the defensive half of a player rating needs
(PostHockey's Net Rating takes its defence from on-ice goals and xG against).

What it cannot give, stated so nobody infers otherwise:

* **A change at the moment of a shot is ambiguous.** A shift is read as
  covering the seconds after its start up to and including its end, so a shot
  at the second of a change is charged to the players coming off. Over a
  season this is a fraction of a percent of attempts.
* **A game whose chart is empty is not final yet, or was never charted.** It
  is not cached, and it is asked again on a later run.

Caching follows `play_by_play.fetch_play_by_play`: only a chart with shifts in
it is written, and a written chart is never fetched again. The caller passes
only final games.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nhl_betting_lab.data.nhl_api import (
    STATS_BASE_URL,
    CacheEntry,
    NhlApiError,
    Requester,
    _cache_root,
    _default_requester,
    _get_json,
    _read_cache,
    _write_cache,
)

#: The row type of a shift; goals are 505 and are not shifts.
SHIFT_TYPE = 517

#: Where a game's chart is cached, under `data/raw/nhl`.
CACHE_DIRNAME = "shift_charts"


def cache_path(game_id: int, raw_dir: Path | None = None) -> Path:
    return _cache_root(raw_dir) / CACHE_DIRNAME / f"{int(game_id)}.json"


def is_charted(payload: Any) -> bool:
    """Whether a payload holds at least one shift."""
    if not isinstance(payload, Mapping):
        return False
    return any(_is_shift(row) for row in payload.get("data") or [])


def fetch_shift_chart(
    game_id: int,
    *,
    requester: Requester | None = None,
    raw_dir: Path | None = None,
) -> CacheEntry:
    """One final game's shift chart, from cache once it has been charted."""
    identifier = int(game_id)
    if identifier <= 0:
        raise NhlApiError(f"{game_id!r} is not a usable NHL game id.")
    path = cache_path(identifier, raw_dir)
    cached = _read_cache(path)
    if cached is not None and is_charted(cached):
        return CacheEntry(path=path, payload=cached, from_cache=True, complete=True)
    payload = _get_json(
        f"{STATS_BASE_URL}/shiftcharts?cayenneExp=gameId={identifier}",
        requester=requester or _default_requester,
    )
    complete = is_charted(payload)
    if complete:
        _write_cache(path, payload)
    return CacheEntry(path=path, payload=payload, from_cache=False, complete=complete)


def _clock(value: object) -> int | None:
    try:
        minutes, seconds = str(value).split(":")
        return int(minutes) * 60 + int(seconds)
    except (TypeError, ValueError):
        return None


def _is_shift(row: object) -> bool:
    if not isinstance(row, Mapping):
        return False
    kind = row.get("typeCode")
    if kind is not None:
        try:
            return int(kind) == SHIFT_TYPE
        except (TypeError, ValueError):
            return False
    return not row.get("eventDescription")


def shifts(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every shift as {player_id, team, period, start, end}, seconds into the period.

    A row without a player, a team, a period or a readable start and end, or
    one that ends before it starts, is dropped. The shootout (period 5 of a
    regular-season game) is not hockey at any strength and is dropped too.
    """
    out: list[dict[str, Any]] = []
    for row in (payload or {}).get("data") or []:
        if not _is_shift(row):
            continue
        try:
            player = int(row.get("playerId"))
            period = int(row.get("period"))
        except (TypeError, ValueError):
            continue
        team = str(row.get("teamAbbrev") or "").strip().upper()
        start, end = _clock(row.get("startTime")), _clock(row.get("endTime"))
        if not team or start is None or end is None or end <= start or period < 1:
            continue
        game = str(row.get("gameId") or "")
        if period >= 5 and game[4:6] == "02":
            continue
        out.append({"player_id": player, "team": team, "period": period, "start": start, "end": end})
    return out
