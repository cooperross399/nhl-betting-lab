"""An NHL outage could spend the whole Fetch results step.

Every request makes four attempts (30-second timeouts, 2+4+8 seconds of
backoff) and `fetch_nhl_data.py` asks about 160 schedules, rosters and
registries live before any boxscore, so a dead API used the 18 minutes
Gameday Refresh gives the step (#270). The fetch now runs behind a circuit
breaker: after `CIRCUIT_BREAKER_THRESHOLD` requests in a row fail on every
attempt, nothing more is asked this run, a `::warning::` names how many
requests were skipped, and the fetch exits 1 so the run stays degraded.

Driven through the real script against a stub transport; `time.sleep` is
patched and recorded, so nothing sleeps and the backoff spent is counted.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest
import requests

from conftest import FakeResponse, RecordingRequester, boxscore_payload
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api


SEASON = "20262027"
GAMES = [2026020001 + i for i in range(6)]
TEAM_COUNT = 32


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "fetch_nhl_data.py"
    spec = importlib.util.spec_from_file_location("_script_fetch_breaker", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sleeps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[float]:
    monkeypatch.setattr(nhl_api, "RAW_DIR", tmp_path / "raw")
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    return slept


def _schedule() -> FakeResponse:
    return FakeResponse(
        {"games": [{"id": g, "gameType": 2, "gameDate": "2026-10-08"} for g in GAMES]}
    )


def _roster() -> FakeResponse:
    return FakeResponse({"forwards": [], "defensemen": [], "goalies": []})


def _run(monkeypatch, capsys, requester) -> tuple[int, str, str]:
    monkeypatch.setattr(nhl_api, "_default_requester", requester)
    code = load_script().main(
        ["--seasons", SEASON, "--polite-seconds", "0", "--skip-registry"]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_a_dead_api_is_asked_threshold_times_and_no_more(
    sleeps, monkeypatch, capsys
) -> None:
    calls: list[str] = []

    def unreachable(url, **kwargs):
        calls.append(url)
        raise requests.ConnectTimeout("timed out")

    code, out, err = _run(monkeypatch, capsys, unreachable)

    threshold = nhl_api.CIRCUIT_BREAKER_THRESHOLD
    assert len(calls) == threshold * nhl_api.MAX_ATTEMPTS
    # Bounded: only the tripping requests' backoff, not 64 requests' worth.
    assert sum(sleeps) == threshold * (2 + 4 + 8)
    assert code == 1, "an outage must still mark the run degraded"
    skipped = (TEAM_COUNT - threshold) + TEAM_COUNT  # schedules + rosters
    assert f"{skipped} live request(s) were skipped" in out
    assert "::warning::" in out
    assert "::error::" in err  # every source down, as before
    # The breaker is removed after the run, so no other caller inherits it.
    assert nhl_api._circuit_breaker is None


def test_a_dead_api_returning_503_trips_too(sleeps, monkeypatch, capsys) -> None:
    requester = RecordingRequester()
    requester.default = FakeResponse(status_code=503)

    code, out, _ = _run(monkeypatch, capsys, requester)

    assert len(requester.calls) == nhl_api.CIRCUIT_BREAKER_THRESHOLD * nhl_api.MAX_ATTEMPTS
    assert code == 1 and "were skipped" in out


def test_a_flaky_api_that_recovers_keeps_going(sleeps, monkeypatch, capsys) -> None:
    """Fewer failures in a row than the threshold, then answers: every club,
    roster and boxscore is still asked for."""
    dead_teams = {"ANA", "BOS", "BUF", "CAR"}  # threshold - 1 in a row
    assert len(dead_teams) < nhl_api.CIRCUIT_BREAKER_THRESHOLD

    def schedule(url, **kwargs):
        if any(f"/{team}/" in url for team in dead_teams):
            raise requests.ConnectionError("blip")
        return _schedule()

    requester = RecordingRequester({
        "club-schedule-season": schedule,
        "/roster/": _roster(),
        "/boxscore": lambda url, **kw: FakeResponse(
            boxscore_payload(game_id=int(url.split("/")[-2]), game_state="OFF")
        ),
    })

    code, out, err = _run(monkeypatch, capsys, requester)

    assert "were skipped" not in out
    assert sum("/roster/" in u for u in requester.urls) == TEAM_COUNT
    assert sum("/boxscore" in u for u in requester.urls) == len(GAMES)
    assert code == 0  # a partial schedule failure warns, as before
    assert "club schedules: 4" in out


def test_a_healthy_run_is_unchanged(sleeps, monkeypatch, capsys) -> None:
    def boxscore(url, **kwargs):
        return FakeResponse(
            boxscore_payload(game_id=int(url.split("/")[-2]), game_state="OFF")
        )

    def run_once(install: bool) -> tuple[list[str], list[str], int]:
        requester = RecordingRequester({
            "club-schedule-season": _schedule(),
            "/roster/": _roster(),
            "/boxscore": boxscore,
        })
        raw = nhl_api.RAW_DIR / ("with" if install else "without")
        monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
        monkeypatch.setattr(nhl_api, "_default_requester", requester)
        script = load_script()
        if install:
            code = script.main(["--seasons", SEASON, "--polite-seconds", "0", "--skip-registry"])
        else:
            code = script._main(["--seasons", SEASON, "--polite-seconds", "0", "--skip-registry"])
        files = sorted(
            str(p.relative_to(raw)) for p in raw.rglob("*.json")
        )
        return requester.urls, files, code

    urls_with, files_with, code_with = run_once(True)
    urls_without, files_without, code_without = run_once(False)
    out = capsys.readouterr().out

    assert urls_with == urls_without
    assert files_with == files_without and files_with
    assert code_with == code_without == 0
    assert "were skipped" not in out


def test_any_answer_resets_the_count() -> None:
    breaker = nhl_api.CircuitBreaker(threshold=2)
    nhl_api.install_circuit_breaker(breaker)
    try:
        def down(url, **kwargs):
            raise requests.ConnectionError("down")

        not_found = RecordingRequester()  # answers 404: the API is up
        for requester in (down, not_found, down, not_found, down):
            with pytest.raises(nhl_api.NhlApiError):
                nhl_api._get_json("https://x/a", requester=requester, sleeper=lambda s: None)
        assert not breaker.open
        with pytest.raises(nhl_api.NhlApiError):
            nhl_api._get_json("https://x/a", requester=down, sleeper=lambda s: None)
        assert breaker.open
        with pytest.raises(nhl_api.CircuitOpenError):
            nhl_api._get_json("https://x/a", requester=not_found, sleeper=lambda s: None)
        assert breaker.skipped == 1
        assert not_found.calls and len(not_found.calls) == 2
    finally:
        nhl_api.install_circuit_breaker(None)


def test_the_tripping_request_is_cached_nowhere(sleeps, monkeypatch, capsys) -> None:
    def unreachable(url, **kwargs):
        raise requests.ConnectionError("down")

    _run(monkeypatch, capsys, unreachable)
    raw = Path(nhl_api.RAW_DIR)
    assert not raw.exists() or not any(raw.rglob("*.json"))
