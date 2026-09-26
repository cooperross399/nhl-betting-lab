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
`::warning::`, and exits 0. The job's artifact carries every day and each
run restores the newest copy, so a day damaged in October is still damaged
in March: were every damaged file to fail the run, one bad day would turn
every later run of the season red, and the red X that reports uncollectable
line units or scratch lists would be lost under one that nothing clears.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.ladder_coherence import (
    DETECTION_FLOOR,
    LADDER_CLASSES,
    LADDER_KEY,
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
        try:
            frame = pd.read_csv(path, low_memory=False)
        except (
            OSError,
            UnicodeDecodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ) as error:
            damaged[path.name] = f"{type(error).__name__}: {error}".strip()
            continue
        # The floor comes from the file, not the parse: stray quotes make
        # pandas swallow rows into one field without an error.
        rows_on_disk = existing_row_count(path)
        if len(frame) < rows_on_disk:
            damaged[path.name] = (
                f"holds {rows_on_disk} row(s) and parses to only {len(frame)}"
            )
            continue
        missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
        if "snapshot" not in frame.columns and CAPTURE_MOMENT not in frame.columns:
            # With no instant on its rows, any grouping would be a guess, and
            # a guessed moment merges two captures into one deeper ladder.
            missing.append(f"{CAPTURE_MOMENT} (or snapshot)")
        if missing:
            # Checked before emptiness, so a truncated header with no rows
            # (`captured_at,commence`) is named, as `load_movement_captures`
            # names it: the capture never writes a header it cannot fill.
            damaged[path.name] = f"missing column(s): {', '.join(missing)}"
            continue
        if frame.empty:
            continue
        frames.append(frame)
        read.append(path.name)
    if not frames:
        return pd.DataFrame(), read
    return pd.concat(frames, ignore_index=True), read


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
    args = parser.parse_args(argv)

    directory = Path(args.processed_dir) / MOVEMENT_DIRNAME
    unreadable: dict[str, str] = {}
    prices, files = load_captures(directory, unreadable=unreadable)
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

    if prices.empty:
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

    prices = with_ladder_moment(prices)
    found, scan = find_violations(prices[prices["line"].notna()].copy())
    print(scan.summary_line())

    by_class = (
        found["ladder_class"].value_counts().to_dict() if not found.empty else {}
    )
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
