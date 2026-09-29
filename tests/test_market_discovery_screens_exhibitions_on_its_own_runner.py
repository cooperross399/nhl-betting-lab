"""Provider Market Discovery caches the club schedules, so its screen can run.

#242 put the preseason screen in every `run_provider_shadow.py` run, and the
record says exhibitions therefore no longer take Provider Market Discovery
probe slots either (the whole posted board, `--max-events 20`). #249 then
found that a runner with no club-schedule cache abstains, and gave Line
Movement a free "Cache the club schedules" step, but not Discovery. That
runner restores no state and fetches no schedule, so `data/raw` (gitignored)
held nothing, `preseason_screen` returned "No regular-season schedule is
cached", and a late-September or early-October props dispatch spent its ten
per-event slots in face-off order, exhibitions first. The coverage table then
read "k of 20 — incomplete" for regular-season games the cap never reached:
the starved-probe look this workflow exists to prevent.

Discovery now takes the same free step before the probe spends a credit.
"""

from __future__ import annotations

import json

import yaml

from nhl_betting_lab.config import PROJECT_ROOT


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "provider-market-discovery.yml"
PROBE = "Fetch and report coverage"


def _job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["discover"]


def _schedule_step() -> tuple[int, dict]:
    steps = _job()["steps"]
    matches = [
        (index, step) for index, step in enumerate(steps)
        if "fetch_nhl_data.py" in str(step.get("run", ""))
    ]
    assert len(matches) == 1, "exactly one step caches the club schedules"
    return matches[0]


def test_discovery_caches_the_club_schedules_before_the_probe_spends_a_credit() -> None:
    steps = _job()["steps"]
    names = [step.get("name", "") for step in steps]
    index, step = _schedule_step()
    assert index < names.index(PROBE)
    assert "run_provider_shadow.py" in steps[names.index(PROBE)]["run"]
    # Only the schedules: the probe needs nothing else, and nothing else is free
    # of the minutes it would cost.
    assert "--schedules-only" in step["run"]
    # The script imports the package from src, as the probe's step does.
    assert (step.get("env") or {}).get("PYTHONPATH") == "src"


def test_the_schedule_step_can_never_cost_the_probe() -> None:
    _, step = _schedule_step()
    # Never fatal: a failed or partial fetch leaves the cache incomplete, the
    # screen abstains on that and says so, and the probe runs unscreened.
    assert step.get("continue-on-error") is True
    # Never slow enough to cost it either: a hanging NHL API retries 4 x 30 s
    # for each of 32 clubs, far past the job's limit.
    assert 0 < int(step.get("timeout-minutes", 0)) <= 3
    assert int(step["timeout-minutes"]) < int(_job()["timeout-minutes"])


def test_the_schedule_step_holds_no_provider_credential() -> None:
    """Free: the NHL API only. No step that holds the key is widened."""
    _, step = _schedule_step()
    assert "NHL_ODDS_API_KEY" not in json.dumps(step)
    assert "secrets" not in json.dumps(step)
