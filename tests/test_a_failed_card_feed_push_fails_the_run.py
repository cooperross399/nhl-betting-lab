"""A card-feed publish that failed finished the run green.

"Publish the card to the card-feed branch" is `continue-on-error: true`, had
no `id:`, and nothing read its outcome. It is the only place the morning
brief reads today's card and status from, and the only copy of the forward
ledger outside the state artifact. A push that failed (a rejected push, a
network fault, a token that could not write) left no status for today and no
ledger backup, and "Report the outcome" still said "Clean run.", so no failure
notice arrived and nobody learned the brief had nothing to read.

Confirmed on main d0cc593 by reading the step: no `id:`, and "Report the
outcome" reads only the final health and the empty slate.

The publish now has an id, and "Report the outcome" fails the run when it did
not succeed, whatever the health said and on an empty slate too. It does NOT
rewrite the health. The publish runs after the final health on purpose, and
the status it tried to publish said what the run's health was; a failed push
published no status at all, so the next trigger's precheck finds no clean
card for today and the backup runs. The failure is reported as a failed
publish, not as a degraded run.

These tests run the real publish block with real git plumbing into a local
bare remote that refuses the push, then the next trigger's precheck and
"Report the outcome", under `bash -eo pipefail`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from test_a_blocked_card_is_a_degraded_run import (
    _bash,
    _git_env,
    _precheck,
    _publish,
    _render,
)


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
PUBLISH = "Publish the card to the card-feed branch"
REPORT = "Report the outcome"
DAY = "2026-10-08"


@pytest.fixture(autouse=True)
def a_real_jq() -> None:
    assert shutil.which("jq"), "the card-feed step writes its status with jq"


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        steps = job.get("steps", [])
        if any(step.get("name") == PUBLISH for step in steps):
            return steps
    raise AssertionError(f"no job has the step {PUBLISH!r}")


def _step(name: str) -> dict:
    found = [step for step in _steps() if step.get("name") == name]
    assert len(found) == 1, f"{name!r} appears {len(found)} times"
    return found[0]


def _publish_id() -> str:
    found = _step(PUBLISH).get("id")
    assert found, "the card-feed publish has no id, so no step can read its outcome"
    return found


def _report(work: Path, *, degraded: str, published: str,
            empty_slate: str = "false") -> subprocess.CompletedProcess:
    block = _render(_step(REPORT)["run"], {
        "steps.final.outputs.degraded": degraded,
        "steps.prices.outputs.empty_slate": empty_slate,
        f"steps.{_publish_id()}.outcome": published,
    })
    return _bash(block, work, dict(os.environ))


def _workspace(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    (work / "data" / "outputs").mkdir(parents=True)
    (work / "card_comment.md").write_text("Today's card.\n", encoding="utf-8")
    return work


def _refusing_remote(tmp_path: Path, day: str) -> None:
    """The bare remote `_publish` pushes to, set to refuse every push."""
    env = _git_env(tmp_path, day)
    hook = tmp_path / "remote.git" / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'refused' >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    assert env  # the remote now exists


def _try_publish(work: Path, tmp_path: Path, degraded: str) -> subprocess.CompletedProcess:
    """The publish block, returning its result rather than asserting it."""
    env = _git_env(tmp_path, DAY)
    subprocess.run(["git", "init", "-q"], cwd=work, env=env, check=True)
    block = _render(_step(PUBLISH)["run"], {
        "github.repository": "o/r",
        "github.server_url": "https://github.com",
        "github.run_id": "1",
        "steps.post.outputs.decision || 'none'": "post",
        "steps.final.outputs.degraded || 'unknown'": degraded,
        "steps.prices.outputs.empty_slate || 'false'": "false",
    })
    return _bash(block, work, env)


def test_the_publish_stays_soft_and_after_the_health() -> None:
    """Soft, so the reports and the state still upload after it; after the
    final health, because the status it publishes is that health."""
    names = [step.get("name") for step in _steps()]
    step = _step(PUBLISH)

    assert step.get("continue-on-error") is True
    assert step.get("if") == "always()"
    assert names.index("Record whether the card was delivered") < names.index(PUBLISH)
    assert names.index(PUBLISH) < names.index(REPORT)
    assert names[-1] == REPORT


def test_a_refused_push_fails_the_run_and_publishes_no_status(tmp_path: Path) -> None:
    work = _workspace(tmp_path)
    _refusing_remote(tmp_path, DAY)

    result = _try_publish(work, tmp_path, "false")
    published = "success" if result.returncode == 0 else "failure"
    already = _precheck(tmp_path, DAY)
    report = _report(work, degraded="false", published=published)

    assert published == "failure", result.stdout
    assert already == "false", "the backup stood down on a day with no status"
    assert report.returncode != 0, report.stdout
    assert "card-feed" in report.stdout
    # The health was clean, and the report says so rather than calling the
    # run degraded after the fact.
    assert "This run was degraded" not in report.stdout
    assert "degraded=false" in report.stdout


def test_a_push_that_went_through_leaves_the_run_clean(tmp_path: Path) -> None:
    work = _workspace(tmp_path)

    status = _publish(work, tmp_path, "false", DAY)
    report = _report(work, degraded="false", published="success")

    assert status["degraded"] == "false"
    assert report.returncode == 0, report.stdout
    assert "Clean run." in report.stdout


@pytest.mark.parametrize("published", ["failure", "cancelled", "skipped"])
def test_a_failed_publish_is_not_excused_by_an_empty_slate(
    tmp_path: Path, published: str
) -> None:
    """On a dark night the brief still reads card-feed for today."""
    report = _report(_workspace(tmp_path), degraded="false", published=published,
                     empty_slate="true")

    assert report.returncode != 0, report.stdout


def test_a_degraded_run_is_still_red_when_the_publish_worked(tmp_path: Path) -> None:
    report = _report(_workspace(tmp_path), degraded="true", published="success")

    assert report.returncode != 0
