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
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.ladder_coherence import (
    DETECTION_FLOOR,
    LADDER_CLASSES,
    find_violations,
)

MOVEMENT_DIRNAME = "line_movement"

#: The column `scripts/capture_line_movement.py` stamps on every row it
#: appends: the instant that capture was taken, shared by every book and rung
#: it fetched. It is the "one moment" the detector compares inside.
CAPTURE_MOMENT = "captured_at"


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


def load_captures(directory: Path) -> tuple[pd.DataFrame, list[str]]:
    """Every captured day, and the names of the files that were read.

    The file list is returned rather than just the row count because "0
    violations" means something different over three nights than over eighty,
    and only the caller can see which one it is looking at.
    """
    if not directory.is_dir():
        return pd.DataFrame(), []
    paths = sorted(directory.glob("*.csv"))
    frames = []
    read: list[str] = []
    for path in paths:
        try:
            frame = pd.read_csv(path, low_memory=False)
        except (OSError, pd.errors.ParserError):
            continue
        if frame.empty:
            continue
        frames.append(frame)
        read.append(path.name)
    if not frames:
        return pd.DataFrame(), read
    return pd.concat(frames, ignore_index=True), read


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    directory = Path(args.processed_dir) / MOVEMENT_DIRNAME
    prices, files = load_captures(directory)
    outputs = Path(args.output_dir)
    outputs.mkdir(parents=True, exist_ok=True)

    if prices.empty:
        body = (
            "# Ladder coherence\n\n"
            f"- Captures read: {len(files)}\n"
            "- **Nothing has been captured yet.** Before the season starts "
            "this is the correct state, not a fault. A scan of no ladders is "
            "not a coherent market; it is an absence, and no rate is quoted "
            "for it.\n"
        )
        (outputs / "ladder_coherence.md").write_text(body, encoding="utf-8")
        (outputs / "ladder_coherence.json").write_text(
            json.dumps({"captures": len(files), "ladders": 0}, indent=2) + "\n",
            encoding="utf-8",
        )
        print("Nothing captured yet; wrote the empty-state report.")
        return 0

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
