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
