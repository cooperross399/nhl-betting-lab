#!/usr/bin/env python3
"""Hold a scheduled run until the round it was scheduled for.

Used by Line Movement Capture (rounds 14:00, 18:00, 21:00, 23:00, 01:00 UTC)
and Gameday Refresh (the 13:30 card and the 15:00 backup).

    python scripts/wait_for_round.py --schedule "0 15 * 1-4,10-12 *"
    python scripts/wait_for_round.py --at 2026-09-29T21:30Z

WHY. A capture only counts as the close when it lands strictly before face-off
and no more than `closing_lines.CLOSE_MAX_LEAD` (150 minutes) before it. GitHub
starts this repository's scheduled runs hours late: 3.5-4.2 h measured on
2026-09-24, 5.5-6.0 h on 2026-09-28. A cron written at the round it wants
therefore lands at 7pm ET face-off or after it, and the 23:00 UTC round lands
past midnight in New York, so it captures tomorrow's slate and restores
nothing of today's. Lateness is not stable enough to aim a cron at: it moves
by hours between days, and the close window is 150 minutes wide.

Gameday Refresh has the same problem: its 13:30 card landed about 19:30,
after the routines that read it and at the first 17:00 ET face-off.

So every cron fires `ROUND_LEAD` before its round, and the run waits here,
before the capture or the card, until the round. Lateness up to `ROUND_LEAD` then costs
nothing; beyond it, the run captures as soon as it starts, which is what
every run did before. A run is never held past its round and never captures
early because it started early.

A job may run for at most six hours, so the wait is split across two jobs,
each waiting at most `--budget-minutes`; the second picks up where the first
stopped, because the round is recomputed from the same cron each time.

The round is the most recent time the cron named, at or before now, plus
`ROUND_LEAD`: a scheduled run always starts after its cron time, and never a
day late. A cron that names specific days (the opening week) is read the same
way; only its minute and hour matter here.

`--at` is for a run started by hand: it waits until that UTC time, which must
be in the future and within `MAX_AT_AHEAD`. No schedule and no `--at` means
no wait. Nothing here fetches, spends a credit or reads a secret.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

#: How far before its round every Line Movement cron fires. Covers every
#: afternoon lateness measured on this account (worst 6.0 h, 2026-09-28) with
#: two hours spare; the account-wide worst, 7.38 h, was a 06:00 UTC cron.
ROUND_LEAD = timedelta(hours=8)

#: The furthest ahead a hand-started run may be told to wait: two jobs of at
#: most six hours each, less the time the capture itself needs.
MAX_AT_AHEAD = timedelta(hours=11)


def round_for(schedule: str, now: datetime) -> datetime:
    """The round a run fired by `schedule` is for."""
    fields = schedule.split()
    if len(fields) != 5:
        raise ValueError(f"not a five-field cron: {schedule!r}")
    minute, hour = int(fields[0]), int(fields[1])
    fired = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if fired > now:
        fired -= timedelta(days=1)
    return fired + ROUND_LEAD


def parse_at(value: str, now: datetime) -> datetime:
    """A UTC time to wait for: ISO (`2026-09-29T21:30Z`) or `HH:MM`, taken as
    the time the clock reads that nearest to now, within twelve hours either
    side.

    Not the NEXT time the clock reads it. The wait runs in two jobs and each
    recomputes the target from the same `--at`. When the first job's wait
    ended at the target, the second started a few seconds after it, read
    "19:45" as tomorrow's 19:45, found that more than `MAX_AT_AHEAD` away and
    exited 2: the capture still ran on time, but the run went red (run
    36582803431, 2026-09-29). A time a few seconds or hours past is a target
    already reached, and the run captures now."""
    text = value.strip()
    if len(text) == 5 and text[2] == ":":
        target = now.replace(
            hour=int(text[:2]), minute=int(text[3:]), second=0, microsecond=0
        )
        if target - now > timedelta(hours=12):
            target -= timedelta(days=1)
        elif now - target >= timedelta(hours=12):
            target += timedelta(days=1)
        return target
    target = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if target.tzinfo is None:
        raise ValueError(f"--at needs a UTC offset or a trailing Z: {value!r}")
    return target.astimezone(timezone.utc)


def target_for(schedule: str, at: str, now: datetime) -> datetime | None:
    if at.strip():
        target = parse_at(at, now)
        if target - now > MAX_AT_AHEAD:
            raise ValueError(
                f"--at {at!r} is {target - now} away; a run can wait at most "
                f"{MAX_AT_AHEAD}"
            )
        return target
    if schedule.strip():
        return round_for(schedule, now)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--schedule", default="", help="github.event.schedule")
    parser.add_argument("--at", default="", help="UTC time a hand-started run waits for")
    parser.add_argument("--budget-minutes", type=float, default=340.0)
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    try:
        target = target_for(args.schedule, args.at, now)
    except ValueError as exc:
        print(f"::error::{exc}")
        return 2
    if target is None:
        print("Started by hand with no --at: capturing now.")
        return 0
    stamp = f"{target:%Y-%m-%d %H:%M} UTC"
    remaining = target - now
    if remaining <= timedelta(0):
        print(
            f"This round was due at {stamp}; the run started {-remaining} "
            "after it, so it captures now."
        )
        return 0
    wait = min(remaining, timedelta(minutes=args.budget_minutes))
    print(f"Round due at {stamp}; waiting {wait} of the {remaining} left.")
    sys.stdout.flush()
    time.sleep(wait.total_seconds())
    if wait < remaining:
        print("This job's budget is spent; the next wait job holds the rest.")
    else:
        print(f"Reached {stamp}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
