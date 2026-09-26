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

**Only runs on the default branch are sources** (`--branch`, default
`main`). The listing used to pass no `--branch` and never read a run's
`headBranch`, so the newest carrier on ANY branch became the state main's
next run started from. A feature-branch dispatch runs code nobody has
reviewed, and every store restored here is append-only or first-opinion-
stands: a branch's frozen snapshot would have stood as the day's opinion
and settled into the pre-registered forward ledger, and Publish Site would
have frozen the public board from it. It was already set to happen: Line
Movement's only unexpired artifact (run 33691822845, 2026-09-02, branch
`rehearse-the-line-fetch`, expiring 2026-12-01; the two main runs before it
carry none) would have seeded the season's capture chain on 2026-09-29.
The branch is filtered twice, and each half does work the other cannot:
`gh run list --branch` keeps branch runs out of the `--limit` window, so a
burst of dispatches cannot crowd main's carriers out of it; and each run's
own `headBranch` is checked, so the restore does not rest on a flag whose
effect it cannot see. Every older carrier the fill and the union read is
sliced from that same list. On 2026-09-25 `gh run list --branch main`
returned exactly the unfiltered list for Gameday Refresh and Historical
Props Purchase, so no carrier this lab holds is lost; a branch's artifact
is restored only when `--branch` names that branch.

Standard library only, so it runs before anything is installed. By default
it never fails the calling step: whatever it restores, it says, and a
restore that finds nothing is a statement, not an error.

**`--success-only --require-newest --attempts N`, for Publish Site's
`site-history`.** That restore was `gh run list --status success --limit 1`
and `gh run download ... || echo`, so a failed API call read exactly like
"there has never been a publish": the build froze today's board alone, the
run went green, and its one-board history became the next run's source. In
the failure-shape audit's replay one HTTP 502 took a three-board history to
one, for good, and Results said "No board was published" about a day whose
board had 14 games. The history is not a cache that an older copy can stand
in for: every publish may add the day's frozen board, so a download from an
older run loses whatever the newest added. So under `--require-newest` a
listing that fails, or a download from the newest listed run that fails,
exits 1 after N attempts — the caller refuses to publish — and only a
listing that succeeds and holds no run starts without the artifact.
`--success-only` has GitHub filter the listing (`--status success`), so a
red streak longer than `--limit` cannot hide the last good run and read as
"there has never been one".

**`--refuse-unreachable --attempts N`, for Historical Props Purchase's
bought prices.** A failure to ask GitHub is never read as an answer. Without
it, a listing that fails prints and reads as "no runs", and a download that
fails moves on to an older run. In the purchase that was the whole chain.
Its `historical-props` listing was inline and read no status, so one HTTP
502 became "No purchase run on main carries bought prices. Anything bought
this run is bought fresh." (exit 0 under the `bash -e` GitHub runs). The
buy then found no cached event and paid for the window again. In the
failure-shape audit's replay that was 12 events and 1,284 credits that a
working restore served from the cache for 0. The CSV it wrote held that
run's 7,961 rows alone, and both uploads carried them. The carrier before
held 40,942, and the next purchase and Experiment Refresh took the thin one
as the chain.

Under this flag, these exit 1 after N attempts:
* a listing that fails;
* a download that fails, from the chosen run or from any run the fill or
  the union reads, unless gh says the run holds no such artifact.

The purchase then stops before it spends or uploads. gh's two answers for
"not here" (`ABSENT`) are answers, so they are not retried, and that run is
passed over as before. `--require-newest` refuses that too, which is right
for a history that every successful publish adds to. It would be wrong for
the purchase. A purchase that is refused or cancelled uploads nothing, and
under `--require-newest` it would become a newest run that no later
purchase could get past. `--record-run FILE` writes the chosen run's id to
FILE, or an empty FILE when the listing holds no carrier, so a calling step
can name its source without parsing this log. FILE is emptied before
anything is asked, so a refused restore never leaves an id behind.

**`--also NAME=DIR`** takes a second artifact from the same chosen run
(Publish Site: the run's reports, beside its state). It goes through an
empty temporary directory like the first and is then copied over DIR, the
chosen run's files winning. It used to be downloaded straight into DIR, and
gh refuses to overwrite: into a data/outputs already holding the committed
reports it stopped at the first one, so forward_evidence.json never reached
the site, and the log blamed a missing artifact. See `_restore_also`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path


#: Relative to the artifact root. Append-only; the longer copy is the truth.
LEDGER = Path("processed") / "forward_evidence.csv"

#: The only branch whose runs are restored from unless `--branch` says
#: otherwise: the protected one, where code arrives only through review.
#: A literal, so no caller has to pass it: a workflow expression that came
#: out empty would name no branch, restore nothing and start every store
#: cold.
DEFAULT_BRANCH = "main"


class Unreachable(RuntimeError):
    """GitHub could not be asked, which is not the same as having nothing."""


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _pause(attempt: int) -> None:
    """Wait before the next attempt: 10s, then 20s, and so on. The tests set
    RESTORE_STATE_RETRY_SECONDS to 0; nothing else needs to."""
    time.sleep(float(os.environ.get("RESTORE_STATE_RETRY_SECONDS", "10")) * attempt)


def completed_runs(
    workflow: str, limit: int, branch: str = DEFAULT_BRANCH, *,
    success_only: bool = False, attempts: int = 1, strict: bool = False,
) -> list[dict]:
    """The workflow's completed runs on `branch`, newest first, of every
    conclusion — or, with `success_only`, its successes as GitHub filters them.

    This listed every branch: no `--branch`, no `headBranch`. Line Movement's
    newest carrier is a 2026-09-02 dispatch on `rehearse-the-line-fetch`, and
    it would have seeded the season's capture chain; a Gameday Refresh
    dispatched on a branch would have become the day's frozen opinion. `gh`
    filters by branch so branch runs cannot fill the `--limit` window, and
    each run's `headBranch` is checked as well, so nothing rests on a flag
    whose effect this script cannot otherwise see.

    A listing that fails is printed and read as no runs, unless `strict`,
    when it raises `Unreachable` after `attempts` tries.
    """
    args = ["run", "list", "--workflow", workflow, "--branch", branch,
            "--limit", str(limit),
            "--json", "databaseId,conclusion,status,headBranch"]
    if success_only:
        args += ["--status", "success"]
    problem = f"{workflow} runs were listed as something other than JSON."
    for attempt in range(attempts):
        if attempt:
            _pause(attempt)
        result = _gh(*args)
        if result.returncode != 0:
            problem = f"Could not list {workflow} runs: {result.stderr.strip()}"
            print(problem)
            continue
        try:
            runs = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            continue
        completed = [r for r in runs if r.get("status") == "completed"]
        elsewhere = [r for r in completed if r.get("headBranch") != branch]
        if elsewhere:
            print(
                f"::warning::gh listed {len(elsewhere)} completed {workflow} run(s) "
                f"on other branches despite --branch {branch} ("
                + ", ".join(f"{r.get('databaseId')} on {r.get('headBranch')!r}"
                            for r in elsewhere)
                + "); none of them is a restore source."
            )
        return [r for r in completed if r.get("headBranch") == branch]
    if strict:
        raise Unreachable(f"{problem} ({attempts} attempt(s))")
    return []


def _download(run_id: object, artifact: str, into: Path) -> subprocess.CompletedProcess:
    return _gh("run", "download", str(run_id), "--name", artifact, "--dir", str(into))


#: What gh 2.97.0 prints when the run holds no artifact of that name (or only
#: an expired one). Every other failure is a failure to download an artifact
#: that is there, and is reported as gh's own words, never as an absence.
NO_SUCH_ARTIFACT = "no artifact matches any of the names or patterns provided"

#: What gh 2.97.0 prints when the run holds no valid artifact at all: none
#: was uploaded (a refused or cancelled run), or every one has expired.
NO_ARTIFACTS = "no valid artifacts found to download"

#: gh's answers that a run holds no such artifact. Under `--refuse-unreachable`
#: every other failed download is a failure to ask, never an absence.
ABSENT = (NO_SUCH_ARTIFACT, NO_ARTIFACTS)


def download(run_id: object, artifact: str, into: Path) -> bool:
    return _download(run_id, artifact, into).returncode == 0


def _said(result: subprocess.CompletedProcess) -> str:
    return " ".join((result.stderr or "").split()) or f"nothing (exit {result.returncode})"


def _obtain(run_id: object, artifact: str, into: Path, attempts: int) -> bool:
    """Download for `--refuse-unreachable`: True when it downloaded, False
    when gh says the run holds no such artifact (an answer, so not retried),
    and `Unreachable` when any other failure outlasts `attempts` tries, each
    into an emptied folder."""
    for attempt in range(attempts):
        if attempt:
            _pause(attempt)
            shutil.rmtree(into)
            into.mkdir()
        result = _download(run_id, artifact, into)
        if result.returncode == 0:
            return True
        said = _said(result)
        if any(answer in said for answer in ABSENT):
            return False
        print(f"Attempt {attempt + 1} of {attempts} to download {artifact} "
              f"from run {run_id} failed: {said}")
    raise Unreachable(
        f"Could not download {artifact} from run {run_id} after {attempts} "
        f"attempt(s), and gh did not say the run holds none. An older run "
        "cannot stand in for it: whatever this one added would be lost."
    )


def _take(run_id: object, artifact: str, into: Path, refuse_after: int) -> bool:
    """The fill's and the union's download. By default a failure reads as
    "this run has none" and the next one is tried, as it always has; with
    `refuse_after` (`--refuse-unreachable`'s attempts) that is `_obtain`."""
    if refuse_after:
        return _obtain(run_id, artifact, into, refuse_after)
    return download(run_id, artifact, into)


def _fetch(run_id: object, artifact: str, into: Path, attempts: int) -> bool:
    """`download`, tried up to `attempts` times, each into an emptied folder."""
    for attempt in range(attempts):
        if attempt:
            _pause(attempt)
            shutil.rmtree(into)
            into.mkdir()
        result = _download(run_id, artifact, into)
        if result.returncode == 0:
            return True
        if attempts > 1:
            print(f"Attempt {attempt + 1} of {attempts} to download {artifact} "
                  f"from run {run_id} failed: {result.stderr.strip()}")
    return False


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
    branch: str = DEFAULT_BRANCH,
    success_only: bool = False,
    require_newest: bool = False,
    attempts: int = 1,
    refuse_unreachable: bool = False,
) -> dict:
    """Restore `artifact` into `dest`; returns what it did, for the log and tests.

    With `require_newest`, raises `Unreachable` when a listing fails or the
    newest listed run's download fails. With `refuse_unreachable`, raises it
    when a listing fails or any download fails for a reason other than gh
    saying the run holds none. See the module docstring.
    """
    refuse_after = attempts if refuse_unreachable else 0
    report: dict = {"run": None, "conclusion": None, "filled_from": None,
                    "filled": 0, "ledger_from": None, "unioned_from": [],
                    "rows_recovered": 0, "not_merged": [], "also": {}}
    dest.mkdir(parents=True, exist_ok=True)
    for workflow in workflows:
        runs = completed_runs(workflow, limit, branch, success_only=success_only,
                              attempts=attempts,
                              strict=require_newest or refuse_unreachable)
        for index, run in enumerate(runs):
            with tempfile.TemporaryDirectory() as scratch:
                if refuse_unreachable:
                    if not _obtain(run["databaseId"], artifact, Path(scratch), attempts):
                        continue
                elif not _fetch(run["databaseId"], artifact, Path(scratch), attempts):
                    if require_newest:
                        raise Unreachable(
                            f"Could not download {artifact} from {workflow} run "
                            f"{run['databaseId']}, the newest "
                            f"{'successful ' if success_only else ''}run, after "
                            f"{attempts} attempt(s). An older run cannot stand in "
                            "for it: whatever the newest added would be lost."
                        )
                    continue
                _copy(Path(scratch), dest, overwrite=True)
            report.update(run=run["databaseId"], conclusion=run.get("conclusion"))
            print(
                f"Restored {artifact} from {workflow} run {run['databaseId']} "
                f"({run.get('conclusion')}) on {branch}."
            )
            for name, directory in also:
                report["also"][name] = _restore_also(run["databaseId"], name, directory)
            if union > 1:
                _union_older(
                    runs[index + 1:], artifact, dest, workflow, report,
                    carriers=union - 1, refuse_after=refuse_after,
                )
            elif merge and run.get("conclusion") != "success":
                _fill_from_last_success(
                    runs[index + 1:], artifact, dest, workflow, report,
                    refuse_after=refuse_after,
                )
            return report
    if require_newest:
        print(
            f"GitHub lists no {'successful' if success_only else 'completed'} "
            f"run of {', '.join(workflows)}; this run starts without {artifact}."
        )
        return report
    print(
        f"No completed run of {', '.join(workflows)} on {branch} carries "
        f"{artifact}; this run starts without it."
    )
    return report


def _restore_also(run_id: object, name: str, directory: Path) -> int | None:
    """Lay artifact `name` from the chosen run over `directory`.

    Returns how many files were written, or None when nothing was.

    This used to run `gh run download --name NAME --dir DIRECTORY` straight
    into the target. gh creates every zip entry with O_EXCL and stops at the
    first one that exists, and Publish Site's target, data/outputs, already
    holds five committed reports plus the gameday_card.json the state artifact
    just restored — six of gameday-reports' 13 entries — so the download died
    before forward_evidence.json (entry 12) on every run. The failure was then
    logged as "Run N carries no gameday-reports", which was false (the API
    listed the artifact at 15,257 bytes on the day it was measured), and the
    site's forward-ledger chip read "Ledger size not reported" from opening
    night on. So the artifact is downloaded into an empty temporary directory,
    as the primary one always was, and copied over the target: the chosen
    run's reports replace the checkout's committed copies and the state's card
    (the same run's card), which is what pairing "the state and the reports
    from one run" means. Nothing on the runner is committed back.

    "carries no" is printed only when gh itself says no artifact of that name
    is there. Any other failure prints gh's own words as a warning, so a
    failed extraction or a network error is never reported as an absence.
    """
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        result = _download(run_id, name, Path(scratch))
        if result.returncode == 0:
            written = _copy(Path(scratch), directory, overwrite=True)
            print(f"Restored {name} from the same run: {written} file(s) into {directory}.")
            return written
    said = " ".join((result.stderr or "").split())
    if NO_SUCH_ARTIFACT in said:
        print(f"Run {run_id} carries no {name}.")
    else:
        print(
            f"::warning::{name} from run {run_id} could not be restored; gh "
            f"said: {said or f'nothing (exit {result.returncode})'}"
        )
    return None


def _fill_from_last_success(
    older: list[dict], artifact: str, dest: Path, workflow: str, report: dict,
    *, refuse_after: int = 0,
) -> None:
    for run in older:
        if run.get("conclusion") != "success":
            continue
        with tempfile.TemporaryDirectory() as scratch:
            base = Path(scratch)
            if not _take(run["databaseId"], artifact, base, refuse_after):
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
    *, carriers: int, refuse_after: int = 0,
) -> None:
    """Union `dest` with up to `carriers` older runs' copies of `artifact`."""
    for run in older:
        if len(report["unioned_from"]) >= carriers:
            return
        with tempfile.TemporaryDirectory() as scratch:
            base = Path(scratch)
            if not _take(run["databaseId"], artifact, base, refuse_after):
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
        help=(
            "Another artifact from the same chosen run, copied over DIR "
            "(its files replace any already there)."
        ),
    )
    parser.add_argument(
        "--union", type=int, default=0, metavar="N",
        help=(
            "The artifact holds append-only CSV stores: union each CSV, row "
            "by row, with the same file in the N-1 carriers before the "
            "newest, instead of laying the last success underneath."
        ),
    )
    parser.add_argument(
        "--branch", default=DEFAULT_BRANCH,
        help=(
            "Restore only from runs on this branch (default: %(default)s). A "
            "run dispatched on a feature branch ran unreviewed code."
        ),
    )
    parser.add_argument(
        "--success-only", action="store_true",
        help="Only successful runs are sources, filtered by GitHub (--status success).",
    )
    # Two contracts that differ on one case, a run that holds none: the
    # first refuses it, the second passes over it. Asked for both, refuse to
    # guess which was meant.
    strictness = parser.add_mutually_exclusive_group()
    strictness.add_argument(
        "--require-newest", action="store_true",
        help=(
            "The newest listed run must yield the artifact: a failed listing, "
            "or a failed download from that run, exits 1 instead of falling "
            "back to an older run or starting without it. Only a listing "
            "that succeeds and holds no run starts without it."
        ),
    )
    strictness.add_argument(
        "--refuse-unreachable", action="store_true",
        help=(
            "A failed listing, or a download that fails for any reason other "
            "than gh saying the run holds no such artifact, exits 1 instead "
            "of reading as \"no runs\" or falling back to an older run. A run "
            "that holds none is passed over; only a listing that succeeds "
            "and holds no carrier starts without it."
        ),
    )
    parser.add_argument(
        "--attempts", type=int, default=1, metavar="N",
        help="Try each listing and download up to N times, pausing between.",
    )
    parser.add_argument(
        "--record-run", metavar="FILE",
        help=(
            "Write the id of the run the artifact was restored from to FILE, "
            "or an empty FILE when no run carries it. FILE is emptied first, "
            "so a restore that fails leaves no id in it."
        ),
    )
    args = parser.parse_args(argv)
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    also = []
    for item in args.also:
        name, _, directory = item.partition("=")
        if not name or not directory:
            parser.error(f"--also takes NAME=DIR, not {item!r}")
        also.append((name, Path(directory)))
    if args.record_run:
        # Emptied before GitHub is asked, so no failure can leave an earlier
        # id standing for the caller to read as this restore's source. The
        # caller's refusal to go on must not rest on the file being absent.
        Path(args.record_run).write_text("", encoding="utf-8")
    try:
        report = restore(
            artifact=args.artifact,
            dest=Path(args.dest),
            workflows=list(args.workflow),
            limit=args.limit,
            merge=not args.no_merge,
            also=also,
            union=args.union,
            branch=args.branch,
            success_only=args.success_only,
            require_newest=args.require_newest,
            attempts=args.attempts,
            refuse_unreachable=args.refuse_unreachable,
        )
    except Unreachable as exc:
        print(f"::error::{exc}")
        return 1
    if args.record_run:
        Path(args.record_run).write_text(
            "" if report["run"] is None else f"{report['run']}\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
