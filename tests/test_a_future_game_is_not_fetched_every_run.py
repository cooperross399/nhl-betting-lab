"""A game that has not been played was fetched on every run, and cached.

`fetch_nhl_data` puts the whole season's ids in scope, future games
included, and `fetch_boxscore` serves from cache only a boxscore that is
final. So every scheduled game was asked for again on every run, each one
counted toward `--max-games`, and its `FUT` answer was written into
`data/raw/nhl/boxscore`. Reproduced with a stub: twenty ids, five final, and
every run made fifteen live requests and left twenty files for five real
games. In season that is up to about six hundred pointless requests a run
(the 429 exposure the polite pause exists to avoid), a future game sorted
ahead of a real final could take its place in the `--max-games` budget, and
Gameday Refresh's thin-history check counted the future games' files with
`find | wc -l`, so a thin history read as a healthy one.

What these tests hold, driving the real script against fake endpoints (no
network):

* a game whose scheduled start is after now is not asked for, so it neither
  costs a request nor spends the `--max-games` budget;
* a schedule fetched live this run that says `FUT` or `PRE` is believed, but
  a CACHED club schedule's state is not (it is frozen at whenever it was
  fetched: the real cache holds August's `FUT` for games long since played),
  and a missing or unreadable start time is fetched — a missed final is
  worse than a wasted call;
* `fetch_boxscore` never writes a boxscore that is not final, removes a
  non-final one an older run left, and never overwrites a final one;
* the health step counts final boxscores only, and agrees with
  `game_is_final` on which those are.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from conftest import FakeResponse, RecordingRequester, boxscore_payload
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api


SEASON = "20262027"
PAST = "2000-01-01T00:00:00Z"
FUTURE = "2999-01-01T00:00:00Z"


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "fetch_nhl_data.py"
    spec = importlib.util.spec_from_file_location("_script_fetch_nhl_data_fut", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _game(game_id: int, *, start: str | None, state: str = "FUT") -> dict:
    game = {"id": game_id, "gameType": 2, "gameDate": "2026-10-08", "gameState": state}
    if start is not None:
        game["startTimeUTC"] = start
    return game


def _boxscore_answer(finals: set[int]):
    """The API's answer: final for a played game, `FUT` for any other."""

    def answer(url: str, **kwargs):
        game_id = int(url.split("/gamecenter/")[1].split("/")[0])
        state = "OFF" if game_id in finals else "FUT"
        return FakeResponse(boxscore_payload(game_id=game_id, game_state=state))

    return answer


def _requester(schedule: list[dict], finals: set[int]) -> RecordingRequester:
    return RecordingRequester({
        "club-schedule-season": FakeResponse({"games": schedule}),
        "/roster/": FakeResponse({"forwards": [], "defensemen": [], "goalies": []}),
        "/boxscore": _boxscore_answer(finals),
    })


def _run(monkeypatch, requester, *extra: str) -> int:
    monkeypatch.setattr(nhl_api, "_default_requester", requester)
    return load_script().main(
        ["--seasons", SEASON, "--polite-seconds", "0", "--skip-registry",
         "--skip-rosters", *extra]
    )


def _boxscore_calls(requester: RecordingRequester) -> list[int]:
    return [
        int(url.split("/gamecenter/")[1].split("/")[0])
        for url in requester.urls
        if "/boxscore" in url
    ]


@pytest.fixture
def raw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "raw"
    (root / "nhl").mkdir(parents=True)
    monkeypatch.setattr(nhl_api, "RAW_DIR", root)
    return root


def _write_club_schedule(raw: Path, games: list[dict]) -> None:
    """Every club's schedule, cached as `fetch_club_season_schedule` left it."""
    for team in load_script().TEAMS:
        nhl_api._write_cache(
            raw / "nhl" / "club_schedule" / f"{team}_{SEASON}.json", {"games": games}
        )


# -- the repro ---------------------------------------------------------------


def test_the_repro_twenty_ids_five_final_costs_nothing_on_the_second_run(
    raw: Path, monkeypatch, capsys
) -> None:
    played = list(range(2026020001, 2026020006))
    unplayed = list(range(2026020006, 2026020021))
    schedule = [_game(g, start=PAST, state="OFF") for g in played] + [
        _game(g, start=FUTURE) for g in unplayed
    ]

    first = _requester(schedule, set(played))
    assert _run(monkeypatch, first) == 0
    assert sorted(_boxscore_calls(first)) == played, "a future game was asked for"

    second = _requester(schedule, set(played))
    assert _run(monkeypatch, second) == 0
    assert _boxscore_calls(second) == [], "the second run asked the API again"

    files = sorted(int(p.stem) for p in (raw / "nhl" / "boxscore").glob("*.json"))
    assert files == played, "the cache holds a file for a game not yet played"
    out = capsys.readouterr().out
    assert "15 not yet played" in out


def test_a_future_game_does_not_spend_the_max_games_budget(
    raw: Path, monkeypatch
) -> None:
    """The future game's id sorts first; the one fetch must go to the final."""
    schedule = [_game(2026020001, start=FUTURE), _game(2026020002, start=PAST, state="OFF")]
    requester = _requester(schedule, {2026020002})

    assert _run(monkeypatch, requester, "--max-games", "1") == 0

    assert _boxscore_calls(requester) == [2026020002]
    assert (raw / "nhl" / "boxscore" / "2026020002.json").is_file()


# -- what counts as "not yet played" -------------------------------------------


@pytest.mark.parametrize("state", ["FUT", "PRE"])
def test_a_live_schedule_that_says_not_started_is_believed(
    raw: Path, monkeypatch, state: str
) -> None:
    """Fetched live this run, the state is today's. The start time here is in
    the past (a late puck drop, warm-ups running long) and it is still not
    worth a request: the game cannot be final."""
    requester = _requester([_game(2026020001, start=PAST, state=state)], set())

    assert _run(monkeypatch, requester) == 0

    assert _boxscore_calls(requester) == []


def test_a_cached_schedules_state_is_not_believed(raw: Path, monkeypatch) -> None:
    """Club schedules are fetched once and served from cache after that, so
    their `gameState` is whatever it was in August. Trusting it would skip
    every game of the season, forever."""
    _write_club_schedule(raw, [_game(2026020001, start=PAST, state="FUT")])
    requester = _requester([], {2026020001})

    assert _run(monkeypatch, requester) == 0

    assert _boxscore_calls(requester) == [2026020001]
    assert not any("club-schedule-season" in url for url in requester.urls)


def test_a_cached_schedules_future_start_is_believed(raw: Path, monkeypatch) -> None:
    _write_club_schedule(raw, [_game(2026020001, start=FUTURE, state="FUT")])
    requester = _requester([], set())

    assert _run(monkeypatch, requester) == 0

    assert _boxscore_calls(requester) == []


@pytest.mark.parametrize(
    "start", [None, "", "TBD", "2999-01-01T00:00:00"], ids=["missing", "blank", "unreadable", "naive"]
)
def test_an_unconfirmed_start_is_fetched(raw: Path, monkeypatch, start) -> None:
    """Ambiguity falls on "fetch it": a wasted call costs a quarter-second, a
    missed final costs a game of history."""
    _write_club_schedule(raw, [_game(2026020001, start=start, state="FUT")])
    requester = _requester([], set())

    assert _run(monkeypatch, requester) == 0

    assert _boxscore_calls(requester) == [2026020001]


def test_one_club_saying_future_does_not_outvote_one_that_does_not(
    raw: Path, monkeypatch
) -> None:
    """Every game is in two clubs' files. It is skipped only when every copy
    says it has not been played."""
    teams = load_script().TEAMS
    for index, team in enumerate(teams):
        start = FUTURE if index else PAST
        nhl_api._write_cache(
            raw / "nhl" / "club_schedule" / f"{team}_{SEASON}.json",
            {"games": [_game(2026020001, start=start)]},
        )
    requester = _requester([], {2026020001})

    assert _run(monkeypatch, requester) == 0

    assert _boxscore_calls(requester) == [2026020001]


def test_the_date_window_skips_future_games_too(raw: Path, monkeypatch) -> None:
    week = {"gameWeek": [{"games": [
        _game(2026020001, start=FUTURE),
        _game(2026020002, start=PAST, state="OFF"),
    ]}]}
    requester = RecordingRequester({
        "/schedule/": FakeResponse(week),
        "/boxscore": _boxscore_answer({2026020002}),
    })
    monkeypatch.setattr(nhl_api, "_default_requester", requester)

    code = load_script().main(
        ["--from", "2026-10-08", "--to", "2026-10-08", "--polite-seconds", "0",
         "--skip-registry", "--skip-rosters"]
    )

    assert code == 0
    assert _boxscore_calls(requester) == [2026020002]


# -- the cache holds finals only -----------------------------------------------


@pytest.mark.parametrize("state", ["FUT", "PRE", "LIVE", "CRIT"])
def test_a_boxscore_that_is_not_final_is_not_written(tmp_path: Path, state: str) -> None:
    requester = RecordingRequester(
        {"boxscore": FakeResponse(boxscore_payload(game_state=state))}
    )

    entry = nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)

    assert entry.complete is False and entry.from_cache is False
    assert entry.payload["gameState"] == state
    assert not entry.path.exists()
    assert nhl_api.cached_boxscore_ids(tmp_path) == []


def test_a_non_final_file_an_older_run_left_is_removed(tmp_path: Path) -> None:
    """Before this fix every run wrote one; the restored cache still has them."""
    path = tmp_path / "nhl" / "boxscore" / "2024020001.json"
    nhl_api._write_cache(path, boxscore_payload(game_state="FUT"))
    requester = RecordingRequester(
        {"boxscore": FakeResponse(boxscore_payload(game_state="LIVE"))}
    )

    nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)

    assert not path.exists()


def test_a_refresh_that_answers_not_final_never_overwrites_a_final(tmp_path: Path) -> None:
    path = tmp_path / "nhl" / "boxscore" / "2024020001.json"
    nhl_api._write_cache(path, boxscore_payload(game_state="OFF"))
    requester = RecordingRequester(
        {"boxscore": FakeResponse(boxscore_payload(game_state="LIVE"))}
    )

    entry = nhl_api.fetch_boxscore(
        2024020001, requester=requester, raw_dir=tmp_path, refresh=True
    )

    assert entry.complete is False
    assert nhl_api.game_is_final(json.loads(path.read_text(encoding="utf-8")))


# -- the health step counts finals only ----------------------------------------


def _health_step() -> str:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml").read_text(
            encoding="utf-8"
        )
    )
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "health":
                block = step["run"]
                for expression, value in (
                    ("${{ steps.results.outcome }}", "success"),
                    ("${{ steps.prices.outputs.empty_slate }}", "false"),
                    ("${{ steps.prices.outcome }}", "success"),
                ):
                    block = block.replace(expression, value)
                assert "${{" not in block, block
                return block
    raise AssertionError("gameday-refresh.yml has no step with id: health")


def _run_health(tmp_path: Path, states: list[str]) -> tuple[str, str]:
    work = tmp_path / "work"
    (work / "data" / "processed").mkdir(parents=True)
    (work / "data" / "processed" / "player_game_logs.csv").write_text(
        "player_id\n1\n", encoding="utf-8"
    )
    box = work / "data" / "raw" / "nhl" / "boxscore"
    for game_id, state in enumerate(states, start=1):
        # Written by the production writer, so the step reads the real format.
        nhl_api._write_cache(box / f"{game_id}.json", {"id": game_id, "gameState": state})
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _health_step()],
        cwd=work, env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout, (work / "run_degraded.txt").read_text(encoding="utf-8")


def test_future_game_files_do_not_make_a_thin_history_look_healthy(tmp_path: Path) -> None:
    """999 finals and a thousand scheduled games is a thin history."""
    stdout, notes = _run_health(tmp_path, ["OFF"] * 999 + ["FUT"] * 1000)

    assert "Boxscores cached: 999" in stdout
    assert "thin history" in notes, notes


def test_the_health_count_agrees_with_game_is_final(tmp_path: Path) -> None:
    states = ["OFF", "FINAL", "off", "final", "FUT", "PRE", "LIVE", "CRIT", ""]
    expected = sum(nhl_api.game_is_final({"gameState": s}) for s in states)

    stdout, _ = _run_health(tmp_path, states)

    assert expected == 4
    assert f"Boxscores cached: {expected}" in stdout


def test_the_health_count_is_zero_with_no_cache(tmp_path: Path) -> None:
    stdout, notes = _run_health(tmp_path, [])

    assert "Boxscores cached: 0" in stdout
    assert "thin history" in notes
