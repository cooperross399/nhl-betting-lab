#!/usr/bin/env python3
"""The site's history only grows: record what was restored, refuse to upload less.

    python scripts/site_history_floor.py record --history dist/data/history \\
        --floor "$RUNNER_TEMP/site-history-floor.json"
    python scripts/site_history_floor.py check --history dist/data/history \\
        --floor "$RUNNER_TEMP/site-history-floor.json"

Publish Site restores the last publish's `site-history` artifact, builds
today's board into it, and uploads it again as tomorrow's source. Nothing
used to compare the history it uploaded with the one it restored. When the
restore failed on a transient API error, the build froze today's board
alone, `index.json` was rewritten with one entry, the run went green, and
that one-board history became every later run's source: in the failure-shape
audit's replay a three-board history became one, for good, and Results said
"No board was published for this date" about a day whose board was
published with 14 games.

`record` runs straight after the restore, before anything is built, and
writes the floor: a SHA-256 of every frozen board (`<date>[_<slot>].json`,
the published opinion Results settles against) and the name of every line
file. `check` runs before the upload and the deploy and fails (exit 1)
unless every recorded board is still there and byte-identical — a board is
frozen once, the day's first published opinion stands, and nothing may
re-freeze it — every recorded line file is still there, and `index.json`,
which the Archive page reads, still lists every recorded board. A missing
floor record is a refusal, not an empty floor: it means the restore step
never got that far.

Standard library only. Fetches nothing, spends nothing, places no bet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

#: The names `web/site_history.py` freezes and indexes.
BOARD = re.compile(r"^\d{4}-\d{2}-\d{2}(?:_\w+)?\.json$")


def snapshot(history: Path) -> dict:
    """{"boards": {name: sha256}, "lines": [relative names]} for `history`."""
    boards = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(history.glob("*.json"))
        if BOARD.match(path.name)
    }
    lines = sorted(
        path.relative_to(history).as_posix()
        for path in (history / "lines").glob("*.json")
    )
    return {"boards": boards, "lines": lines}


def record(history: Path, floor: Path) -> int:
    taken = snapshot(history)
    floor.parent.mkdir(parents=True, exist_ok=True)
    floor.write_text(json.dumps(taken, indent=1, sort_keys=True), encoding="utf-8")
    print(
        f"Restored history: {len(taken['boards'])} frozen board(s) and "
        f"{len(taken['lines'])} line file(s); the upload may hold no fewer."
    )
    return 0


def _indexed(history: Path) -> set[str]:
    """The boards `index.json` lists; none when it is missing or unreadable."""
    try:
        index = json.loads((history / "index.json").read_text(encoding="utf-8"))
        return {str(entry["file"]) for entry in index["dates"]}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def problems(history: Path, floor: dict) -> list[str]:
    """Everything the restored history held that this one has lost."""
    now = snapshot(history)
    found = []
    for name, digest in sorted(floor["boards"].items()):
        if name not in now["boards"]:
            found.append(f"history/{name} was restored and is gone.")
        elif now["boards"][name] != digest:
            found.append(
                f"history/{name} was restored and has been rewritten; the "
                "day's first published opinion stands."
            )
    for name in floor["lines"]:
        if name not in now["lines"]:
            found.append(f"history/{name} was restored and is gone.")
    for name in sorted(set(floor["boards"]) - _indexed(history)):
        found.append(f"history/index.json no longer lists {name}.")
    return found


def check(history: Path, floor_path: Path) -> int:
    try:
        floor = json.loads(floor_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(
            f"::error::No record of the history this run restored ({floor_path}). "
            "Without it there is no telling what an upload would lose, so "
            "nothing is kept or deployed."
        )
        return 1
    found = problems(history, floor)
    if found:
        for line in found:
            print(f"::error::{line}")
        print(
            f"::error::The history holds less than the {len(floor['boards'])} "
            "frozen board(s) this run restored. It is not kept for tomorrow "
            "and not deployed; the site keeps its last build."
        )
        return 1
    boards = len(snapshot(history)["boards"])
    print(
        f"history: all {len(floor['boards'])} restored board(s) and "
        f"{len(floor['lines'])} line file(s) are still here; {boards} to keep."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("record", "check"))
    parser.add_argument("--history", required=True)
    parser.add_argument("--floor", required=True)
    args = parser.parse_args(argv)
    if args.action == "record":
        return record(Path(args.history), Path(args.floor))
    return check(Path(args.history), Path(args.floor))


if __name__ == "__main__":
    sys.exit(main())
