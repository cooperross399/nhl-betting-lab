"""The ladder depth gate counted lines, not de-viggable rungs, and never ran.

`docs/pre_registered_ladder_coherence.md` closes the ladder route on
2026-10-15 "unless `ladders_with_two_rungs` has risen by three orders of
magnitude over the historical rate. Concretely: at least 2,000 ladders
carrying two or more de-viggable rungs ... Two seasons produced 57." The
code's `LadderScan.ladders_with_two_rungs` counted every ladder with two or
more distinct lines, one-sided rungs included, and `run_ladder_coherence.py`
and the Line Movement step summary printed it under the registered label.

Found by the failure-shape audit (finding 20: two of three refuters; the
third agreed the code was wrong and refuted on reachability alone). Measured
read-only on the bought two-season store (3,804,233 rows, 2,004,796
ladders), through the real runner: the report printed "Ladders with two or
more de-viggable rungs: 284544" where the registered count is 57, so history
alone cleared the 2,000 floor 142 times over. Over the first seventeen game
days of 2025-26 (2025-10-07 to 2025-10-23) — core markets only, which is
exactly what a capture looks like after the 422 fallback — it printed 13,010
where the registered count is 0, so the depth-zero alarm that exists to catch
that fallback could not fire.

And the scan never reached that line on a forward capture. The capture
stamps `captured_at` and carries no `snapshot`; `find_violations` groups on
`snapshot` and raised "missing ['snapshot']" on every capture; the step's
`|| true` swallowed it and every run summary read "Ladder scan wrote no
report". The detector's own tests were green because their fixture supplies
the column production drops.

So these tests build captures the way production does — rows from the real
`odds_api.normalize_event`, plus the `captured_at` stamp
`scripts/capture_line_movement.py` adds and nothing else — drive the real
runner's `main()`, and run the Line Movement step's own `run:` block under
`bash --noprofile --norc -eo pipefail`. No test reads the real `data/` tree.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.ladder_coherence import find_violations
from nhl_betting_lab.providers import odds_api

from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
RUNNER = PROJECT_ROOT / "scripts" / "run_ladder_coherence.py"
DEPTH_LINE = re.compile(r"Ladders with two or more de-viggable rungs: (\d+)")
ALARM = "A depth of zero is not a finding about books"


# --------------------------------------------------------------------------
# Tables. Every ladder is one event, market, player, book and moment.
# --------------------------------------------------------------------------

def store_rows(*rungs: tuple, player: str = "A Player") -> list[dict]:
    """Rows shaped like the bought historical store, which has `snapshot`."""
    return [
        {
            "provider_event_id": "evt-1",
            "market": "shots_on_goal",
            "player": player,
            "book": "BookOne",
            "snapshot": "2025-10-18T09:35:39Z",
            "line": line,
            "selection": side,
            "american_odds": odds,
        }
        for line, side, odds in rungs
    ]


OVER_ONLY = ((0.5, "over", -400), (1.5, "over", +110), (2.5, "over", +300))
UNDER_ONLY = ((0.5, "under", +250), (1.5, "under", -140), (2.5, "under", -400))
TWO_SIDED_PAIR = (
    (1.5, "over", +110), (1.5, "under", -140),
    (2.5, "over", +300), (2.5, "under", -400),
)


def _independent_depth(frame: pd.DataFrame) -> int:
    """Ladders with two or more rungs quoted validly on both sides.

    Counted with pandas alone — not with `Rung`, not with `find_violations`
    — so a report that agrees with it agrees with something other than
    itself.
    """
    keys = ["provider_event_id", "market", "player", "book", "snapshot"]
    valid = frame["american_odds"].map(
        lambda v: v == v and math.isfinite(v) and not -100 < v < 100
    )
    sides = frame[valid].groupby(keys + ["line"])["selection"].agg(set)
    two_sided = sides.map(lambda s: {"over", "under"} <= s)
    per_ladder = two_sided.groupby(level=list(range(len(keys)))).sum()
    return int((per_ladder >= 2).sum())


# --------------------------------------------------------------------------
# The detector counts the registered unit.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rungs",
    [
        OVER_ONLY,
        UNDER_ONLY,
        # One two-sided rung is one de-viggable rung, however many lines.
        ((1.5, "over", +110), (1.5, "under", -140), (2.5, "over", +300)),
        ((1.5, "over", +110), (1.5, "under", -140), (2.5, "under", -400)),
        # Both sides quoted, one price unreadable: no de-vig, so no depth.
        ((1.5, "over", +110), (1.5, "under", -140),
         (2.5, "over", +300), (2.5, "under", float("nan"))),
    ],
    ids=["over-only", "under-only", "two-sided-plus-over",
         "two-sided-plus-under", "unreadable-price"],
)
def test_a_ladder_of_lines_without_two_deviggable_rungs_has_no_depth(
    rungs: tuple,
) -> None:
    _, scan = find_violations(pd.DataFrame(store_rows(*rungs)))

    assert scan.ladders_with_two_rungs == 0, "the registered depth"
    assert scan.ladders_with_two_lines == 1, "it is still a ladder of lines"


@pytest.mark.parametrize(
    "rungs",
    [TWO_SIDED_PAIR, TWO_SIDED_PAIR + ((3.5, "over", +600), (3.5, "under", -1000))],
    ids=["two-rungs", "three-rungs"],
)
def test_two_deviggable_rungs_make_one_ladder_of_depth(rungs: tuple) -> None:
    """Depth counts ladders, not rungs or pairs: three rungs are still one."""
    frame = pd.DataFrame(store_rows(*rungs))
    _, scan = find_violations(frame)

    assert scan.ladders_with_two_rungs == 1 == _independent_depth(frame)
    assert scan.ladders_with_two_lines == 1


# --------------------------------------------------------------------------
# The runner prints the registered unit, and prints the alarm on zero.
# --------------------------------------------------------------------------

def _run(processed: Path, outputs: Path) -> tuple[str, dict]:
    module = load_script("run_ladder_coherence.py")
    assert module.main(
        ["--processed-dir", str(processed), "--output-dir", str(outputs)]
    ) == 0
    body = (outputs / "ladder_coherence.md").read_text(encoding="utf-8")
    record = json.loads((outputs / "ladder_coherence.json").read_text(encoding="utf-8"))
    return body, record


def _printed_depth(body: str) -> int:
    found = DEPTH_LINE.findall(body)
    assert len(found) == 1, body
    return int(found[0])


def test_the_report_prints_the_count_of_deviggable_ladders(tmp_path: Path) -> None:
    """Mostly one-sided ladders, as the bought store is: 284,544 against 57.

    Three ladders carry two or more lines and one carries two de-viggable
    rungs. The old counter printed 3 under the de-viggable label.
    """
    frame = pd.DataFrame(
        store_rows(*OVER_ONLY, player="Over Only")
        + store_rows(*UNDER_ONLY, player="Under Only")
        + store_rows(*TWO_SIDED_PAIR, player="Two Sided")
    )
    directory = tmp_path / "processed" / "line_movement"
    directory.mkdir(parents=True)
    frame.to_csv(directory / "store.csv", index=False)

    body, record = _run(tmp_path / "processed", tmp_path / "outputs")

    assert _printed_depth(body) == 1 == _independent_depth(frame)
    assert record["ladders_with_two_rungs"] == 1
    assert record["ladders_with_two_lines"] == 3
    assert ALARM not in body
    # The pair count keeps its own denominator, in its own unit.
    assert "in the 3 of 3 ladder(s) that carry two or more lines" in body


# --------------------------------------------------------------------------
# Captures, as `scripts/capture_line_movement.py` writes them.
# --------------------------------------------------------------------------

def _event(markets: list[dict]) -> dict:
    return {
        "id": "evt-forward",
        "commence_time": "2026-10-01T23:00:00Z",
        "home_team": "Home Team",
        "away_team": "Away Team",
        "bookmakers": [{"key": "bookone", "title": "BookOne", "markets": markets}],
    }


def _market(key: str, *outcomes: tuple) -> dict:
    return {
        "key": key,
        "outcomes": [
            {"name": side, "description": "A Player", "price": price, "point": line}
            for side, line, price in outcomes
        ],
    }


#: The nine-core-market shape: one two-sided line. What a 422 fallback leaves.
CORE = _market("player_shots_on_goal", ("Over", 2.5, -120), ("Under", 2.5, -110))
#: An alternate ladder quoted on the over side only.
OVER_ONLY_LADDER = _market(
    "player_shots_on_goal_alternate",
    ("Over", 0.5, -400), ("Over", 1.5, -200), ("Over", 3.5, +300),
)
#: An alternate ladder with a second two-sided rung beside the core one.
TWO_SIDED_LADDER = _market(
    "player_shots_on_goal_alternate", ("Over", 3.5, +300), ("Under", 3.5, -400),
)


def _capture(processed: Path, markets: list[dict], captured_at: str,
             *, stamp: bool = True) -> None:
    """Append one capture the way `capture_line_movement.main` does.

    Rows from the real `normalize_event`, then the one column the capture
    adds (`frame["captured_at"] = captured_at`), appended to the league
    day's file with a header only when the file is new. No `snapshot`.
    """
    capture = load_script("capture_line_movement.py")
    rows = odds_api.normalize_event(_event(markets), fetched_at=captured_at)
    frame = pd.DataFrame(rows)
    if stamp:
        frame["captured_at"] = captured_at
    assert "snapshot" not in frame.columns
    path = capture.capture_path("2026-10-01", processed_dir=processed)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, mode="a", header=not path.is_file(), index=False,
                 lineterminator="\n")


def test_an_over_only_capture_is_scanned_and_reads_zero_depth(tmp_path: Path) -> None:
    """The report exists, the depth is 0, and the alarm says what 0 means."""
    processed = tmp_path / "processed"
    _capture(processed, [CORE, OVER_ONLY_LADDER], "2026-10-01T14:00:00+00:00")

    body, record = _run(processed, tmp_path / "outputs")

    assert _printed_depth(body) == 0
    assert record["ladders_with_two_rungs"] == 0
    assert record["ladders_with_two_lines"] == 1
    assert ALARM in body


def test_a_capture_with_two_deviggable_rungs_reads_depth_one(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    _capture(processed, [CORE, TWO_SIDED_LADDER], "2026-10-01T14:00:00+00:00")

    body, record = _run(processed, tmp_path / "outputs")

    assert _printed_depth(body) == 1
    assert record["ladders_with_two_rungs"] == 1
    assert ALARM not in body


def test_two_captures_are_two_moments_never_one_ladder(tmp_path: Path) -> None:
    """A book changing its mind between captures is not a deeper ladder.

    Each capture holds one two-sided rung; merged into one moment they would
    read as a two-rung ladder.
    """
    processed = tmp_path / "processed"
    _capture(processed, [CORE], "2026-10-01T14:00:00+00:00")
    _capture(processed, [TWO_SIDED_LADDER], "2026-10-01T18:00:00+00:00")

    body, record = _run(processed, tmp_path / "outputs")

    assert record["ladders"] == 2
    assert record["ladders_with_two_lines"] == 0
    assert _printed_depth(body) == 0


def test_a_capture_with_no_moment_is_refused_not_guessed(tmp_path: Path) -> None:
    """With no instant on the rows, any grouping would be a guess.

    The file used to reach `find_violations`, which raised. It is now
    refused by the loader, named with the column it lacks, and the runner
    exits non-zero; no ladder is scanned from it (see
    tests/test_the_ladder_scan_names_a_damaged_day.py).
    """
    processed = tmp_path / "processed"
    _capture(processed, [CORE, TWO_SIDED_LADDER], "2026-10-01T14:00:00+00:00",
             stamp=False)
    frame = pd.read_csv(processed / "line_movement" / "2026-10-01.csv")
    frame = frame.drop(columns=["fetched_at"])
    frame.to_csv(processed / "line_movement" / "2026-10-01.csv", index=False)

    module = load_script("run_ladder_coherence.py")
    outputs = tmp_path / "outputs"
    assert module.main(
        ["--processed-dir", str(processed), "--output-dir", str(outputs)]
    ) != 0
    record = json.loads((outputs / "ladder_coherence.json").read_text(encoding="utf-8"))
    assert record["ladders"] == 0
    assert record["unreadable_captures"] == [
        {"name": "2026-10-01.csv",
         "reason": "missing column(s): captured_at (or snapshot)",
         "fails_run": True}
    ]


# --------------------------------------------------------------------------
# The Line Movement step summary, run from the workflow file.
# --------------------------------------------------------------------------

STUB_PYTHON = """#!/bin/sh
# The step runs from the repository root, where the runner's default
# directories are ./data/processed and ./data/outputs. Here the root is a
# temporary directory, so the same two directories are named explicitly.
if [ "$1" = "scripts/run_ladder_coherence.py" ]; then
  shift
  exec "$REAL_PYTHON" "$RUNNER" --processed-dir "$PWD/data/processed" \\
    --output-dir "$PWD/data/outputs" "$@"
fi
exec "$REAL_PYTHON" "$@"
"""


def _scan_step() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == "Scan the captured ladders":
                return step["run"]
    raise AssertionError("no step scans the captured ladders")


def _summary(root: Path) -> str:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "python"
    stub.write_text(STUB_PYTHON, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    summary = root / "summary.md"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "REAL_PYTHON": sys.executable,
        "RUNNER": str(RUNNER),
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _scan_step()],
        cwd=root, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return summary.read_text(encoding="utf-8")


def _store_capture(processed: Path, rungs: tuple) -> None:
    directory = processed / "line_movement"
    directory.mkdir(parents=True)
    pd.DataFrame(store_rows(*rungs)).to_csv(directory / "store.csv", index=False)


@pytest.mark.parametrize(
    ("build", "depth", "alarm"),
    [
        (lambda p: _capture(p, [CORE, OVER_ONLY_LADDER], "2026-10-01T14:00:00+00:00"),
         0, True),
        (lambda p: _capture(p, [CORE, TWO_SIDED_LADDER], "2026-10-01T14:00:00+00:00"),
         1, False),
        (lambda p: _store_capture(p, OVER_ONLY), 0, True),
    ],
    ids=["capture-over-only", "capture-two-sided", "store-over-only"],
)
def test_the_step_summary_prints_the_registered_depth(
    tmp_path: Path, build, depth: int, alarm: bool
) -> None:
    build(tmp_path / "data" / "processed")

    text = _summary(tmp_path)

    assert "wrote no report" not in text, text
    assert f"### Ladder depth: {depth}\n" in text, text
    assert ("Depth is zero while" in text) is alarm, text
