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

**`--union N`, for an artifact of append-only CSV stores** (Line Movement's
price, deployment and line-combination captures). Line Movement restored
from `gh run list --status success --limit 1`, so a run that went red — the
price capture's events list failing, or the line units not arriving — was
never restored from, and the free captures it still took and uploaded were
dropped from the chain: in the failure-shape audit's replay (14:00 green,
18:00 red, 21:00 green) the 18:00 scratch list and PP1 promotion survived
only in the red run's own artifact, and the chain first saw them at 21:00,
three hours late. Those sources keep no archive. With `--union N` the newest
carrier is taken whatever its conclusion, and then every CSV in it is
unioned, row by row, with the same file in the N-1 carriers before it, so a
carrier that is thin because its own restore found nothing (and so holds
only its own run's rows) cannot become the base the season is lost from.
A row is never overwritten and never dropped; a file the two copies cannot
be merged safely (different headers, or a parse that disagrees with the
line count) keeps the newer copy and says so. When the older copy is a byte
prefix of the newer one — every ordinary run — nothing is parsed at all.

Standard library only, so it runs before anything is installed. It never
fails the calling step: whatever it restores, it says, and a restore that
finds nothing is a statement, not an error.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
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
    union: int = 0,
) -> dict:
    """Restore `artifact` into `dest`; returns what it did, for the log and tests."""
    report: dict = {"run": None, "conclusion": None, "filled_from": None,
                    "filled": 0, "ledger_from": None, "unioned_from": [],
                    "rows_recovered": 0, "not_merged": []}
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
            if union > 1:
                _union_older(
                    runs[index + 1:], artifact, dest, workflow, report,
                    carriers=union - 1,
                )
            elif merge and run.get("conclusion") != "success":
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


def _records(path: Path) -> tuple[list[str], list[list[str]]] | None:
    """A CSV's header and records, or None when the parse cannot be trusted.

    The floor comes from the bytes, not from the parse it guards: a stray
    quote makes `csv` fold several physical lines into one record, and a
    union written from that read would drop rows while reporting success. A
    file whose record count disagrees with its non-blank line count is
    therefore not merged at all.
    """
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = [row for row in csv.reader(handle) if row]
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    if not rows or len(rows) - 1 != _rows(path):
        return None
    return rows[0], rows[1:]


def union_csv(older: Path, newer: Path) -> int | None:
    """Fold into `newer` the rows of `older` it lacks; returns how many.

    Both are copies of one append-only file. In every ordinary run the older
    copy is a byte prefix of the newer one, and nothing is parsed or written.
    Otherwise the result is the older copy followed by every row the newer
    one added: each row kept as many times as the copy holding it most often
    has it (a multiset union — two identical rows from one capture are two
    rows, not one), and in capture order, because the older copy's rows were
    captured first.

    Returns None, leaving `newer` exactly as it was, when the two cannot be
    merged safely: different headers, or a parse that disagrees with the
    file's line count.
    """
    if newer.read_bytes().startswith(older.read_bytes()):
        return 0
    old, new = _records(older), _records(newer)
    if old is None or new is None or old[0] != new[0]:
        return None
    unmatched = Counter(tuple(record) for record in old[1])
    added = []
    for record in new[1]:
        key = tuple(record)
        if unmatched[key]:
            unmatched[key] -= 1
        else:
            added.append(record)
    recovered = len(old[1]) + len(added) - len(new[1])
    if not recovered:
        return 0
    merged = newer.with_name(newer.name + ".union")
    with merged.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(new[0])
        writer.writerows(old[1])
        writer.writerows(added)
    merged.replace(newer)
    return recovered


def _union_older(
    older: list[dict], artifact: str, dest: Path, workflow: str, report: dict,
    *, carriers: int,
) -> None:
    """Union `dest` with up to `carriers` older runs' copies of `artifact`."""
    for run in older:
        if len(report["unioned_from"]) >= carriers:
            return
        with tempfile.TemporaryDirectory() as scratch:
            base = Path(scratch)
            if not download(run["databaseId"], artifact, base):
                continue
            recovered = 0
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(base)
                target = dest / relative
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                    recovered += _rows(target) if target.suffix == ".csv" else 0
                    continue
                if target.suffix != ".csv":
                    continue
                added = union_csv(path, target)
                if added is None:
                    report["not_merged"].append(str(relative))
                    print(
                        f"::warning::{relative} in {workflow} run "
                        f"{run['databaseId']} could not be merged with the "
                        "newer copy (different header, or a parse that "
                        "disagrees with its line count). The newer copy is "
                        "kept; the older rows remain in that run's artifact."
                    )
                    continue
                recovered += added
        report["unioned_from"].append(run["databaseId"])
        report["rows_recovered"] += recovered
        print(
            f"Unioned {workflow} run {run['databaseId']} "
            f"({run.get('conclusion')}): {recovered} row(s) the newer "
            "captures did not have."
        )


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
    parser.add_argument(
        "--union", type=int, default=0, metavar="N",
        help=(
            "The artifact holds append-only CSV stores: union each CSV, row "
            "by row, with the same file in the N-1 carriers before the "
            "newest, instead of laying the last success underneath."
        ),
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
        union=args.union,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
