"""The card's preseason screen, as a filter over the provider's posted events.

The provider does not flag preseason, and from late September books post
lines for exhibition games beside regular-season ones. `run_gameday_card.py`
drops every price row for a game the cached regular-season schedule does not
know, but only after a per-event fetch has spent its credit cap front-to-back
in face-off order, and an exhibition usually faces off first. So every
script that spends a per-event cap screens the board by the card's rule
BEFORE the cap is applied (`fetch_player_props(keep_event=...)`):

* `run_provider_shadow.py` (#242): an exhibition took one of the eight places
  Gameday Refresh's 320 credits buy, and every per-event market for the
  regular-season game it displaced read "priced for k of N": INCOMPLETE,
  excluded, and absent from the frozen snapshot;
* `capture_line_movement.py`: an exhibition took one of the fifteen places
  Line Movement's 600 credits buy, and a regular-season game skipped for the
  budget lost that round's movement and its closing price, which no source
  keeps an archive of.

One screen, in one place, so the two cannot drift apart from each other or
from the card. It is the card's rule: the same reader
(`known_regular_season_games`), the same (league date, HOME, AWAY) key, and
the same failure direction. A leaked exhibition costs one place under a cap
and the card still drops it; a real game screened out is a game nobody
prices. So it abstains, screening nothing and saying so, whenever it cannot
tell the two apart:

* no club-schedule cache at all;
* a cache that lacks some club's own file for this season, because a hole
  and an exhibition look identical to it;
* a team-name map that resolves nothing from any cache. The map always
  carries the built-in aliases (`build_team_name_map`), so with no boxscores
  and no saved `team_names.csv` it still holds six entries and resolves no
  posted game to both its clubs; a screen that ran on it would drop the
  whole board as "not regular season". Line Movement's runner holds neither,
  which is why the map also reads the clubs' names from the club schedules
  themselves (below).

And past the last date the cache knows, it keeps the game.

`known_regular_season_games` is read, and not
`scheduled_regular_season_starts`, because it is the function the card's
screen reads: whatever it decides about a game (a called-off one included),
the two screens read one function and so decide alike. A game screened here
and kept by the card would leave its bulk rows in the card's slate with no
per-event rows beside them.

The team-name map is the card's (`saved_team_name_map` under
`build_team_name_map`), with one addition laid underneath it: the
`placeName` and `commonName` every club-schedule game carries for both
clubs, composed exactly as the boxscore map composes them. It only fills
spellings the card's map lacks, so where the card resolves a name this
resolves it the same way, and where only the schedule resolves one the
screen may keep a game the card then drops as unrecognisable, which is the
leak direction, never the loss one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from nhl_betting_lab.providers.odds_api import EventScreen
from nhl_betting_lab.providers.team_names import (
    build_team_name_map,
    cache_derived_spellings,
    normalize_team_name,
    resolve_team,
    saved_team_name_map,
)
from nhl_betting_lab.season import (
    EXPECTED_CLUBS,
    game_date,
    known_regular_season_games,
    schedule_cache_is_complete,
    season_id,
)


def schedule_team_names(raw_dir: Path | None = None) -> dict[str, str]:
    """`normalized full name` -> abbreviation, from the cached club schedules.

    Composed as `build_team_name_map` composes a boxscore's clubs, place then
    common name, with the common name alone added only where no other club
    has claimed it. A game whose side carries no names adds nothing, so a
    cache without them yields `{}` and the screen falls back to abstaining.
    """
    from nhl_betting_lab.config import RAW_DIR

    directory = (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / "nhl" / (
        "club_schedule"
    )
    mapping: dict[str, str] = {}
    if not directory.is_dir():
        return mapping
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        games = payload.get("games", []) if isinstance(payload, dict) else []
        for game in games or []:
            if not isinstance(game, Mapping):
                continue
            for side in ("homeTeam", "awayTeam"):
                team = game.get(side)
                if not isinstance(team, Mapping):
                    continue
                abbrev = str(team.get("abbrev", "")).strip().upper()
                place = (team.get("placeName") or {}).get("default", "")
                common = (team.get("commonName") or {}).get("default", "")
                if not abbrev or not place or not common:
                    continue
                mapping.setdefault(normalize_team_name(f"{place} {common}"), abbrev)
                key = normalize_team_name(common)
                if key and key not in mapping:
                    mapping[key] = abbrev
    return mapping


def preseason_screen(
    today: str,
    *,
    raw_dir: Path | None = None,
    processed_dir: Path | None = None,
) -> tuple[EventScreen | None, str]:
    """The screen for the posted events of `today`'s season, and a line
    saying what it will do. The screen is None when it must abstain.

    `today` is a league date (`YYYY-MM-DD`, America/New_York), which picks
    the season whose completeness is judged. `raw_dir` and `processed_dir`
    default to the lab's own, as the card's do.
    """
    schedule = known_regular_season_games(raw_dir)
    if not schedule:
        return None, (
            "No regular-season schedule is cached, so nothing was screened "
            "for preseason: the per-event cap is spent in plain face-off "
            "order, and an exhibition game on the board can take a place a "
            "regular-season game needed."
        )
    complete, clubs = schedule_cache_is_complete(raw_dir, season=season_id(today))
    if not complete:
        return None, (
            f"WARNING: the club-schedule cache holds this season's own "
            f"schedule for only {clubs} of {EXPECTED_CLUBS} clubs, so "
            "nothing was screened for preseason — a hole in the cache and "
            "an exhibition game look identical, and the card abstains on "
            "the same cache. The per-event cap is spent in plain face-off "
            "order."
        )
    card_map = {
        **saved_team_name_map(processed_dir=processed_dir),
        **build_team_name_map(raw_dir),
    }
    team_names = {**schedule_team_names(raw_dir), **card_map}
    if not cache_derived_spellings(team_names):
        return None, (
            "WARNING: the team-name map holds only the built-in aliases (no "
            "boxscore cache, no saved team_names.csv, and no club names in "
            "the cached schedules), so no posted game could be matched to "
            "the schedule and nothing was screened for preseason. The "
            "per-event cap is spent in plain face-off order."
        )
    known_until = max(day for day, _, _ in schedule)

    def keep(event: Mapping) -> bool:
        day = game_date(event.get("commence_time"))
        if day > known_until:
            return True  # abstain: the cache cannot judge this date
        return (
            day,
            resolve_team(event.get("home_team", ""), team_names) or "",
            resolve_team(event.get("away_team", ""), team_names) or "",
        ) in schedule

    return keep, (
        "Preseason screen: posted events the cached regular-season schedule "
        f"does not know (through {known_until}) are dropped before any cap "
        "is applied, by the card's own rule."
    )
