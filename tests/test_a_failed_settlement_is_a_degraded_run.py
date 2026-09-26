"""A settlement that failed was recorded as a clean run.

"Settle the forward ledger" and "Report closing-line value" were
`continue-on-error: true` with no `id:`, and no later step read their
outcome. Both scripts exit non-zero on purpose when they could not do their
job: `run_forward_evidence.py` exits 2 on a ledger it cannot read
(`CorruptStoreError`), a team map that resolves nothing
(`UnresolvedTeamsError`) or an unreadable snapshot ("the exit is non-zero so
it is not missed"), and 1 when the shrink guard refuses a shorter ledger;
`run_closing_line_value.py` exits 2 on a damaged snapshot or capture store.
The run then read those exits as nothing. From opening night, one torn
ledger would fail settlement on every run while every run finished green,
card-feed said `degraded: false`, and the 15:00 backup's precheck stood
down. The ledger, the season's only out-of-sample record, would silently
stop growing.

"Rebuild the measurement reports" had the same shape: soft on purpose (a
measurement must never cost a card), with no `id:` and nothing reading its
outcome, so a rebuild that failed left the committed reports, or an earlier
run's, standing in this run's artifacts looking current.

Confirmed on main d0cc593 by reading the steps: none of the three has an
`id:`, so no expression anywhere in the job can name its outcome.

Each step now has an id, and "Record whether the evidence was kept", after
all three and before anyone is told how the run went, writes a failed one
into `run_degraded.txt`. The summary, the comment, the final health,
card-feed's status and the run's exit then all say the run was degraded, and
the backup runs and retries the settlement (nothing that failed to settle was
marked settled, so it stays pending).

These tests read the workflow with `yaml.safe_load` and run its own step
blocks under `bash -eo pipefail`, with a stub `python` that exits as told and
a stub `git` that reaches no network, then take each step's outcome from its
exit as the runner does, and carry it through the record, the final health,
card-feed (real git plumbing into a local bare remote) and the next trigger's
precheck, the way `test_a_blocked_card_is_a_degraded_run.py` does.
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
    _report,
)


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
DAY = "2026-10-08"

SETTLE = "Settle the forward ledger"
CLV = "Report closing-line value"
REBUILD = "Rebuild the measurement reports"
#: The steps whose failure this record exists to catch, and the script each
#: one's failure comes from.
WATCHED = {SETTLE: "run_forward_evidence.py", CLV: "run_closing_line_value.py",
           REBUILD: "run_allowlist_evidence.py"}

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
    health. It must read the other two watched steps' outcomes as well."""
    expression = f"steps.{_id(SETTLE)}.outcome"
    found = [
        (index, step) for index, step in enumerate(_steps())
        if expression in step.get("run", "")
    ]
    assert len(found) == 1, f"{len(found)} steps read {expression}"
    for name in WATCHED:
        assert f"steps.{_id(name)}.outcome" in found[0][1]["run"], (
            f"the record does not read {name!r}"
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
    values = {f"steps.{_id(name)}.outcome": outcomes.get(name, "success")
              for name in WATCHED}
    result = _bash(_render(step["run"], values), work, dict(os.environ))
    assert result.returncode == 0, result.stderr
    return (work / "run_degraded.txt").read_text(encoding="utf-8")


def _the_run(tmp_path: Path, exits: dict[str, int]) -> tuple[Path, dict, str]:
    """The three watched steps as the runner runs them, then the record.
    Returns the workspace, each step's log, and the notes."""
    work = _workspace(tmp_path)
    env = _stubs(tmp_path, exits)
    outcomes: dict[str, str] = {}
    logs: dict[str, str] = {}
    for name in (REBUILD, SETTLE, CLV):
        result = _run(name, work, env)
        outcomes[name] = _outcome(result)
        logs[name] = result.stdout + result.stderr
    notes = _record(work, outcomes)
    return work, logs, notes


# --------------------------------------------------------------------------
# The order, from the YAML.
# --------------------------------------------------------------------------

def test_the_record_reads_every_watched_step_before_anyone_is_told() -> None:
    index, recorder = _recorder()

    for name in WATCHED:
        step = _step(name)
        assert step.get("continue-on-error") is True, (
            f"{name!r} must stay soft: its failure degrades the run, it never "
            "costs the card"
        )
        assert _index(name) < index, f"the record runs before {name!r}"
    assert recorder.get("if") == "always()"
    assert "continue-on-error" not in recorder
    for name in READERS:
        assert index < _index(name), f"{name!r} runs before the record"


# --------------------------------------------------------------------------
# The real run blocks, under stubs.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("script", "code", "said"),
    [
        ("run_forward_evidence.py", 2, "forward ledger"),
        # The shrink guard raises, and an uncaught raise exits 1.
        ("run_forward_evidence.py", 1, "forward ledger"),
        ("run_closing_line_value.py", 2, "closing-line value"),
        ("run_allowlist_evidence.py", 1, "measurement reports"),
    ],
    ids=["settle-exit-2", "settle-exit-1", "clv-exit-2", "rebuild-exit-1"],
)
def test_a_failed_step_is_a_degraded_run(
    tmp_path: Path, script: str, code: int, said: str
) -> None:
    work, _, notes = _the_run(tmp_path, {script: code})

    assert said in notes, notes
    assert len(notes.splitlines()) == 1, notes
    degraded = _final(work, tmp_path)
    assert degraded == "true"
    assert _report(work, degraded) != 0


def test_a_clean_run_stays_clean(tmp_path: Path) -> None:
    work, _, notes = _the_run(tmp_path, {})

    assert notes == ""
    degraded = _final(work, tmp_path)
    assert degraded == "false"
    assert _report(work, degraded) == 0


def test_no_capture_store_yet_is_not_a_fault(tmp_path: Path) -> None:
    """Closing Lines is disabled by the owner, so there is no capture store
    on the branch it would publish, and the report exits 0 saying so. That
    is the expected state, not a degraded run."""
    work, logs, notes = _the_run(tmp_path, {})

    assert NO_STORE in logs[CLV], logs[CLV]
    assert notes == ""
    assert _final(work, tmp_path) == "false"


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
    assert _record(work, {REBUILD: _outcome(result)}) == ""


@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped"])
@pytest.mark.parametrize("name", sorted(WATCHED))
def test_only_a_step_that_succeeded_is_left_out_of_the_notes(
    tmp_path: Path, name: str, outcome: str
) -> None:
    work = _workspace(tmp_path)

    notes = _record(work, {name: outcome})

    assert len(notes.splitlines()) == 1, notes


def test_every_failure_is_named_and_an_earlier_note_survives(tmp_path: Path) -> None:
    work = _workspace(tmp_path)
    (work / "run_degraded.txt").write_text("The card could not be rendered.\n",
                                          encoding="utf-8")

    notes = _record(work, {name: "failure" for name in WATCHED})

    assert notes.startswith("The card could not be rendered.\n")
    assert len(notes.splitlines()) == 1 + len(WATCHED)


# --------------------------------------------------------------------------
# End to end: through card-feed into the backup's precheck.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("code", [2, 0])
def test_a_failed_settlement_leaves_the_backup_free_to_run(
    tmp_path: Path, code: int
) -> None:
    failed = code != 0
    work, _, _ = _the_run(tmp_path, {"run_forward_evidence.py": code})

    degraded = _final(work, tmp_path)
    status = _publish(work, tmp_path, degraded, DAY)
    already = _precheck(tmp_path, DAY)

    assert status["date"] == DAY and status["degraded"] == degraded
    assert degraded == ("true" if failed else "false")
    assert already == ("false" if failed else "true"), (
        "the backup stood down on a day whose games never reached the ledger"
    )
