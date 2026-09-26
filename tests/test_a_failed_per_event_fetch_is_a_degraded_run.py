"""A per-event fetch in which every request failed was recorded as a clean run.

`run_provider_shadow.py` fetches the team markets in one bulk call and then
asks `/events/{id}/odds` once per game for everything else: every prop, the
regulation three-way, and the alternate ladders. `fetch_player_props` keeps
going when one of those requests fails — rightly, one bad event must not
lose the rest — and appends the failure to `errors`. The script added those
errors to the provenance and returned 0 whatever they held.

"Record what went wrong" reads only the price step's outcome, so a green
exit was a clean run: `degraded=false` went to card-feed and the 15:00
backup's precheck stood down. Found by the failure-shape audit (confirmed by
3/3 refuters), replayed through the real scripts with only the HTTP
transport stubbed: the bulk call priced 3 games at 2 books and each of the 3
per-event calls answered HTTP 503 (429 and a read timeout alike). The fetch
exited 0; `player_props_staging.csv` held 0 rows; the verification report
read "Events: 3 priced of 3 seen" and named the 503s only in an Errors
section nothing reads; the card included only moneyline, puck_line and
total_goals and excluded all nine per-event markets with "The provider
returned no rows for this market"; and the snapshot froze 36 rows, none of
them a prop, the regulation three-way or a team total. With one of three
events failing the exit was 0 as well, and every per-event market read
"Priced for 2 of 3 games ... selection effect" — the card lost every prop.
The health step itself, run on the real shell with 5,280 cached boxscores,
printed "Nothing went wrong." for that exit.

What these tests hold, driving the real script with a real `OddsApiProvider`
over a stub transport, and the workflow's own step blocks under
`bash -eo pipefail`:

* any failed per-event request — 503, 429, a timeout, or a 422 that the
  core-market fallback cannot recover — exits 4, a code of its own, and the
  staging files, the provenance and the reports are still written;
* a fetch that asked every event and got answers exits 0, however few rows
  the books quoted, and so does one the credit cap cut short (a stated
  budget skip is a warning, not a failure);
* the price step turns exit 4 into a degraded note that names the per-event
  fetch, and the health step puts it in `run_degraded.txt`, so card-feed
  reads `degraded=true` and the backup runs;
* a per-event error no longer claims "No staging file was written" when the
  script wrote both staging files; a team-fetch failure, after which none is
  written, still says so.

What this does not fix: the day's first snapshot still stands, so a run
whose per-event fetch failed still freezes the team markets alone and a
later run that day cannot add the props. Changing that touches the "first
opinion of the day stands" rule the forward test reads, and is Cooper's call.
"""

from __future__ import annotations

import importlib.util
import json
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
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"

#: Never a real credential, and never sent anywhere: the transport is a stub.
ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}

#: 09:30 in New York on a three-game night, when the primary trigger fires.
NOW = datetime(2026, 10, 7, 13, 30, tzinfo=timezone.utc)

GAMES = (
    ("ev0", "Winnipeg Jets", "Colorado Avalanche", "2026-10-07T23:00:00Z"),
    ("ev1", "Washington Capitals", "Pittsburgh Penguins", "2026-10-07T23:30:00Z"),
    ("ev2", "Anaheim Ducks", "Edmonton Oilers", "2026-10-08T02:00:00Z"),
)

ASKED = len(odds_api.PER_EVENT_PROVIDER_MARKETS) + len(
    odds_api.ALTERNATE_PROVIDER_MARKETS
)

STAGING_CLAIM = "No staging file was written"


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_provider_shadow.py"
    spec = importlib.util.spec_from_file_location(
        "_script_run_provider_shadow_per_event", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# The provider, as the transport sees it.
# --------------------------------------------------------------------------

def _book(title: str, markets: list[dict]) -> dict:
    return {"key": title.lower(), "title": title, "markets": markets}


def _team_markets(home: str, away: str) -> list[dict]:
    return [
        {"key": "h2h", "outcomes": [
            {"name": home, "price": -140}, {"name": away, "price": 120}]},
        {"key": "totals", "outcomes": [
            {"name": "Over", "price": -110, "point": 6.5},
            {"name": "Under", "price": -110, "point": 6.5}]},
    ]


def _shots(player: str) -> list[dict]:
    return [{"key": "player_shots_on_goal", "outcomes": [
        {"name": "Over", "description": player, "price": -115, "point": 2.5},
        {"name": "Under", "description": player, "price": -105, "point": 2.5}]}]


def _event(event_id: str, home: str, away: str, commence: str,
           books: list[dict]) -> dict:
    return {"id": event_id, "commence_time": commence, "home_team": home,
            "away_team": away, "bookmakers": books}


def _bulk() -> list[dict]:
    """Three games at two books: the team fetch that always worked."""
    return [
        _event(event_id, home, away, commence,
               [_book("DraftKings", _team_markets(home, away)),
                _book("FanDuel", _team_markets(home, away))])
        for event_id, home, away, commence in GAMES
    ]


def _listing() -> list[dict]:
    return [{"id": event_id, "commence_time": commence, "home_team": home,
             "away_team": away} for event_id, home, away, commence in GAMES]


def _per_event_ok(event_id: str, *, quoted: bool = True) -> FakeResponse:
    for game_id, home, away, commence in GAMES:
        if game_id == event_id:
            books = [_book("DraftKings", _shots(f"Skater {event_id}"))] if quoted else []
            return FakeResponse(_event(game_id, home, away, commence, books))
    raise AssertionError(event_id)


class Transport:
    """Answers the three endpoints; `per_event` decides each game's answer."""

    def __init__(self, per_event) -> None:
        self.per_event = per_event
        self.calls: list[str] = []

    def __call__(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(url)
        if "/events/" in url and url.endswith("/odds"):
            event_id = url.split("/events/")[1].split("/")[0]
            return self.per_event(event_id, kwargs)
        if url.endswith("/events"):
            return FakeResponse(_listing())
        if url.endswith("/odds"):
            return FakeResponse(_bulk())
        raise AssertionError(f"unexpected request: {url}")


def _status(code: int, failing: set[str] | None = None):
    def answer(event_id: str, kwargs: object) -> FakeResponse:
        if failing is None or event_id in failing:
            return FakeResponse(status_code=code)
        return _per_event_ok(event_id)
    return answer


def _timeout(event_id: str, kwargs: object) -> FakeResponse:
    raise requests.ReadTimeout("read timed out")


def _all_ok(event_id: str, kwargs: object) -> FakeResponse:
    return _per_event_ok(event_id)


def _none_quoted(event_id: str, kwargs: object) -> FakeResponse:
    return _per_event_ok(event_id, quoted=False)


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def _shadow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event,
            *, cap: int = 320) -> tuple[int, str, str, Transport]:
    """The real script, with the workflow's own flags, over a stub transport."""
    module = load_script()
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
    capture = _Capture()
    with capture:
        code = module.main([
            "--live", "--props", "--overwrite-staging", "--horizon-days", "1",
            "--credit-cap", str(cap),
            "--staging-dir", str(tmp_path / "staging"),
            "--output-dir", str(tmp_path / "outputs"),
        ])
    return code, capture.out, capture.err, transport


class _Capture:
    """stdout and stderr of one call, without leaning on capsys twice."""

    def __enter__(self):
        import io
        self._out, self._err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        return self

    def __exit__(self, *exc):
        self.out, self.err = sys.stdout.getvalue(), sys.stderr.getvalue()
        sys.stdout, sys.stderr = self._out, self._err
        return False


def _staged(tmp_path: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(tmp_path / "staging" / name)


def _provenance(tmp_path: Path) -> dict:
    return json.loads(
        (tmp_path / "staging" / odds_api.PROVENANCE_FILENAME).read_text(encoding="utf-8")
    )


# --------------------------------------------------------------------------
# The script's exit code.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "per_event",
    [_status(503), _status(429), _timeout, _status(422)],
    ids=["http-503", "http-429", "read-timeout", "422-and-422-on-the-core-list"],
)
def test_every_per_event_request_failing_is_not_a_clean_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event
) -> None:
    code, out, err, transport = _shadow(tmp_path, monkeypatch, per_event)

    assert code == 4, (
        f"exit {code}: a fetch whose every per-event request failed must not "
        "read as clean (0) or as an empty slate (3)"
    )
    assert sum("/events/" in url and url.endswith("/odds") for url in transport.calls) >= 3
    # Everything the card and the reports need is still written: the team
    # prices are good and the card should be built from them.
    assert len(_staged(tmp_path, odds_api.STAGING_PRICES_FILENAME)) > 0
    assert (tmp_path / "staging" / odds_api.STAGING_PROPS_FILENAME).is_file()
    assert len(_provenance(tmp_path)["errors"]) == 3
    assert (tmp_path / "outputs" / "provider_shadow_verification.md").is_file()
    assert "3 per-event request(s) failed" in err


def test_one_failed_event_of_three_is_not_a_clean_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One game missing makes every per-event market INCOMPLETE on the card,
    which then carries no prop at all. That is not a blip to warn about."""
    code, out, err, _ = _shadow(tmp_path, monkeypatch, _status(503, {"ev0"}))

    props = _staged(tmp_path, odds_api.STAGING_PROPS_FILENAME)
    assert code == 4
    assert len(props) > 0, "the two games that answered are still staged"
    assert "1 per-event request(s) failed" in err


def test_a_complete_per_event_fetch_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, err, _ = _shadow(tmp_path, monkeypatch, _all_ok)

    assert code == 0, err
    assert len(_staged(tmp_path, odds_api.STAGING_PROPS_FILENAME)) > 0
    assert "per-event request(s) failed" not in err


def test_books_that_quoted_nothing_are_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every request answered and no book posted a prop — August, or a
    morning before the books open. An absence, and not a fault."""
    code, out, err, _ = _shadow(tmp_path, monkeypatch, _none_quoted)

    assert code == 0, err
    assert len(_staged(tmp_path, odds_api.STAGING_PROPS_FILENAME)) == 0
    assert _provenance(tmp_path)["errors"] == []


def test_a_budget_skip_is_a_warning_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cap buys one event here and says so; nothing failed."""
    code, out, err, transport = _shadow(tmp_path, monkeypatch, _all_ok, cap=ASKED)

    provenance = _provenance(tmp_path)
    assert sum("/events/" in url and url.endswith("/odds") for url in transport.calls) == 1
    assert any("cap would have been exceeded" in item for item in provenance["warnings"])
    assert provenance["errors"] == []
    assert code == 0, err


# --------------------------------------------------------------------------
# What the errors say.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("per_event", "cause"),
    [(_status(503), "HTTP 503"), (_status(422), "HTTP 422"),
     (_timeout, "could not be reached (ReadTimeout)")],
    ids=["http-503", "422-fallback-retry", "read-timeout"],
)
def test_a_per_event_error_does_not_claim_no_staging_file_was_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, cause: str
) -> None:
    """Each path that records a per-event failure: a refused request, the
    core-market retry after a 422, and a request that never came back."""
    code, out, err, _ = _shadow(tmp_path, monkeypatch, per_event)

    errors = _provenance(tmp_path)["errors"]
    report = (tmp_path / "outputs" / "provider_shadow_verification.md").read_text(
        encoding="utf-8"
    )
    assert (tmp_path / "staging" / odds_api.STAGING_PROPS_FILENAME).is_file()
    assert len(errors) == 3 and all(cause in item for item in errors), errors
    assert not any(STAGING_CLAIM in item for item in errors), errors
    assert STAGING_CLAIM not in report
    assert STAGING_CLAIM not in err


def test_a_team_fetch_failure_still_says_no_staging_file_was_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There it is true: the script stops before writing anything."""
    module = load_script()
    transport = Transport(_all_ok)

    def bulk_down(url: str, **kwargs: object) -> FakeResponse:
        if url.endswith("/odds") and "/events/" not in url:
            return FakeResponse(status_code=503)
        return transport(url, **kwargs)

    real = odds_api.OddsApiProvider
    monkeypatch.setattr(
        module.odds_api, "OddsApiProvider",
        lambda: real(environment=ENVIRONMENT, requester=bulk_down, regions="us"),
    )
    monkeypatch.setattr(
        module, "load_provider_env",
        lambda: ProviderEnvLoadResult(path=tmp_path / ".env"),
    )
    monkeypatch.setattr(module, "datetime", _Frozen)
    capture = _Capture()
    with capture:
        code = module.main([
            "--live", "--props", "--overwrite-staging", "--credit-cap", "320",
            "--staging-dir", str(tmp_path / "staging"),
            "--output-dir", str(tmp_path / "outputs"),
        ])

    assert code == 2
    assert not (tmp_path / "staging" / odds_api.STAGING_PRICES_FILENAME).exists()
    assert STAGING_CLAIM in capture.err


# --------------------------------------------------------------------------
# The workflow: the price step and the health step, run from the YAML.
# --------------------------------------------------------------------------

def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        steps = job.get("steps", [])
        if any(step.get("id") == "prices" for step in steps):
            return steps
    raise AssertionError("no job fetches prices")


def _step(id_: str) -> dict:
    for step in _steps():
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
    """A workspace the health step would otherwise call clean: player logs
    on disk and a warm boxscore cache."""
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


def _price_step(work: Path, tmp_path: Path, code: int) -> tuple[str, dict[str, str]]:
    """Run the price step with `python` standing in for the script's exit.
    Returns the step outcome as the runner records it, and its outputs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "python"
    stub.write_text(f"#!/bin/sh\nexit {code}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    output = tmp_path / "prices_output"
    output.write_text("", encoding="utf-8")
    block = _render(_step("prices")["run"], {
        "inputs.props_credit_cap || '320'": "320",
    })
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "GITHUB_OUTPUT": str(output)}
    result = _bash(block, work, env)
    return ("success" if result.returncode == 0 else "failure"), _outputs(output)


def _health_step(work: Path, tmp_path: Path, outcome: str,
                 outputs: dict[str, str]) -> tuple[dict[str, str], str]:
    output = tmp_path / "health_output"
    output.write_text("", encoding="utf-8")
    block = _render(_step("health")["run"], {
        "steps.results.outcome": "success",
        "steps.prices.outputs.empty_slate": outputs.get("empty_slate", ""),
        "steps.prices.outcome": outcome,
    })
    result = _bash(block, work, {**os.environ, "GITHUB_OUTPUT": str(output)})
    assert result.returncode == 0, result.stderr
    notes = (work / "run_degraded.txt").read_text(encoding="utf-8")
    return _outputs(output), notes


@pytest.mark.parametrize(
    ("per_event", "degraded"),
    [(_status(503), "true"), (_status(503, {"ev1"}), "true"),
     (_all_ok, "false"), (_none_quoted, "false")],
    ids=["every-event-503", "one-event-503", "every-event-answers", "nothing-quoted"],
)
def test_the_run_health_follows_the_per_event_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, degraded: str
) -> None:
    """End to end: the real script's exit, through the price step, into the
    `degraded` the card-feed status and the backup's precheck read."""
    code, _, _, _ = _shadow(tmp_path, monkeypatch, per_event)
    work = _runner(tmp_path)

    outcome, outputs = _price_step(work, tmp_path, code)
    health, notes = _health_step(work, tmp_path, outcome, outputs)

    assert health["degraded"] == degraded, (code, outcome, notes)
    assert outputs.get("empty_slate", "") != "true"


def test_the_degraded_note_names_the_per_event_fetch(tmp_path: Path) -> None:
    """The note is what the issue comment and card-feed carry, so it has to
    say what is missing — not "built from whatever was already staged",
    which is the note for a price fetch that wrote nothing."""
    work = _runner(tmp_path)

    outcome, outputs = _price_step(work, tmp_path, 4)
    health, notes = _health_step(work, tmp_path, outcome, outputs)

    assert outcome == "failure", "exit 4 must not be swallowed by the step"
    assert health["degraded"] == "true"
    assert "per-event" in notes and "regulation three-way" in notes
    assert "absent, not unquoted" in notes
    assert "whatever was already staged" not in notes


@pytest.mark.parametrize(("code", "outcome", "degraded"),
                         [(0, "success", "false"), (2, "failure", "true"),
                          (3, "success", "false")])
def test_the_other_exits_keep_their_meaning(
    tmp_path: Path, code: int, outcome: str, degraded: str
) -> None:
    work = _runner(tmp_path)

    step_outcome, outputs = _price_step(work, tmp_path, code)
    health, notes = _health_step(work, tmp_path, step_outcome, outputs)

    assert step_outcome == outcome
    assert health["degraded"] == degraded
    assert "per-event" not in notes
