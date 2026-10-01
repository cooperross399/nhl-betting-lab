"""With no private closing-line store, the CLV report reads Line Movement's captures.

Closing Lines was disabled from 2026-09-25 (its branch would have been a
permanent, downloadable odds file on a public repository), and Gameday Refresh
never had Line Movement's captures on its runner, so the closing-line value
report scored no closing price at all. The step restores the `line-movement`
chain, which `load_captures` already falls back to, for the report only, and
removes it afterwards so gameday-state does not upload a second copy of every
price. Since 2026-10-01 the store is private (cooperross399/nhl-closing-lines),
and this fallback is what the step does when the pull finds no store: no
NHL_CLOSING_LINES_TOKEN (exit 3), as here.
`test_closing_prices_never_reach_the_public_repo.py` covers the store read.

These run the workflow's own step block under `bash -eo pipefail` with a stub
`python` and a `git` that reaches no network, as
`test_a_failed_settlement_fails_the_run.py` does.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from test_a_blocked_card_is_a_degraded_run import _bash, _render

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
STEP = "Report closing-line value"
DAY_FILE = "2026-09-29.csv"


def _block() -> str:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["refresh"]["steps"]
    (step,) = [s for s in steps if s.get("name") == STEP]
    return _render(step["run"], {"github.repository": "o/r"})


def _stubs(tmp_path: Path, *, restore: str, clv_exit: int) -> dict:
    """`restore` is "chain" (the artifact holds a day file), "empty" (no run
    carries one yet) or "fail" (the restore could not ask GitHub)."""
    bin_dir = tmp_path / "stubs"
    bin_dir.mkdir()
    restore_case = {
        "chain": f'mkdir -p data/processed/line_movement data/processed/deployment; echo x > data/processed/line_movement/{DAY_FILE}; exit 0',
        "empty": "exit 0",
        "fail": 'echo "listing failed after 3 attempts" >> clv_restore_problem.txt; exit 1',
    }[restore]
    python = bin_dir / "python"
    python.write_text(
        "#!/bin/bash\n"
        'case "$1" in\n'
        "  */private_closing_store.py) exit 3 ;;\n"
        f"  */restore_state.py) {restore_case} ;;\n"
        "  */run_closing_line_value.py)\n"
        f'    if [ -f data/processed/line_movement/{DAY_FILE} ]; then echo saw > clv_saw.txt; else echo none > clv_saw.txt; fi\n'
        f"    exit {clv_exit} ;;\n"
        "esac\nexit 0\n",
        encoding="utf-8",
    )
    git = bin_dir / "git"
    git.write_text(
        '#!/bin/bash\ncase "$1" in\n  ls-remote) exit 0 ;;\n  *) exit 1 ;;\nesac\n',
        encoding="utf-8",
    )
    for path in (python, git):
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "GH_TOKEN": "x", "PYTHONPATH": "src",
            "RUNNER_TEMP": str(tmp_path / "runner_temp")}


def _run(tmp_path: Path, *, restore: str, clv_exit: int = 0
         ) -> tuple[subprocess.CompletedProcess, Path]:
    work = tmp_path / "work"
    (work / "data" / "processed").mkdir(parents=True)
    (work / "data" / "processed" / "kept.csv").write_text("keep\n", encoding="utf-8")
    (work / "run_degraded.txt").write_text("", encoding="utf-8")
    result = _bash(_block(), work, _stubs(tmp_path, restore=restore, clv_exit=clv_exit))
    return result, work


def test_the_report_reads_the_movement_captures(tmp_path: Path) -> None:
    result, work = _run(tmp_path, restore="chain")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (work / "clv_saw.txt").read_text().strip() == "saw"
    assert "line-movement day file(s) for the closing prices" in result.stdout
    assert (work / "run_degraded.txt").read_text() == ""


def test_the_captures_do_not_ride_along_in_gameday_state(tmp_path: Path) -> None:
    _result, work = _run(tmp_path, restore="chain")
    assert not (work / "data" / "processed" / "line_movement").exists()
    assert not (work / "data" / "processed" / "deployment").exists()
    # Everything else the runner had in data/processed is left alone.
    assert (work / "data" / "processed" / "kept.csv").read_text() == "keep\n"


@pytest.mark.parametrize("code", [0, 2])
def test_the_reports_own_exit_is_the_steps_exit(tmp_path: Path, code: int) -> None:
    """Exit 2 (a damaged snapshot or store) is what "Report the outcome"
    reads; the clean-up must neither swallow it nor be skipped by it."""
    result, work = _run(tmp_path, restore="chain", clv_exit=code)
    assert result.returncode == code
    assert not (work / "data" / "processed" / "line_movement").exists()


def test_no_captures_yet_is_not_a_fault(tmp_path: Path) -> None:
    result, work = _run(tmp_path, restore="empty")
    assert result.returncode == 0
    assert (work / "clv_saw.txt").read_text().strip() == "none"
    assert "No line-movement captures yet" in result.stdout
    assert (work / "run_degraded.txt").read_text() == ""


def test_a_restore_that_could_not_ask_is_recorded(tmp_path: Path) -> None:
    result, work = _run(tmp_path, restore="fail")
    assert result.returncode == 0  # the report still runs on what it has
    degraded = (work / "run_degraded.txt").read_text()
    assert "could not be restored" in degraded
    assert "listing failed after 3 attempts" in degraded
