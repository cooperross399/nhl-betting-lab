"""A cached client for the official NHL API at `api-web.nhle.com`.

Public, keyless, no quota. Everything the models are fitted on comes from
here, and every response is written to `data/raw/nhl/` before it is parsed.

**Caching is a correctness rule, not an optimisation.** A completed game's
boxscore never changes, so it is fetched once and never again. Refetching
would make the dataset silently depend on when it was built, which is exactly
the kind of dependency that turns an unreproducible number into an argument.

The rule has one exception and it is explicit: a schedule day, or a boxscore
for a game that is not final, is *incomplete evidence*. Those are cached too,
but `is_final` is recorded alongside so a later run knows to fetch again. A
cache that cannot tell "finished" from "in progress" would freeze a game at
the second period forever.

Nothing here needs a credential, so nothing here can leak one.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

from nhl_betting_lab.config import RAW_DIR


API_BASE_URL = "https://api-web.nhle.com"
STATS_BASE_URL = "https://api.nhle.com/stats/rest/en"

#: Game states the API uses for a game whose result is settled. `OFF` is the
#: usual terminal state; `FINAL` appears briefly between the final horn and
#: the official close.
FINAL_GAME_STATES = frozenset({"OFF", "FINAL"})

#: HTTP statuses worth retrying. 429 is the NHL API asking for a slower pace,
#: and a cold cache makes about four thousand requests — enough to earn one.
#: The first workflow run to fetch from scratch was rate-limited into
#: near-total failure and the reports downstream simply had less data, with
#: nothing saying so.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

#: Attempts per request, including the first. Backoff doubles each time.
MAX_ATTEMPTS = 4

#: Seconds before the first retry. Deliberately generous: being asked to slow
#: down and then retrying immediately is how a client earns a longer ban.
INITIAL_BACKOFF_SECONDS = 2.0

#: Team abbreviation shape. Used to refuse a path segment that could escape
#: the cache directory or the API's own routing.
TEAM_PATTERN = re.compile(r"^[A-Z]{3}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

Requester = Callable[..., Any]


class NhlApiError(RuntimeError):
    """The NHL API could not answer, or answered with something unusable."""


def _default_requester(url: str, **kwargs: Any) -> Any:
    return requests.get(url, **kwargs)


@dataclass(frozen=True)
class CacheEntry:
    """One cached response and how it got there."""

    path: Path
    payload: Any
    from_cache: bool
    #: True when the payload is settled evidence that will never change.
    complete: bool


def _cache_root(raw_dir: Path | None = None) -> Path:
    return (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / "nhl"


def _read_cache(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        # A truncated cache file is worse than no cache file: it makes the
        # dataset silently short. Treat it as a miss and refetch.
        return None


def _write_cache(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # Atomic: a run interrupted mid-write must not leave half a boxscore that
    # a later run trusts.
    temporary.replace(path)


def _get_json(
    url: str,
    *,
    requester: Requester,
    params: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
    sleeper: Callable[[float], None] | None = None,
) -> Any:
    """Fetch and parse, retrying the statuses that mean "try again".

    A cold cache makes about four thousand requests, which is enough to earn a
    429. Without a retry the fetch simply returns less data and every report
    downstream is quietly thinner, with nothing saying so — which is the same
    silent-shortfall failure this repository keeps finding.
    """
    # Resolved at call time rather than bound as a default, so a test that
    # patches `time.sleep` is actually obeyed. A default argument captures the
    # function at import and silently ignores the patch, which is how a suite
    # ends up spending half a minute asleep.
    wait = sleeper if sleeper is not None else time.sleep
    delay = INITIAL_BACKOFF_SECONDS
    last: str = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requester(url, params=params or {}, timeout=timeout_seconds)
        except (requests.RequestException, OSError, TimeoutError) as exc:
            last = f"The NHL API could not be reached ({type(exc).__name__})."
            if attempt == MAX_ATTEMPTS:
                raise NhlApiError(last) from exc
            wait(delay)
            delay *= 2
            continue
        status = int(getattr(response, "status_code", 0) or 0)
        if status == 200:
            try:
                return response.json()
            except (AttributeError, TypeError, ValueError) as exc:
                raise NhlApiError("The NHL API returned unreadable JSON.") from exc
        last = f"The NHL API returned HTTP {status or 'unknown'}."
        if status not in RETRYABLE_STATUSES or attempt == MAX_ATTEMPTS:
            raise NhlApiError(last)
        wait(delay)
        delay *= 2
    raise NhlApiError(last or "The NHL API could not be reached.")


def game_is_final(payload: Any) -> bool:
    """Whether a boxscore payload describes a settled result."""
    if not isinstance(payload, dict):
        return False
    return str(payload.get("gameState", "")).strip().upper() in FINAL_GAME_STATES


def fetch_boxscore(
    game_id: int,
    *,
    requester: Requester | None = None,
    raw_dir: Path | None = None,
    refresh: bool = False,
) -> CacheEntry:
    """One game's boxscore, from cache when the result is already settled."""
    identifier = int(game_id)
    if identifier <= 0:
        raise NhlApiError(f"{game_id!r} is not a usable NHL game id.")
    path = _cache_root(raw_dir) / "boxscore" / f"{identifier}.json"

    if not refresh:
        cached = _read_cache(path)
        if cached is not None and game_is_final(cached):
            return CacheEntry(
                path=path, payload=cached, from_cache=True, complete=True
            )

    payload = _get_json(
        f"{API_BASE_URL}/v1/gamecenter/{identifier}/boxscore", requester=requester or _default_requester
    )
    complete = game_is_final(payload)
    _write_cache(path, payload)
    return CacheEntry(path=path, payload=payload, from_cache=False, complete=complete)


def fetch_schedule_day(
    day: date | str,
    *,
    requester: Requester | None = None,
    raw_dir: Path | None = None,
    refresh: bool = False,
) -> CacheEntry:
    """The schedule week anchored on `day`.

    The endpoint answers with a whole `gameWeek`, not a single day. That is the
    provider's shape and it is kept: trimming it here would throw away six days
    of free evidence and make a season build seven times as many requests.
    """
    text = day.isoformat() if isinstance(day, date) else str(day).strip()
    if not DATE_PATTERN.fullmatch(text):
        raise NhlApiError(f"{day!r} is not an ISO date (YYYY-MM-DD).")
    path = _cache_root(raw_dir) / "schedule" / f"{text}.json"

    if not refresh:
        cached = _read_cache(path)
        if cached is not None:
            # A schedule is never "settled": times move and games are added.
            # It is cached so a rebuild is cheap, never so a refresh is
            # skipped when one was asked for.
            return CacheEntry(
                path=path, payload=cached, from_cache=True, complete=False
            )

    payload = _get_json(
        f"{API_BASE_URL}/v1/schedule/{text}", requester=requester or _default_requester
    )
    _write_cache(path, payload)
    return CacheEntry(path=path, payload=payload, from_cache=False, complete=False)


def fetch_club_season_schedule(
    team: str,
    season_id: int,
    *,
    requester: Requester | None = None,
    raw_dir: Path | None = None,
    refresh: bool = False,
) -> CacheEntry:
    """Every game one club plays in one season, scheduled or completed."""
    abbrev = str(team).strip().upper()
    if not TEAM_PATTERN.fullmatch(abbrev):
        raise NhlApiError(f"{team!r} is not a three-letter NHL team abbreviation.")
    season = int(season_id)
    if len(str(season)) != 8:
        raise NhlApiError(f"{season_id!r} is not an eight-digit NHL season id.")
    path = _cache_root(raw_dir) / "club_schedule" / f"{abbrev}_{season}.json"

    if not refresh:
        cached = _read_cache(path)
        if cached is not None:
            return CacheEntry(
                path=path, payload=cached, from_cache=True, complete=False
            )

    payload = _get_json(
        f"{API_BASE_URL}/v1/club-schedule-season/{abbrev}/{season}",
        requester=requester or _default_requester,
    )
    _write_cache(path, payload)
    return CacheEntry(path=path, payload=payload, from_cache=False, complete=False)


def fetch_club_roster(
    team: str,
    season_id: int,
    *,
    requester: Requester | None = None,
    raw_dir: Path | None = None,
    refresh: bool = False,
) -> CacheEntry:
    """Who is on one club's roster right now.

    The models learn a player's *rates* from his game logs, which is right:
    shooting travels with the player. They also read his *team* from the last
    game in those logs, which is right during a season and wrong every
    October — a summer of trades and free agency leaves every mover pointing
    at the club he left. The card needs the team only to decide which side of
    tonight's game he is on, so it asks the roster instead of the history.

    Fetched fresh rather than served from cache when asked to refresh:
    rosters change on waiver claims and call-ups, and a cached one is a
    guess about today.
    """
    abbrev = str(team).strip().upper()
    if not TEAM_PATTERN.fullmatch(abbrev):
        raise NhlApiError(f"{team!r} is not a three-letter NHL team abbreviation.")
    season = int(season_id)
    if len(str(season)) != 8:
        raise NhlApiError(f"{season_id!r} is not an eight-digit NHL season id.")
    path = _cache_root(raw_dir) / "roster" / f"{abbrev}_{season}.json"

    if not refresh:
        cached = _read_cache(path)
        if cached is not None:
            return CacheEntry(
                path=path, payload=cached, from_cache=True, complete=False
            )

    payload = _get_json(
        f"{API_BASE_URL}/v1/roster/{abbrev}/{season}",
        requester=requester or _default_requester,
    )
    _write_cache(path, payload)
    return CacheEntry(path=path, payload=payload, from_cache=False, complete=False)


#: The roster payload's player groups.
ROSTER_GROUPS = ("forwards", "defensemen", "goalies")


def current_rosters(
    season_id: int | None = None, *, raw_dir: Path | None = None
) -> dict[int, str]:
    """{player id: team} from the cached rosters, newest season cached.

    Empty when nothing is cached, and every caller treats empty as "fall back
    to the logs" rather than "nobody is on a team" — a missing roster must
    never be able to unresolve a player who would otherwise price.
    """
    directory = _cache_root(raw_dir) / "roster"
    if not directory.is_dir():
        return {}
    files = sorted(directory.glob("*.json"))
    if season_id is not None:
        files = [path for path in files if path.stem.endswith(str(int(season_id)))]
    elif files:
        newest = max(path.stem.rsplit("_", 1)[-1] for path in files)
        files = [path for path in files if path.stem.endswith(newest)]
    rosters: dict[int, str] = {}
    for path in files:
        team = path.stem.split("_", 1)[0].upper()
        payload = _read_cache(path)
        if not isinstance(payload, dict):
            continue
        for group in ROSTER_GROUPS:
            for player in payload.get(group) or []:
                if not isinstance(player, dict):
                    continue
                try:
                    player_id = int(player.get("id"))
                except (TypeError, ValueError):
                    continue
                rosters[player_id] = team
    return rosters


def fetch_player_registry(
    season_id: int,
    *,
    requester: Requester | None = None,
    raw_dir: Path | None = None,
    refresh: bool = False,
) -> CacheEntry:
    """`playerId` -> full name, for one season, from the stats API.

    The boxscore abbreviates first names (`"S. Noesen"`); the odds provider
    spells them out (`"Stefan Noesen"`). Joining prop prices to results needs
    the full form, and this is the only thing the stats API is used for.

    It is deliberately not a model input: its per-player endpoints return
    season-to-date totals with no as-of date, so feeding them to a walk-forward
    fit would leak the rest of the season into a game being priced. Names
    cannot leak anything.
    """
    season = int(season_id)
    if len(str(season)) != 8:
        raise NhlApiError(f"{season_id!r} is not an eight-digit NHL season id.")
    path = _cache_root(raw_dir) / "registry" / f"{season}.json"

    if not refresh:
        cached = _read_cache(path)
        if cached is not None:
            return CacheEntry(
                path=path, payload=cached, from_cache=True, complete=False
            )

    request = requester or _default_requester
    combined: dict[str, list[Any]] = {"skaters": [], "goalies": []}
    for role, endpoint, name_field in (
        ("skaters", "skater/summary", "skaterFullName"),
        ("goalies", "goalie/summary", "goalieFullName"),
    ):
        start = 0
        while True:
            payload = _get_json(
                f"{STATS_BASE_URL}/{endpoint}",
                requester=request,
                params={
                    "limit": "100",
                    "start": str(start),
                    "cayenneExp": f"seasonId={season}",
                },
            )
            rows = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                player_id = row.get("playerId")
                full_name = str(row.get(name_field, "")).strip()
                if player_id is None or not full_name:
                    continue
                combined[role].append(
                    {
                        "playerId": int(player_id),
                        "fullName": full_name,
                        "positionCode": str(row.get("positionCode", "")).strip()
                        or ("G" if role == "goalies" else ""),
                        "teamAbbrevs": str(row.get("teamAbbrevs", "")).strip(),
                    }
                )
            if len(rows) < 100:
                break
            start += 100
            if start > 5000:  # a season has ~1,000 players; this is a runaway guard
                break

    payload = {
        "seasonId": season,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **combined,
    }
    _write_cache(path, payload)
    return CacheEntry(path=path, payload=payload, from_cache=False, complete=False)


def cached_boxscore_ids(raw_dir: Path | None = None) -> list[int]:
    """Every game id already on disk, so a rebuild needs no network at all."""
    directory = _cache_root(raw_dir) / "boxscore"
    if not directory.is_dir():
        return []
    ids: list[int] = []
    for path in directory.glob("*.json"):
        try:
            ids.append(int(path.stem))
        except ValueError:
            continue
    return sorted(ids)
