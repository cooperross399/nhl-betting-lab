"""A club-schedule file that parsed but was not an object stopped the card.

`known_regular_season_games` read every cached `club_schedule/*.json` and
called `payload.get("games")` on whatever parsed. A file holding `null`, `[]`
or a string raised AttributeError out of the reader, and the card calls it on
every run, before anything is frozen, with nothing around it. The two sibling
readers of the same files, `scheduled_regular_season_starts` and
`schedule_cache_is_complete`, and `fetch_nhl_data`'s own reader, already
skipped that shape. `fetch_club_season_schedule` wrote any HTTP 200 body to
the cache as it came.

Found by the failure-shape audit and confirmed by two of three refuters, one
of which noted that #145 hardened the same shape for boxscores. Reproduced on
copies of the real 2026-27 cache and processed tables, on the opening-night
slate (2026-09-29, 5 games): with one TOR file written by the real writer from
a 200 whose body was `null`, `[]` or `"x"`, the card raised AttributeError
and wrote nothing, while the siblings read the same cache as (False, 31)
clubs. The same run with an untouched cache built its card. A cached `[]` or
`"x"` was also served from cache on every later fetch (`from_cache=True`) and
`fetch_nhl_data` never refreshes a club schedule, so on a persistent checkout
the file would have stopped every card until someone deleted it by hand. A
`null` was already a cache miss. 0 of the 128 real cached club schedules had
this shape on 2026-09-25; the API's own "no games" answer is an object with
an empty `games` list.

What these tests hold:

* the reader skips a file that is not an object, as it skips an unreadable
  one, and keeps every game the other clubs' files hold. It agrees exactly
  with the two sibling readers on the same cache;
* the card, run as Gameday Refresh runs it (no flags, the default raw cache),
  builds on a cache holding such files. It says the cache is partial (30 of 32
  clubs) and freezes tonight's games;
* `fetch_nhl_data`, the script the card's partial-cache warning tells the
  operator to run, fetches a cached non-object again instead of serving it,
  so the warning's advice completes the cache;
* a 200 whose body is not an object is a failed request, counted and named as
  one. It is not a cached schedule counted as ok.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from itertools import permutations
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd
import pytest

from conftest import FakeResponse, RecordingRequester, boxscore_payload
from nhl_betting_lab import config, verdicts
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.data.build_datasets import (
    PLAYER_LOG_COLUMNS,
    PLAYER_LOGS_FILENAME,
    TEAM_GAME_COLUMNS,
    TEAM_GAMES_FILENAME,
)
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.season import (
    known_regular_season_games,
    schedule_cache_is_complete,
    scheduled_regular_season_starts,
)


CLUBS = (
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET",
    "EDM", "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT",
    "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK",
    "WPG", "WSH",
)
SEASON = "20262027"

#: Bodies that parse as JSON and are not an object, each as the real writer
#: stores it. `null` is the shape #145 found for boxscores.
NOT_AN_OBJECT = pytest.mark.parametrize(
    "body", [None, [], "x"], ids=["null", "list", "string"]
)

Game = tuple[str, str, str]  # (game date, HOME, AWAY)


def _game(day: str, home: str, away: str) -> dict[str, Any]:
    """One game as `club-schedule-season` returns it."""
    return {
        "gameType": 2, "gameDate": day, "startTimeUTC": f"{day}T23:00:00Z",
        "gameScheduleState": "OK",
        "homeTeam": {"abbrev": home}, "awayTeam": {"abbrev": away},
    }


def _own_games(schedule: list[Game], club: str) -> dict[str, Any]:
    """`club`'s own file: every game it plays, home and away, as the API
    returns one club's season."""
    return {"games": [_game(*g) for g in schedule if club in g[1:]]}


def _round_robin() -> list[Game]:
    """Every club hosts every other once: 992 games, 62 in each club's file."""
    start = date(2026, 10, 7)
    return [
        ((start + timedelta(days=i // 16)).isoformat(), home, away)
        for i, (home, away) in enumerate(permutations(CLUBS, 2))
    ]


def _cache(raw: Path, schedule: list[Game], bad: dict[str, Any]) -> Path:
    """Every club's own file, written by the production cache writer; a club
    in `bad` gets that body instead of its schedule."""
    directory = raw / "nhl" / "club_schedule"
    for club in CLUBS:
        body = bad[club] if club in bad else _own_games(schedule, club)
        nhl_api._write_cache(directory / f"{club}_{SEASON}.json", body)
    return directory


# --------------------------------------------------------------------------
# The reader.
# --------------------------------------------------------------------------

@NOT_AN_OBJECT
def test_the_reader_skips_a_club_file_that_is_not_an_object(
    tmp_path: Path, body: Any
) -> None:
    """Eight of 32 club files hold `body`. Their games against the other 24
    clubs are still known from those clubs' own files, and only the 56 games
    between two of the eight are not. The reader must return exactly that.
    A reader that raised, that stopped at the first bad file, or that gave
    up on the whole cache would each return something else."""
    schedule = _round_robin()
    bad = {club: body for club in CLUBS[::4]}
    _cache(tmp_path, schedule, bad)
    good = set(CLUBS) - set(bad)
    expected = {g for g in schedule if g[1] in good or g[2] in good}
    assert len(expected) == 992 - 8 * 7, "the fixture is not the one described"

    known = known_regular_season_games(tmp_path)

    assert known == expected
    # The same cache, read by the two readers that already skipped this shape.
    assert known == set(scheduled_regular_season_starts(tmp_path))
    assert schedule_cache_is_complete(tmp_path, season=SEASON) == (False, 24)


# --------------------------------------------------------------------------
# Through the card, as Gameday Refresh runs it.
# --------------------------------------------------------------------------

#: What the NHL API calls each club on tonight's slate, and what the
#: provider sends.
TEAMS = {
    "TOR": ("Toronto", "Maple Leafs"),
    "BOS": ("Boston", "Bruins"),
    "MTL": ("Montréal", "Canadiens"),
    "OTT": ("Ottawa", "Senators"),
}
PROVIDER = {abbrev: f"{place} {common}" for abbrev, (place, common) in TEAMS.items()}
TONIGHT = "2026-10-15"
NOW = "2026-10-15T15:00:00+00:00"


def _load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _slate_schedule() -> list[Game]:
    """Tonight Toronto hosts Boston and Montréal hosts Ottawa; the other 28
    clubs play in pairs two days later, so every club's own file holds a
    regular-season game."""
    others = [c for c in CLUBS if c not in TEAMS]
    return [(TONIGHT, "TOR", "BOS"), (TONIGHT, "MTL", "OTT")] + [
        ("2026-10-17", others[i], others[i + 1]) for i in range(0, len(others), 2)
    ]


def _boxscores(raw: Path) -> None:
    """Two final games naming tonight's four clubs, so the map the card
    builds from the cache resolves the provider's names."""
    directory = raw / "nhl" / "boxscore"
    for game_id, (home, away) in enumerate((("TOR", "BOS"), ("MTL", "OTT")), 1):
        payload = boxscore_payload(game_id=game_id, game_state="OFF")
        for side, abbrev in (("homeTeam", home), ("awayTeam", away)):
            place, common = TEAMS[abbrev]
            payload[side].update(
                abbrev=abbrev,
                placeName={"default": place},
                commonName={"default": common},
            )
        nhl_api._write_cache(directory / f"{game_id}.json", payload)


def _tables(processed: Path) -> None:
    """Sixty played games per pairing and a skater log for each, enough for
    both models to fit."""
    processed.mkdir(parents=True, exist_ok=True)
    games: list[dict] = []
    logs: list[dict] = []
    for index in range(120):
        day = f"2025-{1 + (index // 2) // 28:02d}-{1 + (index // 2) % 28:02d}"
        pair = ("TOR", "BOS") if index % 2 == 0 else ("MTL", "OTT")
        home, away = pair if (index // 2) % 2 == 0 else pair[::-1]
        games.append({
            "game_id": index, "season": 20242025, "game_type": 2, "date": day,
            "start_time_utc": f"{day}T23:00:00Z", "home_team": home,
            "away_team": away, "home_goals": 4 if home in ("TOR", "MTL") else 2,
            "away_goals": 2 if home in ("TOR", "MTL") else 3,
            "home_shots": 30, "away_shots": 28, "regulation": index % 5 != 0,
        })
        for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
            for offset, position, shots in ((0, "C", 5), (1, "D", 1)):
                player_id = 1 + offset + 100 * list(TEAMS).index(team)
                logs.append({
                    "game_id": index, "season": 20242025, "game_type": 2,
                    "date": day, "start_time_utc": f"{day}T23:00:00Z",
                    "player_id": player_id, "player": f"Skater {player_id}",
                    "boxscore_name": f"S. {player_id}", "role": "skater",
                    "position": position, "team": team, "opponent": opponent,
                    "venue": venue, "toi_seconds": 1200, "shots_on_goal": shots,
                    "goals": 1 if shots > 1 else 0, "assists": 1, "points": 2,
                    "blocked_shots": 1, "hits": 1, "power_play_goals": 0,
                    "saves": 0, "shots_against": 0, "goals_against": 0,
                })
    pd.DataFrame(games, columns=list(TEAM_GAME_COLUMNS)).to_csv(
        processed / TEAM_GAMES_FILENAME, index=False
    )
    pd.DataFrame(logs, columns=list(PLAYER_LOG_COLUMNS)).to_csv(
        processed / PLAYER_LOGS_FILENAME, index=False
    )


def _prices(staging: Path) -> None:
    """Both of tonight's games, moneyline, both sides, staged four hours ago."""
    staging.mkdir(parents=True, exist_ok=True)
    rows = [
        {"date": TONIGHT, "commence_time": f"{TONIGHT}T23:00:00Z",
         "provider_event_id": f"evt-{home}-{away}",
         "home_team": PROVIDER[home], "away_team": PROVIDER[away],
         "market": "moneyline", "player": "", "selection": selection,
         "line": "", "american_odds": -110, "book": "DraftKings",
         "fetched_at": f"{TONIGHT}T11:00:00Z"}
        for home, away in (("TOR", "BOS"), ("MTL", "OTT"))
        for selection in ("home", "away")
    ]
    pd.DataFrame(rows, columns=list(odds_api.PRICE_COLUMNS)).to_csv(
        staging / odds_api.STAGING_PRICES_FILENAME, index=False
    )


def test_the_card_builds_on_a_cache_holding_club_files_that_are_not_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Gameday Refresh runs the card with no flags, so every raw read goes to
    the default cache, pointed here at a scratch one. Toronto's file holds
    `[]` and Boston's `null`: the card used to raise AttributeError out of
    the schedule read and write nothing. It must build, say the cache holds
    30 of 32 clubs' own schedules, and freeze both of tonight's games."""
    raw = tmp_path / "raw"
    _cache(raw, _slate_schedule(), {"TOR": [], "BOS": None})
    _boxscores(raw)
    # Every default the card reads, emptied or pointed at scratch, so the
    # real data/ tree can neither rescue this test nor be written by it.
    # `season` reads `config.RAW_DIR` at call time; `nhl_api` and
    # `team_names` bound theirs at import.
    default_processed = tmp_path / "default_processed"
    default_processed.mkdir()
    recorded = tmp_path / "recorded_outputs"
    recorded.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", default_processed)
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", recorded)
    processed = tmp_path / "processed"
    _tables(processed)
    _prices(tmp_path / "staging")
    outputs = tmp_path / "outputs"

    code = _load_script("run_gameday_card.py").main(
        ["--staging-dir", str(tmp_path / "staging"),
         "--processed-dir", str(processed),
         "--output-dir", str(outputs),
         "--now", NOW]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "holds this season's own schedule for only 30 of 32 clubs" in out
    assert "no regular-season schedule is cached" not in out, (
        "the whole cache was discarded for two bad files"
    )
    card = json.loads((outputs / "gameday_card.json").read_text(encoding="utf-8"))
    assert card["slate_games"] == 2
    frozen = sorted(outputs.rglob("priced_snapshots/*.csv"))
    assert [path.name for path in frozen] == [f"{TONIGHT}.csv"]
    snapshot = pd.read_csv(frozen[0])
    assert sorted(snapshot["home_team"]) == sorted(
        [PROVIDER["MTL"]] * 2 + [PROVIDER["TOR"]] * 2
    )


# --------------------------------------------------------------------------
# The fetch the card's warning tells the operator to run.
# --------------------------------------------------------------------------

def _api(schedule: list[Game], answers: dict[str, Any] | None = None) -> RecordingRequester:
    """The NHL API: each club's own schedule, except a club in `answers`,
    whose schedule request is answered HTTP 200 with that body instead."""
    answers = answers or {}

    def club_schedule(url: str, **kwargs: Any) -> FakeResponse:
        club, season = url.rstrip("/").split("/")[-2:]
        assert season == SEASON, url
        if club in answers:
            return FakeResponse(answers[club])
        return FakeResponse(_own_games(schedule, club))

    return RecordingRequester({
        "club-schedule-season": club_schedule,
        "/roster/": FakeResponse({"forwards": [], "defensemen": [], "goalies": []}),
    })


def _fetch(
    raw: Path, requester: RecordingRequester, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    monkeypatch.setattr(nhl_api, "_default_requester", requester)
    code = _load_script("fetch_nhl_data.py").main(
        ["--seasons", SEASON, "--polite-seconds", "0", "--skip-registry"]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@NOT_AN_OBJECT
def test_a_cached_club_file_that_is_not_an_object_is_fetched_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], body: Any,
) -> None:
    """A runner or a checkout holding 31 good club files and a Toronto file
    holding `body`. The card says "Run scripts/fetch_nhl_data.py to complete
    the cache". Running it must replace Toronto's file, not serve it again.
    (`null` was already a cache miss; `[]` and `"x"` were served forever.)"""
    schedule = _round_robin()
    raw = tmp_path / "raw"
    _cache(raw, schedule, {"TOR": body})
    assert schedule_cache_is_complete(raw, season=SEASON) == (False, 31)

    code, out, err = _fetch(raw, _api(schedule), monkeypatch, capsys)

    assert code == 0, err
    assert "Live requests, club schedules: 1 ok, 31 from cache, 0 failed." in out
    assert schedule_cache_is_complete(raw, season=SEASON) == (True, 32)
    assert known_regular_season_games(raw) == set(schedule)


@NOT_AN_OBJECT
def test_a_club_schedule_answered_with_something_other_than_an_object_is_a_failed_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], body: Any,
) -> None:
    """HTTP 200 with a body that is no schedule. It used to be cached as it
    came and counted ok. It must be counted as a failed request, named, and
    not cached, so nothing downstream ever reads it."""
    schedule = _round_robin()
    raw = tmp_path / "raw"

    code, out, err = _fetch(raw, _api(schedule, {"TOR": body}), monkeypatch, capsys)

    assert code == 0, "one bad club is a partial failure, not an outage"
    assert "Live requests, club schedules: 31 ok, 0 from cache, 1 failed." in out
    assert "::warning::" in out and "club schedules: 1" in out
    assert "TOR" in err and "not a JSON object" in err
    directory = raw / "nhl" / "club_schedule"
    assert not (directory / f"TOR_{SEASON}.json").exists()
    assert not list(directory.glob("*.partial"))
    assert schedule_cache_is_complete(raw, season=SEASON) == (False, 31)
