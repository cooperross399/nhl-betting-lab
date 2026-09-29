"""A scheduled Line Movement run waits for its round, however late GitHub
starts it.

GitHub started this repository's scheduled runs 3.5-6 hours late, so a cron
written at its round landed at or after face-off and no evening game closed.
Each cron now fires `ROUND_LEAD` before its round and the run waits. These
tests pin the arithmetic the wait rests on, and the wiring that puts the wait
in front of the capture: a correct script that the capture does not wait for
fixes nothing.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"


def _script():
    path = PROJECT_ROOT / "scripts" / "wait_for_round.py"
    spec = importlib.util.spec_from_file_location("_wait_for_round_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wfr = _script()


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


@pytest.mark.parametrize("lateness_hours", [0, 3.5, 6, 7.9])
def test_every_lateness_under_the_lead_waits_for_the_same_round(lateness_hours) -> None:
    # The 23:00 round's cron fires at 15:00; it must reach 23:00 whether
    # GitHub starts it on time or nearly eight hours late.
    fired = _utc("2026-10-06T15:00:00")
    now = fired + timedelta(hours=lateness_hours)
    assert wfr.round_for("0 15 * 1-4,10-12 *", now) == _utc("2026-10-06T23:00:00")


def test_a_run_that_started_after_midnight_keeps_yesterdays_round() -> None:
    # The 01:00 round's cron fires at 17:00; started 7.5 h late it is past
    # midnight UTC, and its round is still tonight's 01:00, not tomorrow's.
    now = _utc("2026-10-07T00:30:00")
    assert wfr.round_for("0 17 * 1-4,10-12 *", now) == _utc("2026-10-07T01:00:00")


def test_a_run_later_than_the_lead_captures_at_once(monkeypatch, capsys) -> None:
    slept = []
    monkeypatch.setattr(wfr.time, "sleep", slept.append)
    fake_now = _utc("2026-10-06T23:30:00")  # 15:00 cron, 8.5 h late

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now

    monkeypatch.setattr(wfr, "datetime", Clock)
    assert wfr.main(["--schedule", "0 15 * 1-4,10-12 *"]) == 0
    assert slept == []
    assert "captures now" in capsys.readouterr().out


def test_the_wait_is_cut_to_the_jobs_budget_and_resumed(monkeypatch) -> None:
    slept = []
    monkeypatch.setattr(wfr.time, "sleep", slept.append)
    fake_now = _utc("2026-10-06T15:00:00")  # on time: eight hours to wait

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now

    monkeypatch.setattr(wfr, "datetime", Clock)
    wfr.main(["--schedule", "0 15 * 1-4,10-12 *", "--budget-minutes", "340"])
    assert slept == [340 * 60]
    fake_now = fake_now + timedelta(minutes=340)
    wfr.main(["--schedule", "0 15 * 1-4,10-12 *", "--budget-minutes", "340"])
    assert slept == [340 * 60, 140 * 60]


def test_a_hand_started_run_waits_only_when_told(monkeypatch) -> None:
    now = _utc("2026-09-29T14:30:00")
    assert wfr.target_for("", "", now) is None
    assert wfr.target_for("", "21:30", now) == _utc("2026-09-29T21:30:00")
    assert wfr.target_for("", "01:00", now) == _utc("2026-09-30T01:00:00")
    assert wfr.target_for("", "2026-09-29T21:30Z", now) == _utc("2026-09-29T21:30:00")
    with pytest.raises(ValueError):
        wfr.target_for("", "2026-09-30T12:00Z", now)  # beyond two jobs' reach


def test_both_legs_of_the_wait_fit_the_round_lead() -> None:
    # Two jobs of 340 minutes must be able to cover the whole lead, or an
    # on-time run captures early.
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    budgets = []
    for name in ("wait", "wait-more"):
        (step,) = [s for s in jobs[name]["steps"] if "wait_for_round.py" in str(s.get("run", ""))]
        run = step["run"]
        budget = float(run.split("--budget-minutes")[1].split()[0])
        assert budget < int(jobs[name]["timeout-minutes"])
        budgets.append(budget)
    assert timedelta(minutes=sum(budgets)) >= wfr.ROUND_LEAD
    assert timedelta(minutes=sum(budgets)) >= wfr.MAX_AT_AHEAD


def test_the_capture_waits_for_the_wait_and_runs_even_if_it_failed() -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    assert jobs["wait-more"]["needs"] == "wait"
    assert jobs["capture"]["needs"] == "wait-more"
    for name in ("wait-more", "capture"):
        assert "!cancelled()" in str(jobs[name]["if"])
    for name in ("wait", "wait-more"):
        (step,) = [s for s in jobs[name]["steps"] if "wait_for_round.py" in str(s.get("run", ""))]
        assert step["env"]["SCHEDULE"] == "${{ github.event.schedule }}"
        assert step["env"]["AT"] == "${{ inputs.at }}"
        assert '--schedule "$SCHEDULE"' in step["run"]
        assert '--at "$AT"' in step["run"]


def test_captures_never_overlap_but_waiting_runs_do_not_queue() -> None:
    # A workflow-level group keeps one run pending and cancels the rest, and
    # every waiting run would sit in it for hours.
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert "concurrency" not in document
    group = document["jobs"]["capture"]["concurrency"]
    assert group["group"] == "line-movement"
    assert group["cancel-in-progress"] is False


def test_every_cron_names_a_single_hour_the_wait_can_read() -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = document.get("on", document.get(True))
    now = _utc("2026-10-06T12:00:00")
    for entry in triggers["schedule"]:
        wfr.round_for(entry["cron"], now)  # raises on "6,10" or "*/2"
        minute, hour = entry["cron"].split()[:2]
        assert minute.isdigit() and hour.isdigit(), entry["cron"]


GAMEDAY = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"


def test_the_card_crons_land_on_the_slots_the_routines_read() -> None:
    """13:30 UTC card and 15:00 backup; the routines that read card-feed
    (NHL LAB BRIEF 19:30 UTC, relays 19:45 and 21:45) are timed off these."""
    document = yaml.safe_load(GAMEDAY.read_text(encoding="utf-8"))
    triggers = document.get("on", document.get(True))
    lead = int(wfr.ROUND_LEAD.total_seconds() // 60)
    slots = set()
    for entry in triggers["schedule"]:
        minute, hour = entry["cron"].split()[:2]
        assert minute.isdigit() and hour.isdigit(), entry["cron"]
        slots.add((int(hour) * 60 + int(minute) + lead) % (24 * 60))
    assert slots == {13 * 60 + 30, 15 * 60}


def test_the_card_waits_before_it_asks_whether_it_is_already_published() -> None:
    document = yaml.safe_load(GAMEDAY.read_text(encoding="utf-8"))
    jobs = document["jobs"]
    assert jobs["wait-more"]["needs"] == "wait"
    assert jobs["precheck"]["needs"] == "wait-more"
    assert jobs["refresh"]["needs"] == "precheck"
    for name in ("wait-more", "precheck", "refresh"):
        assert "!cancelled()" in str(jobs[name]["if"]), name
    # The refresh still runs only after a precheck that succeeded and said
    # the card is not out yet; a failed wait must not add a condition.
    condition = str(jobs["refresh"]["if"])
    assert "needs.precheck.result == 'success'" in condition
    assert "needs.precheck.outputs.already != 'true'" in condition
    for name in ("wait", "wait-more"):
        (step,) = [s for s in jobs[name]["steps"] if "wait_for_round.py" in str(s.get("run", ""))]
        assert step["env"]["SCHEDULE"] == "${{ github.event.schedule }}"
        assert '--schedule "$SCHEDULE"' in step["run"]
        budget = float(step["run"].split("--budget-minutes")[1].split()[0])
        assert budget < int(jobs[name]["timeout-minutes"])
    assert "concurrency" not in document
    assert jobs["refresh"]["concurrency"] == {
        "group": "gameday-refresh", "cancel-in-progress": False,
    }
