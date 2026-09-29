"""A Line Movement run whose restore could not ask GitHub is a red run.

"Restore today's captures" made one attempt at each call, named no
`--problem-file`, and turned any failure into a `::warning::`. So a failed
`gh run list` started every day file afresh, uploaded a carrier holding this
round alone, and finished green. The union reads the newest carrier and the
two before it, so three such runs in a row, and the next run never read an
older carrier: every earlier capture left the chain for good, with every run
green (sweep 5, line-movement-three-thin-carriers-drop-the-season).

The step now tries each call three times and records what it still could not
reach in `restore_problem.txt`; a gate after every upload turns that into a
red run, so one thin run is seen the day it happens. Gameday Refresh has
done the same since the failure-shape audit.

These tests run the workflow's own restore step, and its own gate, under
bash with the offline `gh` from
`test_a_red_capture_run_stays_in_the_chain.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_a_red_capture_run_stays_in_the_chain import (
    AT_14,
    AT_18,
    YESTERDAY,
    Chain,
    _steps,
)

RESTORE_STEP = "Restore today's captures"
GATE = "Fail the run when the previous captures were not restored"
PROBLEM_FILE = "restore_problem.txt"


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Chain:
    return Chain(tmp_path, monkeypatch)


def _step(name: str) -> dict:
    matches = [step for step in _steps() if step.get("name") == name]
    assert len(matches) == 1, f"exactly one step named {name!r}"
    return matches[0]


def _gate(work: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _step(GATE)["run"]],
        cwd=work, env=dict(os.environ), capture_output=True, text=True, timeout=60,
    )


def test_a_restore_that_could_not_list_the_runs_turns_the_run_red(
    chain: Chain,
) -> None:
    chain.run(YESTERDAY)
    chain.run(AT_14)
    work = chain.run(AT_18, gh_down=True).parent.parent

    problems = (work / PROBLEM_FILE).read_text(encoding="utf-8")
    assert problems.strip(), chain.logs[chain.last_id()]
    gate = _gate(work)
    assert gate.returncode != 0
    assert "::error::The previous captures were not fully restored" in gate.stdout


def test_a_restore_that_reached_github_leaves_the_run_green(chain: Chain) -> None:
    chain.run(YESTERDAY)
    work = chain.run(AT_14).parent.parent

    assert (work / PROBLEM_FILE).read_text(encoding="utf-8") == ""
    gate = _gate(work)
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert "::error::" not in gate.stdout


def test_the_first_run_of_the_season_with_no_carrier_is_green(chain: Chain) -> None:
    """No run carries the artifact yet: an answer, not a failure to ask."""
    work = chain.run(AT_14).parent.parent

    assert (work / PROBLEM_FILE).read_text(encoding="utf-8") == ""
    assert _gate(work).returncode == 0


def test_a_restore_script_that_crashes_is_recorded(tmp_path: Path) -> None:
    """The `||` branch: whatever made restore_state.py exit non-zero, the
    gate still has something to read."""
    work = tmp_path / "run"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts" / "restore_state.py").write_text(
        "import sys\nsys.exit(1)\n", encoding="utf-8"
    )
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
         _step(RESTORE_STEP)["run"]],
        cwd=work, capture_output=True, text=True, timeout=60, check=True,
        env={**os.environ,
             "PATH": f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"},
    )

    assert "exited non-zero" in (work / PROBLEM_FILE).read_text(encoding="utf-8")
    assert _gate(work).returncode != 0


def test_the_restore_retries_and_names_its_problem_file() -> None:
    command = " ".join(_step(RESTORE_STEP)["run"].split())
    assert "--attempts 3" in command
    assert f"--problem-file {PROBLEM_FILE}" in command
    # Emptied first, so a file left behind can never be read as this run's.
    assert f": > {PROBLEM_FILE}" in command


def test_the_gate_runs_after_every_upload_whatever_failed_before_it() -> None:
    steps = _steps()
    names = [step.get("name") for step in steps]
    gate = names.index(GATE)
    uploads = [
        index for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert uploads and max(uploads) < gate
    step = steps[gate]
    assert str(step.get("if", "")).startswith("always()")
    assert "continue-on-error" not in step
    assert PROBLEM_FILE in step["run"]
