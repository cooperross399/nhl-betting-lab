#!/usr/bin/env python3
"""Restore the two inputs Season Sim carries from earlier runs.

    python scripts/season_sim_inputs.py previous --into "$RUNNER_TEMP/previous-season"
    python scripts/season_sim_inputs.py ratings --into data/processed

`previous` takes the last successful Season Sim's `season.json` (its daily
award rankings are carried forward as trend lines); `ratings` takes
`shadow_team_ratings.json` out of the newest Gameday Refresh `gameday-state`
(the card's own team ratings, which the season is simulated on). Both go
through `scripts/restore_state.py`, exactly as the workflow called it.

WHY A SCRIPT AND NOT TWO SHELL BLOCKS (2026-11-10). The two steps used to say
"The last season projection could not be restored" and "The card's team
ratings could not be restored" from inside their `run:` blocks, and GitHub
prints every step's script at the top of its log. So every Season Sim log
carried both sentences, on every run, whether or not anything failed: a
search of run 42837197651's log found both, while that run had restored the
last projection (run 42832549612) and the card's ratings (through
2026-11-09) and blended them in at 0.50. Across the 40 runs before it, not
one restore had failed. The sentences now live here, and a log carries one
only when it happened, as a `::warning::`.

Soft by design: it always exits 0, because a projection built without either
input is still a projection, and the page says which ratings it ran on.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESTORE = HERE / "restore_state.py"

PREVIOUS_MISSING = (
    "The last season projection could not be restored; the award trend lines start today."
)
RATINGS_MISSING = (
    "The card's team ratings could not be restored; the season is simulated on its own ratings."
)
RATINGS_FILE = "shadow_team_ratings.json"


def _restore(args: list[str]) -> bool:
    """Run restore_state.py as the workflow did; True when it restored."""
    return subprocess.run([sys.executable, str(RESTORE), *args], check=False).returncode == 0


def restore_previous(into: Path, *, restore=_restore) -> bool:
    into.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=into.parent) as scratch:
        # Unpacked aside and moved, so a partial download is never handed on.
        ok = restore(["--artifact", "season-sim", "--dest", scratch,
                      "--workflow", "season-sim.yml", "--success-only", "--no-merge",
                      "--attempts", "2", "--limit", "60"])
        found = Path(scratch) / "season.json"
        if ok and found.is_file() and found.stat().st_size:
            shutil.move(str(found), into / "season.json")
            print(f"The last season projection is restored to {into / 'season.json'}.")
            return True
    print(f"::warning::{PREVIOUS_MISSING}")
    return False


def restore_ratings(into: Path, *, restore=_restore) -> bool:
    into.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        ok = restore(["--artifact", "gameday-state", "--dest", scratch,
                      "--workflow", "gameday-refresh.yml", "--no-merge", "--attempts", "2"])
        found = Path(scratch) / "processed" / RATINGS_FILE
        if ok and found.is_file() and found.stat().st_size:
            try:
                through = json.loads(found.read_text(encoding="utf-8")).get("last_game_date")
            except (OSError, ValueError, AttributeError):
                through = None
            if through:
                shutil.copy(found, into / RATINGS_FILE)
                print(f"Card ratings through {through}")
                return True
    print(f"::warning::{RATINGS_MISSING}")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", choices=("previous", "ratings"))
    parser.add_argument("--into", required=True)
    args = parser.parse_args(argv)
    into = Path(args.into)
    (restore_previous if args.what == "previous" else restore_ratings)(into)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
