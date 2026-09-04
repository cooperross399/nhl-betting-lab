"""Shared fixtures, and the two hooks that make "the suite passed" mean that.

Every test here runs offline. Nothing in this suite makes a network request,
reads a credential, or writes outside `tmp_path`.

Two hooks live here as well, because a fixture file is the one module pytest
loads before it decides what to run:

* `pytest_collection_modifyitems` refuses a session in which any module in
  `REQUIRED_GUARD_MODULES` contributed zero collected tests. `git rm` of the
  secrets guard left this suite green with BETTER metrics — fewer tests, same
  pass rate — and pytest has no way to say so, because a deleted file collects
  nothing and nothing is not a failure. Neither is a rename, a `-k` that
  matches none of its tests, a `--deselect`, an `--ignore`, a positional path
  naming the other modules, or the same flag arriving through `PYTEST_ADDOPTS`.
  The hook runs last (`trylast=True`), AFTER pytest's own `-k`/`-m`/`--deselect`
  filtering has been applied to `items`, so what it counts is what will run.
  It exits with status 1 rather than failing one test, so there is no test to
  deselect.
* `pytest_sessionfinish` refuses a session that skipped, xfailed or xpassed
  anything. `python -m pytest -q` exits 0 on a skip, and a skip that waits on
  gitignored data can never resolve in CI — two of them in this suite had
  never run there once. There is no allowlist and there will not be one: a
  skip is resolved by making the test build what it needs, or by deleting it.

`tests/test_the_guards_exist.py` copies this file into a synthetic tree and
runs pytest against it, so both hooks are observed to fire rather than read.
A subset run is refused by design; `python -m pytest -q` is the only run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

#: Every test module that enforces a hard rule. A session in which any of
#: these contributed zero collected tests is exited with status 1 before a
#: single test runs. `tests/test_the_guards_exist.py` asserts each is tracked
#: by git and still defines at least five tests; this list is the single
#: source both read. Adding a guard means adding it here — an unlisted guard
#: is protected by nothing.
REQUIRED_GUARD_MODULES: tuple[str, ...] = (
    "tests/test_no_secrets_committed.py",
    "tests/test_no_sibling_lab_import.py",
    "tests/test_contract_strings.py",
    "tests/test_workflows.py",
    "tests/test_the_guards_exist.py",
)


def guard_shortfall(paths: list[Path], rootpath: Path) -> list[str]:
    """Which required modules contributed no item in `paths`.

    A pure function over the collected item paths, so the same arithmetic can
    be pointed at a synthetic list and shown to report an absence rather than
    trusted to.
    """
    root = Path(rootpath).resolve()
    counts = dict.fromkeys(REQUIRED_GUARD_MODULES, 0)
    for path in paths:
        try:
            relative = Path(path).resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        if relative in counts:
            counts[relative] += 1
    return [module for module, count in counts.items() if count == 0]


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    missing = guard_shortfall([item.path for item in items], config.rootpath)
    if missing:
        pytest.exit(
            "Refusing to run: these hard-rule guard modules contributed zero "
            "collected tests, so the run would report green having never "
            "checked the rules they enforce — " + ", ".join(missing) + ". "
            "A deleted, renamed, ignored, deselected or -k-filtered guard is "
            "not a smaller green; it is a missing gate. Run the whole suite: "
            "`python -m pytest -q`.",
            returncode=1,
        )


#: Every test that did not run to a plain pass or a plain fail, by outcome.
_NOT_A_PASS: list[str] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when != "call" and not (report.when == "setup" and report.skipped):
        return
    outcome = None
    if report.skipped:
        outcome = "xfailed" if hasattr(report, "wasxfail") else "skipped"
    elif report.passed and hasattr(report, "wasxfail"):
        outcome = "xpassed"
    if outcome:
        _NOT_A_PASS.append(f"{report.nodeid} [{outcome}]")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Turn a green run that skipped into a red one.

    The attribute is set rather than `pytest.exit` raised, because the
    terminal reporter prints its `N passed, M skipped` line after this hook
    returns and an exception here would lose it. `wrap_session` returns
    `session.exitstatus` after every hook has run, so the assignment is the
    exit code. The reasons are printed by `pytest_terminal_summary` below.
    """
    if _NOT_A_PASS and int(exitstatus) == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int) -> None:
    if not _NOT_A_PASS:
        return
    terminalreporter.write_sep("!", "did not pass and did not fail", red=True)
    terminalreporter.write_line(
        f"{len(_NOT_A_PASS)} test(s) did not pass and did not fail, so this run "
        "exits 1. A skip is a gate that passes when it should fail; an xfail is "
        "a known bug the build stopped mentioning. Resolve it or delete it — "
        "there is no exemption list:"
    )
    for entry in _NOT_A_PASS:
        terminalreporter.write_line(f"  {entry}")


class FakeResponse:
    """The narrow slice of `requests.Response` this project actually uses."""

    def __init__(
        self,
        payload: Any = None,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self._raises = raises

    def json(self) -> Any:
        if self._raises is not None:
            raise self._raises
        return self._payload


class RecordingRequester:
    """A requester that answers from a script and records what it was asked.

    Keyed by a substring of the URL so a test states the endpoint it means
    rather than reconstructing a full URL with query parameters.
    """

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.default = FakeResponse(status_code=404)

    def __call__(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, dict(kwargs)))
        for fragment, response in self.responses.items():
            if fragment in url:
                if callable(response):
                    return response(url, **kwargs)
                return response
        return self.default

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.calls]


@pytest.fixture
def responses() -> type[FakeResponse]:
    return FakeResponse


@pytest.fixture
def requester() -> RecordingRequester:
    return RecordingRequester()


def boxscore_payload(
    *,
    game_id: int = 2024020001,
    game_state: str = "OFF",
    season: int = 20242025,
    game_type: int = 2,
    game_date: str = "2024-10-08",
    start_time: str = "2024-10-09T23:00:00Z",
    home: str = "TOR",
    away: str = "NJD",
    home_score: int = 4,
    away_score: int = 2,
    period: int = 3,
    skaters: list[dict[str, Any]] | None = None,
    goalies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A boxscore in the shape `api-web.nhle.com` actually returns."""
    default_skaters = [
        {
            "playerId": 8478483,
            "name": {"default": "M. Marner"},
            "position": "R",
            "goals": 1,
            "assists": 2,
            "points": 3,
            "sog": 4,
            "blockedShots": 1,
            "hits": 2,
            "powerPlayGoals": 1,
            "toi": "21:30",
        }
    ]
    default_goalies = [
        {
            "playerId": 8474593,
            "name": {"default": "J. Markstrom"},
            "position": "G",
            "saveShotsAgainst": "30/31",
            "goalsAgainst": 1,
            "toi": "59:38",
        }
    ]
    block = {
        "forwards": skaters if skaters is not None else default_skaters,
        "defense": [],
        "goalies": goalies if goalies is not None else default_goalies,
    }
    return {
        "id": game_id,
        "season": season,
        "gameType": game_type,
        "gameDate": game_date,
        "startTimeUTC": start_time,
        "gameState": game_state,
        "periodDescriptor": {"number": period},
        "homeTeam": {"abbrev": home, "score": home_score, "sog": 33},
        "awayTeam": {"abbrev": away, "score": away_score, "sog": 28},
        "playerByGameStats": {"homeTeam": block, "awayTeam": block},
    }


@pytest.fixture(autouse=True)
def never_actually_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may spend real time waiting.

    The NHL client backs off between retries, which is correct in production
    and pure cost in a suite. A test that wants to assert on the delays passes
    its own recorder; everything else simply never waits.
    """
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
