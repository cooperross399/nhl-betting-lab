"""Line Movement never spends its credit cap on an exhibition game.

#242 screened the shadow run's posted events by the card's preseason rule
before either fetch sorts and caps them. `capture_line_movement.py` was left
out: it called `fetch_player_props` with no screen, so the 600-credit cap
(19 markets x 2 regions = 38 an event, so 15 events) was spent front-to-back
in face-off order over whatever the board held. On 2026-09-29 and 30 and
into early October the board holds exhibition games, which usually face off
before the evening's regular-season games, so a window holding more than
fifteen events skipped a regular-season game for the budget. Its movement
and its closing price were lost, and this source keeps no archive: a round
not captured is gone.

So the capture runs the same screen, from the same place
(`nhl_betting_lab.preseason_screen`), with the same abstentions: no
club-schedule cache, or one missing a club's own file for the season, screens
nothing and says so; a date past the last one the cache knows is kept. One
abstention is new, and it protects this runner in particular. With no
boxscore cache and no saved `team_names.csv` (Line Movement's runner has
neither) the team-name map holds only the built-in aliases, no posted game
resolves to both its clubs, and a screen that ran anyway would drop every
game on the board as "not regular season". It abstains instead. The club
schedules themselves name every club (`placeName` and `commonName`, the
parts the boxscore map is composed from), so a runner that has cached them
can still resolve the board, and Line Movement now caches them for free
before it captures.

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

import pytest
import yaml

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

#: Three exhibition games, all facing off before either regular-season game.
EXHIBITIONS = (("MTL", "TOR"), ("OTT", "BUF"), ("DET", "CHI"))
EXHIBITION_IDS = ["exh0", "exh1", "exh2"]
#: One evening game, and one West-coast 19:00 PT face-off: 02:00Z on the next
#: UTC day, which the league (and the schedule) files under tonight.
REGULAR = (("BOS", "FLA"), ("LAK", "SJS"))
REGULAR_STARTS = (f"{TONIGHT}T23:00:00Z", "2026-09-30T02:00:00Z")
REGULAR_IDS = ["reg0", "reg1"]

#: 19 markets x 2 regions.
PER_EVENT = (
    len(odds_api.PER_EVENT_PROVIDER_MARKETS)
    + len(odds_api.ALTERNATE_PROVIDER_MARKETS)
) * 2
#: What three events cost: exactly the three exhibitions, unscreened.
CAP = 3 * PER_EVENT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def _name(abbrev: str) -> str:
    """The provider's spelling of a club: `Town XXX ClubXXX`, which the saved
    map resolves, and which the schedule's own names compose to."""
    return f"Town {abbrev} Club{abbrev}"


def _event(event_id: str, commence: str, home: str, away: str) -> dict:
    return {
        "id": event_id,
        "commence_time": commence,
        "home_team": _name(home),
        "away_team": _name(away),
    }


def _board() -> list[dict]:
    board = [
        _event(f"exh{index}", f"{TONIGHT}T22:{index:02d}:00Z", home, away)
        for index, (home, away) in enumerate(EXHIBITIONS)
    ]
    board += [
        _event(f"reg{index}", start, home, away)
        for index, ((home, away), start) in enumerate(zip(REGULAR, REGULAR_STARTS))
    ]
    return board


def _requester(board: list[dict]) -> RecordingRequester:
    by_id = {item["id"]: item for item in board}

    def per_event(url: str, **_kwargs) -> FakeResponse:
        event_id = url.split("/events/", 1)[1].split("/", 1)[0]
        item = by_id[event_id]
        return FakeResponse(
            {
                **item,
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

    return RecordingRequester(
        {"/events/": per_event, "/events": FakeResponse(board)}
    )


def _cache_schedule(
    raw: Path, clubs: tuple[str, ...], *, with_names: bool = False
) -> None:
    """Club schedules as the NHL API returns them, one file per club in
    `clubs`: tonight's exhibitions as gameType 1, tonight's regular-season
    games as gameType 2, and an October game for every club so each file
    holds a regular-season game and the cache's range runs past tonight.
    `with_names` carries each club's `placeName` and `commonName`."""
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)

    def club(abbrev: str) -> dict:
        side = {"abbrev": abbrev}
        if with_names:
            side["placeName"] = {"default": f"Town {abbrev}"}
            side["commonName"] = {"default": f"Club{abbrev}"}
        return side

    def game(day: str, home: str, away: str, game_type: int) -> dict:
        return {
            "gameType": game_type,
            "gameDate": day,
            "gameScheduleState": "OK",
            "startTimeUTC": f"{day}T23:00:00Z",
            "homeTeam": club(home),
            "awayTeam": club(away),
        }

    games = [game(TONIGHT, home, away, 1) for home, away in EXHIBITIONS]
    games += [game(TONIGHT, home, away, 2) for home, away in REGULAR]
    for index in range(0, len(CLUBS), 2):
        games.append(game("2026-10-20", CLUBS[index], CLUBS[index + 1], 2))
    for abbrev in clubs:
        own = [
            item for item in games
            if abbrev in (item["homeTeam"]["abbrev"], item["awayTeam"]["abbrev"])
        ]
        (directory / f"{abbrev}_20262027.json").write_text(
            json.dumps({"games": own}), encoding="utf-8"
        )


def _save_team_names(processed: Path) -> None:
    """A saved team-name map, as the card writes it and
    `saved_team_name_map` reads it."""
    processed.mkdir(parents=True, exist_ok=True)
    lines = ["provider_name,abbrev"] + [
        f"{normalize_team_name(_name(abbrev))},{abbrev}" for abbrev in CLUBS
    ]
    (processed / TEAM_NAMES_FILENAME).write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _load(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    clubs: tuple[str, ...] | None = CLUBS,
    saved_map: bool = True,
    schedule_names: bool = False,
    board: list[dict] | None = None,
) -> tuple[int, str, RecordingRequester]:
    """The real capture with the workflow's own flags, over a stub transport,
    with a club-schedule cache holding `clubs`' own files (None: no cache)
    and, when `saved_map`, a saved team-name map in its --processed-dir."""
    dirs = point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    if clubs is not None:
        _cache_schedule(dirs.raw, clubs, with_names=schedule_names)
    processed = tmp_path / "processed"
    if saved_map:
        _save_team_names(processed)
    requester = _requester(board if board is not None else _board())
    module = _load("capture_line_movement.py")
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
    try:
        code = module.main([
            "--live", "--credit-cap", str(CAP), "--processed-dir", str(processed),
        ])
    finally:
        monkeypatch.setattr(sys, "stdout", sys.__stdout__)
    return code, " ".join(out.getvalue().split()), requester


def _bought(requester: RecordingRequester) -> list[str]:
    """The events a per-event request was spent on, in order."""
    return [
        url.split("/events/", 1)[1].split("/", 1)[0]
        for url in requester.urls
        if "/events/" in url
    ]


def test_the_precondition_the_cap_buys_exactly_the_three_exhibitions() -> None:
    assert CAP // PER_EVENT == len(EXHIBITIONS) == 3
    assert CAP // PER_EVENT < len(EXHIBITIONS) + len(REGULAR)


def test_on_a_mixed_night_the_cap_buys_the_regular_season_games(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unscreened, the three exhibitions took every place and both real
    games were skipped for the budget. The West-coast game is kept, which it
    is only when the screen keys on the LEAGUE date: its UTC date is the
    next day."""
    code, out, requester = _capture(tmp_path, monkeypatch)

    assert code == 0, out
    assert _bought(requester) == REGULAR_IDS
    assert "3 posted event(s) are not on the cached regular-season schedule" in out
    assert "credit cap would have been exceeded" not in out
    assert "Preseason screen:" in out


@pytest.mark.parametrize(
    "clubs",
    [CLUBS[:-1], None],
    ids=["31-of-32-clubs-cached", "no-schedule-cached"],
)
def test_an_incomplete_schedule_cache_screens_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clubs
) -> None:
    """A hole in the cache and an exhibition game look identical to the
    screen, so it abstains: the cap is spent in plain face-off order and
    the capture says why."""
    code, out, requester = _capture(tmp_path, monkeypatch, clubs=clubs)

    assert code == 0, out
    assert _bought(requester) == EXHIBITION_IDS
    assert "not on the cached regular-season schedule" not in out
    assert "nothing was screened for preseason" in out


def test_a_map_of_aliases_alone_screens_nothing_rather_than_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Line Movement's runner has no boxscore cache and no saved map. With a
    complete schedule and nothing to resolve the board's names, a screen that
    ran would read every game as unknown and buy nothing at all."""
    code, out, requester = _capture(tmp_path, monkeypatch, saved_map=False)

    assert code == 0, out
    assert _bought(requester) == EXHIBITION_IDS
    assert "not on the cached regular-season schedule" not in out
    assert "nothing was screened for preseason" in out
    assert "team-name map" in out


def test_the_schedule_s_own_club_names_resolve_the_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner as Line Movement leaves it: club schedules cached, no
    boxscores, no saved map. The schedule names every club itself."""
    code, out, requester = _capture(
        tmp_path, monkeypatch, saved_map=False, schedule_names=True
    )

    assert code == 0, out
    assert _bought(requester) == REGULAR_IDS


def test_past_the_last_date_the_cache_knows_the_screen_abstains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale cache leaks an exhibition rather than dropping a real game.
    The capture's window is today's league date; the cache here ends before
    it."""
    late = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(sys.modules[__name__], "NOW", late)
    board = [
        _event("late0", "2026-11-02T23:00:00Z", "TOR", "MTL"),
        _event("late1", "2026-11-02T23:30:00Z", "BOS", "BUF"),
    ]
    code, out, requester = _capture(tmp_path, monkeypatch, board=board)

    assert code == 0, out
    assert _bought(requester) == ["late0", "late1"]
    assert "not on the cached regular-season schedule" not in out


def test_the_shadow_run_and_the_capture_read_one_screen() -> None:
    """One rule in one place: neither script carries its own copy."""
    for name in ("run_provider_shadow.py", "capture_line_movement.py"):
        text = (PROJECT_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "from nhl_betting_lab.preseason_screen import" in text, name
        assert "keep_event=screen" in text, name
        assert "def _preseason_screen" not in text, name


# --------------------------------------------------------------------------
# The runner: Line Movement caches the club schedules, for free, first.
# --------------------------------------------------------------------------

def _steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["capture"]["steps"]


def test_line_movement_caches_the_club_schedules_before_it_spends_a_credit() -> None:
    steps = _steps()
    names = [step.get("name", "") for step in steps]
    fetch = next(
        index for index, step in enumerate(steps)
        if "fetch_nhl_data.py" in step.get("run", "")
    )
    capture = names.index("Capture prices")
    assert fetch < capture
    step = steps[fetch]
    assert "--schedules-only" in step["run"]
    # Free and never fatal: a failed fetch leaves a partial or empty cache,
    # and the screen abstains on that.
    assert step.get("continue-on-error") is True
    assert "NHL_ODDS_API_KEY" not in json.dumps(step)


def test_schedules_only_fetches_this_season_s_club_schedules_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load("fetch_nhl_data.py")
    asked: list[tuple[str, int]] = []

    class _Entry:
        from_cache = False
        payload = {"games": []}

    def schedule(team, season, **_kwargs):
        asked.append((team, season))
        return _Entry()

    def refuse(*_args, **_kwargs):
        raise AssertionError("--schedules-only asked for something else")

    monkeypatch.setattr(module, "fetch_club_season_schedule", schedule)
    for other in ("fetch_boxscore", "fetch_club_roster",
                  "fetch_player_registry", "fetch_schedule_day"):
        monkeypatch.setattr(module, other, refuse)

    assert module.main(["--schedules-only", "--polite-seconds", "0"]) == 0
    assert sorted(team for team, _ in asked) == sorted(module.TEAMS)
    assert {season for _, season in asked} == {max(module.DEFAULT_SEASONS)}
