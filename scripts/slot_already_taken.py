#!/usr/bin/env python3
"""Has another Gameday Refresh already taken this run's slot?

    python3 scripts/slot_already_taken.py --schedule "30 12 * 1-4,10-12 *" \
        --run-id "$GITHUB_RUN_ID" --repo owner/name

Prints `taken` or `free` and exits 0 either way.

WHY. Each Gameday Refresh slot has two crons since 2026-11-09 (see
`wait_for_round.CRON_LEADS`), because GitHub starts this repository's
scheduled runs up to 8.6 hours late and sometimes not at all: on 2026-11-09
the 12:30 cron behind the 20:30 afternoon update never ran. Two crons buy a
second chance, and without this they would also buy a second fetch on every
day both arrive. The backup is aimed 20 minutes after the slot, so by then
the primary's refresh job has started. A slot is taken when any other run of
this workflow has a "Gameday Refresh" job that started no earlier than 30
minutes before the slot and is running or succeeded. A run dispatched by hand
for the slot counts too. The morning backup (15:00) is unaffected: the 13:30
card's job starts before 14:30.

Anything that cannot be read counts as free: a run spent twice costs credits,
a run skipped costs the update.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

#: How far before the slot a refresh still counts as this slot's.
SLOT_GRACE = timedelta(minutes=30)
#: The job whose start marks a slot as served.
REFRESH_JOB = "Gameday Refresh"


def _wait_for_round():
    path = Path(__file__).resolve().parent / "wait_for_round.py"
    spec = importlib.util.spec_from_file_location("_wait_for_round", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def slot_taken(jobs: list[dict], slot: datetime) -> bool:
    """Whether any of these jobs (from other runs) served the slot."""
    since = slot - SLOT_GRACE
    for job in jobs:
        if job.get("name") != REFRESH_JOB:
            continue
        started = _parse(job.get("started_at"))
        if started is None or started < since:
            continue
        if job.get("status") in ("in_progress", "queued", "waiting"):
            return True
        if job.get("conclusion") == "success":
            return True
    return False


def _get(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def other_jobs(repo: str, run_id: str, since: datetime, token: str) -> list[dict]:
    api = f"https://api.github.com/repos/{repo}/actions"
    created = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    runs = _get(
        f"{api}/workflows/gameday-refresh.yml/runs?per_page=30&created=%3E%3D{created}",
        token,
    ).get("workflow_runs", [])
    jobs: list[dict] = []
    for run in runs:
        if str(run.get("id")) == str(run_id):
            continue
        jobs.extend(_get(f"{api}/runs/{run['id']}/jobs?per_page=30", token).get("jobs", []))
    return jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    try:
        slot = _wait_for_round().round_for(args.schedule, now)
    except ValueError as exc:
        print(f"free ({exc})")
        return 0
    token = os.environ.get("GH_TOKEN", "")
    try:
        # A run that served this slot was created at most a day before it.
        jobs = other_jobs(args.repo, args.run_id, slot - timedelta(hours=24), token)
    except Exception as exc:  # noqa: BLE001 - unreadable means run
        print(f"free (could not list runs: {exc})")
        return 0
    if slot_taken(jobs, slot):
        print(f"taken: another Gameday Refresh already serves the {slot:%H:%M} UTC slot")
    else:
        print(f"free: no other Gameday Refresh has served the {slot:%H:%M} UTC slot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
