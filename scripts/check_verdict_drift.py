#!/usr/bin/env python3
"""Has any recorded verdict changed now that more data exists?

    PYTHONPATH=src .venv/bin/python scripts/check_verdict_drift.py

The card's behaviour follows `verdicts.ships()`, which reads decisions from
tracked JSON files. Those decisions were made against the data available on
the day the experiment last ran — and every experiment in this lab has only
ever been run **by hand**. So a policy that stopped being right in November
would go on shipping until somebody happened to re-run it.

This compares the verdicts an experiment produces **now** against the ones
committed to the repository, and reports any that moved. It is the difference
between a lab that improves as evidence accumulates and one that improves
whenever someone remembers.

**It changes nothing.** It reads, compares, and reports. A verdict that has
moved is a pull request for a human to look at, never an automatic edit —
because a scheduled job that silently rewrites the card's policy mid-season
is indistinguishable from tuning, and this lab's whole discipline is that
what ships is auditable against the experiment that decided it.

Exit codes: 0 nothing moved, 1 something moved, **2 the refresh was broken**
— an experiment produced no readable file this run, so nothing was compared
and "nothing moved" would be a false statement rather than a clean bill. The
check failing outright is a broken refresh too, and exits 2: 1 is the code on
which Experiment Refresh opens a pull request.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.verdicts import VERDICT_FILES


def committed(path: Path) -> dict | None:
    """The version of a verdict file as tracked in git, not on disk."""
    rel = path.as_posix()
    for ref in ("HEAD",):
        result = subprocess.run(
            ["git", "show", f"{ref}:{rel}"], capture_output=True, text=True
        )
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return None
    return None


def ships_of(payload: dict | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    value = payload.get("ships")
    if isinstance(value, bool):  # an older convention; a bare true ships nothing
        return []
    return sorted(str(item) for item in (value or []))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument(
        "--since",
        default="",
        help=(
            "Unix timestamp the run started. A verdict file older than this "
            "was not produced by this run, so its experiment did not "
            "actually re-decide anything and 'unchanged' would be a lie."
        ),
    )
    args = parser.parse_args(argv)
    outputs = Path(args.output_dir)

    since = float(args.since) if args.since else 0.0
    moved: list[str] = []
    stale: list[str] = []
    lines = ["# Verdict drift", ""]
    lines.append(
        "What the experiments decide **now**, against what the repository has "
        "committed. A difference is not a bug — it is the evidence having "
        "moved, which is the thing this lab is supposed to notice."
    )
    lines.append("")
    lines.append(
        "**Read a moved verdict against the window it was measured in.** The "
        "price store holds more than one snapshot window, and a verdict "
        "re-decided on a different window from the one that first decided it "
        "has not seen new evidence — it has been asked a different question. "
        "The experiments name their window explicitly for this reason."
    )
    lines.append("")
    lines.append("| policy | committed | now | moved |")
    lines.append("|:--|:--|:--|:--|")

    for policy, filename in sorted(VERDICT_FILES.items()):
        path = outputs / filename
        rel = Path("data/outputs") / filename
        now = None
        if path.is_file():
            try:
                now = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                now = None
        if not isinstance(now, dict):
            now = None
        was_ships = ships_of(committed(rel))
        now_ships = ships_of(now)
        was = "in force" if policy in was_ships else "off"
        current = "in force" if policy in now_ships else "off"
        # A MISSING OR UNREADABLE FILE WAS NOT RE-DECIDED EITHER. This branch
        # dates from when 1 was the only non-zero exit; it labelled the file
        # "not produced" and then compared that label with the committed
        # verdict, so an experiment cut off mid-write ("| `team_b2b` | in
        # force | not produced | **yes** |") exited 1, and the refresh opened
        # a pull request committing the truncated file — which
        # `verdicts.ships()` reads as off. It is a broken refresh: exit 2.
        if now is None:
            current = "**not produced** (missing or unreadable)"
            stale.append(policy)
        # A file that predates this run was not re-decided. Reading it as
        # "unchanged" reports a stale belief as a confirmed one, which is the
        # exact failure this script exists to catch — one level up.
        elif since and path.stat().st_mtime < since:
            current = "**not re-decided** (file predates this run)"
            stale.append(policy)
        changed = was != current and policy not in stale
        if changed:
            moved.append(policy)
        lines.append(
            f"| `{policy}` | {was} | {current} | {'**yes**' if changed else 'no'} |"
        )

    lines.append("")
    if stale:
        lines.append(
            f"**{len(stale)} verdict(s) were not re-decided: "
            + ", ".join(f"`{s}`" for s in stale)
            + ".** Their experiments did not produce a readable file during "
            "this run, so nothing was compared for them. This is a broken "
            "refresh, not "
            "a clean one: a job that cannot re-decide must never report that "
            "nothing changed, because on more data it might have."
        )
        lines.append("")
    if moved:
        lines.append(
            f"**{len(moved)} verdict(s) moved: "
            + ", ".join(f"`{m}`" for m in moved)
            + ".** The card follows these, so this is a change to what it "
            "would do. It is deliberately not applied here: a scheduled job "
            "that rewrites the card's policy on its own is indistinguishable "
            "from tuning. A human reads the evidence and merges, or does not."
        )
    elif not stale:
        lines.append(
            "**Nothing moved.** Every recorded verdict still says what it said "
            "when it was committed, on more data than it had then."
        )

    report = "\n".join(lines) + "\n"
    (outputs / "verdict_drift.md").write_text(report, encoding="utf-8")
    print(report)
    # 2 is a broken refresh and 1 is a real finding. Collapsing them would
    # make a job that failed to run indistinguishable from one that ran and
    # found nothing, which is the whole defect.
    if stale:
        return 2
    return 1 if moved else 0


def cli(argv: list[str] | None = None) -> int:
    """`main`, with a crash reported as the broken refresh it is.

    An uncaught exception ends Python with status 1, and 1 is "a verdict
    moved": the refresh would open a pull request from a check that never
    finished. So a failure here exits 2, which fails the run instead.
    """
    try:
        return main(argv)
    except Exception as error:  # noqa: BLE001 - every failure is a broken refresh
        traceback.print_exc()
        print(
            f"::error::The verdict drift check failed ({type(error).__name__}: "
            f"{error}), so nothing was compared. This is a broken refresh, not "
            "a moved verdict.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
