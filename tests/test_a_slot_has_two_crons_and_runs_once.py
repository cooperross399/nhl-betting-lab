"""Every Gameday Refresh slot has two crons and is served once (2026-11-09).

GitHub skipped the 12:30 cron behind the 20:30 afternoon update on
2026-11-09 and started the 05:30 card cron up to 8.6 hours late. Each slot
now has an early primary and a backup 20 minutes after the slot; the backup
stands down when another run's refresh job already started for the slot.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone

import yaml

from nhl_betting_lab.config import PROJECT_ROOT


def _script():
    path = PROJECT_ROOT / "scripts" / "slot_already_taken.py"
    spec = importlib.util.spec_from_file_location("_slot_already_taken", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sat = _script()
SLOT = datetime(2026, 11, 9, 20, 30, tzinfo=timezone.utc)


def _job(started: str, status: str = "completed", conclusion: str | None = "success",
         name: str = "Gameday Refresh") -> dict:
    return {"name": name, "started_at": started, "status": status, "conclusion": conclusion}


def test_a_primary_running_for_the_slot_takes_it() -> None:
    assert sat.slot_taken([_job("2026-11-09T20:30:12Z", "in_progress", None)], SLOT)


def test_a_hand_dispatch_just_before_the_slot_takes_it() -> None:
    assert sat.slot_taken([_job("2026-11-09T20:12:00Z")], SLOT)


def test_the_morning_card_does_not_take_the_afternoon_slot() -> None:
    assert not sat.slot_taken([_job("2026-11-09T13:42:00Z")], SLOT)


def test_a_failed_refresh_leaves_the_slot_free() -> None:
    assert not sat.slot_taken([_job("2026-11-09T20:31:00Z", conclusion="failure")], SLOT)


def test_only_the_refresh_job_counts() -> None:
    assert not sat.slot_taken(
        [_job("2026-11-09T20:31:00Z", "in_progress", None, name="Already published?")], SLOT
    )


def test_an_unreadable_listing_runs_rather_than_skips(monkeypatch, capsys) -> None:
    def boom(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr(sat, "other_jobs", boom)
    assert sat.main(["--schedule", "30 12 * 1-4,10-12 *", "--run-id", "1", "--repo", "a/b"]) == 0
    assert capsys.readouterr().out.startswith("free")


def test_the_precheck_asks_before_anything_else() -> None:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml").read_text(encoding="utf-8")
    )
    feed = next(s for s in workflow["jobs"]["precheck"]["steps"] if s.get("id") == "feed")
    script = feed["run"]
    assert "scripts/slot_already_taken.py" in script
    assert script.index("slot_already_taken.py") < script.index("Afternoon update")
