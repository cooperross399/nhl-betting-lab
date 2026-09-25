"""The drift check counted a verdict it could not read as a verdict that moved.

`scripts/check_verdict_drift.py` promises exit 2 when "an experiment produced
no file this run" — the broken refresh Experiment Refresh fails on — and exit
1 when a verdict really moved, which opens the pull request "A recorded
verdict moved on the accumulated data". Only a file with an old mtime reached
exit 2. A file that was missing, empty, truncated or not UTF-8 was labelled
"not produced" and then compared as a verdict: `"not produced" != "in force"`,
so it was counted as moved and the run exited 1. Found by the failure-shape
audit (finding 63; 2/3 refuters). Reproduced with the real
`run_rest_experiment.py` cut off mid-write (a 2,000-byte prefix of
`rest_experiment.json` with a fresh mtime): the report read
"| `team_b2b` | in force | not produced | **yes** |", "1 verdict(s) moved",
exit 1 — and the pull-request step would have committed the truncated file,
which `verdicts.ships()` reads as off, withdrawing `team_b2b` from the card.
The `not produced` branch dates from #64, when 1 was the only non-zero code;
#68 added exit 2 and never routed it there.

A non-UTF-8 file raised `UnicodeDecodeError`, which the `except` did not name,
and any uncaught exception ends Python with status 1 — the same code as
"moved".

What these tests hold, calling the real `main()` with only the git read of
the committed record replaced:

* a missing, empty, truncated, non-UTF-8 or non-object verdict file after the
  run is "not re-decided": exit 2, no `**yes**`, no "moved", no clean bill;
* a verdict that really moved still exits 1, and one that did not still 0;
* the script run as a program exits 2, not 1, when it fails outright.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.verdicts import VERDICT_FILES


SCRIPT = PROJECT_ROOT / "scripts" / "check_verdict_drift.py"
COMMITTED_REST = (PROJECT_ROOT / "data" / "outputs" / "rest_experiment.json").read_bytes()


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_script_check_verdict_drift", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(tmp_path: Path, monkeypatch, team_b2b: bytes | None) -> tuple[int, str]:
    """Every policy committed as in force; `props_b2b` and `by_toi` re-decided
    unchanged this run; `team_b2b` left as the test says (None: no file)."""
    module = _script()
    monkeypatch.setattr(
        module, "committed",
        lambda rel: {"ships": [p for p, f in VERDICT_FILES.items() if f == rel.name]},
    )
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    started = time.time() - 60
    for policy, filename in VERDICT_FILES.items():
        if policy != "team_b2b":
            (outputs / filename).write_text(f'{{"ships": ["{policy}"]}}', encoding="utf-8")
        elif team_b2b is not None:
            (outputs / filename).write_bytes(team_b2b)
    code = module.main(["--output-dir", str(outputs), "--since", str(started)])
    return code, (outputs / "verdict_drift.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "body",
    [
        None,
        b"",
        COMMITTED_REST[:2000],
        COMMITTED_REST[:1],
        b'{"ships": ["team_b2b"], "verdict": "caf\xe9"}',
        b'["team_b2b"]',
        b"null",
    ],
    ids=["missing", "empty", "truncated-2000-bytes", "truncated-1-byte",
         "not-utf-8", "a-list", "null"],
)
def test_an_unreadable_verdict_is_a_broken_refresh_not_a_move(
    tmp_path, monkeypatch, body
):
    code, report = _run(tmp_path, monkeypatch, body)

    assert code == 2
    assert "**yes**" not in report
    assert "moved:" not in report and "Nothing moved" not in report
    assert "were not re-decided: `team_b2b`" in report
    assert "| `team_b2b` | in force | **not produced**" in report


def test_a_verdict_that_really_moved_still_opens_the_pull_request(
    tmp_path, monkeypatch
):
    code, report = _run(tmp_path, monkeypatch, b'{"ships": []}')

    assert code == 1
    assert "| `team_b2b` | in force | off | **yes** |" in report
    assert "1 verdict(s) moved: `team_b2b`" in report


def test_a_verdict_that_held_is_still_a_clean_bill(tmp_path, monkeypatch):
    code, report = _run(tmp_path, monkeypatch, b'{"ships": ["team_b2b"]}')

    assert code == 0
    assert "Nothing moved" in report


def test_the_program_exits_2_not_1_when_it_fails_outright(tmp_path):
    """1 is the code on which the workflow opens a pull request. An output
    directory that is a file makes the report unwritable, which is one way
    the script can die after reading everything."""
    not_a_directory = tmp_path / "outputs"
    not_a_directory.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "PYTHONSAFEPATH": "1",
    }

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(not_a_directory)],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )

    assert result.returncode == 2, result.stderr
    assert "::error::" in result.stderr
