"""A game day whose scratch lists were not captured exited 0, and nothing gated it.

`scripts/capture_deployment.py` records the NHL's own pre-game scratch list
with the instant it was read, five times a day in season, so that a season
from now "was the scratch public before the market moved?" can be answered.
Who was scratched can be rebuilt from box scores later; WHEN the list became
public cannot, and that instant is the whole point of the capture.

Found by the failure-shape audit and confirmed by all three refuters, who drove
the real `main` through the real `nhl_api._get_json` (its status handling and
its four-attempt retry loop) with only the HTTP call stubbed. With two games
today:

* every right-rail fetch HTTP 403 (2 requests), HTTP 503 past the retries
  (8 requests), or unreachable (8 requests): the script printed "No
  deployment rows returned; nothing written." and **exited 0**, with no file
  written. A moved endpoint or a block on that one path would have lost the
  whole season behind green runs.
* one game 429 past the retries and the other a real body: exit 0 and "2
  game(s), 0 scratch row(s) -> ...", with only the second game in the file.
* a 200 body with no `gameInfo` (`{'message': 'not found'}`): exit 0 and four
  rows with no player and `scratch_count` 0 — exactly the row the docstring
  reserves for "we looked and it was empty". The live API answers a bogus id
  with a 404 rather than this body, so this is the schema-drift path, not
  today's; but if the block ever moves, every run would keep writing
  healthy-looking empty lists.

And the workflow could not have seen any of it. "Capture deployment" is
`continue-on-error` with no `id`, and the only gate in the job (#128) reads
`steps.lines.outcome`, so even the script's one failing exit (2, on an
unreadable schedule) left the run green. #128 made exactly this loss red for
the Daily Faceoff line units and left the scratch list out.

What these tests hold, through the real script and the real workflow file:

* no game captured -> exit 2 and nothing written; no games today -> exit 0;
* a partial capture keeps what came back, names the games it lost in a
  `::warning::`, and does not claim every game — the same rule
  `fetch_nhl_data.py` and `capture_line_combinations.py` already follow;
* a body without a `gameInfo` block for both teams is a game not captured,
  never an empty scratch list, while a real empty list still is one;
* the capture step has an id, stays `continue-on-error`, and one gate after
  every upload reads its outcome and fails the run saying why.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
import requests
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api

from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
CAPTURE_STEP = "Capture deployment"

#: The 14:00 UTC cron on a league day (10:00 Eastern, 2026-10-15).
AT = "2026-10-15T14:00:00+00:00"
DAY = "2026-10-15"
EARLY, LATE = "2026020077", "2026020078"


def _clock(instant: str) -> type:
    fixed = datetime.fromisoformat(instant)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401 - the script's only use
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    return Frozen


def _schedule(*games: dict) -> dict:
    """`/v1/schedule/now`: two games tonight, and one tomorrow the day filter drops."""
    tonight = games or (
        {"id": int(EARLY), "startTimeUTC": f"{DAY}T23:00:00Z"},
        # 20:00 Eastern: still tonight's league date, though tomorrow in UTC.
        {"id": int(LATE), "startTimeUTC": "2026-10-16T00:00:00Z"},
    )
    return {"gameWeek": [
        {"games": list(tonight)},
        {"games": [{"id": 2026020099, "startTimeUTC": "2026-10-16T23:00:00Z"}]},
    ]}


def _scratch(player_id: int, first: str, last: str) -> dict:
    return {"id": player_id, "firstName": {"default": first}, "lastName": {"default": last}}


def _rail(home: list[dict], away: list[dict]) -> dict:
    """A right-rail body keyed exactly as the live endpoint keys it.

    Taken from real responses read on 2026-09-25 (2025020001, and opening
    night 2026020001, whose scratch lists were present and empty four days
    out): `gameInfo` carries `referees`, `linesmen`, `awayTeam` and
    `homeTeam`, and each team carries `headCoach` and `scratches`.
    """
    return {
        "seasonSeries": [],
        "seasonSeriesWins": {"awayTeamWins": 0, "homeTeamWins": 0},
        "gameInfo": {
            "referees": [{"fullName": {"default": "Kelly Sutherland"}, "sweaterNumber": 11}],
            "linesmen": [{"fullName": {"default": "Scott Cherrey"}, "sweaterNumber": 50}],
            "awayTeam": {"headCoach": {"default": "Jeff Blashill"}, "scratches": away},
            "homeTeam": {"headCoach": {"default": "Paul Maurice"}, "scratches": home},
        },
        "teamSeasonStats": {},
    }


SCRATCHED = _rail([_scratch(8479393, "Noah", "Gregor")], [])
EMPTY = _rail([], [])


class _Response:
    def __init__(self, status: int, body: object = None) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> object:
        if self.status_code != 200:
            raise ValueError("an HTML error page is not JSON")
        return self._body


class FakeNhlApi:
    """`requests.get` for the two NHL endpoints, counting every request.

    Each right-rail answer is a status (anything but 200 is an error page), an
    exception to raise, or a dict served with 200 — the same answer on every
    attempt, so a retryable status really does run the retries out.
    """

    def __init__(self, rails: dict[str, object], schedule: object = None) -> None:
        self.rails = rails
        self.schedule = _schedule() if schedule is None else schedule
        self.calls: Counter[str] = Counter()

    def __call__(self, url: str, params=None, timeout=None) -> _Response:
        if url.endswith("/v1/schedule/now"):
            self.calls["schedule"] += 1
            answer = self.schedule
        else:
            game_id = url.split("/gamecenter/")[1].split("/")[0]
            self.calls[game_id] += 1
            answer = self.rails[game_id]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, int):
            return _Response(answer)
        return _Response(200, answer)


def _run(tmp_path: Path, monkeypatch, capsys, api: FakeNhlApi):
    """The real `main`, through the real `_get_json`; only HTTP, sleep and clock stubbed."""
    deployment = load_script("capture_deployment.py")
    monkeypatch.setattr(deployment, "datetime", _clock(AT))
    monkeypatch.setattr(deployment, "_default_requester", api)
    monkeypatch.setattr(
        deployment, "_get_json",
        functools.partial(nhl_api._get_json, sleeper=lambda seconds: None),
    )
    processed = tmp_path / "processed"
    code = deployment.main(["--processed-dir", str(processed), "--polite-seconds", "0"])
    printed = capsys.readouterr()
    return code, printed.out, printed.err, deployment.capture_path(DAY, processed_dir=processed)


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _summary(out: str) -> str:
    """The line that says how many of tonight's games this run captured."""
    lines = [line for line in out.splitlines() if "scratch row(s) at" in line]
    assert len(lines) == 1, f"one summary line:\n{out}"
    return lines[0]


# -- the script ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "attempts"),
    [
        pytest.param(403, 1, id="http-403"),
        pytest.param(404, 1, id="http-404-html"),
        pytest.param(503, nhl_api.MAX_ATTEMPTS, id="http-503-past-the-retries"),
        pytest.param(requests.ConnectionError("refused"), nhl_api.MAX_ATTEMPTS, id="unreachable"),
    ],
)
def test_a_game_day_with_no_scratch_list_captured_exits_2_and_writes_nothing(
    tmp_path, monkeypatch, capsys, answer, attempts,
) -> None:
    api = FakeNhlApi({EARLY: answer, LATE: answer})
    code, out, err, path = _run(tmp_path, monkeypatch, capsys, api)

    assert api.calls[EARLY] == attempts and api.calls[LATE] == attempts, (
        "the real retry loop ran for both games"
    )
    assert code == 2, f"two games tonight and none captured must fail the step:\n{out}{err}"
    assert not path.exists(), "a capture of nothing writes nothing"
    assert EARLY in err and LATE in err, "the lost games are named"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"message": "not found"}, id="no-gameInfo"),
        pytest.param({"gameInfo": None}, id="gameInfo-null"),
        pytest.param({"gameInfo": {"referees": [], "linesmen": []}}, id="no-team-blocks"),
        pytest.param(
            {"gameInfo": {"homeTeam": {"headCoach": {"default": "Paul Maurice"},
                                       "scratches": []}}},
            id="one-team-block",
        ),
    ],
)
def test_a_body_without_the_scratch_lists_is_not_an_empty_scratch_list(
    tmp_path, monkeypatch, capsys, body,
) -> None:
    code, out, err, path = _run(
        tmp_path, monkeypatch, capsys, FakeNhlApi({EARLY: body, LATE: body})
    )
    assert code == 2, f"a list nobody saw was recorded as an empty one:\n{out}{err}"
    assert not path.exists(), "no scratch_count-0 row may stand for a list that was not there"
    assert EARLY in err and LATE in err


@pytest.mark.parametrize(
    "lost",
    [
        pytest.param(429, id="http-429-past-the-retries"),
        pytest.param({"message": "not found"}, id="200-without-gameInfo"),
    ],
)
def test_a_partial_capture_keeps_what_came_back_and_names_what_did_not(
    tmp_path, monkeypatch, capsys, lost,
) -> None:
    code, out, err, path = _run(
        tmp_path, monkeypatch, capsys, FakeNhlApi({EARLY: lost, LATE: SCRATCHED})
    )
    assert code == 0, "one game read is a capture; the red X is for a night with none"
    frame = _read(path)
    assert set(frame["game_id"]) == {LATE}, "only the game that answered is in the file"
    assert "Noah Gregor" in set(frame["player"])

    warnings = [line for line in out.splitlines() if line.startswith("::warning::")]
    assert len(warnings) == 1, f"a partial capture must warn on the run page:\n{out}"
    assert EARLY in warnings[0] and LATE not in warnings[0], warnings[0]
    assert _summary(out).startswith("1 of 2 game(s) captured"), "the summary claimed every game"
    assert EARLY in err, "the reason is in the log"


def test_a_scheduled_game_without_an_id_is_named_not_skipped(
    tmp_path, monkeypatch, capsys,
) -> None:
    schedule = _schedule(
        {"startTimeUTC": f"{DAY}T23:00:00Z"},
        {"id": int(LATE), "startTimeUTC": "2026-10-16T00:00:00Z"},
    )
    code, out, err, path = _run(
        tmp_path, monkeypatch, capsys, FakeNhlApi({LATE: SCRATCHED}, schedule=schedule)
    )
    assert code == 0
    assert set(_read(path)["game_id"]) == {LATE}
    warnings = [line for line in out.splitlines() if line.startswith("::warning::")]
    assert len(warnings) == 1 and "no id" in warnings[0], out
    assert _summary(out).startswith("1 of 2 game(s) captured")


def test_a_real_empty_scratch_list_is_still_a_capture(tmp_path, monkeypatch, capsys) -> None:
    """Opening night four days out: both lists present and empty. That IS a capture."""
    code, out, err, path = _run(
        tmp_path, monkeypatch, capsys, FakeNhlApi({EARLY: EMPTY, LATE: EMPTY})
    )
    assert code == 0, f"{out}{err}"
    frame = _read(path)
    assert len(frame) == 4, "one row per side per game: we looked and it was empty"
    assert set(frame["game_id"]) == {EARLY, LATE}
    assert set(frame["scratch_count"]) == {"0"} and set(frame["player"]) == {""}
    assert set(frame["head_coach"]) == {"Paul Maurice", "Jeff Blashill"}
    assert "::warning::" not in out, "a full capture is not a degraded one"
    assert _summary(out).startswith("2 of 2 game(s) captured")


def test_no_games_today_is_not_a_fault(tmp_path, monkeypatch, capsys) -> None:
    api = FakeNhlApi({}, schedule={"gameWeek": [{"games": [
        {"id": 2026020099, "startTimeUTC": "2026-10-16T23:00:00Z"},
    ]}]})
    code, out, err, path = _run(tmp_path, monkeypatch, capsys, api)
    assert code == 0, f"{out}{err}"
    assert not path.exists()
    assert set(api.calls) == {"schedule"}, "no right-rail is read on a night with no games"


def test_an_unreadable_schedule_is_a_failed_capture(tmp_path, monkeypatch, capsys) -> None:
    api = FakeNhlApi({}, schedule=503)
    code, out, err, path = _run(tmp_path, monkeypatch, capsys, api)
    assert api.calls["schedule"] == nhl_api.MAX_ATTEMPTS
    assert code == 2
    assert not path.exists()


# -- the workflow -------------------------------------------------------------


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for job in document["jobs"].values() for step in job["steps"]]


def _capture() -> dict:
    matches = [s for s in _steps() if s.get("name") == CAPTURE_STEP]
    assert len(matches) == 1, f"exactly one step named {CAPTURE_STEP!r}"
    return matches[0]


def _gate() -> tuple[int, dict]:
    # Read the id off the capture step, so a renamed id cannot leave a gate
    # watching a step that no longer exists.
    reads = f"steps.{_capture().get('id')}.outcome == 'failure'"
    matches = [
        (index, step) for index, step in enumerate(_steps())
        if reads in str(step.get("if", ""))
    ]
    assert len(matches) == 1, f"exactly one step must fail the run on {reads!r}"
    return matches[0]


def test_the_deployment_capture_can_still_never_cost_the_prices() -> None:
    step = _capture()
    assert step.get("id") == "deployment", "a step without an id has an outcome nothing can read"
    assert step.get("continue-on-error") is True
    assert str(step.get("if", "")).startswith("always()")


def test_the_gate_runs_after_every_upload_and_is_not_itself_forgiven() -> None:
    index, gate = _gate()
    uploads = [
        i for i, step in enumerate(_steps())
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert uploads, "the workflow uploads its captures"
    assert index > max(uploads), "a red run must never stop a capture from being kept"
    assert "always()" in str(gate.get("if", ""))
    assert gate.get("continue-on-error") in (None, False)


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_gate_fails_and_says_why(tmp_path) -> None:
    _, gate = _gate()
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", gate["run"]],
        cwd=tmp_path, env={"PATH": os.environ["PATH"]},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert "scratch list" in result.stdout
    assert "cannot be collected later" in result.stdout
