"""Exhibition games never spend the per-event cap a regular-season game needed.

The provider does not flag preseason, and on a mixed night books post lines
for both. The preseason screen ran only in the card (`run_gameday_card.py`),
AFTER `run_provider_shadow.py` had spent the per-event cap front-to-back in
start-time order: at Gameday Refresh's 320 credits (19 markets x 2 regions =
38 an event) the cap buys 8 events, and on 2026-09-29, a night with
exhibitions and regular-season games on the board, an early exhibition took
a slot a regular-season game needed. The card then dropped the exhibitions,
as it should, and every per-event market for the displaced real games read
"priced for k of N": INCOMPLETE, excluded. The run stayed clean, and the
frozen snapshot and the forward ledger lost those props without a word.

So the shadow run screens the posted events by the card's own rule BEFORE
either fetch sorts and caps them: a game the cached regular-season schedule
does not know is not asked about, and the run says how many it dropped. The
rule's failure direction is the card's too. With a club-schedule cache that
is incomplete for the season, or absent, nothing is screened (a hole and an
exhibition game look identical), and past the last date the cache knows the
screen abstains.

Every request goes to a stub transport. Nothing reaches the network, and no
credit is spent.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult
from nhl_betting_lab.providers.team_names import (
    TEAM_NAMES_FILENAME,
    normalize_team_name,
)
from test_no_test_reads_the_checkouts_data import CLUBS, point_default_data_dirs_at


#: Never a real credential, and never sent anywhere: the transport is a stub.
ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}

#: 10:00 in New York on the mixed night, before any of its games.
NOW = datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc)
TONIGHT = "2026-09-29"

#: Four exhibition games, all face-off before any regular-season game.
EXHIBITIONS = (("MTL", "TOR"), ("OTT", "BUF"), ("DET", "CHI"), ("NJD", "NYI"))
#: Eight regular-season games: exactly what a 320-credit cap buys.
REGULAR = (
    ("WPG", "COL"), ("WSH", "PIT"), ("ANA", "EDM"), ("BOS", "FLA"),
    ("CAR", "TBL"), ("DAL", "STL"), ("VGK", "SEA"), ("LAK", "SJS"),
)
EXHIBITION_IDS = [f"exh{index}" for index in range(len(EXHIBITIONS))]
REGULAR_IDS = [f"reg{index}" for index in range(len(REGULAR))]

#: Gameday Refresh's own flags.
GAMEDAY_REFRESH_FLAGS = ["--live", "--props", "--overwrite-staging",
                         "--horizon-days", "1", "--credit-cap", "320"]
#: The market-discovery probe's shape: no window, and an event cap that
#: truncates the bulk fetch too.
MARKET_DISCOVERY_FLAGS = ["--live", "--props", "--overwrite-staging",
                          "--horizon-days", "0", "--max-events", "8",
                          "--credit-cap", "320"]


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def _name(abbrev: str) -> str:
    """The provider's spelling of a club, which only the saved team-name map
    (`_save_team_names`) resolves."""
    return f"Club {abbrev}"


def _save_team_names(processed: Path) -> None:
    """A saved team-name map, as `saved_team_name_map` reads it."""
    processed.mkdir(parents=True, exist_ok=True)
    lines = ["provider_name,abbrev"] + [
        f"{normalize_team_name(_name(club))},{club}" for club in CLUBS
    ]
    (processed / TEAM_NAMES_FILENAME).write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _event(event_id: str, commence: str, home_abbrev: str, away_abbrev: str) -> dict:
    home, away = _name(home_abbrev), _name(away_abbrev)
    return {
        "id": event_id,
        "commence_time": commence,
        "home_team": home,
        "away_team": away,
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": home, "price": -120},
                        {"name": away, "price": 100},
                    ]},
                ],
            }
        ],
    }


def _board() -> list[dict]:
    """The posted board: exhibitions at 22:0xZ, regular games from 23:00Z."""
    board = [
        _event(f"exh{index}", f"{TONIGHT}T22:{index:02d}:00Z", home, away)
        for index, (home, away) in enumerate(EXHIBITIONS)
    ]
    board += [
        _event(f"reg{index}", f"{TONIGHT}T23:{index:02d}:00Z", home, away)
        for index, (home, away) in enumerate(REGULAR)
    ]
    return board


_HEAD = ("id", "commence_time", "home_team", "away_team")


def _requester(board: list[dict]) -> RecordingRequester:
    by_id = {item["id"]: item for item in board}

    def per_event(url: str, **_kwargs) -> FakeResponse:
        event_id = url.split("/events/", 1)[1].split("/", 1)[0]
        item = by_id[event_id]
        return FakeResponse(
            {
                **{key: item[key] for key in _HEAD},
                "bookmakers": [
                    {
                        "key": "draftkings",
                        "title": "DraftKings",
                        "markets": [
                            {"key": "player_shots_on_goal", "outcomes": [
                                {"name": "Over", "description": f"Skater {event_id}",
                                 "price": -115, "point": 2.5},
                                {"name": "Under", "description": f"Skater {event_id}",
                                 "price": -105, "point": 2.5},
                            ]},
                        ],
                    }
                ],
            }
        )

    listing = [{key: item[key] for key in _HEAD} for item in board]
    return RecordingRequester(
        {
            "/events/": per_event,
            "/events": FakeResponse(listing),
            "/odds": FakeResponse(board, headers={"x-requests-remaining": "19000"}),
        }
    )


def _cache_schedule(raw: Path, clubs: tuple[str, ...]) -> None:
    """Club schedules as the NHL API returns them, one file per club in
    `clubs`: tonight's exhibitions as gameType 1, tonight's regular-season
    games as gameType 2, and an October regular-season game for every club,
    so each file holds one and the cache's range runs past tonight."""
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)

    def game(day: str, home: str, away: str, game_type: int) -> dict:
        return {
            "gameType": game_type,
            "gameDate": day,
            "gameScheduleState": "OK",
            "startTimeUTC": f"{day}T23:00:00Z",
            "homeTeam": {"abbrev": home},
            "awayTeam": {"abbrev": away},
        }

    games = [game(TONIGHT, home, away, 1) for home, away in EXHIBITIONS]
    games += [game(TONIGHT, home, away, 2) for home, away in REGULAR]
    for index in range(0, len(CLUBS), 2):
        games.append(game("2026-10-20", CLUBS[index], CLUBS[index + 1], 2))
    for club in clubs:
        own = [
            item for item in games
            if club in (item["homeTeam"]["abbrev"], item["awayTeam"]["abbrev"])
        ]
        (directory / f"{club}_20262027.json").write_text(
            json.dumps({"games": own}), encoding="utf-8"
        )


def _load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_provider_shadow.py"
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _shadow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    clubs: tuple[str, ...] | None = CLUBS,
    flags: list[str] = GAMEDAY_REFRESH_FLAGS,
    board: list[dict] | None = None,
) -> tuple[int, str, RecordingRequester, Path]:
    """The real script with a workflow's flags, over a stub transport, with
    a club-schedule cache holding `clubs`' own files (None: no cache)."""
    dirs = point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    if clubs is not None:
        _cache_schedule(dirs.raw, clubs)
    _save_team_names(dirs.processed)
    requester = _requester(board if board is not None else _board())
    module = _load_script()
    real = odds_api.OddsApiProvider
    monkeypatch.setattr(
        module.odds_api, "OddsApiProvider",
        lambda: real(environment=ENVIRONMENT, requester=requester, regions="us,us2"),
    )
    monkeypatch.setattr(
        module, "load_provider_env",
        lambda: ProviderEnvLoadResult(path=tmp_path / ".env"),
    )
    monkeypatch.setattr(module, "datetime", _Frozen)
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    staging = tmp_path / "staging"
    try:
        code = module.main([
            *flags,
            "--staging-dir", str(staging),
            "--output-dir", str(tmp_path / "outputs"),
        ])
    finally:
        monkeypatch.setattr(sys, "stdout", sys.__stdout__)
    return code, " ".join(out.getvalue().split()), requester, staging


def _bought(requester: RecordingRequester) -> list[str]:
    """The events a per-event request was spent on, in order."""
    return [
        url.split("/events/", 1)[1].split("/", 1)[0]
        for url in requester.urls
        if "/events/" in url
    ]


def _games(path: Path) -> set[tuple[str, str]]:
    """The (HOME, AWAY) abbreviations of every game a staged file prices."""
    frame = pd.read_csv(path)
    return {
        (home.removeprefix("Club "), away.removeprefix("Club "))
        for home, away in zip(frame["home_team"], frame["away_team"])
    }


def test_the_precondition_the_cap_buys_exactly_eight_events() -> None:
    asked = len(odds_api.PER_EVENT_PROVIDER_MARKETS) + len(
        odds_api.ALTERNATE_PROVIDER_MARKETS
    )
    assert 320 // (asked * 2) == len(REGULAR) == 8


def test_on_a_mixed_night_the_cap_buys_the_regular_season_games(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, requester, staging = _shadow(tmp_path, monkeypatch)

    assert code == 0
    # Every one of the eight slots went to a regular-season game, in
    # start-time order. Unscreened, the four exhibitions took the first four.
    assert _bought(requester) == REGULAR_IDS
    assert _games(staging / odds_api.STAGING_PROPS_FILENAME) == set(REGULAR)
    # The bulk fetch is screened by the same rule, so the staged slate is
    # the one the card will judge: no exhibition game in either file.
    assert _games(staging / odds_api.STAGING_PRICES_FILENAME) == set(REGULAR)
    # The run says what it dropped, with the count, and no event was
    # skipped for the budget.
    assert "4 posted event(s) are not on the cached regular-season schedule" in out
    assert "credit cap would have been exceeded" not in out


def test_the_probe_s_event_cap_selects_the_same_games_in_both_fetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--max-events truncates the bulk fetch to the first N by start time.
    Screened on one side only, the bulk's first eight would be the four
    exhibitions and four regular games while the per-event fetch bought
    eight regular games: two different slates in one staging directory."""
    code, _out, requester, staging = _shadow(
        tmp_path, monkeypatch, flags=MARKET_DISCOVERY_FLAGS
    )

    assert code == 0
    assert _bought(requester) == REGULAR_IDS
    assert _games(staging / odds_api.STAGING_PRICES_FILENAME) == set(REGULAR)
    assert _games(staging / odds_api.STAGING_PROPS_FILENAME) == set(REGULAR)


@pytest.mark.parametrize(
    "clubs",
    [CLUBS[:-1], None],
    ids=["31-of-32-clubs-cached", "no-schedule-cached"],
)
def test_an_incomplete_schedule_cache_screens_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clubs
) -> None:
    """A hole in the cache and an exhibition game look identical to the
    screen, so without every club's own file it abstains, as the card does:
    the cap is spent in plain start-time order and the run says why."""
    code, out, requester, staging = _shadow(tmp_path, monkeypatch, clubs=clubs)

    assert code == 0
    assert _bought(requester) == EXHIBITION_IDS + REGULAR_IDS[:4]
    assert _games(staging / odds_api.STAGING_PRICES_FILENAME) == (
        set(EXHIBITIONS) | set(REGULAR)
    )
    assert "not on the cached regular-season schedule" not in out
    assert "nothing was screened for preseason" in out


def test_past_the_last_date_the_cache_knows_the_screen_abstains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The card's rule: a date past the cached schedule is kept, so a stale
    cache leaks an exhibition rather than dropping a real game."""
    late = "2026-11-02"
    board = [
        _event("late0", f"{late}T23:00:00Z", "TOR", "MTL"),
        _event("late1", f"{late}T23:30:00Z", "BOS", "BUF"),
    ]
    code, out, requester, staging = _shadow(
        tmp_path, monkeypatch, board=board,
        flags=["--live", "--props", "--overwrite-staging",
               "--horizon-days", "0", "--credit-cap", "320"],
    )

    assert code == 0
    assert _bought(requester) == ["late0", "late1"]
    assert _games(staging / odds_api.STAGING_PRICES_FILENAME) == {
        ("TOR", "MTL"), ("BOS", "BUF")
    }
    assert "not on the cached regular-season schedule" not in out


def test_the_provider_screens_before_it_sorts_and_caps() -> None:
    """The library hook itself: a screen the caller passes runs before the
    cap is spent, and what it dropped is counted and said."""
    requester = _requester(_board())
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester, regions="us"
    )

    result = provider.fetch_player_props(
        markets=["player_shots_on_goal"],
        credit_cap=2,
        league_days=[TONIGHT],
        keep_event=lambda event: str(event.get("id", "")).startswith("reg"),
    )

    assert _bought(requester) == ["reg0", "reg1"]
    assert result.events_not_regular_season == len(EXHIBITIONS)
    assert any(
        "not on the cached regular-season schedule" in warning
        for warning in result.warnings
    )
