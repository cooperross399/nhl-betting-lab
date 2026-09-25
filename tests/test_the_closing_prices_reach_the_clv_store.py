"""Line Movement's closing prices reach the store CLV is measured from.

Gameday Refresh measures closing-line value from `closing_line_captures.csv`
on the `closing-lines` branch. On 2026-08-29 Closing Lines lost its schedule,
because Line Movement Capture's single fetch already produced the same best
price per selection and two schedules were paying twice. That retired the
branch's only writer. Line Movement wrote the closing prices on its runner,
uploaded them nowhere, and the branch did not exist, so every in-season CLV
report would have read an empty store.

Now Line Movement hands its closing prices over as an artifact, and Closing
Lines runs when it completes and publishes them. That path fetches nothing,
reads no secret and spends no credit.

The structural half reads the YAML. The executed half runs the two `run:`
blocks exactly as written under `bash -e`, with `gh` replaced by a stub and
the branch's remote redirected to a local bare repository, because shell in
YAML otherwise has no test at all.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab.config import PROJECT_ROOT

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
HANDOFF = "Take the closing prices Line Movement handed over"
PUBLISH = "Publish the store"
REPO = "owner/lab"
TOKEN = "rehearsal-token"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(document: dict) -> dict:
    # PyYAML reads the bare key `on` as the boolean True.
    return document.get("on", document.get(True)) or {}


def _steps(document: dict) -> dict[str, dict]:
    (job,) = document["jobs"].values()
    return {step.get("name"): step for step in job["steps"]}


def _handed_over_artifact() -> str:
    """The artifact Line Movement uploads carrying the closing-price store."""
    for job in _load("line-movement.yml")["jobs"].values():
        for step in job["steps"]:
            given = step.get("with") or {}
            if str(given.get("path", "")).strip() == f"data/processed/{cl.CAPTURES_FILENAME}":
                return str(given["name"])
    raise AssertionError("Line Movement uploads no closing-price store")


# -- structure ----------------------------------------------------------------


def test_line_movement_hands_over_exactly_the_store_the_code_writes():
    name = _handed_over_artifact()
    steps = _steps(_load("closing-lines.yml"))
    assert f"--name {name} " in steps[HANDOFF]["run"]


def test_closing_lines_runs_when_line_movement_completes():
    source = _load("line-movement.yml")["name"]
    trigger = _triggers(_load("closing-lines.yml")).get("workflow_run") or {}
    assert trigger.get("workflows") == [source]
    assert "completed" in trigger.get("types", [])


def test_no_step_that_can_spend_runs_on_a_hand_off():
    """A step that reads the provider key is a step that can buy prices."""
    steps = _load("closing-lines.yml")["jobs"]["capture"]["steps"]
    spending = [s for s in steps if "secrets." in yaml.safe_dump(s)]
    assert spending, "the dispatch path must still be able to capture"
    for step in spending:
        assert "github.event_name != 'workflow_run'" in str(step.get("if", "")), step["name"]
    assert "secrets." not in yaml.safe_dump(_steps(_load("closing-lines.yml"))[HANDOFF])


def test_each_path_runs_the_steps_it_needs():
    steps = _steps(_load("closing-lines.yml"))
    assert steps[HANDOFF]["if"] == "github.event_name == 'workflow_run'"
    assert steps["Restore the capture store"]["if"] == "github.event_name != 'workflow_run'"
    assert "event_name" not in steps[PUBLISH]["if"], "both paths publish"
    assert "steps.handoff.outputs.empty != 'true'" in steps[PUBLISH]["if"]


def test_a_hand_off_is_taken_only_from_the_default_branch():
    guard = str(_load("closing-lines.yml")["jobs"]["capture"]["if"])
    assert "github.event.workflow_run.head_branch" in guard
    assert "github.event.repository.default_branch" in guard


def test_the_hand_off_can_read_another_runs_artifacts():
    permissions = _load("closing-lines.yml")["permissions"]
    assert permissions.get("actions") == "read"
    assert permissions.get("contents") == "write"


# -- execution ----------------------------------------------------------------


GAME = {
    "provider_event_id": "evt1",
    "commence_time": "2026-10-08T23:00:00Z",
    "home_team": "Toronto Maple Leafs",
    "away_team": "Boston Bruins",
    "date": "2026-10-08",
}


def _captures(count: int, first_hour: int) -> pd.DataFrame:
    frames = [
        cl.best_prices(
            pd.DataFrame([{**GAME, "market": "moneyline", "player": "",
                           "selection": "away", "line": None,
                           "american_odds": 120.0 + i, "book": "BetMGM"}]),
            captured_at=f"2026-10-08T{first_hour + i:02d}:00:00Z",
        )
        for i in range(count)
    ]
    return pd.concat(frames, ignore_index=True)


def _block(name: str) -> str:
    return _steps(_load("closing-lines.yml"))[name]["run"].replace(
        "${{ github.repository }}", REPO
    )


def _run(cmd, cwd, env):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


@pytest.fixture
def rig(tmp_path):
    if not (shutil.which("git") and shutil.which("bash")):
        pytest.fail("this test needs git and bash, which every runner here has")
    home, bare, work, stub = (tmp_path / d for d in ("home", "remote.git", "work", "bin"))
    for directory in (home, work, stub):
        directory.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GH_TOKEN": TOKEN,
        "RUN_ID": "4242",
        "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
        "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
    }
    _run(["git", "init", "-q", "--bare", str(bare)], tmp_path, env)
    _run(["git", "config", "--global", f"url.file://{bare}.insteadOf",
          f"https://x-access-token:{TOKEN}@github.com/{REPO}"], tmp_path, env)
    (stub / "python").write_text(f'#!/bin/bash\nexec "{sys.executable}" "$@"\n')
    (stub / "python").chmod(0o755)
    shutil.copytree(PROJECT_ROOT / "scripts", work / "scripts")
    (work / "src").symlink_to(PROJECT_ROOT / "src")
    _run(["git", "init", "-q"], work, env)
    return {"root": tmp_path, "bare": bare, "work": work, "stub": stub, "env": env}


def _seed(rig, *, rows: int | None, without_file: bool = False) -> None:
    if rows is None:
        return
    seed = rig["root"] / "seed"
    seed.mkdir()
    env = rig["env"]
    _run(["git", "init", "-q"], seed, env)
    if without_file:
        (seed / "other.txt").write_text("x\n")
    else:
        _captures(rows, 0).to_csv(seed / cl.CAPTURES_FILENAME, index=False, lineterminator="\n")
    _run(["git", "add", "-A"], seed, env)
    _run(["git", "-c", "user.name=s", "-c", "user.email=s@s", "commit", "-qm", "seed"], seed, env)
    _run(["git", "push", "-q", f"file://{rig['bare']}", "HEAD:refs/heads/closing-lines"], seed, env)


def _stub_gh(rig, *, handed: int, listed: bool = True, download_fails: bool = False) -> None:
    handed_file = rig["root"] / "handed.csv"
    _captures(handed, 12).to_csv(handed_file, index=False, lineterminator="\n")
    (rig["stub"] / "gh").write_text(
        "#!/bin/bash\n"
        f'if [ "$1" = api ]; then echo {1 if listed else 0}; exit 0; fi\n'
        'if [ "$1" = run ] && [ "$2" = download ]; then\n'
        f"  {'exit 1' if download_fails else ':'}\n"
        '  while [ $# -gt 0 ]; do [ "$1" = --dir ] && dir="$2"; shift; done\n'
        f'  mkdir -p "$dir"; cp "{handed_file}" "$dir/{cl.CAPTURES_FILENAME}"; exit 0\n'
        "fi\nexit 2\n"
    )
    (rig["stub"] / "gh").chmod(0o755)


def _branch_rows(rig) -> int | None:
    shown = subprocess.run(
        ["git", "--git-dir", str(rig["bare"]), "show",
         f"refs/heads/closing-lines:{cl.CAPTURES_FILENAME}"],
        capture_output=True, text=True,
    )
    return len(shown.stdout.splitlines()) - 1 if shown.returncode == 0 else None


def _hand_off_then_publish(rig) -> tuple[int, int | None]:
    """The two blocks as GitHub runs them: bash -e, publish only if not empty."""
    handoff = _run(["bash", "-e", "-c", _block(HANDOFF)], rig["work"], rig["env"])
    output = Path(rig["env"]["GITHUB_OUTPUT"])
    empty = output.is_file() and "empty=true" in output.read_text()
    if handoff.returncode or empty:
        return handoff.returncode, None
    publish = _run(["bash", "-e", "-c", _block(PUBLISH)], rig["work"], rig["env"])
    return handoff.returncode, publish.returncode


def test_handed_rows_are_merged_into_the_season_store(rig):
    _seed(rig, rows=5)
    _stub_gh(rig, handed=3)
    assert _hand_off_then_publish(rig) == (0, 0)
    assert _branch_rows(rig) == 8


def test_the_first_hand_off_establishes_the_store(rig):
    _seed(rig, rows=None)
    _stub_gh(rig, handed=3)
    assert _hand_off_then_publish(rig) == (0, 0)
    assert _branch_rows(rig) == 3


def test_a_night_with_nothing_handed_over_publishes_nothing(rig):
    _seed(rig, rows=5)
    _stub_gh(rig, handed=3, listed=False)
    assert _hand_off_then_publish(rig) == (0, None)
    assert _branch_rows(rig) == 5


def test_a_download_that_fails_is_a_red_run_not_a_quiet_one(rig):
    """The artifact exists, so that run's closing prices are otherwise lost."""
    _seed(rig, rows=5)
    _stub_gh(rig, handed=3, download_fails=True)
    handoff, publish = _hand_off_then_publish(rig)
    assert handoff != 0 and publish is None
    assert _branch_rows(rig) == 5


def test_a_branch_without_its_store_is_never_overwritten(rig):
    """A hand-off skips the restore step that used to refuse this."""
    _seed(rig, rows=1, without_file=True)
    _stub_gh(rig, handed=3)
    handoff, publish = _hand_off_then_publish(rig)
    assert handoff == 0 and publish != 0
    tip = subprocess.run(
        ["git", "--git-dir", str(rig["bare"]), "ls-tree", "--name-only", "refs/heads/closing-lines"],
        capture_output=True, text=True,
    ).stdout.split()
    assert tip == ["other.txt"]


def test_the_store_format_is_the_one_clv_reads():
    """`best_prices` writes exactly `CAPTURE_COLUMNS`, and no helper column.

    This docstring used to say "The hand-off carries what `best_prices`
    writes, which `load_captures` reads". Nothing here calls `load_captures`.
    The comparison checks `best_prices` against the constant it projects
    onto. Twelve mutants each left CLV matching nothing, and this test passed
    under every one (finding 87). What it does catch is `best_prices`
    dropping its projection and leaking `_decimal` into the store.
    The claim in its name is now held by
    tests/test_clv_reads_the_store_the_hand_off_publishes.py, which runs the
    published store through `run_closing_line_value.main`.
    """
    assert re.fullmatch(r"[a-z_]+\.csv", cl.CAPTURES_FILENAME)
    assert list(_captures(1, 0).columns) == list(cl.CAPTURE_COLUMNS)
