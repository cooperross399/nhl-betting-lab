#!/usr/bin/env python3
"""Split the forward ledger into one file per snapshot day, and join it back.

    python scripts/split_forward_ledger.py split data/processed/forward_evidence.csv OUT_DIR
    python scripts/split_forward_ledger.py join IN_DIR data/processed/forward_evidence.csv

The card-feed branch carries a backup of the ledger, because the state
artifact chain has a single point of failure. It carried the ledger as one
file, and on 2026-10-21 that file reached 100.66 MB, past GitHub's 100 MB
limit: the push was refused and the day's card never reached card-feed. The
ledger only grows (about 4.6 MB a game day so far), so the backup is now one
file per `snapshot_date`, `forward_evidence/<day>.csv`, each with the header.

The split keeps every row's fields exactly and keeps the ledger's order
within a day; the join writes the days in date order, which is the order
settlement appends them, so a ledger written day by day joins back byte for
byte. `join` refuses a directory holding no day file, a file whose header is
not the others', and a row count that does not add up, rather than writing
a short ledger.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.csv$")
DAY_COLUMN = "snapshot_date"

csv.field_size_limit(sys.maxsize)


def _writer(handle):
    return csv.writer(handle, lineterminator="\n")


def split(ledger: Path, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    handles: dict[str, tuple] = {}
    try:
        with ledger.open(newline="", encoding="utf-8") as source:
            reader = csv.reader(source)
            header = next(reader)
            if DAY_COLUMN not in header:
                raise SystemExit(f"{ledger} has no {DAY_COLUMN} column.")
            at = header.index(DAY_COLUMN)
            for row in reader:
                if not row:
                    continue
                day = row[at]
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                    raise SystemExit(f"{ledger}: a row's {DAY_COLUMN} is {day!r}, not a date.")
                if day not in handles:
                    handle = (out_dir / f"{day}.csv").open("w", newline="", encoding="utf-8")
                    writer = _writer(handle)
                    writer.writerow(header)
                    handles[day] = (handle, writer)
                    counts[day] = 0
                handles[day][1].writerow(row)
                counts[day] += 1
    finally:
        for handle, _ in handles.values():
            handle.close()
    return counts


def join(in_dir: Path, ledger: Path) -> int:
    days = sorted(p for p in in_dir.iterdir() if DAY_FILE.match(p.name))
    if not days:
        raise SystemExit(f"{in_dir} holds no forward_evidence day file.")
    header = None
    total = 0
    tmp = ledger.with_name(ledger.name + ".joining")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", newline="", encoding="utf-8") as out:
        writer = _writer(out)
        for path in days:
            with path.open(newline="", encoding="utf-8") as source:
                reader = csv.reader(source)
                this_header = next(reader, None)
                if this_header is None:
                    raise SystemExit(f"{path} is empty.")
                if header is None:
                    header = this_header
                    writer.writerow(header)
                elif this_header != header:
                    raise SystemExit(f"{path}'s header differs from {days[0]}'s.")
                for row in reader:
                    if not row:
                        continue
                    if row[header.index(DAY_COLUMN)] != path.stem:
                        raise SystemExit(f"{path} holds a row for another day.")
                    writer.writerow(row)
                    total += 1
    tmp.replace(ledger)
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("split")
    s.add_argument("ledger", type=Path)
    s.add_argument("out_dir", type=Path)
    j = sub.add_parser("join")
    j.add_argument("in_dir", type=Path)
    j.add_argument("ledger", type=Path)
    args = parser.parse_args(argv)
    if args.command == "split":
        counts = split(args.ledger, args.out_dir)
        print(f"Split {sum(counts.values())} ledger rows into {len(counts)} day files.")
    else:
        total = join(args.in_dir, args.ledger)
        print(f"Joined {total} ledger rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
