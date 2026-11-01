"""Publish Site refreshes the public site at 7:00 AM New York every day.

Cooper asked on 2026-11-01. Cron reads UTC, so two crons are scheduled, one
for each New York offset, and the `when` job keeps exactly one of them: the
one that lands at 7 AM given whether New York is on daylight time today.
These tests replay that job's script under both offsets.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish-site.yml"
EDT_CRON = "55 10 * * *"
EST_CRON = "55 11 * * *"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _gate_script() -> str:
    steps = _workflow()["jobs"]["when"]["steps"]
    (step,) = [s for s in steps if s.get("id") == "clock"]
    return step["run"]


def _decide(tmp_path: Path, schedule: str, offset: str) -> str:
    # `date` is stubbed so the test does not depend on today's offset.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "date"
    stub.write_text(f"#!/bin/sh\necho '{offset}'\n", encoding="utf-8")
    stub.chmod(0o755)
    out = tmp_path / "out"
    out.write_text("", encoding="utf-8")
    subprocess.run(
        ["bash", "-e", "-c", _gate_script()],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "SCHEDULE": schedule, "GITHUB_OUTPUT": str(out)},
        check=True,
    )
    return out.read_text(encoding="utf-8").strip()


def test_both_seven_am_crons_are_scheduled_beside_the_existing_one() -> None:
    on = _workflow().get("on", _workflow().get(True))
    crons = [c["cron"] for c in on["schedule"]]
    assert crons == ["45 14 * * *", EDT_CRON, EST_CRON]
    assert "workflow_run" in on and "workflow_dispatch" in on


@pytest.mark.parametrize(
    "offset, publishes",
    [("-0400", EDT_CRON), ("-0500", EST_CRON)],
)
def test_exactly_one_morning_cron_publishes_on_each_offset(tmp_path: Path, offset: str, publishes: str) -> None:
    for cron in (EDT_CRON, EST_CRON):
        want = "go=true" if cron == publishes else "go=false"
        assert _decide(tmp_path, cron, offset) == want, (cron, offset)


@pytest.mark.parametrize("schedule", ["45 14 * * *", ""])
def test_every_other_trigger_still_publishes(tmp_path: Path, schedule: str) -> None:
    # The 14:45 cron, and the empty schedule of a workflow_run or a dispatch.
    for offset in ("-0400", "-0500"):
        assert _decide(tmp_path, schedule, offset) == "go=true"


def test_the_publish_job_waits_on_the_gate() -> None:
    publish = _workflow()["jobs"]["publish"]
    assert publish["needs"] == "when"
    assert publish["if"] == "needs.when.outputs.go == 'true'"
