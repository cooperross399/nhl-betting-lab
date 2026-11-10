"""The ladder checkpoint's depth is read over its own window, and printed.

`docs/pre_registered_ladder_coherence.md` closes the route on 2026-10-15
unless the FIRST SEVENTEEN DAYS carried at least 2,000 ladders with two or
more de-viggable rungs. `run_ladder_coherence.py` counted only the depth
across every capture the chain holds, so read after 2026-10-15 it could not
say what the window held; and it wrote that depth only to the step summary
and the `ladder-coherence` artifact, while the job log printed every count
but the registered one. Found on 2026-11-10, when the checkpoint was read
from the job log and the registered number was not there.

The scan now tags each row with its day file, counts the registered depth
per day in the same pass (no second scan), and prints the window's depth
and the whole chain's to the log, the report and the JSON. Counts of
ladders only: no price, line or book.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.ladder_coherence import find_violations
from nhl_betting_lab.providers import odds_api

from test_ladder_depth_counts_deviggable_rungs import (
    CORE,
    TWO_SIDED_LADDER,
    TWO_SIDED_PAIR,
    _event,
    store_rows,
)
from test_scripts import load_script


def _capture_on(processed: Path, day: str, captured_at: str) -> None:
    """One capture with one two-sided-two-rung ladder, in `day`'s file."""
    capture = load_script("capture_line_movement.py")
    rows = odds_api.normalize_event(
        _event([CORE, TWO_SIDED_LADDER]), fetched_at=captured_at
    )
    frame = pd.DataFrame(rows)
    frame["captured_at"] = captured_at
    path = capture.capture_path(day, processed_dir=processed)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, mode="a", header=not path.is_file(), index=False,
                 lineterminator="\n")


def test_the_window_holds_only_the_days_on_or_before_the_checkpoint(
    tmp_path: Path, capsys
) -> None:
    processed = tmp_path / "processed"
    _capture_on(processed, "2026-10-01", "2026-10-01T14:00:00+00:00")
    _capture_on(processed, "2026-10-15", "2026-10-15T14:00:00+00:00")
    _capture_on(processed, "2026-10-16", "2026-10-16T14:00:00+00:00")
    _capture_on(processed, "2026-11-09", "2026-11-09T14:00:00+00:00")

    module = load_script("run_ladder_coherence.py")
    outputs = tmp_path / "outputs"
    assert module.main(
        ["--processed-dir", str(processed), "--output-dir", str(outputs)]
    ) == 0
    record = json.loads((outputs / "ladder_coherence.json").read_text("utf-8"))
    body = (outputs / "ladder_coherence.md").read_text("utf-8")
    printed = capsys.readouterr().out

    assert record["ladders_with_two_rungs"] == 4
    assert record["ladders_with_two_rungs_by_day"] == {
        "2026-10-01": 1, "2026-10-15": 1, "2026-10-16": 1, "2026-11-09": 1,
    }
    assert record["checkpoint_window"] == {
        "through": "2026-10-15",
        "captures": 2,
        "ladders_with_two_rungs": 2,
        "floor": 2000,
        "clears_floor": False,
    }
    # The registered number reaches the log, not only the summary.
    assert "Registered depth (ladders with two or more de-viggable rungs): 4 " \
        "across all 4 capture(s); 2 in the checkpoint window" in printed
    assert "**In the checkpoint window** (day files through 2026-10-15, " \
        "2 capture(s)): 2, against the registered floor of 2,000." in body


def test_the_registration_is_not_moved() -> None:
    """The window and floor are copied from the registration, never tuned."""
    module = load_script("run_ladder_coherence.py")
    registration = (
        Path(__file__).resolve().parents[1]
        / "docs" / "pre_registered_ladder_coherence.md"
    ).read_text("utf-8")

    assert module.CHECKPOINT_DAY == "2026-10-15"
    assert module.CHECKPOINT_DEPTH_FLOOR == 2_000
    assert "**On 2026-10-15**" in registration
    assert "**2,000 ladders carrying two or more de-viggable rungs**" in registration


def test_counting_by_day_changes_no_count() -> None:
    """`depth_by` only splits the depth; every other count is the same."""
    frame = pd.DataFrame(
        store_rows(*TWO_SIDED_PAIR, player="One")
        + store_rows(*TWO_SIDED_PAIR, player="Two")
    )
    frame["capture_day"] = ["2026-10-01"] * 4 + ["2026-10-20"] * 4

    plain_found, plain = find_violations(frame.drop(columns=["capture_day"]))
    tagged_found, tagged = find_violations(frame, depth_by="capture_day")

    assert plain.depth_by == {}
    assert tagged.depth_by == {"2026-10-01": 1, "2026-10-20": 1}
    assert sum(tagged.depth_by.values()) == tagged.ladders_with_two_rungs
    for name in ("ladders", "ladders_with_two_lines", "ladders_with_two_rungs",
                 "comparable_pairs", "comparable_wagers",
                 "duplicate_rows_collapsed", "violations"):
        assert getattr(plain, name) == getattr(tagged, name), name
    assert plain_found.equals(tagged_found)
