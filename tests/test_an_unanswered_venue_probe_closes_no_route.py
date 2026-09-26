"""The venue probe closed the venue route on calls that were never answered.

`probe_low_vig_venues.py` asks one past event, region by region, whether the
low-vig venues quote NHL player props. A call the provider refused was
recorded with its error and skipped; a call the credit cap ruled out was
recorded as skipped. Neither reached the responses the venue table is built
from, and `_verdict` looked only at that table. So when nothing was answered
the table was empty, and an empty table is exactly what the decisive negative
reads: "No target venue returned a single NHL player-prop market on this
event. The venue route cannot carry the props model". The script then
returned 0 whatever had happened.

Found by the failure-shape audit (confirmed 3/3 by the reproduce,
reachability and intent refuters), replayed through the real `main()` with a
real `OddsApiProvider` and only the HTTP transport stubbed, no credit spent:

* all 9 historical calls answering HTTP 503 (404 from a mistyped event id,
  422, and a transport timeout alike): 0 of 9 answered, 0 credits spent, the
  decisive negative bolded in the report, exit 0;
* `--credit-cap 5`, every call skipped for the cap and 0 requests sent: the
  same verdict, exit 0; `--credit-cap 60` skips all 5 props calls (worst
  case 70 each) while the 4 moneyline calls run: the same verdict, exit 0;
* the props calls failing while the moneyline calls answered: 40 credits,
  Pinnacle and Novig shown as "h2h yes, 0 prop markets" — the precise
  "lists the moneyline and not the props" pattern
  `docs/the_venue_route_is_closed.md` calls decisive — with no props call
  answered, exit 0;
* only `props@eu` and `props@bookmakers` failing — the two calls that carried
  every prop the real 130-credit run of 2026-09-02 found (50 and 40
  credits) — was enough to flip that run's answer to the decisive negative,
  exit 0.

The Venue Probe workflow writes the report to the run summary and the
artifact whatever the step did, and nothing in it reads the per-call errors,
so a provider outage or a mistyped input would publish a green, bolded
negative with no measurement behind it.

What these tests hold, driving the real script over a stub transport and
running the workflow's own step blocks under `bash -eo pipefail`:

* a verdict that no venue quotes props is stated as closing the route only
  when every props call was answered;
* no props call answered — failed, skipped for the cap, or both — is "No
  measurement", naming each call and why;
* some props calls unanswered: the verdict names them, and neither the
  negative nor a positive reads as covering the venues they would have asked;
* any planned call unanswered exits 3, the code this script already uses
  for a provider refusal, after the report is written, and the workflow
  still puts that report in the run summary; every call answered exits 0 with
  the verdict exactly as before.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import pytest
import requests
import yaml

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers.odds_api import OddsApiProvider


SCRIPT = PROJECT_ROOT / "scripts" / "probe_low_vig_venues.py"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "venue-probe.yml"

#: Never a real credential, and never sent anywhere: the transport is a stub.
ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}
#: A fake id on purpose: a real one is key-shaped and the secrets scan
#: refuses it (see tests/test_venue_probe.py).
EVENT = "evt-venue-unanswered"
SNAPSHOT = "2025-01-14T20:10:00Z"
WHICH = ["--event-id", EVENT, "--snapshot", SNAPSHOT]

#: The decisive negative, as the script words it. Neither half may be said
#: about a run in which a props call went unanswered.
DECISIVE = "No target venue returned a single NHL player-prop market on this event"
CLOSES_ROUTE = "cannot carry the props model"

DEFAULT_PROPS_STEPS = ("props@us_ex", "props@eu", "props@uk", "props@au", "props@bookmakers")
DEFAULT_H2H_STEPS = ("h2h@us_ex", "h2h@eu", "h2h@uk", "h2h@au")

Answer = Callable[[str, dict[str, str]], Any]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_probe_low_vig_venues_unanswered", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    loaded = _load()
    # Never read a local `.env`: the provider below carries its own stub.
    monkeypatch.setattr(loaded, "load_provider_env", lambda: None)
    return loaded


def _quote(name: str, point: float, over: int, under: int) -> list[dict]:
    return [
        {"description": name, "name": "Over", "point": point, "price": over},
        {"description": name, "name": "Under", "point": point, "price": under},
    ]


MONEYLINE = [
    {"name": "Anaheim Ducks", "price": 150},
    {"name": "Washington Capitals", "price": -170},
]


def _event(books: dict[str, dict[str, list[dict]]]) -> dict:
    """A historical per-event response: `data` wraps the event."""
    return {
        "timestamp": SNAPSHOT,
        "data": {
            "id": EVENT,
            "bookmakers": [
                {"key": book, "markets": [{"key": k, "outcomes": o} for k, o in markets.items()]}
                for book, markets in books.items()
            ],
        },
    }


def _ok(payload: dict, cost: int) -> FakeResponse:
    return FakeResponse(payload, headers={"x-requests-last": str(cost), "x-requests-remaining": "3000000"})


def _step_of(params: dict[str, str]) -> str:
    """The script's own step name, read back off what it asked for."""
    where = params.get("regions") or "bookmakers"
    kind = "h2h" if params.get("markets") == "h2h" else "props"
    return f"{kind}@{where}"


def _probe(module: ModuleType, tmp_path: Path, answer: Answer, *extra: str, cap: str = "400"):
    """Run the real main() over a stub transport. `answer(step, params)`
    returns the response for one historical call, or raises."""
    asked: list[str] = []

    def historical(url: str, *, params: dict[str, str], timeout: Any) -> Any:
        step = _step_of(params)
        asked.append(step)
        return answer(step, params)

    requester = RecordingRequester(
        {
            "/historical/": historical,
            "/v4/sports": FakeResponse([], headers={"x-requests-last": "0", "x-requests-remaining": "3000000"}),
        }
    )
    provider = OddsApiProvider(environment=ENVIRONMENT, requester=requester)
    raw = tmp_path / "raw"
    out = tmp_path / "outputs"
    code = module.main(
        ["--live", "--credit-cap", cap, *WHICH, *extra, "--raw-dir", str(raw), "--output-dir", str(out)],
        provider=provider,
    )
    result = json.loads((out / module.JSON_FILENAME).read_text(encoding="utf-8"))
    markdown = (out / module.MARKDOWN_FILENAME).read_text(encoding="utf-8")
    return code, result, markdown, asked


def _status(code: int) -> Answer:
    def answer(step: str, params: dict[str, str]) -> Any:
        return FakeResponse(status_code=code)
    return answer


def _timeout(step: str, params: dict[str, str]) -> Any:
    raise requests.Timeout("read timed out")


def _assert_no_route_is_closed(verdict: str, markdown: str) -> None:
    assert CLOSES_ROUTE not in verdict, verdict
    assert DECISIVE not in verdict, verdict
    assert CLOSES_ROUTE not in markdown
    assert DECISIVE not in markdown


# --------------------------------------------------------------------------
# Nothing answered is no measurement, and the run fails.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("answer", "shown"),
    [
        (_status(503), "HTTP 503"),
        (_status(404), "HTTP 404"),
        (_status(422), "HTTP 422"),
        (_status(429), "HTTP 429"),
        (_timeout, "could not be reached"),
    ],
    ids=["outage-503", "mistyped-event-404", "bad-snapshot-422", "throttled-429", "timeout"],
)
def test_every_call_failing_is_no_measurement_and_exits_nonzero(
    module: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str], answer: Answer, shown: str
) -> None:
    code, result, markdown, asked = _probe(module, tmp_path, answer)
    captured = capsys.readouterr()

    assert len(asked) == 9, "all nine planned calls were sent"
    assert result["spent"] == 0
    assert all("error" in c for c in result["calls"])
    verdict = result["verdict"]
    _assert_no_route_is_closed(verdict, markdown)
    assert verdict.startswith("No measurement"), verdict
    for step in DEFAULT_PROPS_STEPS:
        assert step in verdict, step
    assert shown in verdict
    assert f"**{verdict}**" in markdown, "the report still carries the verdict"
    assert "## Calls" in markdown and shown in markdown, "and the calls that failed"
    assert verdict in captured.out
    assert code == 3
    assert "9 of 9" in captured.err


def test_every_call_skipped_for_the_cap_is_no_measurement(
    module: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def never(step: str, params: dict[str, str]) -> Any:
        raise AssertionError(f"{step} was sent past a cap of 5")

    code, result, markdown, asked = _probe(module, tmp_path, never, cap="5")
    captured = capsys.readouterr()

    assert asked == []
    assert all("skipped" in c for c in result["calls"]) and len(result["calls"]) == 9
    verdict = result["verdict"]
    _assert_no_route_is_closed(verdict, markdown)
    assert verdict.startswith("No measurement"), verdict
    for step in DEFAULT_PROPS_STEPS:
        assert step in verdict, step
    assert "skipped for the cap" in verdict
    assert code == 3
    assert "9 of 9" in captured.err


def test_a_cap_that_skips_every_props_call_is_no_measurement_whatever_the_moneyline_says(
    module: ModuleType, tmp_path: Path
) -> None:
    """A cap of 60 is below one props call's worst case (7 markets x 10), so
    only the four moneyline calls run. They find Pinnacle and Novig listing
    the moneyline: the table then reads "h2h yes, 0 prop markets" for both,
    and nobody asked either for a prop."""
    def answer(step: str, params: dict[str, str]) -> Any:
        assert step.startswith("h2h@"), f"{step} was sent past a cap of 60"
        return _ok(_event({"pinnacle": {"h2h": MONEYLINE}, "novig": {"h2h": MONEYLINE}}), 10)

    code, result, markdown, asked = _probe(module, tmp_path, answer, cap="60")

    assert sorted(asked) == sorted(DEFAULT_H2H_STEPS)
    assert result["venues"]["pinnacle"]["h2h"] is True
    assert result["venues"]["pinnacle"]["prop_markets"] == {}
    verdict = result["verdict"]
    _assert_no_route_is_closed(verdict, markdown)
    assert verdict.startswith("No measurement"), verdict
    for step in DEFAULT_PROPS_STEPS:
        assert step in verdict, step
    assert code == 3


def test_props_failing_while_the_moneyline_answers_is_not_the_decisive_negative(
    module: ModuleType, tmp_path: Path
) -> None:
    """The worst shape: the moneyline answers, the props do not, and the
    table shows exactly the pattern the closed-route doc calls decisive."""
    def answer(step: str, params: dict[str, str]) -> Any:
        if step.startswith("props@"):
            return FakeResponse(status_code=503)
        return _ok(_event({"pinnacle": {"h2h": MONEYLINE}, "novig": {"h2h": MONEYLINE}}), 10)

    code, result, markdown, _ = _probe(module, tmp_path, answer)

    assert result["spent"] == 40
    assert result["venues"]["pinnacle"]["h2h"] is True
    assert result["venues"]["novig"]["prop_markets"] == {}
    verdict = result["verdict"]
    _assert_no_route_is_closed(verdict, markdown)
    assert verdict.startswith("No measurement"), verdict
    assert "HTTP 503" in verdict
    assert code == 3


# --------------------------------------------------------------------------
# Some props calls unanswered: say which, and close nothing they covered.
# --------------------------------------------------------------------------

def test_the_two_calls_that_carried_the_real_answer_failing_names_them(
    module: ModuleType, tmp_path: Path
) -> None:
    """The 2026-09-02 run found every prop it found in `props@eu` and
    `props@bookmakers`. With only those two failing, the others answered
    empty and the moneyline answered, the old verdict closed the route."""
    def answer(step: str, params: dict[str, str]) -> Any:
        if step in ("props@eu", "props@bookmakers"):
            return FakeResponse(status_code=503)
        if step.startswith("h2h@"):
            return _ok(_event({"pinnacle": {"h2h": MONEYLINE}}), 10)
        return _ok(_event({}), 0)

    code, result, markdown, _ = _probe(module, tmp_path, answer)

    verdict = result["verdict"]
    _assert_no_route_is_closed(verdict, markdown)
    assert not verdict.startswith("No measurement"), "three props calls were answered"
    assert "3 of 5 props calls" in verdict
    for step in DEFAULT_PROPS_STEPS:
        assert step in verdict, step
    assert verdict.count("HTTP 503") == 2, "each unanswered call, and why"
    assert "does not close the venue route" in verdict
    assert code == 3


def test_a_positive_answer_with_an_unanswered_props_call_names_the_gap(
    module: ModuleType, tmp_path: Path
) -> None:
    """Pinnacle quoting in `eu` is a measurement and stays one. But the
    bookmakers call is the only one that asks LowVig or BetOnline by name, so
    a verdict naming only Pinnacle must not read as saying they quote none."""
    def answer(step: str, params: dict[str, str]) -> Any:
        if step == "props@bookmakers":
            return FakeResponse(status_code=503)
        if step == "props@eu":
            return _ok(_event({"pinnacle": {"player_points": _quote("Tom Wilson", 0.5, -115, -115)}}), 10)
        return _ok(_event({}), 0)

    code, result, markdown, _ = _probe(module, tmp_path, answer)

    verdict = result["verdict"]
    assert "pinnacle: props quoted" in verdict
    assert "props@bookmakers" in verdict
    assert "HTTP 503" in verdict
    _assert_no_route_is_closed(verdict, markdown)
    assert code == 3


def test_a_failed_moneyline_call_keeps_a_measured_props_verdict_but_fails_the_run(
    module: ModuleType, tmp_path: Path
) -> None:
    """Every props call answered with nothing: that IS the decisive negative,
    measured. A moneyline call that failed does not change it — but the
    table's h2h column no longer covers that region, so the verdict says so
    and the run does not exit clean."""
    def answer(step: str, params: dict[str, str]) -> Any:
        if step == "h2h@eu":
            return FakeResponse(status_code=503)
        return _ok(_event({}), 0)

    code, result, _, _ = _probe(module, tmp_path, answer)

    verdict = result["verdict"]
    assert DECISIVE in verdict and CLOSES_ROUTE in verdict
    assert "h2h@eu" in verdict
    assert code == 3


# --------------------------------------------------------------------------
# Every call answered: exactly the verdict it always gave, and exit 0.
# --------------------------------------------------------------------------

def test_every_call_answered_with_nothing_is_still_the_decisive_negative(
    module: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, result, markdown, asked = _probe(module, tmp_path, lambda step, params: _ok(_event({}), 0))
    captured = capsys.readouterr()

    assert len(asked) == 9
    assert result["verdict"] == (
        "No target venue returned a single NHL player-prop market on this "
        "event. The venue route cannot carry the props model: a book "
        "that lists the moneyline and not the props offers nothing for a "
        "props opinion to be placed against."
    )
    assert f"**{result['verdict']}**" in markdown
    assert code == 0
    assert captured.err == ""


def test_every_call_answered_with_props_exits_zero_with_the_positive_verdict(
    module: ModuleType, tmp_path: Path
) -> None:
    def answer(step: str, params: dict[str, str]) -> Any:
        if step == "props@eu":
            return _ok(_event({"pinnacle": {"player_points": _quote("Tom Wilson", 0.5, -115, -115)}}), 10)
        return _ok(_event({}), 0)

    code, result, _, _ = _probe(module, tmp_path, answer)

    assert result["verdict"].startswith("pinnacle: props quoted, median two-sided margin")
    assert "unanswered" not in result["verdict"]
    assert code == 0


# --------------------------------------------------------------------------
# The workflow: a failed probe goes red and its report still reaches the summary.
# --------------------------------------------------------------------------

def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    (job,) = document["jobs"].values()
    return job["steps"]


def _step(name: str) -> dict:
    for step in _steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step {name!r}")


def _render(block: str, values: dict[str, str]) -> str:
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _bash(block: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def test_the_probe_step_does_not_swallow_the_scripts_exit(tmp_path: Path) -> None:
    """The step's own block, with a stub `python` that exits as the script
    now does on an unanswered run: the step must fail, so the run goes red.
    A `continue-on-error` on the step would turn that red back to green."""
    step = _step("Probe the venues")
    assert "continue-on-error" not in step
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "python"
    stub.write_text('#!/bin/sh\necho "$@" > "$STUB_ARGS"\nexit 3\n', encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    block = _render(
        step["run"],
        {"inputs.credit_cap": "400", "inputs.regions": "us_ex,eu,uk,au",
         "inputs.event_id": EVENT, "inputs.snapshot": SNAPSHOT},
    )
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
           "STUB_ARGS": str(tmp_path / "args.txt")}

    result = _bash(block, tmp_path, env)

    assert "scripts/probe_low_vig_venues.py --live" in (tmp_path / "args.txt").read_text(encoding="utf-8")
    assert result.returncode == 3, result.stderr


def test_an_unanswered_runs_report_still_reaches_the_run_summary(
    module: ModuleType, tmp_path: Path
) -> None:
    """The real script writes the report of a run in which every call
    failed; the workflow's own summary step, which runs after a failed step,
    carries its "No measurement" verdict to the run summary."""
    work = tmp_path / "checkout"
    (work / "data").mkdir(parents=True)
    code, result, _, _ = _probe(module, tmp_path, _status(503))
    assert code == 3
    (work / "data" / "outputs").mkdir()
    for name in (module.JSON_FILENAME, module.MARKDOWN_FILENAME):
        (work / "data" / "outputs" / name).write_bytes((tmp_path / "outputs" / name).read_bytes())

    for name in ("Write the result to the run summary", "Upload what came back"):
        assert str(_step(name).get("if", "")).strip() == "always()", name
    summary = tmp_path / "summary.md"
    ran = _bash(_step("Write the result to the run summary")["run"], work,
                {"PATH": os.environ.get("PATH", ""), "GITHUB_STEP_SUMMARY": str(summary)})

    assert ran.returncode == 0, ran.stderr
    text = summary.read_text(encoding="utf-8")
    assert f"**{result['verdict']}**" in text
    assert "No measurement" in text
    assert CLOSES_ROUTE not in text
