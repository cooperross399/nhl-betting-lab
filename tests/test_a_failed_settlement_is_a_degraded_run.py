"""A failed settlement was recorded as a clean run, and so were a failed
measurement rebuild and a failed closing-line value report.

"Settle the forward ledger", "Report closing-line value" and "Rebuild the
measurement reports" were `continue-on-error: true` with no `id:`, and no
later step read their outcome. `run_forward_evidence.py` exits 2 on a ledger
it cannot read (`CorruptStoreError`), a team map that resolves nothing
(`UnresolvedTeamsError`) or an unreadable snapshot ("the exit is non-zero so
it is not missed"), and 1 when the shrink guard refuses a shorter ledger;
`run_closing_line_value.py` exits 2 on a damaged snapshot or capture store.
The run read those exits as nothing. From opening night, one torn ledger
would fail settlement on every run while every run finished green, card-feed
said `degraded: false`, and the 15:00 backup's precheck stood down. The
ledger, the season's only out-of-sample record, would silently stop growing.

Confirmed on main d0cc593 by reading the steps: none of the three has an
`id:`, so no expression anywhere in the job can name its outcome.

Each step now has an id, and the two kinds of failure are told apart by what
a backup run could do about them:

* a failed SETTLEMENT is a degraded run. "Record whether the evidence was
  kept" writes it into `run_degraded.txt`, so the summary, the comment, the
  final health, card-feed's status and the run's exit all say so, and the
  backup runs and retries it (nothing that failed to settle was marked
  settled, so it stays pending);
* a failed REBUILD or CLV REPORT fails the run red in "Report the outcome",
  naming the step, and does NOT degrade it. A backup buys the prices again,
  and a report script that fails or a capture store that is damaged fails
  the backup identically, so the published status stays `degraded: false`
  and the backup stands down.

These tests read the workflow with `yaml.safe_load` and run its own step
blocks under `bash -eo pipefail`, with a stub `python` that exits as told and
a stub `git` that reaches no network, then take each step's outcome from its
exit as the runner does, and carry it through the record, the final health,
"Report the outcome", card-feed (real git plumbing into a local bare remote)
and the next trigger's precheck, the way
`test_a_blocked_card_is_a_degraded_run.py` does.
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
#: The soft steps whose outcome the run now reads.
WATCHED = (REBUILD, SETTLE, CLV)

#: Every step that tells anyone the run was clean. The record must come
#: before all of them, or a failed settlement cannot reach them.
READERS = (
    "Write the card to the run summary",
    "Post the card to the operating home",
    "Record whether the card was delivered",
    "Publish the card to the card-feed branch",
    "Report the outcome",
)

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


def _recorder() -> tuple[int, dict]:
    """The one step that reads the settlement's outcome into the run's
    health. It must NOT read the rebuild's or the CLV report's: those fail
    the run without sending for a backup that would fail the same way."""
    expression = f"steps.{_id(SETTLE)}.outcome"
    found = [
        (index, step) for index, step in enumerate(_steps())
        if expression in step.get("run", "")
    ]
    assert len(found) == 1, f"{len(found)} steps read {expression}"
    for name in (REBUILD, CLV):
        assert f"steps.{_id(name)}.outcome" not in found[0][1]["run"], (
            f"the record degrades the run on {name!r}"
        )
    return found[0]


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


def _record(work: Path, outcomes: dict[str, str]) -> str:
    _, step = _recorder()
    values = {f"steps.{_id(SETTLE)}.outcome": outcomes.get(SETTLE, "success")}
    result = _bash(_render(step["run"], values), work, dict(os.environ))
    assert result.returncode == 0, result.stderr
    return (work / "run_degraded.txt").read_text(encoding="utf-8")


def _report(work: Path, degraded: str, outcomes: dict[str, str],
            *, empty_slate: str = "false") -> subprocess.CompletedProcess:
    """"Report the outcome", with the card-feed publish having worked."""
    values = {
        "steps.final.outputs.degraded": degraded,
        "steps.prices.outputs.empty_slate": empty_slate,
        "steps.cardfeed.outcome": "success",
    }
    for name in (REBUILD, CLV):
        values[f"steps.{_id(name)}.outcome"] = outcomes.get(name, "success")
    return _bash(_render(_step(REPORT)["run"], values), work, dict(os.environ))


def _the_run(tmp_path: Path, exits: dict[str, int]
             ) -> tuple[Path, dict, dict, str]:
    """The three watched steps as the runner runs them, then the record.
    Returns the workspace, each step's outcome and log, and the notes."""
    work = _workspace(tmp_path)
    env = _stubs(tmp_path, exits)
    outcomes: dict[str, str] = {}
    logs: dict[str, str] = {}
    for name in WATCHED:
        result = _run(name, work, env)
        outcomes[name] = _outcome(result)
        logs[name] = result.stdout + result.stderr
    notes = _record(work, outcomes)
    return work, outcomes, logs, notes


# --------------------------------------------------------------------------
# The order, from the YAML.
# --------------------------------------------------------------------------

def test_the_steps_stay_soft_and_the_record_runs_before_anyone_is_told() -> None:
    index, recorder = _recorder()

    for name in WATCHED:
        assert _step(name).get("continue-on-error") is True, (
            f"{name!r} must stay soft: its failure never costs the card"
        )
    assert _index(SETTLE) < index and _index(CLV) < index
    assert recorder.get("if") == "always()"
    assert "continue-on-error" not in recorder
    for name in READERS:
        assert index < _index(name), f"{name!r} runs before the record"


def test_the_outcome_reads_the_rebuild_and_the_clv_report() -> None:
    """"Report the outcome" is the last step, so it runs after both."""
    report = _step(REPORT)["run"]

    assert _index(REPORT) == len(_steps()) - 1
    for name in (REBUILD, CLV):
        assert f"steps.{_id(name)}.outcome" in report, name


# --------------------------------------------------------------------------
# The real run blocks, under stubs.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("code", [2, 1], ids=["exit-2", "shrink-guard-exit-1"])
def test_a_failed_settlement_is_a_degraded_run(tmp_path: Path, code: int) -> None:
    work, outcomes, _, notes = _the_run(tmp_path, {"run_forward_evidence.py": code})

    assert "forward ledger" in notes, notes
    assert len(notes.splitlines()) == 1, notes
    degraded = _final(work, tmp_path)
    assert degraded == "true"
    assert _report(work, degraded, outcomes).returncode != 0


@pytest.mark.parametrize(
    ("script", "code", "step"),
    [
        ("run_closing_line_value.py", 2, CLV),
        ("run_allowlist_evidence.py", 1, REBUILD),
    ],
    ids=["clv-exit-2", "rebuild-exit-1"],
)
def test_a_failed_report_fails_the_run_without_degrading_it(
    tmp_path: Path, script: str, code: int, step: str
) -> None:
    work, outcomes, _, notes = _the_run(tmp_path, {script: code})

    assert outcomes[step] == "failure"
    assert notes == "", "a failed report must not send for the backup"
    degraded = _final(work, tmp_path)
    assert degraded == "false"
    report = _report(work, degraded, outcomes)
    assert report.returncode != 0, report.stdout
    assert f"::error::{step} failed" in report.stdout, report.stdout
    assert "This run was degraded" not in report.stdout


@pytest.mark.parametrize("step", [CLV, REBUILD])
def test_a_failed_report_is_not_excused_by_an_empty_slate(
    tmp_path: Path, step: str
) -> None:
    report = _report(_workspace(tmp_path), "false", {step: "failure"},
                     empty_slate="true")

    assert report.returncode != 0, report.stdout


def test_both_failed_reports_are_named(tmp_path: Path) -> None:
    report = _report(_workspace(tmp_path), "false",
                     {REBUILD: "failure", CLV: "failure"})

    assert report.returncode != 0
    assert f"::error::{REBUILD} failed" in report.stdout, report.stdout
    assert f"::error::{CLV} failed" in report.stdout, report.stdout


def test_a_skipped_rebuild_is_not_named_as_a_failed_one(tmp_path: Path) -> None:
    """The rebuild has no `if: always()`, so an earlier step that failed the
    job skips it. That failure fails the run on its own; the report must not
    point at a rebuild log that does not exist."""
    report = _report(_workspace(tmp_path), "false", {REBUILD: "skipped"})

    assert report.returncode == 0, report.stdout
    assert f"{REBUILD} failed" not in report.stdout


def test_a_clean_run_stays_clean(tmp_path: Path) -> None:
    work, outcomes, _, notes = _the_run(tmp_path, {})

    assert notes == ""
    degraded = _final(work, tmp_path)
    assert degraded == "false"
    report = _report(work, degraded, outcomes)
    assert report.returncode == 0, report.stdout
    assert "Clean run." in report.stdout


def test_no_capture_store_yet_is_not_a_fault(tmp_path: Path) -> None:
    """Closing Lines is disabled by the owner, so there is no capture store
    on the branch it would publish, and the report exits 0 saying so. That
    is the expected state: not degraded, and not red."""
    work, outcomes, logs, notes = _the_run(tmp_path, {})

    assert NO_STORE in logs[CLV], logs[CLV]
    assert outcomes[CLV] == "success"
    assert notes == ""
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


@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped"])
def test_only_a_settlement_that_succeeded_is_left_out_of_the_notes(
    tmp_path: Path, outcome: str
) -> None:
    notes = _record(_workspace(tmp_path), {SETTLE: outcome})

    assert len(notes.splitlines()) == 1, notes


def test_an_earlier_note_survives_the_record(tmp_path: Path) -> None:
    work = _workspace(tmp_path)
    (work / "run_degraded.txt").write_text("The card could not be rendered.\n",
                                          encoding="utf-8")

    notes = _record(work, {SETTLE: "failure"})

    assert notes.startswith("The card could not be rendered.\n")
    assert len(notes.splitlines()) == 2


# --------------------------------------------------------------------------
# End to end: through card-feed into the backup's precheck.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("exits", "degraded", "red", "backup_stands_down"),
    [
        ({"run_forward_evidence.py": 2}, "true", True, False),
        ({"run_closing_line_value.py": 2}, "false", True, True),
        ({"run_allowlist_evidence.py": 1}, "false", True, True),
        ({}, "false", False, True),
    ],
    ids=["settle-fails", "clv-fails", "rebuild-fails", "clean"],
)
def test_only_a_failed_settlement_sends_for_the_backup(
    tmp_path: Path, exits: dict[str, int], degraded: str, red: bool,
    backup_stands_down: bool,
) -> None:
    work, outcomes, _, _ = _the_run(tmp_path, exits)

    health = _final(work, tmp_path)
    status = _publish(work, tmp_path, health, DAY)
    already = _precheck(tmp_path, DAY)
    report = _report(work, health, outcomes)

    assert health == degraded
    assert status["date"] == DAY and status["degraded"] == degraded
    assert (report.returncode != 0) is red, report.stdout
    assert already == ("true" if backup_stands_down else "false"), (
        "the backup ran on a failure it would repeat, or stood down on a day "
        "whose games never reached the ledger"
    )
