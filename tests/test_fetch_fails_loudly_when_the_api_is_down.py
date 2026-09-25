"""fetch_nhl_data exited 0 when the NHL API could not be reached at all.

It returned 1 only when boxscores failed AND nothing was cached or fetched.
With the API down every club-schedule request fails, so no game id is in
scope, the boxscore loop never runs, and the boxscore failure count stays 0;
and on a runner restored from gameday-state thousands of boxscores are cached
anyway. So the Fetch results step went green in a complete outage, and
Gameday Refresh's "Results could not be refreshed" — the only thing that
calls such a run degraded and summons the backup — could never be written.
Found by the failure-shape audit (3/3 refuters, reproduced with the
workflow's own argv against 656 failed requests: exit 0).

What these tests hold, driving the real script against fake endpoints:

* a complete outage, and a single source that is completely down, exit 1 and
  name what failed;
* failing boxscores on a warm cache exit 1 — a cache hit proves nothing about
  whether the API answered;
* a partial failure warns and exits 0, so a blip cannot turn a run red;
* the workflow step rebuilds the datasets whatever the fetch returns, and
  still exits with the fetch's code.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import requests
import yaml

from conftest import FakeResponse, RecordingRequester, boxscore_payload
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api


SEASON = "20262027"
CACHED_GAME = 2026020001
NEW_GAME = 2026020002


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "fetch_nhl_data.py"
    spec = importlib.util.spec_from_file_location("_script_fetch_nhl_data", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _schedule(*game_ids: int) -> FakeResponse:
    return FakeResponse(
        {"games": [{"id": g, "gameType": 2, "gameDate": "2026-10-08"} for g in game_ids]}
    )


def _roster() -> FakeResponse:
    return FakeResponse({"forwards": [], "defensemen": [], "goalies": []})


@pytest.fixture
def restored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A runner as "Restore the previous state" leaves it: one final boxscore
    cached, no club schedules, no rosters."""
    raw = tmp_path / "raw"
    box = raw / "nhl" / "boxscore"
    box.mkdir(parents=True)
    (box / f"{CACHED_GAME}.json").write_text(
        json.dumps(boxscore_payload(game_id=CACHED_GAME, game_state="OFF")),
        encoding="utf-8",
    )
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    return raw


def _run(monkeypatch, capsys, requester) -> tuple[int, str, str]:
    monkeypatch.setattr(nhl_api, "_default_requester", requester)
    code = load_script().main(
        ["--seasons", SEASON, "--polite-seconds", "0", "--skip-registry"]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_a_complete_outage_fails_the_fetch(restored, monkeypatch, capsys) -> None:
    def unreachable(url, **kwargs):
        raise requests.ConnectionError("no route to host")

    code, out, err = _run(monkeypatch, capsys, unreachable)

    assert code == 1, "a complete outage must not exit 0"
    assert "::error::" in err
    assert "club schedules" in err and "rosters" in err


def test_a_healthy_refresh_exits_zero(restored, monkeypatch, capsys) -> None:
    requester = RecordingRequester({
        "club-schedule-season": _schedule(CACHED_GAME, NEW_GAME),
        "/roster/": _roster(),
        f"/gamecenter/{NEW_GAME}/boxscore": FakeResponse(
            boxscore_payload(game_id=NEW_GAME, game_state="OFF")
        ),
    })

    code, out, err = _run(monkeypatch, capsys, requester)

    assert code == 0
    assert "::error::" not in err and "::warning::" not in out


def test_one_failed_roster_warns_and_does_not_fail(restored, monkeypatch, capsys) -> None:
    requester = RecordingRequester({
        "club-schedule-season": _schedule(CACHED_GAME),
        "/roster/TOR/": FakeResponse(status_code=404),
        "/roster/": _roster(),
    })

    code, out, err = _run(monkeypatch, capsys, requester)

    assert code == 0
    assert "::warning::" in out and "rosters: 1" in out


def test_one_source_completely_down_fails(restored, monkeypatch, capsys) -> None:
    requester = RecordingRequester({
        "club-schedule-season": _schedule(CACHED_GAME),
        "/roster/": FakeResponse(status_code=404),
    })

    code, out, err = _run(monkeypatch, capsys, requester)

    assert code == 1
    assert "rosters" in err


def test_failing_boxscores_on_a_warm_cache_fail(restored, monkeypatch, capsys) -> None:
    """The old rule excused this: one failure, but one boxscore cached."""
    requester = RecordingRequester({
        "club-schedule-season": _schedule(CACHED_GAME, NEW_GAME),
        "/roster/": _roster(),
        "/boxscore": FakeResponse(status_code=404),
    })

    code, out, err = _run(monkeypatch, capsys, requester)

    assert code == 1
    assert "boxscores" in err


# --------------------------------------------------------------------------
# The workflow step that reads the exit code.
# --------------------------------------------------------------------------

def _fetch_step_block() -> str:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml").read_text(
            encoding="utf-8"
        )
    )
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "results":
                return step["run"]
    raise AssertionError("no step with id: results in gameday-refresh.yml")


@pytest.mark.parametrize(("fetch_exit", "expected"), [(1, 1), (0, 0)])
def test_the_step_rebuilds_either_way_and_keeps_the_fetchs_code(
    tmp_path: Path, fetch_exit: int, expected: int
) -> None:
    shim = tmp_path / "bin"
    shim.mkdir()
    log = tmp_path / "calls.log"
    python = shim / "python"
    python.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{log}"\n'
        f'case "$*" in *fetch_nhl_data*) exit {fetch_exit};; esac\n'
        "exit 0\n",
        encoding="utf-8",
    )
    python.chmod(python.stat().st_mode | stat.S_IEXEC)

    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _fetch_step_block()],
        env={**os.environ, "PATH": f"{shim}:{os.environ.get('PATH', '')}"},
        capture_output=True,
        text=True,
    )
    calls = log.read_text(encoding="utf-8").splitlines()

    assert result.returncode == expected
    assert any("build_datasets.py" in call for call in calls), (
        "the datasets must be rebuilt even when the fetch failed"
    )
