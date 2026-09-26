"""A failed settlement, measurement rebuild or closing-line value report was
recorded as a clean run.

"Settle the forward ledger", "Report closing-line value" and "Rebuild the
measurement reports" were `continue-on-error: true` with no `id:`, and no
later step read their outcome. `run_forward_evidence.py` exits 2 on a ledger
it cannot read (`CorruptStoreError`), a team map that resolves nothing
(`UnresolvedTeamsError`) or an unreadable snapshot ("the exit is non-zero so
it is not missed"), and 1 when the shrink guard refuses a shorter ledger;
`run_closing_line_value.py` exits 2 on a damaged snapshot or capture store.
The run read those exits as nothing. From opening night, one torn ledger
would fail settlement on every run while every run finished green and
nobody was told. The ledger, the season's only out-of-sample record, would
silently stop growing.

Confirmed on main d0cc593 by reading the steps: none of the three has an
`id:`, so no expression anywhere in the job can name its outcome.

Each step now has an id, and "Report the outcome" fails the run red on any
of them, naming the step. None of them degrades the run. A degraded run
sends for the 15:00 backup, which buys the prices again, and every one of
these faults is a property of the restored state or of the scripts: the
backup restores the same files (the red run is the newest carrier), runs
the same scripts, and fails identically. So the published status stays
`degraded: false` and the backup stands down. Nothing that failed to settle
was marked settled, so a later run settles it once the state is repaired.

These tests read the workflow with `yaml.safe_load` and run its own step
blocks under `bash -eo pipefail`, with a stub `python` that exits as told and
a stub `git` that reaches no network, then take each step's outcome from its
exit as the runner does, and carry it through the final health, "Report the
outcome", card-feed (real git plumbing into a local bare remote) and the next
trigger's precheck, the way `test_a_blocked_card_is_a_degraded_run.py` does.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from test_a_blocked_card_is_a_degraded_run import (
    _bash,
    _final,
    _precheck,
    _publish,
    _render,
)


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
DAY = "2026-10-08"

SETTLE = "Settle the forward ledger"
CLV = "Report closing-line value"
REBUILD = "Rebuild the measurement reports"
REPORT = "Report the outcome"
#: The soft steps whose failure the run now reads, in the order they run.
WATCHED = (REBUILD, SETTLE, CLV)
#: The script whose exit each one's failure comes from, in the stub.
SCRIPT = {
    SETTLE: "run_forward_evidence.py",
    CLV: "run_closing_line_value.py",
    REBUILD: "run_allowlist_evidence.py",
}

NO_STORE = "No capture store yet"


@pytest.fixture(autouse=True)
def a_real_jq() -> None:
    assert shutil.which("jq"), "the card-feed step writes its status with jq"


# --------------------------------------------------------------------------
# The workflow's own steps.
# --------------------------------------------------------------------------

def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        steps = job.get("steps", [])
        if any(step.get("name") == SETTLE for step in steps):
            return steps
    raise AssertionError(f"no job has the step {SETTLE!r}")


def _index(name: str) -> int:
    names = [step.get("name") for step in _steps()]
    assert names.count(name) == 1, f"{name!r} appears {names.count(name)} times"
    return names.index(name)


def _step(name: str) -> dict:
    return _steps()[_index(name)]


def _id(name: str) -> str:
    found = _step(name).get("id")
    assert found, f"{name!r} has no id, so no step can read its outcome"
    return found


# --------------------------------------------------------------------------
# Running the steps, with stubs where the runner would reach the world.
# --------------------------------------------------------------------------

def _stubs(tmp_path: Path, exits: dict[str, int]) -> dict:
    """A `python` that exits as `exits` says for the script it is given (0
    otherwise), and a `git` that reaches no network: `ls-remote` finds no
    closing-lines branch and a fetch fails, which is what a repository with
    no capture store yet answers."""
    bin_dir = tmp_path / "stubs"  # not "bin": card-feed puts its `date` there
    bin_dir.mkdir(exist_ok=True)
    cases = "".join(
        f'  */{script}) echo "stub {script} exit {code}"; exit {code} ;;\n'
        for script, code in exits.items()
    )
    python = bin_dir / "python"
    python.write_text(
        "#!/bin/bash\n"
        'case "$1" in\n' + cases + "esac\nexit 0\n",
        encoding="utf-8",
    )
    git = bin_dir / "git"
    git.write_text(
        "#!/bin/bash\n"
        'case "$1" in\n'
        "  ls-remote) exit 0 ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    for path in (python, git):
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "GH_TOKEN": "x",
        "PYTHONPATH": "src",
    }


def _workspace(tmp_path: Path) -> Path:
    """A runner's working directory after a clean run up to the rebuild."""
    work = tmp_path / "work"
    (work / "data" / "outputs").mkdir(parents=True)
    (work / "data" / "processed").mkdir(parents=True)
    (work / "run_degraded.txt").write_text("", encoding="utf-8")
    (work / "card_comment.md").write_text("Today's card.\n", encoding="utf-8")
    return work


def _run(name: str, work: Path, env: dict) -> subprocess.CompletedProcess:
    block = _render(_step(name)["run"], {"github.repository": "o/r"})
    return _bash(block, work, env)


def _outcome(result: subprocess.CompletedProcess) -> str:
    """As the runner sets `steps.<id>.outcome` on a continue-on-error step."""
    return "success" if result.returncode == 0 else "failure"


def _report(work: Path, degraded: str, outcomes: dict[str, str], *,
            empty_slate: str = "false", cardfeed: str = "success"
            ) -> subprocess.CompletedProcess:
    values = {
        "steps.final.outputs.degraded": degraded,
        "steps.prices.outputs.empty_slate": empty_slate,
        "steps.cardfeed.outcome": cardfeed,
    }
    for name in WATCHED:
        values[f"steps.{_id(name)}.outcome"] = outcomes.get(name, "success")
    return _bash(_render(_step(REPORT)["run"], values), work, dict(os.environ))


def _errors(report: subprocess.CompletedProcess) -> list[str]:
    return [line for line in report.stdout.splitlines()
            if line.startswith("::error::")]


def _the_run(tmp_path: Path, exits: dict[str, int]
             ) -> tuple[Path, dict, dict]:
    """The three watched steps as the runner runs them. Returns the
    workspace and each step's outcome and log."""
    work = _workspace(tmp_path)
    env = _stubs(tmp_path, exits)
    outcomes: dict[str, str] = {}
    logs: dict[str, str] = {}
    for name in WATCHED:
        result = _run(name, work, env)
        outcomes[name] = _outcome(result)
        logs[name] = result.stdout + result.stderr
    return work, outcomes, logs


# --------------------------------------------------------------------------
# The shape, from the YAML.
# --------------------------------------------------------------------------

def test_the_steps_stay_soft_and_only_the_outcome_reads_them() -> None:
    """Soft, so none of them costs the card. Read only by "Report the
    outcome", the last step, and by no step that writes the run's health,
    so none of them sends for a backup that would fail the same way."""
    steps = _steps()

    assert _index(REPORT) == len(steps) - 1
    for name in WATCHED:
        assert _step(name).get("continue-on-error") is True, name
        expression = f"steps.{_id(name)}.outcome"
        readers = [step.get("name") for step in steps
                   if expression in step.get("run", "")]
        assert readers == [REPORT], (name, readers)


# --------------------------------------------------------------------------
# The real run blocks, under stubs.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("step", "code"),
    [(SETTLE, 2), (SETTLE, 1), (CLV, 2), (REBUILD, 1)],
    ids=["settle-exit-2", "settle-shrink-guard-exit-1", "clv-exit-2",
         "rebuild-exit-1"],
)
def test_a_failed_step_fails_the_run_without_degrading_it(
    tmp_path: Path, step: str, code: int
) -> None:
    work, outcomes, _ = _the_run(tmp_path, {SCRIPT[step]: code})

    assert outcomes[step] == "failure"
    assert (work / "run_degraded.txt").read_text(encoding="utf-8") == "", (
        "a failure a backup would repeat must not send for the backup"
    )
    degraded = _final(work, tmp_path)
    assert degraded == "false"
    report = _report(work, degraded, outcomes)
    assert report.returncode != 0, report.stdout
    errors = _errors(report)
    assert len(errors) == 1, report.stdout
    assert errors[0].startswith(f"::error::{step} failed"), errors
    assert "This run was degraded" not in report.stdout


@pytest.mark.parametrize("step", WATCHED)
def test_a_failed_step_is_not_excused_by_an_empty_slate(
    tmp_path: Path, step: str
) -> None:
    report = _report(_workspace(tmp_path), "false", {step: "failure"},
                     empty_slate="true")

    assert report.returncode != 0, report.stdout
    assert "No NHL games on the slate" not in report.stdout


def test_every_failure_is_named_before_the_exit(tmp_path: Path) -> None:
    """The degraded check used to exit on the spot, so a degraded run that
    also failed a watched step or its card-feed publish named only that it
    was degraded. Every failure is printed, then the step exits once."""
    work, outcomes, _ = _the_run(tmp_path, {
        SCRIPT[SETTLE]: 2, SCRIPT[REBUILD]: 1, SCRIPT[CLV]: 2,
    })
    # Degraded by something else this run: the card could not be rendered.
    (work / "run_degraded.txt").write_text("The card could not be rendered.\n",
                                          encoding="utf-8")
    degraded = _final(work, tmp_path)

    report = _report(work, degraded, outcomes, empty_slate="true",
                     cardfeed="failure")

    assert degraded == "true"
    assert report.returncode != 0
    errors = _errors(report)
    assert len(errors) == 5, report.stdout
    assert "This run was degraded" in errors[0]
    for step in WATCHED:
        assert any(line.startswith(f"::error::{step} failed") for line in errors), (
            step, errors
        )
    assert any("card-feed" in line for line in errors), errors
    assert "No NHL games on the slate" not in report.stdout


def test_a_degraded_run_with_a_failed_rebuild_names_both(tmp_path: Path) -> None:
    work, outcomes, _ = _the_run(tmp_path, {SCRIPT[REBUILD]: 1})
    (work / "run_degraded.txt").write_text("The card could not be rendered.\n",
                                          encoding="utf-8")
    degraded = _final(work, tmp_path)

    report = _report(work, degraded, outcomes)

    assert degraded == "true"
    assert report.returncode != 0
    errors = _errors(report)
    assert len(errors) == 2, report.stdout
    assert "This run was degraded" in errors[0]
    assert errors[1].startswith(f"::error::{REBUILD} failed"), errors


def test_a_skipped_rebuild_is_not_named_as_a_failed_one(tmp_path: Path) -> None:
    """The rebuild has no `if: always()`, so an earlier step that failed the
    job skips it. That failure fails the run on its own; the report must not
    point at a rebuild log that does not exist."""
    report = _report(_workspace(tmp_path), "false", {REBUILD: "skipped"})

    assert report.returncode == 0, report.stdout
    assert f"{REBUILD} failed" not in report.stdout


def test_a_clean_run_stays_clean(tmp_path: Path) -> None:
    work, outcomes, _ = _the_run(tmp_path, {})

    assert set(outcomes.values()) == {"success"}
    degraded = _final(work, tmp_path)
    assert degraded == "false"
    report = _report(work, degraded, outcomes)
    assert report.returncode == 0, report.stdout
    assert "Clean run." in report.stdout


def test_no_capture_store_yet_is_not_a_fault(tmp_path: Path) -> None:
    """Closing Lines is disabled by the owner, so there is no capture store
    on the branch it would publish, and the report exits 0 saying so. That
    is the expected state: not degraded, and not red."""
    work, outcomes, logs = _the_run(tmp_path, {})

    assert NO_STORE in logs[CLV], logs[CLV]
    assert outcomes[CLV] == "success"
    degraded = _final(work, tmp_path)
    assert degraded == "false"
    assert _report(work, degraded, outcomes).returncode == 0


def test_a_rebuild_that_falls_back_and_succeeds_is_clean(tmp_path: Path) -> None:
    """The calibration reuses its samples, or rebuilds them when it cannot:
    a failed first try the second one recovers is not a failure."""
    work = _workspace(tmp_path)
    env = _stubs(tmp_path, {})
    python = tmp_path / "stubs" / "python"
    python.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = scripts/run_props_calibration.py ] && [ "$2" = --reuse-samples ]; then exit 1; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )

    result = _run(REBUILD, work, env)

    assert result.returncode == 0, result.stderr
    assert _report(work, "false", {REBUILD: _outcome(result)}).returncode == 0


# --------------------------------------------------------------------------
# End to end: through card-feed into the backup's precheck.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("step", "code"),
    [(SETTLE, 2), (CLV, 2), (REBUILD, 1), (None, 0)],
    ids=["settle-fails", "clv-fails", "rebuild-fails", "clean"],
)
def test_no_failure_a_backup_would_repeat_sends_for_it(
    tmp_path: Path, step: str | None, code: int
) -> None:
    work, outcomes, _ = _the_run(tmp_path, {SCRIPT[step]: code} if step else {})

    degraded = _final(work, tmp_path)
    status = _publish(work, tmp_path, degraded, DAY)
    already = _precheck(tmp_path, DAY)
    report = _report(work, degraded, outcomes)

    assert degraded == "false"
    assert status["date"] == DAY and status["degraded"] == "false"
    assert (report.returncode != 0) is (step is not None), report.stdout
    assert already == "true", (
        "the backup ran on a failure it would only repeat, buying the "
        "prices again for nothing"
    )
