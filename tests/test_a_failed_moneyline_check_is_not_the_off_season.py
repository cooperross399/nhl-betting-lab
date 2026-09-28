"""A moneyline check that failed was read as the off-season.

`OddsApiProvider.fetch_team_markets` asks the bulk `/odds` endpoint for
h2h, spreads and totals in one request. A 422 there means one of two things:
the provider is serving no NHL odds at all, which is the ordinary state
between seasons, or it refused the market list. To tell them apart, the
method asks again for `h2h` alone. If that is refused too, there are no odds.
If it is served, the market list was the problem.

The retry sat in a bare `except ProviderError`, so ANY failure of it raised
`EmptySlateError`, "The provider is serving no NHL odds at all ... it is not
a fault". That covered a 503, a 429, a 500, a 401, a read timeout, a refused
connection and an unreadable body alike. `run_provider_shadow.py` turns
that error into exit 3, and Gameday Refresh turns exit 3 into
`empty_slate=true`. From there:
- "Record what went wrong" printed "Nothing went wrong.";
- the post step posted nothing;
- card-feed recorded `degraded: false, empty_slate: true`;
- the 15:00 backup's precheck (`FEED_DAY = DAY and DEGRADED = false`) stood
  down.
The result was a game day with no card, no post and no frozen snapshot, on
a green run.

Found by the failure-shape audit (group c3x0-odds-api-600, confirmed by
three of three refuters). They replayed it with only the transport stubbed:
- A bulk 422 followed by a retry answering 503, 429, 500, 401, a read
  timeout or a connection error each raised `EmptySlateError` after two
  `/odds` requests. `/events` was never consulted.
- The real script exited 3 and staged nothing.
- The workflow's own step blocks, run under `bash -eo pipefail` with 5,280
  cached boxscores, wrote empty_slate=true and degraded=false. The job was
  green, and the backup precheck printed "already published and clean.
  Skipping."
The only tests covered 422 then 422, and 422 then 200.

The verdict also had no evidence from outside the provider. The error's
docstring said a 422 was "only ever reported as an empty slate after the
free events endpoint confirms the board really is empty". That check was
removed in #21, because through September the October schedule is listed
and it answered the wrong question, and nothing replaced it. So a 422 to both
requests from a parameter both share, such as a region the provider stops
serving, would read as the off-season on every run of a season. The
2026-27 season opens on 2026-09-29.

What these tests hold:

* after a bulk 422, the off-season verdict needs the moneyline retry itself
  to be refused with a 422; any other failure of it is a failed fetch
  (ProviderError, exit 2), and the error says the check could not be made.
  Both checks read the status the provider refused with, which
  `ProviderError.status` now carries, and not the words of the message; a
  bulk request that failed any other way is not checked again;
* a 422 to both requests stays the off-season when the NHL schedule cached
  by this run lists no regular-season game in the fetch window (today, for
  a run with no window). When it lists one, the run is a failed fetch: books
  post regular-season lines days ahead, so "no NHL odds at all" on a
  scheduled game day is a fault;
* through the workflow's own price and health steps, both of those reach
  `degraded=true` and never `empty_slate=true`, so the 15:00 backup runs.

Limits, stated rather than hidden. The schedule check reads the
club-schedule cache, so on a runner with no cache it cannot contradict
anything, and a 422 to both stays exit 3, as before. It covers the "no NHL
odds at all" verdict only. The ordinary off-day verdict (the provider lists
upcoming games and none on today's date) rests on a board the provider did
serve, and is unchanged.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest
import requests
import yaml

from conftest import FakeResponse
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"

#: Never a real credential, and never sent anywhere: the transport is a stub.
ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}

#: 09:30 in New York, when the primary trigger fires, on a three-game night.
NOW = datetime(2026, 10, 7, 13, 30, tzinfo=timezone.utc)
TODAY = "2026-10-07"

TONIGHT = (("WPG", "COL"), ("WSH", "PIT"), ("ANA", "EDM"))

BULK = ",".join(odds_api.BULK_PROVIDER_MARKETS)


# --------------------------------------------------------------------------
# The provider, as the transport sees it.
# --------------------------------------------------------------------------

def _refused(code: int):
    return lambda: FakeResponse(status_code=code)


def _raises(exc: Exception):
    def answer() -> FakeResponse:
        raise exc
    return answer


#: Every way the moneyline retry can fail without being refused with a 422,
#: and the words its failure is reported in.
RETRY_FAILURES = {
    "http-503": (_refused(503), "HTTP 503"),
    "http-429": (_refused(429), "HTTP 429"),
    "http-500": (_refused(500), "HTTP 500"),
    "http-401": (_refused(401), "HTTP 401"),
    "read-timeout": (_raises(requests.ReadTimeout("read timed out")),
                     "could not be reached (ReadTimeout)"),
    "connection-refused": (_raises(requests.ConnectionError("refused")),
                           "could not be reached (ConnectionError)"),
    "unreadable-body": (lambda: FakeResponse(raises=ValueError("not json")),
                        "unreadable JSON"),
}


class Transport:
    """The bulk request answers `bulk`; the moneyline retry answers `retry`.

    Anything else is refused as unexpected, so a test also sees that the
    free events list was never needed."""

    def __init__(self, retry, bulk=_refused(422)) -> None:
        self.retry = retry
        self.bulk = bulk
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url: str, **kwargs: object) -> FakeResponse:
        params = kwargs["params"]
        assert isinstance(params, dict)
        self.calls.append((url, str(params.get("markets", ""))))
        if url.endswith("/odds") and "/events/" not in url:
            return self.retry() if params.get("markets") == "h2h" else self.bulk()
        raise AssertionError(f"unexpected request: {url}")

    @property
    def markets_asked(self) -> list[str]:
        return [markets for _, markets in self.calls]


def _provider(transport: Transport) -> odds_api.OddsApiProvider:
    return odds_api.OddsApiProvider(environment=ENVIRONMENT, requester=transport)


# --------------------------------------------------------------------------
# The provider's verdict.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("failure", sorted(RETRY_FAILURES))
def test_a_moneyline_check_that_failed_is_not_the_off_season(failure: str) -> None:
    retry, cause = RETRY_FAILURES[failure]
    transport = Transport(retry)

    with pytest.raises(odds_api.ProviderError) as raised:
        _provider(transport).fetch_team_markets()

    assert not isinstance(raised.value, odds_api.EmptySlateError), (
        f"{failure}: a moneyline request that was not refused with a 422 is "
        "no evidence that the provider serves no NHL odds"
    )
    assert transport.markets_asked == [BULK, "h2h"]
    text = str(raised.value)
    assert cause in text, text
    assert "cannot be read as the off-season" in text, text
    assert odds_api.NO_STAGING_WRITTEN in text
    assert "not a fault" not in text


def test_both_refused_with_a_422_is_still_the_off_season() -> None:
    """The case the check was written for, and between seasons the ordinary
    one: the market list and a plain moneyline both refused."""
    transport = Transport(_refused(422))

    with pytest.raises(odds_api.EmptySlateError) as raised:
        _provider(transport).fetch_team_markets()

    assert isinstance(raised.value, odds_api.NoOddsServedError)
    assert "not a fault" in str(raised.value)
    assert transport.markets_asked == [BULK, "h2h"]


@pytest.mark.parametrize("failure", ["http-503", "http-429", "read-timeout"])
def test_only_a_market_list_refused_with_a_422_is_checked_again(failure: str) -> None:
    """The check keys on the status now, not on the words of the message. A
    bulk request that failed any other way is a failed fetch at once, and no
    moneyline request is spent on it."""
    transport = Transport(lambda: FakeResponse([]), bulk=RETRY_FAILURES[failure][0])

    with pytest.raises(odds_api.ProviderError) as raised:
        _provider(transport).fetch_team_markets()

    assert not isinstance(raised.value, odds_api.EmptySlateError)
    assert transport.markets_asked == [BULK]


def test_a_refused_market_list_with_a_served_moneyline_is_still_a_request_problem() -> None:
    transport = Transport(lambda: FakeResponse([]))

    with pytest.raises(odds_api.ProviderError) as raised:
        _provider(transport).fetch_team_markets()

    assert not isinstance(raised.value, odds_api.EmptySlateError)
    assert "not a market it serves" in str(raised.value)


@pytest.mark.parametrize(
    ("answer", "status"),
    [(_refused(422), 422), (_refused(503), 503),
     (_raises(requests.ReadTimeout("slow")), None),
     (lambda: FakeResponse(raises=ValueError("not json")), None)],
    ids=["http-422", "http-503", "read-timeout", "unreadable-body"],
)
def test_a_provider_error_carries_the_status_it_was_refused_with(
    answer, status: int | None
) -> None:
    """The verdict reads the status, not the words of the message. A request
    that never came back, or came back 200 and unreadable, was not refused."""
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=lambda url, **kwargs: answer()
    )

    with pytest.raises(odds_api.ProviderError) as raised:
        provider.list_events()

    assert raised.value.status == status


# --------------------------------------------------------------------------
# The script, run the way Gameday Refresh runs it.
# --------------------------------------------------------------------------

def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_provider_shadow.py"
    spec = importlib.util.spec_from_file_location(
        "_script_run_provider_shadow_off_season_check", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class _Capture:
    """stdout and stderr of one call."""

    def __enter__(self):
        self._out, self._err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        return self

    def __exit__(self, *exc):
        self.out, self.err = sys.stdout.getvalue(), sys.stderr.getvalue()
        sys.stdout, sys.stderr = self._out, self._err
        return False


def _cache_schedule(raw: Path, games: list[tuple[str, str, str, int]]) -> None:
    """Club schedules as the NHL API returns them, one file per home club."""
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    by_club: dict[str, list[dict]] = {}
    for day, home, away, game_type in games:
        by_club.setdefault(home, []).append({
            "gameType": game_type,
            "gameDate": day,
            "gameScheduleState": "OK",
            "startTimeUTC": f"{day}T23:00:00Z",
            "homeTeam": {"abbrev": home},
            "awayTeam": {"abbrev": away},
        })
    for club, club_games in by_club.items():
        (directory / f"{club}_20262027.json").write_text(
            json.dumps({"games": club_games}), encoding="utf-8"
        )


def _tonight(game_type: int = 2, day: str = TODAY) -> list[tuple[str, str, str, int]]:
    return [(day, home, away, game_type) for home, away in TONIGHT]


#: The flags each workflow runs the script with, beside the scratch dirs.
GAMEDAY_REFRESH_FLAGS = ["--live", "--props", "--overwrite-staging",
                         "--horizon-days", "1", "--credit-cap", "320"]
#: The scheduled market-discovery probe: no window, so no league days.
MARKET_DISCOVERY_FLAGS = ["--live", "--overwrite-staging", "--horizon-days", "0",
                          "--max-events", "20", "--credit-cap", "380"]


def _shadow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: Transport,
            schedule: list[tuple[str, str, str, int]],
            flags: list[str] = GAMEDAY_REFRESH_FLAGS) -> tuple[int, str, str]:
    """The real script with a workflow's own flags, over a stub transport,
    with `schedule` as the only club-schedule cache it can read."""
    dirs = point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    if schedule:
        _cache_schedule(dirs.raw, schedule)
    module = load_script()
    real = odds_api.OddsApiProvider
    monkeypatch.setattr(
        module.odds_api, "OddsApiProvider",
        lambda: real(environment=ENVIRONMENT, requester=transport, regions="us"),
    )
    # No `.env` is read, whatever the checkout holds.
    monkeypatch.setattr(
        module, "load_provider_env",
        lambda: ProviderEnvLoadResult(path=tmp_path / ".env"),
    )
    monkeypatch.setattr(module, "datetime", _Frozen)
    capture = _Capture()
    with capture:
        code = module.main([
            *flags,
            "--staging-dir", str(tmp_path / "staging"),
            "--output-dir", str(tmp_path / "outputs"),
        ])
    return code, capture.out, capture.err


@pytest.mark.parametrize("failure", ["http-503", "http-429", "read-timeout"])
def test_the_script_does_not_call_a_failed_check_an_empty_slate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """No schedule is cached here, so only the provider's answer decides."""
    code, out, err = _shadow(
        tmp_path, monkeypatch, Transport(RETRY_FAILURES[failure][0]), []
    )

    assert code == 2, (
        f"exit {code}: a failed moneyline check must be a failed fetch (2), "
        "not an empty slate (3)"
    )
    assert "No slate" not in out
    assert "Team-market fetch failed" in err
    assert not (tmp_path / "staging" / odds_api.STAGING_PRICES_FILENAME).exists()


@pytest.mark.parametrize(
    "flags", [GAMEDAY_REFRESH_FLAGS, MARKET_DISCOVERY_FLAGS],
    ids=["gameday-refresh", "market-discovery-no-window"],
)
def test_no_odds_at_all_on_a_scheduled_game_day_is_a_failed_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: list[str]
) -> None:
    """Both requests refused with a 422 while the NHL schedule lists three
    regular-season games tonight. The provider cannot tell that from the
    off-season; the schedule can. A run with no window checks today."""
    code, out, err = _shadow(
        tmp_path, monkeypatch, Transport(_refused(422)), _tonight(), flags
    )

    assert code == 2
    assert "No slate" not in out
    assert "3 regular-season game(s)" in err and TODAY in err, err
    assert not (tmp_path / "staging" / odds_api.STAGING_PRICES_FILENAME).exists()


@pytest.mark.parametrize(
    "schedule",
    [_tonight(day="2026-10-12"), _tonight(game_type=1)],
    ids=["season-opens-later", "exhibitions-only-tonight"],
)
def test_no_odds_at_all_with_no_regular_season_game_tonight_is_the_off_season(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schedule
) -> None:
    code, out, err = _shadow(tmp_path, monkeypatch, Transport(_refused(422)), schedule)

    assert code == 3, err
    assert "No slate" in out


# --------------------------------------------------------------------------
# The workflow: the price step and the health step, run from the YAML.
# --------------------------------------------------------------------------

def _step(id_: str) -> dict:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == id_:
                return step
    raise AssertionError(f"no step {id_}")


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions a test names; refuse any it did not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _bash(block: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def _outputs(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        found[key] = value
    return found


def _runner(tmp_path: Path) -> Path:
    """A workspace the health step would otherwise call clean: player logs on
    disk and a warm boxscore cache."""
    work = tmp_path / "work"
    (work / "data" / "processed").mkdir(parents=True)
    (work / "data" / "processed" / "player_game_logs.csv").write_text(
        "player_id\n1\n", encoding="utf-8"
    )
    box = work / "data" / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for game in range(1200):
        (box / f"{game}.json").write_text('{"gameState": "OFF"}', encoding="utf-8")
    return work


def _price_and_health(tmp_path: Path, code: int) -> tuple[str, dict[str, str], dict[str, str]]:
    """The price step with `python` standing in for the script's exit, then
    the health step on what it recorded."""
    work = _runner(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "python"
    stub.write_text(f"#!/bin/sh\nexit {code}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    prices_output = tmp_path / "prices_output"
    prices_output.write_text("", encoding="utf-8")
    block = _render(_step("prices")["run"], {
        "inputs.props_credit_cap || '320'": "320",
    })
    result = _bash(block, work, {**os.environ,
                                 "PATH": f"{bin_dir}:{os.environ['PATH']}",
                                 "GITHUB_OUTPUT": str(prices_output)})
    outcome = "success" if result.returncode == 0 else "failure"
    prices = _outputs(prices_output)

    health_output = tmp_path / "health_output"
    health_output.write_text("", encoding="utf-8")
    block = _render(_step("health")["run"], {
        "steps.results.outcome": "success",
        "steps.prices.outputs.empty_slate": prices.get("empty_slate", ""),
        "steps.prices.outcome": outcome,
    })
    result = _bash(block, work, {**os.environ, "GITHUB_OUTPUT": str(health_output)})
    assert result.returncode == 0, result.stderr
    return outcome, prices, _outputs(health_output)


@pytest.mark.parametrize(
    ("retry", "schedule", "degraded"),
    [("http-503", [], "true"),
     ("http-422", "tonight", "true"),
     ("http-422", [], "false")],
    ids=["check-failed", "no-odds-on-a-game-day", "no-odds-in-the-off-season"],
)
def test_the_run_health_follows_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    retry: str, schedule, degraded: str
) -> None:
    """End to end: the real script's exit, through the price step, into the
    `degraded` the card-feed status and the 15:00 backup's precheck read."""
    answer = _refused(422) if retry == "http-422" else RETRY_FAILURES[retry][0]
    games = _tonight() if schedule == "tonight" else schedule
    code, _, _ = _shadow(tmp_path, monkeypatch, Transport(answer), games)

    outcome, prices, health = _price_and_health(tmp_path, code)

    assert health["degraded"] == degraded, (code, outcome, prices)
    if degraded == "true":
        assert outcome == "failure"
        assert prices.get("empty_slate", "") != "true"
    else:
        assert prices.get("empty_slate") == "true"
