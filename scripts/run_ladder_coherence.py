#!/usr/bin/env python3
"""Scan captured ladders for books contradicting themselves, and report.

    PYTHONPATH=src .venv/bin/python scripts/run_ladder_coherence.py

Reads whatever `scripts/capture_line_movement.py` has accumulated under
`data/processed/line_movement/` and writes
`data/outputs/ladder_coherence.md` / `.json`.

It settles nothing and returns no ROI. The return test is registered in
`docs/pre_registered_ladder_coherence.md` and runs on the forward ledger; this
answers the prior question of whether the phenomenon occurs often enough to be
worth testing at all. On the two-season historical store the answer was
essentially no, but that store never bought the alternate ladders, so it could
not answer for the ladders this hypothesis is actually about.

It reads only captured files, spends no credit, places no bet, edits no
policy, and produces no selection.

Exits 2 when a captured day file cannot be read. It still writes the report,
which counts every day it could read and names each one it could not, with
the reason; the same names go to stderr as `::error::` lines.

With `--fail-on-day YYYY-MM-DD` (the Line Movement job passes the league day
it captured into), only damage in that day's file exits 2. Damage in an
earlier day is still named in the report, the JSON and on stderr, as a
`::warning::`, and exits 0. The private movement chain carries every day and
each run restores the newest copy, so a day damaged in October is still
damaged in March: were every damaged file to fail the run, one bad day would turn
every later run of the season red, and the red X that reports uncollectable
line units or scratch lists would be lost under one that nothing clears.

With `--cache-dir DIR` (the Line Movement job passes one under the runner's
temp directory and keeps it between rounds in the Actions cache), each
readable day file's counts are kept in `DIR/ladder_scan_cache.json`, keyed on
the file's name, the SHA-256 of its bytes and the detector's fingerprint (the
source of every module the scan's arithmetic runs through, and the pandas and
numpy versions), so a later run scans only the day files that are new or
changed. Until 2026-11-10 every round rescanned every day the chain holds:
6.4 to 15.9 minutes per round by early November, growing with the season. A
ladder is one book at one instant and one round appends to one day file, so
no ladder spans two files and every count is a sum over days. The report, the
JSON, the checkpoint window, the unreadable list and the exit are what a full
scan writes, byte for byte (`tests/test_the_ladder_scan_is_incremental.py`).
The cache holds counts and hashes only: no price, line, book or player. A
damaged day is never cached, so it is read, and named, on every run.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nhl_betting_lab.closing_lines import team_market_rows
from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.ladder_coherence import (
    DETECTION_FLOOR,
    LADDER_CLASSES,
    LADDER_KEY,
    LadderScan,
    find_violations,
)
from nhl_betting_lab.stores import existing_row_count

MOVEMENT_DIRNAME = "line_movement"

#: The column `scripts/capture_line_movement.py` stamps on every row it
#: appends: the instant that capture was taken, shared by every book and rung
#: it fetched. It is the "one moment" the detector compares inside.
CAPTURE_MOMENT = "captured_at"

#: What every day file must carry for its rows to be scanned: the ladder
#: identity except its moment, and the rung itself. The moment is checked on
#: its own, because a file may carry it as `snapshot` or as `captured_at`.
#: The column each row is tagged with: the stem of the day file it came
#: from (the league day `capture_line_movement.py` appended it to).
CAPTURE_DAY = "capture_day"

#: The registered feasibility checkpoint, copied from
#: `docs/pre_registered_ladder_coherence.md` and never moved: on 2026-10-15,
#: the route is closed unless the first seventeen days (2026-09-29 through
#: 2026-10-15) carried at least 2,000 ladders with two or more de-viggable
#: rungs. The window is the day files named on or before this date.
CHECKPOINT_DAY = "2026-10-15"
CHECKPOINT_DEPTH_FLOOR = 2_000

REQUIRED_COLUMNS: tuple[str, ...] = (
    *(name for name in LADDER_KEY if name != "snapshot"),
    "line",
    "selection",
    "american_odds",
)


def with_ladder_moment(prices: pd.DataFrame) -> pd.DataFrame:
    """The capture, with its moment under the name the detector groups on.

    `find_violations` compares rungs only inside one (event, market, player,
    book, snapshot). The bought historical store names its moment
    `snapshot`; the forward capture names it `captured_at` and has no
    `snapshot` column at all. Until 2026-09-25 this script passed the capture
    through as read, so every forward capture raised "missing ['snapshot']",
    the Line Movement step's `|| true` swallowed it, and every run summary
    read "Ladder scan wrote no report": the 2026-10-15 depth checkpoint in
    `docs/pre_registered_ladder_coherence.md` could not have produced a
    number. The registration already takes the capture's instant as the
    moment ("the book, the rung, the price and the instant"), so this maps a
    name and changes nothing about what is compared.

    A frame that already carries `snapshot` is left alone, and one carrying
    neither is left for `find_violations` to refuse: guessing a moment would
    merge two captures and call a book changing its mind a contradiction.
    """
    if "snapshot" in prices.columns or CAPTURE_MOMENT not in prices.columns:
        return prices
    return prices.assign(snapshot=prices[CAPTURE_MOMENT])


def load_captures(
    directory: Path, *, unreadable: dict[str, str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Every captured day, and the names of the files that were read.

    The file list is returned rather than just the row count because "0
    violations" means something different over three nights than over eighty,
    and only the caller can see which one it is looking at.

    `unreadable`, when given, receives every day file that could not be read,
    by file name, with the reason. Until 2026-09-26 a file that did not parse
    was skipped with a bare `continue`, so it fell out of "Captures read" and
    out of the registered depth without a word and the run exited 0; an
    undecodable byte was not caught at all, raised, and the Line Movement
    step's `|| true` turned it into "Ladder scan wrote no report"; stray
    quotes parse short WITHOUT an error, so the rows they swallowed were lost
    with nothing to catch; and a file missing a ladder column was
    concatenated with the good days, its rows reaching the detector with
    that column blank. The same four shapes, and zero bytes, are what
    `closing_lines.load_movement_captures` names for the CLV report. That
    loader cannot be reused here: it collapses each round to the best price
    across books, and a ladder is one book's.

    A damaged day is left out and named rather than raised, so every good
    day is still counted. A header-only file still reads as empty: it holds
    no row to lose. The capture only ever creates a file with rows in it, so
    zero bytes is damage here, not an empty day.
    """
    damaged = unreadable if unreadable is not None else {}
    if not directory.is_dir():
        return pd.DataFrame(), []
    paths = sorted(directory.glob("*.csv"))
    frames = []
    read: list[str] = []
    for path in paths:
        frame, reason = read_day(path)
        if reason is not None:
            damaged[path.name] = reason
            continue
        if frame.empty:
            continue
        frames.append(frame.assign(**{CAPTURE_DAY: path.stem}))
        read.append(path.name)
    if not frames:
        return pd.DataFrame(), read
    return pd.concat(frames, ignore_index=True), read


def read_day(path: Path) -> tuple[pd.DataFrame | None, str | None]:
    """One day file's ladder rows, or None and the reason it is damaged.

    The rows are the file's with the bulk request's dropped. An empty frame
    is a day with nothing to scan (header only, or bulk rows only), which is
    not damage. `load_captures` names every shape that is.
    """
    try:
        frame = pd.read_csv(path, low_memory=False)
    except (
        OSError,
        UnicodeDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as error:
        return None, f"{type(error).__name__}: {error}".strip()
    # The floor comes from the file, not the parse: stray quotes make
    # pandas swallow rows into one field without an error.
    rows_on_disk = existing_row_count(path)
    if len(frame) < rows_on_disk:
        return None, (
            f"holds {rows_on_disk} row(s) and parses to only {len(frame)}"
        )
    missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
    if "snapshot" not in frame.columns and CAPTURE_MOMENT not in frame.columns:
        # With no instant on its rows, any grouping would be a guess, and
        # a guessed moment merges two captures into one deeper ladder.
        missing.append(f"{CAPTURE_MOMENT} (or snapshot)")
    if missing:
        # Checked before emptiness, so a truncated header with no rows
        # (`captured_at,commence`) is named, as `load_movement_captures`
        # names it: the capture never writes a header it cannot fill.
        return None, f"missing column(s): {', '.join(missing)}"
    # THE BULK REQUEST'S ROWS ARE NOT A LADDER'S. Since the capture
    # added the bulk moneyline, puck line and total to each round, a
    # day file holds a featured `total_goals` line per book beside that
    # book's `alternate_totals` rungs, under the same `captured_at` and
    # spelled the same way. They came from a different request, seconds
    # or a minute from the per-event one, and the registration compares
    # "one book, one moment, two rungs" and never two moments; left in,
    # a main line that moved between the two requests would read as the
    # book contradicting its own ladder, and the featured rung would add
    # to the depth the 2026-10-15 checkpoint reads, which was registered
    # on the ladders alone. So they are dropped here, by the request they
    # came from (`team_market_rows`), and the scan reads what it read
    # before they existed. (The bulk moneyline has no line and the puck
    # line no over/under, so neither was ever a rung either way.)
    return frame[~team_market_rows(frame)], None


def _unreadable_lines(damaged: list[dict]) -> list[str]:
    """One bullet per day file that could not be read, above every count."""
    if not damaged:
        return []
    lines = [
        f"- **{len(damaged)} captured day file(s) could not be read**, so "
        "every ladder in them is missing from the counts below, the "
        "registered depth included:",
    ]
    for entry in damaged:
        standing = (
            "" if entry["fails_run"]
            else " An earlier day: a standing warning, not this run's capture."
        )
        lines.append(f"  - `{entry['name']}` ({entry['reason']}).{standing}")
    return lines


def _say_unreadable(damaged: list[dict]) -> None:
    for entry in damaged:
        level = "error" if entry["fails_run"] else "warning"
        print(
            f"::{level}::Ladder scan could not read {entry['name']} "
            f"({entry['reason']}); its ladders are not in the depth. Every "
            "other day is still counted, and the report names this one.",
            file=sys.stderr,
        )


CACHE_FILENAME = "ladder_scan_cache.json"

#: The counts one scan returns, each a sum over day files: every integer
#: field of `LadderScan`, read off the class so a count added there is
#: cached and summed without a second list to forget. (`depth_by` is a
#: per-day split, merged on its own.)
SCAN_COUNTS: tuple[str, ...] = tuple(
    field.name for field in dataclasses.fields(LadderScan)
    if field.name != "depth_by"
)

#: Every module whose code decides a day's counts. Their bytes, with the
#: pandas and numpy versions, make the fingerprint a cached count is keyed
#: on, so changing any of them (a detector fix, a loader fix) rescans every
#: day rather than trusting a count the new code might not reproduce.
_FINGERPRINT_SOURCES: tuple[str, ...] = (
    "ladder_coherence.py",
    "closing_lines.py",
    "stores.py",
    "models/value.py",
)


def detector_fingerprint() -> str:
    """A digest of the code and libraries a day's counts depend on."""
    import nhl_betting_lab

    package = Path(nhl_betting_lab.__file__).resolve().parent
    digest = hashlib.sha256()
    digest.update(Path(__file__).resolve().read_bytes())
    for name in _FINGERPRINT_SOURCES:
        digest.update(name.encode("utf-8"))
        digest.update((package / name).read_bytes())
    digest.update(f"pandas {pd.__version__} numpy {np.__version__}".encode())
    return digest.hexdigest()


def _file_sha256(path: Path) -> str | None:
    """The file's content hash, or None when it cannot be read (it is then
    read the ordinary way, which names the damage)."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def scan_day(frame: pd.DataFrame, day: str, *, snapshot_elsewhere: bool) -> dict:
    """One readable, non-empty day's counts, as the full scan counts them.

    `snapshot_elsewhere` reproduces the one way the concatenated scan let a
    file's columns reach another file's rows: when any scanned day carries a
    `snapshot` column, `with_ladder_moment` leaves the concatenation alone and
    every day without one reads its moment as blank. The capture never
    writes `snapshot`, so this is False on every real run; it is kept so the
    two scans cannot disagree even then.
    """
    frame = frame.assign(**{CAPTURE_DAY: day})
    if snapshot_elsewhere and "snapshot" not in frame.columns:
        frame = frame.assign(snapshot=np.nan)
    else:
        frame = with_ladder_moment(frame)
    found, scan = find_violations(
        frame[frame["line"].notna()].copy(), depth_by=CAPTURE_DAY
    )
    by_class = (
        found["ladder_class"].value_counts().to_dict() if not found.empty else {}
    )
    return {
        **{name: int(getattr(scan, name)) for name in SCAN_COUNTS},
        "by_class": {name: int(by_class.get(name, 0)) for name, _ in LADDER_CLASSES},
        "depth_by": {str(k): int(v) for k, v in scan.depth_by.items()},
    }


def _load_cache(directory: Path | None, fingerprint: str) -> dict:
    """The cached days, or nothing when absent, unreadable or another
    fingerprint's. A cache is a convenience: any doubt rescans."""
    if directory is None:
        return {}
    try:
        payload = json.loads((directory / CACHE_FILENAME).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict) or payload.get("fingerprint") != fingerprint:
        return {}
    days = payload.get("days")
    return days if isinstance(days, dict) else {}


def _save_cache(directory: Path | None, fingerprint: str, days: dict) -> None:
    """Best effort: a cache that cannot be written costs the next run time,
    never a count."""
    if directory is None:
        return
    try:
        directory.mkdir(parents=True, exist_ok=True)
        partial = directory / f".{CACHE_FILENAME}.tmp"
        partial.write_text(
            json.dumps({"fingerprint": fingerprint, "days": days},
                       indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(partial, directory / CACHE_FILENAME)
    except OSError as error:
        print(f"::warning::Ladder scan cache not written ({error}); the next "
              "run scans every day again.", file=sys.stderr)


def scan_captures(
    directory: Path,
    *,
    unreadable: dict[str, str],
    cache_dir: Path | None = None,
) -> tuple[dict | None, list[str], dict]:
    """Every day's counts summed, the day files read, and what was reused.

    Returns None for the counts when no day could be scanned (the report's
    empty states). A day is read only when it is not in the cache under its
    current content hash; every damaged day is read, and named, every time.
    """
    fingerprint = detector_fingerprint()
    cached = _load_cache(cache_dir, fingerprint)
    paths = sorted(directory.glob("*.csv")) if directory.is_dir() else []
    entries: dict[str, dict] = {}
    frames: dict[str, pd.DataFrame] = {}
    reused = 0
    for path in paths:
        digest = _file_sha256(path)
        hit = cached.get(path.name)
        if digest is not None and isinstance(hit, dict) and hit.get("sha256") == digest:
            entries[path.name] = hit
            reused += 1
            continue
        frame, reason = read_day(path)
        if reason is not None:
            unreadable[path.name] = reason
            continue
        entries[path.name] = {
            "sha256": digest,
            "empty": bool(frame.empty),
            "has_snapshot": "snapshot" in frame.columns,
            "counts": {},
        }
        if not frame.empty:
            frames[path.name] = frame
    files = [name for name in sorted(entries) if not entries[name]["empty"]]
    snapshot_elsewhere = any(entries[name]["has_snapshot"] for name in files)
    variant = "snapshot_elsewhere" if snapshot_elsewhere else "own_moment"
    totals: dict | None = None
    for name in files:
        entry = entries[name]
        counts = entry["counts"].get(variant)
        if counts is None:
            frame = frames.get(name)
            if frame is None:
                frame, reason = read_day(directory / name)
                if reason is not None:  # changed under us since it was hashed
                    unreadable[name] = reason
                    del entries[name]
                    continue
            counts = scan_day(frame, Path(name).stem,
                              snapshot_elsewhere=snapshot_elsewhere)
            entry["counts"][variant] = counts
        if totals is None:
            totals = {key: 0 for key in SCAN_COUNTS}
            totals["by_class"] = {cls: 0 for cls, _ in LADDER_CLASSES}
            totals["depth_by"] = {}
        for key in SCAN_COUNTS:
            totals[key] += counts[key]
        for cls, value in counts["by_class"].items():
            totals["by_class"][cls] += value
        for day, value in counts["depth_by"].items():
            totals["depth_by"][day] = totals["depth_by"].get(day, 0) + value
    files = [name for name in files if name in entries]
    _save_cache(cache_dir, fingerprint,
                {name: e for name, e in entries.items() if e.get("sha256")})
    return totals, files, {"reused": reused, "scanned": len(paths) - reused}


def checkpoint_window(depth_by_day: dict[str, int], files: list[str]) -> dict:
    """The registered depth over the day files on or before the checkpoint.

    Day files are named by their league day (`YYYY-MM-DD.csv`), so the
    window is read off the name, as the registration words it ("the first
    seventeen days"). A file with no de-viggable ladder still counts as a
    capture read in the window.
    """
    in_window = [name for name in files if Path(name).stem <= CHECKPOINT_DAY]
    depth = sum(
        count for day, count in depth_by_day.items() if day <= CHECKPOINT_DAY
    )
    return {
        "through": CHECKPOINT_DAY,
        "captures": len(in_window),
        "ladders_with_two_rungs": int(depth),
        "floor": CHECKPOINT_DEPTH_FLOOR,
        "clears_floor": bool(depth >= CHECKPOINT_DEPTH_FLOOR),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument(
        "--fail-on-day",
        default=None,
        help="League day (YYYY-MM-DD) this run captured into. Only damage "
        "in that day's file exits 2; an earlier damaged day is named as a "
        "warning. Omitted, any damaged file exits 2.",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Keep each readable day's counts here, keyed on its content "
        "hash and the detector's fingerprint, and scan only new or changed "
        "days. Counts and hashes only. Omitted, every day is scanned.",
    )
    args = parser.parse_args(argv)

    directory = Path(args.processed_dir) / MOVEMENT_DIRNAME
    unreadable: dict[str, str] = {}
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    totals, files, reuse = scan_captures(
        directory, unreadable=unreadable, cache_dir=cache_dir
    )
    if cache_dir is not None:
        print(f"Ladder scan: {reuse['reused']} day file(s) reused from the "
              f"cache, {reuse['scanned']} read.")
    own_file = f"{args.fail_on_day}.csv" if args.fail_on_day else None
    damaged = [
        {"name": name, "reason": reason,
         "fails_run": own_file is None or name == own_file}
        for name, reason in sorted(unreadable.items())
    ]
    _say_unreadable(damaged)
    # The report is written either way and names each damaged file; the exit
    # says whether the day this run wrote is one of them.
    exit_code = 2 if any(entry["fails_run"] for entry in damaged) else 0
    outputs = Path(args.output_dir)
    outputs.mkdir(parents=True, exist_ok=True)

    if totals is None:
        if damaged:
            # Never "Nothing has been captured yet ... not a fault" over a
            # list of captured days that could not be read.
            state = (
                "- **No captured day could be read.** This is not the "
                "pre-season state: the file(s) named above hold captures. "
                "No depth and no rate is quoted for them.\n"
            )
        else:
            state = (
                "- **Nothing has been captured yet.** Before the season "
                "starts this is the correct state, not a fault. A scan of no "
                "ladders is not a coherent market; it is an absence, and no "
                "rate is quoted for it.\n"
            )
        body = (
            "# Ladder coherence\n\n"
            f"- Captures read: {len(files)}\n"
            + "".join(line + "\n" for line in _unreadable_lines(damaged))
            + state
        )
        (outputs / "ladder_coherence.md").write_text(body, encoding="utf-8")
        (outputs / "ladder_coherence.json").write_text(
            json.dumps(
                {"captures": len(files), "ladders": 0,
                 "unreadable_captures": damaged},
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        if damaged:
            print("No captured day could be read; wrote a report naming each.")
        else:
            print("Nothing captured yet; wrote the empty-state report.")
        return exit_code

    scan = LadderScan(**{name: totals[name] for name in SCAN_COUNTS})
    scan.depth_by = dict(totals["depth_by"])
    print(scan.summary_line())
    checkpoint = checkpoint_window(scan.depth_by, files)
    # THE REGISTERED NUMBERS GO TO THE LOG, NOT ONLY TO THE RUN SUMMARY.
    # Until 2026-11-10 the depth reached only the step summary and the
    # `ladder-coherence` artifact, neither of which a reader without
    # download access can open, while the log printed every count but the
    # registered one; and only the cumulative depth was counted, which after
    # 2026-10-15 cannot say what the first seventeen days held.
    print(
        f"Registered depth (ladders with two or more de-viggable rungs): "
        f"{scan.ladders_with_two_rungs} across all {len(files)} capture(s); "
        f"{checkpoint['ladders_with_two_rungs']} in the checkpoint window "
        f"(day files through {CHECKPOINT_DAY}, {checkpoint['captures']} "
        f"capture(s)), against the registered floor of "
        f"{CHECKPOINT_DEPTH_FLOOR:,}."
    )

    by_class = totals["by_class"]
    record = {
        "captures": len(files),
        "ladders": scan.ladders,
        # The registered depth: two or more DE-VIGGABLE rungs. The name is
        # the one the pre-registration and the Line Movement summary read.
        "ladders_with_two_rungs": scan.ladders_with_two_rungs,
        # Two or more lines of either side. A denominator, not the depth.
        "ladders_with_two_lines": scan.ladders_with_two_lines,
        "comparable_pairs": scan.comparable_pairs,
        "duplicate_rows_collapsed": scan.duplicate_rows_collapsed,
        "violations": scan.violations,
        "detection_floor": DETECTION_FLOOR,
        "by_class": {name: int(by_class.get(name, 0)) for name, _ in LADDER_CLASSES},
        # Each day file left out of every count above, with the reason.
        "unreadable_captures": damaged,
        # The registered depth inside the checkpoint's own window, and per
        # day file: counts of ladders only, no price, line or book.
        "checkpoint_window": checkpoint,
        "ladders_with_two_rungs_by_day": dict(sorted(scan.depth_by.items())),
    }
    (outputs / "ladder_coherence.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )

    # The registered checkpoint reads DEPTH, not violations: no violation
    # rate can rescue a population that does not exist, so depth leads.
    #
    # Depth is ladders with two or more de-viggable rungs, the unit the
    # 2,000 floor and the historical 57 are both in. Until 2026-09-25 the
    # field behind this line counted two or more lines of either side, and
    # this printed 284,544 for the bought store under a label that says 57,
    # and 13,010 for a core-markets-only window whose true depth is 0 —
    # so the warning below could not fire in the case it was written for.
    depth = scan.ladders_with_two_rungs
    lines = [
        "# Ladder coherence",
        "",
        "Where a book contradicted its own ladder. This counts occurrences "
        "and states the denominator; it settles nothing and reports no "
        "return. See `docs/pre_registered_ladder_coherence.md`.",
        "",
        f"- Captures read: {len(files)}",
        *_unreadable_lines(damaged),
        f"- **Ladders with two or more de-viggable rungs: {depth}** — the "
        "2026-10-15 checkpoint reads this. Two seasons of bought history "
        "produced 57.",
        f"- **In the checkpoint window** (day files through {CHECKPOINT_DAY}, "
        f"{checkpoint['captures']} capture(s)): "
        f"{checkpoint['ladders_with_two_rungs']}, against the registered "
        f"floor of {CHECKPOINT_DEPTH_FLOOR:,}. This is the number the "
        "registration reads; the line above is every capture since.",
        f"- {scan.summary_line()}",
        "",
    ]
    if depth == 0:
        lines += [
            "> **A depth of zero is not a finding about books.** The "
            "provider answers a refused market list with a 422, and the "
            "fetch falls back to the nine core markets, dropping all ten "
            "alternate keys — with a warning, but with the job still green. "
            "Zero de-viggable ladders is indistinguishable from that "
            "failure in this output, so read it as *the capture may not "
            "have run*, never as *the market is coherent*. Check the "
            "capture's warnings first.",
            "",
        ]
    lines += [
        "| Class | Minimum edge | Violations |",
        "|:--|--:|--:|",
    ]
    for name, threshold in LADDER_CLASSES:
        lines.append(
            f"| {name} | {threshold * 100:.0f} pts | "
            f"{int(by_class.get(name, 0))} |"
        )
    lines += [
        "",
        "No bet was placed, no market was allowlisted, no policy was edited, "
        "and no price was invented.",
        "",
    ]
    (outputs / "ladder_coherence.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  wrote: {outputs / 'ladder_coherence.md'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
