"""Publish Site refreshes the public site at 7:00 AM New York every day.

Cooper asked on 2026-11-01. Cron reads UTC, so two crons are scheduled, one
for each New York offset, and the `when` job keeps exactly one of them: the
one that lands at 7 AM given whether New York is on daylight time at the
slot. GitHub starts this repository's scheduled runs hours late (the first
crons written at 10:55 and 11:55 UTC had not started by 12:34 UTC on
2026-11-02), so each cron fires eight hours before its slot and the `wait`
jobs hold the run until it, as Gameday Refresh does. These tests replay the
gate under both offsets and check the wait lands on the slot.
"""

from __future__ import annotations

import importlib.util
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-site.yml"
EDT_CRON = "55 2 * * *"
EST_CRON = "55 3 * * *"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _gate_script() -> str:
    steps = _workflow()["jobs"]["when"]["steps"]
    (step,) = [s for s in steps if s.get("id") == "clock"]
    return step["run"]


def _decide(tmp_path: Path, schedule: str, offset: str) -> dict[str, str]:
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
    return dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").split())


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
        decided = _decide(tmp_path, cron, offset)
        if cron == publishes:
            assert decided == {"go": "true", "hold": "true"}, (cron, offset)
        else:
            assert decided == {"go": "false", "hold": "false"}, (cron, offset)


@pytest.mark.parametrize("schedule", ["45 14 * * *", ""])
def test_every_other_trigger_publishes_without_waiting(tmp_path: Path, schedule: str) -> None:
    # The 14:45 cron, and the empty schedule of a workflow_run or a dispatch.
    for offset in ("-0400", "-0500"):
        assert _decide(tmp_path, schedule, offset) == {"go": "true", "hold": "false"}


def test_the_gate_reads_new_yorks_offset_at_the_slot_not_at_the_fire() -> None:
    # A cron that fires before a daylight saving change publishes after it.
    script = _gate_script()
    assert 'date -d "$slot UTC" +%z' in script
    assert '"55 2 * * *") want="-0400"; slot="10:55"' in script
    assert '"55 3 * * *") want="-0500"; slot="11:55"' in script


def _wait_for_round():
    path = ROOT / "scripts" / "wait_for_round.py"
    spec = importlib.util.spec_from_file_location("_wait_for_round_site", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("cron, slot", [(EDT_CRON, (10, 55)), (EST_CRON, (11, 55))])
def test_the_wait_ends_at_the_slot_the_gate_names(cron: str, slot: tuple[int, int]) -> None:
    started = datetime(2026, 11, 2, 7, 13, tzinfo=timezone.utc)  # four hours late
    target = _wait_for_round().round_for(cron, started)
    assert (target.hour, target.minute) == slot
    assert target.date() == started.date()


def test_only_the_publishing_morning_run_waits_and_nothing_cancels_the_wait() -> None:
    workflow = _workflow()
    jobs = workflow["jobs"]
    for name in ("wait", "wait-more"):
        (step,) = [s for s in jobs[name]["steps"] if "wait_for_round.py" in str(s.get("run", ""))]
        assert "--budget-minutes 340" in step["run"]
        assert "needs.when.outputs.hold == 'true'" in str(jobs[name]["if"])
        assert jobs[name]["timeout-minutes"] <= 360
    # A workflow-level group with cancel-in-progress would let a Gameday
    # Refresh completion, or the other morning cron, cancel the wait.
    assert "concurrency" not in workflow
    publish = jobs["publish"]
    assert publish["concurrency"] == {"group": "publish-site", "cancel-in-progress": True}
    assert publish["needs"] == ["when", "wait-more"]
    assert "!cancelled()" in publish["if"]
    assert "needs.when.outputs.go == 'true'" in publish["if"]


def test_the_seven_am_board_fetches_todays_team_odds_softly() -> None:
    """Cooper, 2026-11-11: live odds on the site by 7 AM. The 7 AM run's
    restored state holds last night's prices, for yesterday's games, so the
    publish job asks the bulk team markets itself: never per-event props,
    never on a run a Gameday Refresh started (that run's prices are fresh),
    and never able to stop the board being built. It must run before the
    board is built."""
    steps = _workflow()["jobs"]["publish"]["steps"]
    names = [s.get("name", "") for s in steps]
    (step,) = [s for s in steps if s.get("name") == "Fetch this morning's team odds for the board"]
    assert step.get("continue-on-error") is True
    assert "workflow_run" in step["if"] and "!=" in step["if"]
    run = step["run"]
    assert "run_provider_shadow.py --live" in run
    assert "--props" not in run
    assert "--output-dir \"$RUNNER_TEMP/" in run
    assert names.index(step["name"]) > names.index("Restore the lab's latest state")
    assert names.index(step["name"]) < names.index("Build today's board and yesterday's results")
