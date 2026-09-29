"""An NHL API outage could use up Gameday Refresh's whole job inside a soft step.

"Fetch results" is documented as soft: if it fails, the run carries on with
the restored cache and says so. But the step had no `timeout-minutes` in a
job capped at 45. The NHL client makes four attempts at every request (a
30-second timeout each, 2+4+8 seconds of backoff), and the fetch asks about
160 schedules, rosters and registries live on every run. Replayed with a
stubbed transport and a simulated clock, fast 503s took about 38 minutes and
a hanging API about 6 hours, so the job was cancelled inside this step:
"Fetch prices into staging" never ran, no card was built, no snapshot was
frozen, and the 15:00 backup met the same outage. Found by sweep 6
(gameday-fetch-results-unbounded-under-nhl-outage, confirmed 2/2).

What these tests hold, on the workflow's own blocks under
`bash --noprofile --norc -eo pipefail` with a stub `python` on PATH:

* the step carries its own `timeout-minutes`, well above a healthy heavy run
  (6 to 11 minutes observed for the first-of-season fills) and well inside
  the job, and the fetch inside it is cut by `timeout` a little earlier;
* a fetch that hangs is stopped, the datasets are still rebuilt on the
  cache, and the step exits non-zero, so its outcome is `failure`;
* "Record what went wrong" calls the run degraded for a results step that
  read `failure` or `cancelled` (what a step stopped at its timeout may
  read), with a full cache, so card-feed reads degraded=true and the backup
  runs; a clean fetch stays clean.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"

#: The slowest healthy "Fetch results" step seen (2026-08-25, a first-fill
#: run of 600 new boxscores plus every schedule, roster and registry) took 11
#: minutes. A bound at or below about half again that would cut legitimate
#: heavy runs.
SLOWEST_HEALTHY_MINUTES = 11

#: What the rest of the job needs after the fetch (prices, the report
#: rebuild, the card, settlement, the upload, the post, card-feed): 7 to 9
#: minutes in those same runs, so leave at least 15.
AFTER_THE_FETCH_MINUTES = 15

INNER = re.compile(r"timeout\s+(?:--kill-after=\d+s\s+)?(\d+)m\s+\\?\s*\n?\s*python scripts/fetch_nhl_data\.py")


def _job() -> dict:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        if any(step.get("id") == "results" for step in job.get("steps", [])):
            return job
    raise AssertionError("no job in gameday-refresh.yml fetches results")


def _step(id_: str) -> dict:
    for step in _job()["steps"]:
        if step.get("id") == id_:
            return step
    raise AssertionError(f"no step {id_} in gameday-refresh.yml")


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions named; refuse any that is not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _inner_minutes() -> int:
    match = INNER.search(_step("results")["run"])
    assert match, "the NHL fetch is not run under `timeout`"
    return int(match.group(1))


# --------------------------------------------------------------------------
# The bounds.
# --------------------------------------------------------------------------

def test_the_results_step_has_its_own_timeout_inside_the_job() -> None:
    step, job = _step("results"), _job()
    assert step["name"] == "Fetch results"
    assert step.get("continue-on-error") is True
    minutes = int(step.get("timeout-minutes", 0))
    assert minutes > 0, "Fetch results has no timeout-minutes"
    assert minutes <= int(job["timeout-minutes"]) - AFTER_THE_FETCH_MINUTES


def test_the_bounds_leave_a_heavy_healthy_run_room() -> None:
    inner, step = _inner_minutes(), int(_step("results")["timeout-minutes"])
    assert inner >= SLOWEST_HEALTHY_MINUTES * 1.5
    # The inner cut comes first, so the datasets are still rebuilt; the
    # step's own bound is only the backstop.
    assert inner < step


# --------------------------------------------------------------------------
# A hanging fetch is stopped, and the run is degraded.
# --------------------------------------------------------------------------

FAKE_PYTHON = """#!/bin/sh
echo "$*" >> "$STUB_LOG"
case "$1" in
  scripts/fetch_nhl_data.py) [ "$FETCH" = hang ] && exec sleep 600; exit 0;;
  scripts/build_datasets.py) exit 0;;
esac
exit 2
"""


def _bin(tmp_path: Path) -> dict:
    if shutil.which("bash") is None or shutil.which("timeout") is None:
        pytest.fail("this test needs bash and coreutils timeout")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    path = bin_dir / "python"
    path.write_text(FAKE_PYTHON, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
            "STUB_LOG": str(tmp_path / "calls.log")}


def _results(tmp_path: Path, fetch: str) -> subprocess.CompletedProcess:
    block = _step("results")["run"]
    minutes = _inner_minutes()
    # The real bound is minutes long; the same line, cut at two seconds.
    block = re.sub(rf"\b{minutes}m\b", "2s", block, count=1)
    block = block.replace("--kill-after=30s", "--kill-after=1s")
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=tmp_path, env={**_bin(tmp_path), "FETCH": fetch},
        capture_output=True, text=True, timeout=60,
    )


def test_a_hanging_fetch_is_stopped_and_the_datasets_still_rebuilt(tmp_path: Path) -> None:
    run = _results(tmp_path, "hang")
    assert run.returncode == 124, run.stdout + run.stderr
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8").splitlines()
    assert calls[-1] == "scripts/build_datasets.py", calls
    assert "stopped" in run.stdout


def test_a_healthy_fetch_is_not_touched(tmp_path: Path) -> None:
    run = _results(tmp_path, "ok")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "stopped" not in run.stdout


def _health(tmp_path: Path, outcome: str) -> tuple[str, str]:
    box = tmp_path / "data" / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for game in range(1200):
        (box / f"{2025020001 + game}.json").write_text('{"gameState": "OFF"}',
                                                       encoding="utf-8")
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "player_game_logs.csv").write_text("game_id\n1\n", encoding="utf-8")
    output = tmp_path / "health_output"
    output.write_text("", encoding="utf-8")
    run = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
         _render(_step("health")["run"], {
             "steps.results.outcome": outcome,
             "steps.prices.outputs.empty_slate": "false",
             "steps.prices.outcome": "success",
         })],
        cwd=tmp_path, env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True, text=True, timeout=60,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    outputs = dict(line.partition("=")[::2]
                   for line in output.read_text(encoding="utf-8").splitlines())
    return outputs.get("degraded", ""), (tmp_path / "run_degraded.txt").read_text(
        encoding="utf-8")


@pytest.mark.parametrize("outcome", ["failure", "cancelled"])
def test_a_fetch_that_failed_or_was_stopped_is_a_degraded_run(tmp_path: Path, outcome: str) -> None:
    degraded, notes = _health(tmp_path, outcome)
    assert degraded == "true"
    assert "could not be refreshed" in notes


def test_a_clean_fetch_with_a_full_cache_is_a_clean_run(tmp_path: Path) -> None:
    degraded, notes = _health(tmp_path, "success")
    assert degraded == "false"
    assert notes == ""

