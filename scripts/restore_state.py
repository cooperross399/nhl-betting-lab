#!/usr/bin/env python3
"""Restore a workflow artifact from the newest run that actually carries it.

    python scripts/restore_state.py --artifact gameday-state --dest data \\
        --workflow gameday-refresh.yml --workflow historical-props-purchase.yml

Every workflow here used to pick its restore source with
`gh run list --status success --limit 1`, which is wrong twice over:

* **A skipped run is a success with no artifact.** When the primary Gameday
  Refresh finishes clean, the 15:00 backup's precheck skips the job, and
  GitHub records that run as `success` with zero artifacts. The next day's
  restore picked it, found nothing, and started cold — with no boxscores, no
  snapshots and no ledger — and a cold run is degraded, so red, so it never
  became the next restore source either: every later run started cold too.
* **A red run's state was never restored.** A degraded run still fetches
  boxscores, freezes and posts the day's snapshot, and uploads its state;
  then it fails itself on purpose. Restoring only from green runs threw that
  state away, so a cold cache capped at 600 games a run refetched the same
  600 every day ("this resolves itself" never could), and the posted
  opinion was lost from the forward ledger.

So the source is chosen by the artifact, not the conclusion: the newest
COMPLETED run that can actually be downloaded from, any conclusion. If that
run is not a success, the newest successful run that carries the artifact is
laid underneath it without overwriting anything — a red run that itself
started cold must not replace a full cache with a thin one — and the forward
ledger, which only ever grows, is taken from whichever copy holds more rows.
Workflows are tried in the order given; a later one is used only when no run
of an earlier one carries the artifact.

Standard library only, so it runs before anything is installed. It never
fails the calling step: whatever it restores, it says, and a restore that
finds nothing is a statement, not an error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


#: Relative to the artifact root. Append-only; the longer copy is the truth.
LEDGER = Path("processed") / "forward_evidence.csv"


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def completed_runs(workflow: str, limit: int) -> list[dict]:
    """The workflow's completed runs, newest first, of every conclusion."""
    result = _gh(
        "run", "list", "--workflow", workflow, "--limit", str(limit),
        "--json", "databaseId,conclusion,status",
    )
    if result.returncode != 0:
        print(f"Could not list {workflow} runs: {result.stderr.strip()}")
        return []
    try:
        runs = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [r for r in runs if r.get("status") == "completed"]


def download(run_id: object, artifact: str, into: Path) -> bool:
    return _gh(
        "run", "download", str(run_id), "--name", artifact, "--dir", str(into)
    ).returncode == 0


def _rows(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("rb") as handle:
        return max(0, sum(1 for line in handle if line.strip()) - 1)


def _copy(source: Path, dest: Path, *, overwrite: bool) -> int:
    """Copy every file under `source` into `dest`; count what was written."""
    written = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        target = dest / path.relative_to(source)
        if target.exists() and not overwrite:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        written += 1
    return written


def restore(
    *,
    artifact: str,
    dest: Path,
    workflows: list[str],
    limit: int = 30,
    merge: bool = True,
    also: list[tuple[str, Path]] = (),
) -> dict:
    """Restore `artifact` into `dest`; returns what it did, for the log and tests."""
    report: dict = {"run": None, "conclusion": None, "filled_from": None,
                    "filled": 0, "ledger_from": None}
    dest.mkdir(parents=True, exist_ok=True)
    for workflow in workflows:
        runs = completed_runs(workflow, limit)
        for index, run in enumerate(runs):
            with tempfile.TemporaryDirectory() as scratch:
                if not download(run["databaseId"], artifact, Path(scratch)):
                    continue
                _copy(Path(scratch), dest, overwrite=True)
            report.update(run=run["databaseId"], conclusion=run.get("conclusion"))
            print(
                f"Restored {artifact} from {workflow} run {run['databaseId']} "
                f"({run.get('conclusion')})."
            )
            for name, directory in also:
                directory.mkdir(parents=True, exist_ok=True)
                if not download(run["databaseId"], name, directory):
                    print(f"Run {run['databaseId']} carries no {name}.")
            if merge and run.get("conclusion") != "success":
                _fill_from_last_success(
                    runs[index + 1:], artifact, dest, workflow, report
                )
            return report
    print(
        f"No completed run of {', '.join(workflows)} carries {artifact}; "
        "this run starts without it."
    )
    return report


def _fill_from_last_success(
    older: list[dict], artifact: str, dest: Path, workflow: str, report: dict
) -> None:
    for run in older:
        if run.get("conclusion") != "success":
            continue
        with tempfile.TemporaryDirectory() as scratch:
            base = Path(scratch)
            if not download(run["databaseId"], artifact, base):
                continue
            report["filled_from"] = run["databaseId"]
            report["filled"] = _copy(base, dest, overwrite=False)
            print(
                f"Laid {workflow} run {run['databaseId']} (success) underneath: "
                f"{report['filled']} file(s) the newer state did not have."
            )
            ours, theirs = _rows(dest / LEDGER), _rows(base / LEDGER)
            if theirs > ours:
                shutil.copy2(base / LEDGER, dest / LEDGER)
                report["ledger_from"] = run["databaseId"]
                print(
                    f"The forward ledger from run {run['databaseId']} holds "
                    f"{theirs} row(s) against {ours}; it only ever grows, so "
                    "the longer one is kept."
                )
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--dest", required=True)
    parser.add_argument(
        "--workflow", action="append", required=True,
        help="In priority order; repeat for a fallback.",
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--no-merge", action="store_true",
        help="Take the chosen run's artifact alone, never laying a success under it.",
    )
    parser.add_argument(
        "--also", action="append", default=[], metavar="NAME=DIR",
        help="Another artifact to download from the same chosen run.",
    )
    args = parser.parse_args(argv)
    also = []
    for item in args.also:
        name, _, directory = item.partition("=")
        if not name or not directory:
            parser.error(f"--also takes NAME=DIR, not {item!r}")
        also.append((name, Path(directory)))
    restore(
        artifact=args.artifact,
        dest=Path(args.dest),
        workflows=list(args.workflow),
        limit=args.limit,
        merge=not args.no_merge,
        also=also,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
