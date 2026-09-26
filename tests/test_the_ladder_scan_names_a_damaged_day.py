"""A line-movement day the ladder scan cannot read is named, and the run says so.

`scripts/run_ladder_coherence.py` read each `line_movement/<day>.csv` with a
bare `pd.read_csv` and `continue`d past an `OSError` or a `ParserError`. A
damaged day therefore fell out of the scan without a word: the report said
"Captures read: 1" over two captured days and the runner exited 0. Three more
shapes were not even caught:

* an undecodable byte raised `UnicodeDecodeError` out of the runner, the Line
  Movement step's `|| true` swallowed it, and every run summary read "Ladder
  scan wrote no report";
* stray quotes parse short without an error, so the rows they swallow were
  dropped with no exception to catch;
* a day missing a ladder column was concatenated with the good days, and its
  rows reached the detector with that column blank.

The 2026-10-15 checkpoint in `docs/pre_registered_ladder_coherence.md` reads
the depth this report prints, so each of these undercounted it with the step
green.

What these tests hold, through the real `run_ladder_coherence.main()` and the
Line Movement step's own `run:` block:

* each damaged shape is named in the report, in the JSON and on stderr, and
  the runner exits non-zero;
* the good day beside it is still read and still counted;
* a scan whose only day is damaged never says "Nothing has been captured
  yet";
* the step writes its summary, names the damaged file, and exits non-zero; it
  stays `continue-on-error` so the captures are still uploaded, and a final
  gate after every upload turns the run red.

No test reads the real `data/` tree.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api

from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
RUNNER = PROJECT_ROOT / "scripts" / "run_ladder_coherence.py"

GOOD_DAY = "2026-10-01"
BAD_DAY = "2026-10-02"
ROUNDS = 4
EMPTY_STATE = "Nothing has been captured yet"


def _event(event_id: str, day: str) -> dict:
    """One game, one book, one player with two de-viggable rungs: depth 1."""
    outcomes = [("Over", 2.5, -120), ("Under", 2.5, -110),
                ("Over", 3.5, +300), ("Under", 3.5, -400)]
    return {
        "id": event_id,
        "commence_time": f"{day}T23:00:00Z",
        "home_team": "Home Team",
        "away_team": "Away Team",
        "bookmakers": [{
            "key": "bookone", "title": "BookOne",
            "markets": [{
                "key": "player_shots_on_goal",
                "outcomes": [
                    {"name": side, "description": "A Player", "price": price,
                     "point": line}
                    for side, line, price in outcomes
                ],
            }],
        }],
    }


def _capture_day(processed: Path, day: str, rounds: int) -> Path:
    """Append `rounds` captures the way `capture_line_movement.main` does."""
    capture = load_script("capture_line_movement.py")
    path = capture.capture_path(day, processed_dir=processed)
    path.parent.mkdir(parents=True, exist_ok=True)
    for index in range(rounds):
        captured_at = f"{day}T{14 + index:02d}:00:00+00:00"
        rows = odds_api.normalize_event(_event(f"evt-{day}", day),
                                        fetched_at=captured_at)
        frame = pd.DataFrame(rows)
        frame["captured_at"] = captured_at
        frame.to_csv(path, mode="a", header=not path.is_file(), index=False,
                     lineterminator="\n")
    return path


# --------------------------------------------------------------------------
# Damage, each applied to the bad day's file. Line 0 is the header.
# --------------------------------------------------------------------------

def _stray_quote(path: Path) -> None:
    """Parses without an error, and short: the quotes swallow the rows between."""
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[3] = lines[3].replace(",BookOne", ',"BookOne')
    lines[9] = lines[9].replace(",BookOne", ',BookOne"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(pd.read_csv(path)) < ROUNDS * 4, "the damage must shorten the parse"


def _one_row_short(path: Path) -> None:
    """The smallest short parse: two adjacent lines merge into one row."""
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[3] = lines[3].replace(",BookOne", ',"BookOne')
    lines[4] = lines[4].replace(",BookOne", ',BookOne"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(pd.read_csv(path)) == ROUNDS * 4 - 1


def _undecodable_byte(path: Path) -> None:
    raw = path.read_bytes()
    index = raw.index(b"Home Team", raw.index(b"\n"))
    path.write_bytes(raw[:index] + b"\xff" + raw[index + 1:])
    with pytest.raises(UnicodeDecodeError):
        pd.read_csv(path, low_memory=False)


def _missing_column(path: Path) -> None:
    """A ladder-identity column absent: concatenated, its rows lose their book."""
    pd.read_csv(path).drop(columns=["book"]).to_csv(path, index=False)


def _missing_moment(path: Path) -> None:
    """Neither `captured_at` nor `snapshot`: any moment would be a guess."""
    pd.read_csv(path).drop(columns=["captured_at", "fetched_at"]).to_csv(
        path, index=False
    )


def _ragged_row(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[5] += ",extra,extra,extra"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _unterminated_quote(path: Path) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write('"2026-10-02,2026-10-02T23:00:00Z\n')


def _zero_bytes(path: Path) -> None:
    path.write_bytes(b"")


DAMAGE = {
    "stray-quote": (_stray_quote, "parses to only"),
    "one-row-short": (_one_row_short, "parses to only"),
    "undecodable-byte": (_undecodable_byte, "UnicodeDecodeError"),
    "missing-column": (_missing_column, "book"),
    "missing-moment": (_missing_moment, "captured_at"),
    "ragged-row": (_ragged_row, "ParserError"),
    "unterminated-quote": (_unterminated_quote, "ParserError"),
    "zero-bytes": (_zero_bytes, "EmptyDataError"),
}


def _main(processed: Path, outputs: Path) -> tuple[int, str, dict]:
    module = load_script("run_ladder_coherence.py")
    code = module.main(
        ["--processed-dir", str(processed), "--output-dir", str(outputs)]
    )
    body = (outputs / "ladder_coherence.md").read_text(encoding="utf-8")
    record = json.loads(
        (outputs / "ladder_coherence.json").read_text(encoding="utf-8")
    )
    return code, body, record


@pytest.mark.parametrize("shape", list(DAMAGE))
def test_a_damaged_day_is_named_and_the_good_day_still_counted(
    tmp_path: Path, capsys, shape: str
) -> None:
    damage, reason = DAMAGE[shape]
    processed = tmp_path / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    damage(_capture_day(processed, BAD_DAY, ROUNDS))
    bad_name = f"{BAD_DAY}.csv"

    code, body, record = _main(processed, tmp_path / "outputs")
    stderr = capsys.readouterr().err

    assert code != 0, "a scan that could not read a captured day is not clean"
    # Named in the report, with its reason, and in the log.
    assert f"`{bad_name}`" in body, body
    assert reason in body, body
    assert bad_name in stderr and "::error::" in stderr, stderr
    assert [entry["name"] for entry in record["unreadable_captures"]] == [bad_name]
    assert reason in record["unreadable_captures"][0]["reason"]
    # The good day is still read and counted, and only it.
    assert "- Captures read: 1\n" in body, body
    assert record["captures"] == 1
    assert record["ladders_with_two_rungs"] == 1
    assert EMPTY_STATE not in body


@pytest.mark.parametrize("shape", ["undecodable-byte", "stray-quote", "missing-column"])
def test_a_scan_whose_only_day_is_damaged_is_never_the_empty_state(
    tmp_path: Path, capsys, shape: str
) -> None:
    damage, _ = DAMAGE[shape]
    processed = tmp_path / "processed"
    damage(_capture_day(processed, BAD_DAY, ROUNDS))

    code, body, record = _main(processed, tmp_path / "outputs")

    assert code != 0
    assert EMPTY_STATE not in body, body
    assert f"`{BAD_DAY}.csv`" in body, body
    assert record["captures"] == 0
    assert [entry["name"] for entry in record["unreadable_captures"]] == [
        f"{BAD_DAY}.csv"
    ]
    assert f"{BAD_DAY}.csv" in capsys.readouterr().err


def test_undamaged_days_are_all_counted_and_exit_zero(tmp_path: Path, capsys) -> None:
    processed = tmp_path / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    _capture_day(processed, BAD_DAY, ROUNDS)

    code, body, record = _main(processed, tmp_path / "outputs")

    assert code == 0
    assert "- Captures read: 2\n" in body
    assert record["captures"] == 2
    assert record["unreadable_captures"] == []
    # One ladder per capture moment: one on the first day, four on the second.
    assert record["ladders_with_two_rungs"] == 1 + ROUNDS
    assert "::error::" not in capsys.readouterr().err
    assert "could not be read" not in body


def test_a_header_only_day_is_empty_not_damaged(tmp_path: Path) -> None:
    """It holds no row to lose, so there is nothing to name."""
    processed = tmp_path / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    path = _capture_day(processed, BAD_DAY, 1)
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n",
                    encoding="utf-8")

    code, _, record = _main(processed, tmp_path / "outputs")

    assert code == 0
    assert record["unreadable_captures"] == []


# --------------------------------------------------------------------------
# The Line Movement step, and the gate that reads its outcome.
# --------------------------------------------------------------------------

STUB_PYTHON = """#!/bin/sh
if [ "$1" = "scripts/run_ladder_coherence.py" ]; then
  shift
  exec "$REAL_PYTHON" "$RUNNER" --processed-dir "$PWD/data/processed" \\
    --output-dir "$PWD/data/outputs" "$@"
fi
exec "$REAL_PYTHON" "$@"
"""


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for job in document["jobs"].values() for step in job["steps"]]


def _scan_step() -> dict:
    matches = [s for s in _steps() if s.get("name") == "Scan the captured ladders"]
    assert len(matches) == 1
    return matches[0]


def _run_step(root: Path) -> tuple[int, str, str]:
    """The step's own block, under the shell GitHub gives a `run:` (bash -e)."""
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
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
         _scan_step()["run"]],
        cwd=root, env=env, capture_output=True, text=True, timeout=120,
    )
    text = summary.read_text(encoding="utf-8") if summary.is_file() else ""
    return result.returncode, text, result.stdout + result.stderr


@pytest.mark.parametrize("shape", ["undecodable-byte", "stray-quote"])
def test_the_step_names_the_damaged_day_and_exits_non_zero(
    tmp_path: Path, shape: str
) -> None:
    damage, _ = DAMAGE[shape]
    processed = tmp_path / "data" / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    damage(_capture_day(processed, BAD_DAY, ROUNDS))

    code, summary, log = _run_step(tmp_path)

    assert code != 0, log
    assert "wrote no report" not in summary, summary
    # The depth of the days that were read is still reported ...
    assert "### Ladder depth: 1\n" in summary, summary
    # ... under the name of the day that was not.
    assert f"{BAD_DAY}.csv" in summary, summary
    assert f"{BAD_DAY}.csv" in log, log


def test_the_step_exits_zero_on_undamaged_days(tmp_path: Path) -> None:
    processed = tmp_path / "data" / "processed"
    _capture_day(processed, GOOD_DAY, 1)

    code, summary, log = _run_step(tmp_path)

    assert code == 0, log
    assert "### Ladder depth: 1\n" in summary, summary
    assert "could not be read" not in summary, summary


def test_the_step_no_longer_swallows_its_own_exit() -> None:
    step = _scan_step()
    assert "|| true" not in step["run"]
    # A failed scan can never cost the captures: the step is still forgiven
    # and still runs after a failed capture.
    assert step.get("continue-on-error") is True
    assert str(step.get("if", "")).startswith("always()")
    assert step.get("id") == "ladder", "the gate reads this step by its id"


def test_a_failed_scan_turns_the_run_red_after_every_upload(tmp_path: Path) -> None:
    steps = _steps()
    gates = [
        (index, step) for index, step in enumerate(steps)
        if "steps.ladder.outcome == 'failure'" in str(step.get("if", ""))
    ]
    assert len(gates) == 1, "exactly one step must fail the run on a failed scan"
    index, gate = gates[0]
    uploads = [
        i for i, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert uploads and index > max(uploads), (
        "a red run must never stop a capture from being kept"
    )
    assert "always()" in str(gate.get("if", ""))
    assert gate.get("continue-on-error") in (None, False)

    result = subprocess.run(
        ["bash", "-e", "-c", gate["run"]], cwd=tmp_path,
        env={"PATH": os.environ["PATH"]}, capture_output=True, text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "::error::" in result.stdout
