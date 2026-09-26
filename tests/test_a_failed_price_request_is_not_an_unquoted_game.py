"""The two price captures never read `errors`, so a failed request looked like a game no book quoted.

`fetch_player_props` asks `/events/{id}/odds` once per game. When one of
those requests fails it keeps going, rightly, and records the failure in
`FetchResult.errors`. #187 made `run_provider_shadow.py` act on that list.
The other two callers never read it:

* `scripts/capture_line_movement.py` runs five times a day in season (the
  Line Movement Capture workflow). It printed `summary_line()` and the
  warnings, then returned 0. Nothing in the script mentioned `errors`. The
  same fetch feeds the closing-line store, and a game's close is the last
  round captured strictly before its face-off. So when that last round
  failed for one game, CLV quietly used the round before it as the close.
* `scripts/capture_closing_lines.py`, the dispatch capture, printed
  `per_event.warnings` and not `per_event.errors`, then returned 0.

The failure-shape audit found it, and two of three refuters confirmed it by
replaying the real scripts with only the HTTP transport stubbed. On a
three-game night where the request for one game answered HTTP 503 (429 and a
read timeout behaved the same), the line-movement capture exited 0 and its
whole log was: "4 rows appended ... 4 best-price row(s) appended to the
closing-line store. 4 price rows from 2 of 3 events". That is identical to
a night where that game answered with no bookmakers, apart from the credit
figure, because a 503 is not billed. Neither 503, the event id nor the word
"fail" appeared anywhere. In a two-round replay (18:00 all at -115, then
23:10 with ev1 failing and the others moved to +105), `closing_prices`
closed ev1 at the 18:00 round's -115 and gave no sign that the last
pre-game round had been lost. The dispatch capture printed "Captured 10
selection(s) ... from 10 raw price rows" and exited 0. The whole suite
(2,504 tests) was green with the defect present. When every request failed,
the line-movement capture printed "No rows returned; nothing written." and
exited 0. That all-fail case was already on file (w1), and this fix covers
it too.

What these tests hold, through the real `main` of each script, a real
`OddsApiProvider` over a stub transport, and the workflows' own step blocks:

* the line-movement capture follows the rule its own job already applies to
  the scratch list (`capture_deployment.py`). A partial round keeps what came
  back, writes both stores, exits 0, and names every failed request in a
  `::warning::` and on stderr. A round in which requests failed and nothing
  was captured exits 2, which turns the Capture prices step red, and every
  step after it is `if: always()`, so no upload and no hand-off is lost;
* the dispatch capture names its failed requests the same way and still
  exits 0. Its Publish step runs only after a successful Capture step, so
  a nonzero exit would throw away the team markets and the games that
  answered;
* an answered request with no bookmakers, a board where nothing was quoted,
  and a credit-cap skip are absences, not failures: exit 0, with no failure
  warning.
"""

from __future__ import annotations

import io
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
import requests
import yaml

from conftest import FakeResponse
from nhl_betting_lab.closing_lines import captures_path
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult

from test_scripts import load_script


LINE_MOVEMENT = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
CLOSING_LINES = PROJECT_ROOT / ".github" / "workflows" / "closing-lines.yml"

#: Never a real credential, and never sent anywhere: the transport is a stub.
ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}

#: The 21:00 UTC Line Movement cron on a three-game night (17:00 Eastern).
NOW = datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)
DAY = "2026-10-07"

GAMES = (
    ("ev0", "Winnipeg Jets", "Colorado Avalanche", "2026-10-07T23:00:00Z"),
    ("ev1", "Washington Capitals", "Pittsburgh Penguins", "2026-10-07T23:30:00Z"),
    ("ev2", "Anaheim Ducks", "Edmonton Oilers", "2026-10-08T02:00:00Z"),
)
HOME = {event_id: home for event_id, home, _, _ in GAMES}

#: Credits one per-event request costs at one region: every market asked.
ASKED = len(odds_api.PER_EVENT_PROVIDER_MARKETS) + len(
    odds_api.ALTERNATE_PROVIDER_MARKETS
)


# --------------------------------------------------------------------------
# The provider, as the transport sees it.
# --------------------------------------------------------------------------

def _book(title: str, markets: list[dict]) -> dict:
    return {"key": title.lower(), "title": title, "markets": markets}


def _shots(player: str) -> list[dict]:
    return [{"key": "player_shots_on_goal", "outcomes": [
        {"name": "Over", "description": player, "price": -115, "point": 2.5},
        {"name": "Under", "description": player, "price": -105, "point": 2.5}]}]


def _team_markets(home: str, away: str) -> list[dict]:
    return [{"key": "h2h", "outcomes": [
        {"name": home, "price": -140}, {"name": away, "price": 120}]}]


def _event(event_id: str, home: str, away: str, commence: str,
           books: list[dict]) -> dict:
    return {"id": event_id, "commence_time": commence, "home_team": home,
            "away_team": away, "bookmakers": books}


def _listing() -> list[dict]:
    return [{"id": event_id, "commence_time": commence, "home_team": home,
             "away_team": away} for event_id, home, away, commence in GAMES]


def _bulk() -> list[dict]:
    """The bulk team fetch the dispatch capture makes first; always answers."""
    return [
        _event(event_id, home, away, commence,
               [_book("DraftKings", _team_markets(home, away))])
        for event_id, home, away, commence in GAMES
    ]


def _answer(event_id: str, *, quoted: bool = True) -> FakeResponse:
    for game_id, home, away, commence in GAMES:
        if game_id == event_id:
            books = [_book("DraftKings", _shots(f"Skater {event_id}"))] if quoted else []
            return FakeResponse(_event(game_id, home, away, commence, books))
    raise AssertionError(event_id)


class Transport:
    """Answers the events list, the bulk odds and each game's odds."""

    def __init__(self, per_event) -> None:
        self.per_event = per_event
        self.calls: list[str] = []

    def __call__(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(url)
        if "/events/" in url and url.endswith("/odds"):
            event_id = url.split("/events/")[1].split("/")[0]
            return self.per_event(event_id)
        if url.endswith("/events"):
            return FakeResponse(_listing())
        if url.endswith("/odds"):
            return FakeResponse(_bulk())
        raise AssertionError(f"unexpected request: {url}")

    def per_event_requests(self) -> int:
        return sum("/events/" in url and url.endswith("/odds") for url in self.calls)


def _status(code: int, failing: set[str]):
    def answer(event_id: str) -> FakeResponse:
        if event_id in failing:
            return FakeResponse(status_code=code)
        return _answer(event_id)
    return answer


def _timeout(failing: set[str]):
    def answer(event_id: str) -> FakeResponse:
        if event_id in failing:
            raise requests.ReadTimeout("read timed out")
        return _answer(event_id)
    return answer


def _all_ok(event_id: str) -> FakeResponse:
    return _answer(event_id)


def _ev1_unquoted(event_id: str) -> FakeResponse:
    return _answer(event_id, quoted=event_id != "ev1")


def _none_quoted(event_id: str) -> FakeResponse:
    return _answer(event_id, quoted=False)


EVERY = {"ev0", "ev1", "ev2"}

#: One failed request of three, each way a request can fail. The 422 fails
#: the full list and then the core-market fallback, so it is lost as well.
ONE_FAILS = [
    pytest.param(_status(503, {"ev1"}), "HTTP 503", id="http-503"),
    pytest.param(_status(429, {"ev1"}), "HTTP 429", id="http-429"),
    pytest.param(_timeout({"ev1"}), "ReadTimeout", id="read-timeout"),
    pytest.param(_status(422, {"ev1"}), "HTTP 422", id="422-and-422-on-the-core-list"),
]

EVERY_ONE_FAILS = [
    pytest.param(_status(503, EVERY), "HTTP 503", id="http-503"),
    pytest.param(_status(429, EVERY), "HTTP 429", id="http-429"),
    pytest.param(_timeout(EVERY), "ReadTimeout", id="read-timeout"),
    pytest.param(_status(422, EVERY), "HTTP 422", id="422-and-422-on-the-core-list"),
]


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


def _drive(script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
           per_event, *, cap: int) -> tuple[int, str, str, Transport, Path]:
    """The real script with the workflow's own flags, over a stub transport."""
    module: ModuleType = load_script(script)
    transport = Transport(per_event)
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
    processed = tmp_path / "processed"
    capture = _Capture()
    with capture:
        code = module.main([
            "--live", "--credit-cap", str(cap), "--processed-dir", str(processed),
        ])
    return code, capture.out, capture.err, transport, processed


def _movement(tmp_path, monkeypatch, per_event, *, cap: int = 600):
    return _drive("capture_line_movement.py", tmp_path, monkeypatch, per_event, cap=cap)


def _closing(tmp_path, monkeypatch, per_event, *, cap: int = 400):
    return _drive("capture_closing_lines.py", tmp_path, monkeypatch, per_event, cap=cap)


def _movement_file(processed: Path) -> Path:
    return processed / "line_movement" / f"{DAY}.csv"


def _movement_events(processed: Path) -> set[str]:
    frame = pd.read_csv(_movement_file(processed), dtype=str, keep_default_na=False)
    return set(frame["provider_event_id"])


def _closing_homes(processed: Path, *, market: str | None = None) -> set[str]:
    frame = pd.read_csv(captures_path(processed), dtype=str, keep_default_na=False)
    if market is not None:
        frame = frame[frame["market"] == market]
    return set(frame["home_team"])


def _annotations(out: str, kind: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith(f"::{kind}::")]


# --------------------------------------------------------------------------
# The line-movement capture.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(("per_event", "cause"), ONE_FAILS)
def test_one_failed_request_is_named_and_the_games_that_answered_are_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, cause: str
) -> None:
    code, out, err, transport, processed = _movement(tmp_path, monkeypatch, per_event)

    assert transport.per_event_requests() >= 3, "every game was asked"
    # Kept: the round's other games reach both stores, exactly as before.
    assert _movement_events(processed) == {"ev0", "ev2"}
    assert _closing_homes(processed) == {HOME["ev0"], HOME["ev2"]}
    # Named: on the run page, and with its reason in the log.
    warnings = _annotations(out, "warning")
    assert len(warnings) == 1, f"a lost game must warn on the run page:\n{out}"
    assert "ev1" in warnings[0] and cause in warnings[0], warnings[0]
    assert "ev0" not in warnings[0] and "ev2" not in warnings[0], warnings[0]
    assert "absent" in warnings[0] and "not unquoted" in warnings[0]
    assert "1 per-event request(s) failed" in err, err
    assert "ev1" in err and cause in err, err
    # One lost game is a partial round, the rule the scratch-list capture in
    # the same job follows: warn, keep the rest, stay green.
    assert code == 0, f"exit {code}: a partial round is not a failed capture\n{out}{err}"


@pytest.mark.parametrize(("per_event", "cause"), EVERY_ONE_FAILS)
def test_a_round_in_which_every_request_failed_is_a_failed_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, cause: str
) -> None:
    """The all-fail case (w1): it printed "No rows returned; nothing written."
    and exited 0, the same words and code as a board no book had priced."""
    code, out, err, transport, processed = _movement(tmp_path, monkeypatch, per_event)

    assert transport.per_event_requests() >= 3
    assert code == 2, f"exit {code}: nothing captured, because requests failed\n{out}{err}"
    assert not _movement_file(processed).exists(), "a capture of nothing writes nothing"
    assert not captures_path(processed).exists()
    assert "3 per-event request(s) failed" in err, err
    assert all(event_id in err for event_id in EVERY), err
    assert cause in err
    errors = _annotations(out, "error")
    assert len(errors) == 1 and all(event_id in errors[0] for event_id in EVERY), out


@pytest.mark.parametrize(
    ("per_event", "cap", "events"),
    [
        pytest.param(_all_ok, 600, {"ev0", "ev1", "ev2"}, id="every-game-answered"),
        pytest.param(_ev1_unquoted, 600, {"ev0", "ev2"}, id="one-game-no-book-quoted"),
        pytest.param(_none_quoted, 600, None, id="no-book-quoted-anything"),
        pytest.param(_all_ok, ASKED, {"ev0"}, id="credit-cap-skipped-two-games"),
    ],
)
def test_an_absence_is_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, cap: int,
    events: set[str] | None,
) -> None:
    """A game answered with no bookmakers, a board nobody priced yet, and a
    budget skip the fetch already states as a warning. None of them lost a
    request, so none of them may read as one."""
    code, out, err, transport, processed = _movement(
        tmp_path, monkeypatch, per_event, cap=cap
    )

    assert code == 0, f"exit {code}\n{out}{err}"
    assert _annotations(out, "warning") == [], out
    assert _annotations(out, "error") == [], out
    assert "request(s) failed" not in err, err
    if events is None:
        assert "No rows returned; nothing written." in out
        assert not _movement_file(processed).exists()
    else:
        assert _movement_events(processed) == events
    if cap == ASKED:
        assert transport.per_event_requests() == 1
        assert "cap would have been exceeded" in out, "the skip is still stated"


# --------------------------------------------------------------------------
# The dispatch capture (capture_closing_lines.py).
# --------------------------------------------------------------------------

@pytest.mark.parametrize(("per_event", "cause"), ONE_FAILS[:3])
def test_the_dispatch_capture_names_a_failed_request_and_keeps_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, cause: str
) -> None:
    code, out, err, transport, processed = _closing(tmp_path, monkeypatch, per_event)

    assert transport.per_event_requests() >= 3
    assert _closing_homes(processed, market="moneyline") == set(HOME.values())
    assert _closing_homes(processed, market="shots_on_goal") == {HOME["ev0"], HOME["ev2"]}
    warnings = _annotations(out, "warning")
    assert len(warnings) == 1, f"a lost game must warn on the run page:\n{out}"
    assert "ev1" in warnings[0] and cause in warnings[0], warnings[0]
    assert "ev0" not in warnings[0] and "ev2" not in warnings[0]
    assert "1 per-event request(s) failed" in err and "ev1" in err, err
    # Publish runs only after a successful Capture step (see the workflow
    # test below), so a nonzero exit here would discard every row above.
    assert code == 0, f"exit {code}\n{out}{err}"


def test_the_dispatch_capture_names_every_game_when_every_request_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, err, _, processed = _closing(tmp_path, monkeypatch, _status(503, EVERY))

    assert code == 0, "the team markets were captured and must still publish"
    assert _closing_homes(processed) == set(HOME.values())
    assert set(pd.read_csv(captures_path(processed))["market"]) == {"moneyline"}
    warnings = _annotations(out, "warning")
    assert len(warnings) == 1 and all(e in warnings[0] for e in EVERY), out
    assert "3 per-event request(s) failed" in err


@pytest.mark.parametrize(
    ("per_event", "cap"),
    [
        pytest.param(_all_ok, 400, id="every-game-answered"),
        pytest.param(_ev1_unquoted, 400, id="one-game-no-book-quoted"),
        pytest.param(_all_ok, ASKED, id="credit-cap-skipped-two-games"),
    ],
)
def test_the_dispatch_capture_does_not_call_an_absence_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, cap: int
) -> None:
    code, out, err, _, processed = _closing(tmp_path, monkeypatch, per_event, cap=cap)

    assert code == 0, f"{out}{err}"
    assert _annotations(out, "warning") == [], out
    assert "request(s) failed" not in err, err
    assert _closing_homes(processed, market="moneyline") == set(HOME.values())


# --------------------------------------------------------------------------
# The workflows: the steps that run these scripts, from the YAML.
# --------------------------------------------------------------------------

def _steps(workflow: Path) -> list[dict]:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    return [step for job in document["jobs"].values() for step in job["steps"]]


def _named(workflow: Path, name: str) -> tuple[int, dict]:
    matches = [(i, s) for i, s in enumerate(_steps(workflow)) if s.get("name") == name]
    assert len(matches) == 1, f"exactly one step named {name!r} in {workflow.name}"
    return matches[0]


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions a test names; refuse any it did not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _run_step(block: str, tmp_path: Path, code: int) -> tuple[str, dict[str, str]]:
    """The step's own run block under the runner's shell, with `python`
    standing in for the script and exiting with the script's real code."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "python"
    stub.write_text(f"#!/bin/sh\nexit {code}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    output = tmp_path / "step_output"
    output.write_text("", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=work, capture_output=True, text=True, timeout=60,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
             "GITHUB_OUTPUT": str(output)},
    )
    outputs = dict(
        line.partition("=")[::2]
        for line in output.read_text(encoding="utf-8").splitlines()
    )
    return ("success" if result.returncode == 0 else "failure"), outputs


def test_a_red_price_capture_costs_the_line_movement_run_nothing() -> None:
    """Exit 2 turns Capture prices red. That is the report and must stay one,
    so the step is not forgiven; and every step after it still runs, so the
    captures, the ladder scan and the closing-price hand-off are all kept."""
    index, capture = _named(LINE_MOVEMENT, "Capture prices")
    assert "capture_line_movement.py" in capture["run"]
    assert capture.get("continue-on-error") in (None, False), (
        "a forgiven price step turns a round that captured nothing green again"
    )
    assert "if" not in capture, "the price capture runs on every trigger"
    later = _steps(LINE_MOVEMENT)[index + 1:]
    assert any(step.get("name") == "Hand the closing prices to Closing Lines"
               for step in later)
    for step in later:
        assert str(step.get("if", "")).startswith("always()"), (
            f"{step.get('name')!r} would be skipped after a red price capture"
        )


@pytest.mark.parametrize(
    ("per_event", "outcome"),
    [
        pytest.param(_status(503, {"ev1"}), "success", id="one-game-503"),
        pytest.param(_status(503, EVERY), "failure", id="every-game-503"),
        pytest.param(_none_quoted, "success", id="no-book-quoted-anything"),
    ],
)
def test_the_price_step_is_red_only_when_failed_requests_left_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, outcome: str
) -> None:
    """End to end: the real script's exit, through the step's own block."""
    code, _, _, _, _ = _movement(tmp_path, monkeypatch, per_event)
    _, step = _named(LINE_MOVEMENT, "Capture prices")
    block = _render(step["run"], {"inputs.credit_cap || '600'": "600"})

    assert _run_step(block, tmp_path, code)[0] == outcome, f"script exit {code}"


def test_a_partial_dispatch_capture_still_reaches_the_publish_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing Lines' Publish step carries no `always()`, so it runs only
    after a Capture step that succeeded. A partial capture has to leave that
    step green, or the team markets and the games that answered are lost."""
    code, _, _, _, _ = _closing(tmp_path, monkeypatch, _status(503, {"ev1"}))
    _, step = _named(CLOSING_LINES, "Capture")
    block = _render(step["run"], {"inputs.credit_cap || '400'": "400"})

    outcome, outputs = _run_step(block, tmp_path, code)

    assert outcome == "success", f"script exit {code}"
    assert outputs.get("empty_slate", "") != "true", "a partial night is not a dark one"
