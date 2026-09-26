"""An HTTP 502 while restoring the bought prices re-decided the verdicts on older ones.

Experiment Refresh's "Restore the accumulated state" step restored four
artifact/workflow pairs with

    python scripts/restore_state.py --artifact "$name" --dest data \\
      --workflow "$wf" --no-merge || true

— no `--refuse-unreachable`, no `--attempts`, and every exit swallowed.
Historical Props Purchase restores the same bought prices with
`--refuse-unreachable --attempts 3` and stops on a failure to ask GitHub
(tests/test_an_unreachable_github_never_reads_as_no_bought_prices.py). Here,
without the flag, restore_state.py records a failed listing or download in
`report["unreached"]` and exits 0, and a failed download of the newest
carrier falls through to an older run. So one 502 while listing (or
downloading from) the purchase runs left `historical_prop_prices.csv` as
whatever older copy `gameday-state` or an older purchase carried, the step
passed its "the bought prices did not restore" check on that stale file, and
the weekly refresh re-decided every verdict on prices it did not know were
old. When no older copy existed, the step failed with "The bought prices did
not restore", which names an absence where GitHub had not answered.

These tests execute the step's own run block, as GitHub runs it (`bash -e`,
and `shell: bash`'s pipefail form), with the REAL restore_state.py and a
fake `gh` that can answer HTTP 502. Everything else the block calls
(`build_datasets.py`, `run_props_calibration.py`) is stubbed: neither decides
what was restored. They hold that:

* a listing that fails on every attempt fails the step, naming GitHub as
  unreachable, and never as "the bought prices did not restore";
* a download of the newest price carrier that fails does the same, instead
  of an older carrier standing in for it;
* one transient 502 is retried and the newest prices are restored;
* a listing that answers and holds no carrier is still an absence, not an
  outage: the step goes on to its own checks, which decide as before.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "experiment-refresh.yml"
RESTORE_STATE = PROJECT_ROOT / "scripts" / "restore_state.py"
GAMEDAY = "gameday-refresh.yml"
PURCHASE = "historical-props-purchase.yml"
PRICES = Path("processed") / "historical_prop_prices.csv"

#: The price file `gameday-state` carries: older than the purchase's own.
STALE = "event_id,price\nold,1.90\n"
#: The price file the newest purchase run carries.
FRESH = "event_id,price\nold,1.90\nnew,2.10\n"

#: The step's own refusal. restore_state.py's output is not enough: without
#: `--refuse-unreachable` it prints its own "GitHub could not be asked" and
#: exits 0, so the words alone prove nothing about the step stopping.
UNREACHABLE = "::error::GitHub could not be reached"
ABSENT_PRICES = "The bought prices did not restore"

SHELLS = {
    "github-default": ["bash", "-e", "-c"],
    "pipefail": ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c"],
}

FAKE_GH = r'''#!{python}
import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ["FAKE_GH_STATE"])
registry = json.loads((state / "registry.json").read_text())
failures_path = state / "failures.json"
failures = json.loads(failures_path.read_text())

def value(flag):
    return args[args.index(flag) + 1] if flag in args else None

def injected(key, message):
    if failures.get(key, 0) > 0:
        failures[key] -= 1
        failures_path.write_text(json.dumps(failures))
        print(message, file=sys.stderr)
        sys.exit(1)

if args[:2] == ["run", "list"]:
    workflow = value("--workflow")
    injected("list:" + workflow, "HTTP 502: Bad Gateway")
    runs = [r for r in registry if r["workflow"] == workflow
            and r["headBranch"] == value("--branch")][: int(value("--limit"))]
    fields = value("--json").split(",")
    print(json.dumps([{{k: r[k] for k in fields}} for r in runs]))
    sys.exit(0)
if args[:2] == ["run", "download"]:
    run_id, name, dest = args[2], value("--name"), Path(value("--dir"))
    injected("download:" + run_id + ":" + name,
             "error downloading " + name + ": HTTP 502: Bad Gateway")
    run = next(r for r in registry if str(r["databaseId"]) == run_id)
    if name not in run["artifacts"]:
        print("no artifact matches any of the names or patterns provided",
              file=sys.stderr)
        sys.exit(1)
    shutil.copytree(run["artifacts"][name], dest, dirs_exist_ok=True)
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''

#: `python` on the step's PATH: restore_state.py runs for real, under this
#: interpreter; the dataset build and the calibration are stubbed, the
#: calibration writing the samples file the step checks for.
FAKE_PYTHON = """#!/bin/bash
case "$1" in
  scripts/restore_state.py) shift; exec {python} {restore} "$@" ;;
  scripts/run_props_calibration.py)
    mkdir -p data/outputs && echo built > data/outputs/prop_calibration_samples.csv ;;
esac
exit 0
"""


def _restore_block() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "restore":
                assert "shell" not in step, "the shells below assume GitHub's default"
                return step["run"]
    raise AssertionError("no restore step")


def _artifact(root: Path, *, boxscores: int = 0, prices: str | None = None) -> str:
    root.mkdir(parents=True)
    box = root / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for game in range(boxscores):
        (box / f"{game}.json").write_text("{}", encoding="utf-8")
    if prices is not None:
        (root / PRICES).parent.mkdir(parents=True, exist_ok=True)
        (root / PRICES).write_text(prices, encoding="utf-8")
    return str(root)


def _run(workflow: str, run_id: int, **artifacts: str) -> dict:
    return {"databaseId": run_id, "workflow": workflow, "status": "completed",
            "conclusion": "success", "headBranch": "main",
            "artifacts": {name.replace("_", "-"): path for name, path in artifacts.items()}}


def _refresh(tmp_path: Path, shell: str, *, fail: dict[str, int],
             purchase_carries_prices: bool = True) -> tuple[subprocess.CompletedProcess, Path]:
    """The restore step, run once against a chain where Gameday Refresh
    carries the boxscores and an OLDER price file and the newest purchase
    run (8002) carries the newest prices, above an older purchase (8001)."""
    arts = tmp_path / "artifacts"
    gameday = _artifact(arts / "gameday", boxscores=500, prices=STALE)
    registry = [_run(GAMEDAY, 6001, gameday_state=gameday)]
    if purchase_carries_prices:
        registry += [
            _run(PURCHASE, 8002, historical_props=_artifact(arts / "p2", prices=FRESH)),
            _run(PURCHASE, 8001, historical_props=_artifact(arts / "p1", prices=STALE)),
        ]
    else:
        registry += [_run(PURCHASE, 8002)]

    state = tmp_path / "gh"
    state.mkdir()
    (state / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (state / "failures.json").write_text(json.dumps(fail), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("gh", FAKE_GH.format(python=sys.executable)),
        ("python", FAKE_PYTHON.format(python=sys.executable, restore=RESTORE_STATE)),
    ):
        path = bin_dir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    work = tmp_path / "work"
    work.mkdir()

    result = subprocess.run(
        [*SHELLS[shell], _restore_block()],
        cwd=work, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
             "FAKE_GH_STATE": str(state), "TMPDIR": str(tmp_path),
             "RESTORE_STATE_RETRY_SECONDS": "0"},
    )
    return result, work / "data" / PRICES


def _prices(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


ALWAYS = 99


@pytest.mark.parametrize("shell", sorted(SHELLS))
def test_a_failed_purchase_listing_fails_the_refresh_naming_github(
    tmp_path: Path, shell: str,
) -> None:
    result, _ = _refresh(tmp_path, shell, fail={f"list:{PURCHASE}": ALWAYS})
    said = result.stdout + result.stderr

    assert result.returncode != 0, (
        "the refresh went on to re-decide on the older price file:\n" + said
    )
    assert UNREACHABLE in said, said
    assert ABSENT_PRICES not in said, "an outage was reported as an absence"
    assert "samples:" not in said, "the step went on past the restore"


@pytest.mark.parametrize("shell", sorted(SHELLS))
def test_a_failed_download_of_the_newest_prices_is_not_stood_in_for(
    tmp_path: Path, shell: str,
) -> None:
    result, prices = _refresh(tmp_path, shell,
                              fail={"download:8002:historical-props": ALWAYS})
    said = result.stdout + result.stderr

    assert result.returncode != 0, (
        "an older purchase run stood in for the newest:\n" + said
    )
    assert UNREACHABLE in said, said
    assert ABSENT_PRICES not in said
    assert _prices(prices) != FRESH


def test_a_failed_gameday_listing_fails_the_refresh_too(tmp_path: Path) -> None:
    """Not the prices alone: every restore in the step is held to it."""
    result, _ = _refresh(tmp_path, "github-default", fail={f"list:{GAMEDAY}": ALWAYS})

    assert result.returncode != 0, result.stdout + result.stderr
    assert UNREACHABLE in result.stdout + result.stderr


@pytest.mark.parametrize("fail", [f"list:{PURCHASE}", "download:8002:historical-props"])
def test_a_transient_failure_is_retried_and_the_newest_prices_restored(
    tmp_path: Path, fail: str,
) -> None:
    """Two 502s, then an answer: inside `--attempts 3`. Two, because the
    purchase runs are listed once for `gameday-state` before the listing
    that finds the prices, and one failure would be spent on that."""
    result, prices = _refresh(tmp_path, "github-default", fail={fail: 2})

    assert result.returncode == 0, result.stdout + result.stderr
    assert _prices(prices) == FRESH


def test_a_listing_that_holds_no_carrier_is_an_absence_not_an_outage(
    tmp_path: Path,
) -> None:
    """The purchase runs answer and none carries prices: that is an answer.
    The restore goes on, and the step's own checks decide on what arrived
    (here, the price file `gameday-state` carries)."""
    result, prices = _refresh(tmp_path, "github-default", fail={},
                              purchase_carries_prices=False)
    said = result.stdout + result.stderr

    assert result.returncode == 0, said
    assert UNREACHABLE not in said
    assert _prices(prices) == STALE


def test_the_newest_prices_are_restored_when_github_answers(tmp_path: Path) -> None:
    result, prices = _refresh(tmp_path, "github-default", fail={})

    assert result.returncode == 0, result.stdout + result.stderr
    assert _prices(prices) == FRESH
