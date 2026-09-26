"""A state upload that failed was published to card-feed as a clean run.

Gameday Refresh carries its boxscore cache, processed tables, frozen priced
snapshots and forward ledger to the next gameday in one artifact,
`gameday-state`, and nowhere else. "Upload the state for the next run" ran
AFTER "Publish the card to the card-feed branch", and nothing read its
outcome. So when the upload failed, card-feed had already recorded
`degraded: false` for today. The 15:00 backup's precheck read a clean card
and stood down, the only run that could have carried today's state forward
never ran, and the next day restored yesterday's state, or none, with today's
frozen snapshot missing from it for good.

Confirmed on main d0cc593 by reading the step order: the card-feed publish
sat at index 16 of the refresh job and the state upload at 18, with no `id:`
on the upload for any step to read.

The state upload now runs as soon as the last step that writes state has
finished, before the post and before the final health, and a step right after
it writes a failed upload into `run_degraded.txt`. The comment, the run
summary, the final health, card-feed's status and the run's exit then all
say the run was degraded, and the backup runs.

These tests read the workflow with `yaml.safe_load` and run its own step
blocks under `bash -eo pipefail`, with real git plumbing into a local bare
remote for card-feed, the way `test_a_blocked_card_is_a_degraded_run.py`
does:

1. the step that records the upload's outcome;
2. the final health;
3. the card-feed publish;
4. the next trigger's precheck, reading that status back;
5. "Report the outcome".
"""

from __future__ import annotations

import os
import re
import shutil
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
UPLOAD = "Upload the state for the next run"
DAY = "2026-10-01"

#: Every step that writes something the state artifact carries. The upload
#: must come after all of them, or it carries a half-finished state.
WRITERS = (
    "Restore the previous state",
    "Fetch results",
    "Rebuild the measurement reports",
    "Render the card",
    "Settle the forward ledger",
    "Report closing-line value",
)

#: Every step that tells anyone the run was clean. The upload must come
#: before all of them, or its failure cannot reach them.
READERS = (
    "Write the card to the run summary",
    "Post the card to the operating home",
    "Record whether the card was delivered",
    "Publish the card to the card-feed branch",
    "Report the outcome",
)


@pytest.fixture(autouse=True)
def a_real_jq() -> None:
    assert shutil.which("jq"), "the card-feed step writes its status with jq"


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        steps = job.get("steps", [])
        if any(step.get("name") == UPLOAD for step in steps):
            return steps
    raise AssertionError(f"no job has the step {UPLOAD!r}")


def _index(name: str) -> int:
    names = [step.get("name") for step in _steps()]
    assert names.count(name) == 1, f"{name!r} appears {names.count(name)} times"
    return names.index(name)


def _upload() -> dict:
    return _steps()[_index(UPLOAD)]


def _recorder() -> tuple[int, dict]:
    """The one step that reads the upload's outcome into the run's health."""
    upload_id = _upload().get("id")
    assert upload_id, "the state upload has no id, so no step can read its outcome"
    expression = f"steps.{upload_id}.outcome"
    found = [
        (index, step) for index, step in enumerate(_steps())
        if expression in step.get("run", "")
    ]
    assert len(found) == 1, f"{len(found)} steps read {expression}"
    return found[0]


def _record(work: Path, outcome: str) -> str:
    _, step = _recorder()
    block = _render(step["run"], {f"steps.{_upload()['id']}.outcome": outcome})
    result = _bash(block, work, dict(os.environ))
    assert result.returncode == 0, result.stderr
    return (work / "run_degraded.txt").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The order, from the YAML.
# --------------------------------------------------------------------------

def test_the_state_is_uploaded_before_anyone_is_told_the_run_was_clean() -> None:
    upload = _index(UPLOAD)

    for name in WRITERS:
        assert _index(name) < upload, f"{name!r} writes state after it was uploaded"
    for name in READERS:
        assert upload < _index(name), f"{name!r} runs before the state is uploaded"


def test_the_upload_always_runs_and_its_failure_is_recorded_not_fatal() -> None:
    """`if: always()` so a failed card still carries the cache forward, and
    `continue-on-error` so a failed upload is read by the health rather than
    ending the job's say in the matter. "Report the outcome" stays the only
    step that fails the job."""
    upload = _upload()

    assert upload.get("if") == "always()"
    assert upload.get("continue-on-error") is True
    assert upload["with"]["name"] == "gameday-state"
    index, recorder = _recorder()
    assert recorder.get("if") == "always()"
    assert "continue-on-error" not in recorder
    assert _index(UPLOAD) < index
    for name in READERS:
        assert index < _index(name), f"{name!r} runs before the upload is recorded"


@pytest.mark.parametrize(("outcome", "noted"), [
    ("failure", True), ("cancelled", True), ("skipped", True), ("success", False),
])
def test_only_an_upload_that_succeeded_is_left_out_of_the_notes(
    tmp_path: Path, outcome: str, noted: bool
) -> None:
    (tmp_path / "run_degraded.txt").write_text("", encoding="utf-8")

    notes = _record(tmp_path, outcome)

    assert bool(notes.strip()) is noted, notes
    if noted:
        assert len(notes.splitlines()) == 1
        assert "state" in notes


def test_an_earlier_note_survives_the_record(tmp_path: Path) -> None:
    (tmp_path / "run_degraded.txt").write_text("The card could not be rendered.\n",
                                              encoding="utf-8")

    notes = _record(tmp_path, "failure")

    assert notes.startswith("The card could not be rendered.\n")
    assert len(notes.splitlines()) == 2


# --------------------------------------------------------------------------
# End to end: through card-feed into the backup's precheck.
# --------------------------------------------------------------------------

def _workspace(tmp_path: Path) -> Path:
    """A runner's working directory after a clean run up to the upload."""
    work = tmp_path / "work"
    (work / "data" / "outputs").mkdir(parents=True)
    (work / "run_degraded.txt").write_text("", encoding="utf-8")
    (work / "card_comment.md").write_text("Today's card.\n", encoding="utf-8")
    return work


@pytest.mark.parametrize("outcome", ["failure", "success"])
def test_a_failed_upload_leaves_the_backup_free_to_run(
    tmp_path: Path, outcome: str
) -> None:
    work = _workspace(tmp_path)
    failed = outcome != "success"

    _record(work, outcome)
    degraded = _final(work, tmp_path)
    status = _publish(work, tmp_path, degraded, DAY)
    already = _precheck(tmp_path, DAY)

    assert degraded == ("true" if failed else "false")
    assert status["date"] == DAY and status["degraded"] == degraded
    assert already == ("false" if failed else "true"), (
        "the backup stood down on a day whose state never reached the next run"
    )
    assert (_report(work, degraded) == 0) is not failed


def test_the_upload_step_still_carries_the_whole_state() -> None:
    """Moving the step moved none of what it carries."""
    paths = {
        line.strip() for line in _upload()["with"]["path"].splitlines() if line.strip()
    }
    assert {
        "data/raw/nhl/boxscore", "data/raw/nhl/registry", "data/processed",
        "data/outputs/gameday_card.json", "data/archive/priced_snapshots",
        "data/processed/forward_evidence.csv",
    } <= paths
    assert re.fullmatch(r"actions/upload-artifact@v\d+", _upload()["uses"])
