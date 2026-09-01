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

Exit codes: 0 nothing moved, 1 something moved (so a workflow can branch).
"""

from __future__ import annotations

import argparse
import json
import subprocess
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
    args = parser.parse_args(argv)
    outputs = Path(args.output_dir)

    moved: list[str] = []
    lines = ["# Verdict drift", ""]
    lines.append(
        "What the experiments decide **now**, against what the repository has "
        "committed. A difference is not a bug — it is the evidence having "
        "moved, which is the thing this lab is supposed to notice."
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
            except (OSError, json.JSONDecodeError):
                now = None
        was_ships = ships_of(committed(rel))
        now_ships = ships_of(now)
        was = "in force" if policy in was_ships else "off"
        current = "in force" if policy in now_ships else "off"
        if now is None:
            current = "not produced"
        changed = was != current
        if changed:
            moved.append(policy)
        lines.append(
            f"| `{policy}` | {was} | {current} | {'**yes**' if changed else 'no'} |"
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
    else:
        lines.append(
            "**Nothing moved.** Every recorded verdict still says what it said "
            "when it was committed, on more data than it had then."
        )

    report = "\n".join(lines) + "\n"
    (outputs / "verdict_drift.md").write_text(report, encoding="utf-8")
    print(report)
    return 1 if moved else 0


if __name__ == "__main__":
    raise SystemExit(main())
