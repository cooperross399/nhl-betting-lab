"""What day an NHL game belongs to.

The provider timestamps a game by when the puck drops, in UTC. The NHL
timestamps it by the day it is played. For a North American evening those are
different days — a 19:10 Eastern face-off is 00:10 UTC the following morning —
and roughly three quarters of the schedule is an evening game.

Joining prices to results on the raw UTC date therefore drops most of the
season, and what survives is not a random sample: it is the afternoon games.
Weekend matinees, holiday specials and national-TV windows are a
systematically different set of fixtures from a Tuesday night in Winnipeg.

This module exists so that rule lives in one place. It was fixed once in the
slate sampler and not here, and the second copy quietly discarded 69% of every
price bought.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


#: The NHL's own calendar runs on Eastern time: a game's `gameDate` is the
#: date in America/New_York at face-off, whatever the venue's own timezone.
#: A 22:00 Pacific start in Vancouver is 01:00 Eastern the next day and the
#: NHL still calls it the previous day's game — which is why this is the
#: league's rule rather than the venue's.
LEAGUE_TIMEZONE = ZoneInfo("America/New_York")


def game_date(commence_time: object) -> str:
    """The NHL game date for a provider timestamp, as `YYYY-MM-DD`.

    An unparseable value falls back to its leading ten characters, which is
    the best available guess and is never silently better than the input.
    """
    text = str(commence_time or "").strip()
    if not text:
        return ""
    candidate = text.replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(candidate)
    except ValueError:
        return text[:10]
    if moment.tzinfo is None:
        # No timezone means no conversion is possible, and inventing one would
        # move a third of the schedule by a day.
        return text[:10]
    return moment.astimezone(LEAGUE_TIMEZONE).date().isoformat()


def clean_text(value: object) -> str:
    """A CSV-safe string: NaN, None and whitespace all read as empty.

    `str(x or "")` looks like it does this and does not — float NaN is
    truthy, so an empty CSV cell round-trips to the literal string "nan",
    which then matches nothing, resolves nothing, and renders as a player
    called nan. Three copies of that pattern shipped before this function.
    """
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN without numpy
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def row_game_date(row: object) -> str:
    """The league game date for a price row: commence time, else its date.

    The fallback exists for hand-built frames; real staged rows always carry
    a commence time. `or` cannot express it, because a NaN commence time is
    truthy and `game_date(nan)` is the string "nan" — which made two fixtures
    between the same clubs on different days share one key.
    """
    commence = clean_text(getattr(row, "commence_time", ""))
    return game_date(commence or clean_text(getattr(row, "date", "")))


def known_regular_season_games(raw_dir=None) -> set[tuple[str, str, str]]:
    """(game date, HOME, AWAY) for every regular-season game the cache knows.

    Read from the cached club schedules, which carry the full season —
    including future games — the moment they are fetched. This exists because
    the odds provider does not flag preseason: books post lines for
    exhibition games from late September, the models are fitted on regular
    season only, and `build_datasets` never ingests exhibition results — so
    an unfiltered card would freeze opinions it has no business holding into
    the forward ledger, where they would rot as unsettleable noise for the
    two weeks before opening night.
    """
    import json
    from pathlib import Path

    from nhl_betting_lab.config import RAW_DIR, REGULAR_SEASON_GAME_TYPE

    directory = (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / "nhl" / (
        "club_schedule"
    )
    known: set[tuple[str, str, str]] = set()
    if not directory.is_dir():
        return known
    # Every club's own schedule holds every game it plays, so a complete
    # cache names all thirty-two clubs. An incomplete one is the dangerous
    # shape: it still yields a plausible date range, so a screen that trusts
    # it drops every game whose club file never landed — silently, as
    # "preseason". Callers get the club count and decide; the failure
    # direction has to be theirs, not a set that cannot say how sure it is.
    for path in directory.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        for game in payload.get("games", []) or []:
            if not isinstance(game, dict):
                continue
            if int(game.get("gameType", 0) or 0) != REGULAR_SEASON_GAME_TYPE:
                continue
            day = str(game.get("gameDate", ""))[:10]
            home = str((game.get("homeTeam") or {}).get("abbrev", "")).upper()
            away = str((game.get("awayTeam") or {}).get("abbrev", "")).upper()
            if len(day) == 10 and home and away:
                known.add((day, home, away))
    return known


#: `gameScheduleState` for a game that will be played when the schedule says.
#: Any other stated value (the real cache holds `CNCL`) is a game called off.
SCHEDULED_STATE = "OK"


def scheduled_regular_season_starts(
    raw_dir=None,
) -> dict[tuple[str, str, str], str]:
    """(game date, HOME, AWAY) -> scheduled face-off, for every regular-season
    game the cache says will be played.

    The face-off is the cache's `startTimeUTC`, verbatim ("" when absent);
    the caller decides what an unreadable one means. This is the slate the
    card's eligibility gate is judged against, so it keeps a game unless the
    schedule POSITIVELY calls it off. A called-off game stays in the cache
    under its original date — the real cache holds the 2024-10-07
    exhibition NSH at TBL as `CNCL`, its `gameState` still `FUT` — and a
    regular-season one kept here would read as a game every market failed
    to price, excluding every market for a game nobody will play. A missing
    state is not a called-off game. A game both clubs' files carry is kept
    if either copy says it is on.
    """
    import json
    from pathlib import Path

    from nhl_betting_lab.config import RAW_DIR, REGULAR_SEASON_GAME_TYPE

    directory = (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / "nhl" / (
        "club_schedule"
    )
    starts: dict[tuple[str, str, str], str] = {}
    if not directory.is_dir():
        return starts
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        games = payload.get("games", []) if isinstance(payload, dict) else []
        for game in games or []:
            if not isinstance(game, dict):
                continue
            if int(game.get("gameType", 0) or 0) != REGULAR_SEASON_GAME_TYPE:
                continue
            state = str(game.get("gameScheduleState") or "").strip().upper()
            if state and state != SCHEDULED_STATE:
                continue
            day = str(game.get("gameDate", ""))[:10]
            home = str((game.get("homeTeam") or {}).get("abbrev", "")).upper()
            away = str((game.get("awayTeam") or {}).get("abbrev", "")).upper()
            if len(day) == 10 and home and away:
                starts[(day, home, away)] = str(
                    game.get("startTimeUTC") or ""
                ).strip()
    return starts


#: The number of clubs a complete `club_schedule` cache holds. A cache with
#: fewer has games it simply does not know about, and cannot be used to judge
#: whether a game is preseason.
EXPECTED_CLUBS = 32


def season_id(day: object) -> str:
    """The NHL season a league date belongs to, as the cache names it.

    A season runs from the autumn into the next summer, so a date from July
    onwards belongs to the season starting that year: 2026-10-08 and
    2027-04-10 are both "20262027".
    """
    text = str(day)[:10]
    year, month = int(text[:4]), int(text[5:7])
    start = year if month >= 7 else year - 1
    return f"{start}{start + 1}"


def schedule_cache_is_complete(
    raw_dir=None, *, season: str | None = None
) -> tuple[bool, int]:
    """(is complete, clubs whose own schedule for `season` is cached).

    A partial cache is not a smaller truth. It is the same truth with holes,
    and the holes are indistinguishable from exhibition games to anything
    that only asks "is this fixture in the set?".

    Completeness is counted by OWN files: a club counts only when
    `{ABBR}_{season}.json` is cached, parses, and holds a regular-season game.
    This used to count every club named in any cached game — opponents
    included — and one club's 82-game schedule meets all 31 others, so a
    cache holding a single file read as complete (True, 32), the card's
    partial-cache warning could never fire, and the screen dropped every
    game whose club file had not landed as "preseason". It is also counted
    per season: across seasons the real cache names 33 clubs (ARI and UTA),
    and last season's 32 files say nothing about this one. `season` is the
    slate's (see `season_id`); by default, the newest season cached.
    """
    import json
    import re
    from pathlib import Path

    from nhl_betting_lab.config import RAW_DIR, REGULAR_SEASON_GAME_TYPE

    directory = (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / "nhl" / (
        "club_schedule"
    )
    owners: dict[str, set[str]] = {}
    if directory.is_dir():
        for path in directory.glob("*.json"):
            match = re.fullmatch(r"([A-Z]{2,3})_(\d{8})", path.stem)
            if not match:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            games = payload.get("games", []) if isinstance(payload, dict) else []
            if any(
                isinstance(game, dict)
                and int(game.get("gameType", 0) or 0) == REGULAR_SEASON_GAME_TYPE
                for game in games or []
            ):
                owners.setdefault(match.group(2), set()).add(match.group(1))
    target = season or (max(owners) if owners else "")
    found = len(owners.get(target, set()))
    return found >= EXPECTED_CLUBS, found
