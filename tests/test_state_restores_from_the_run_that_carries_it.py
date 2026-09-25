"""The state was restored from "the newest successful run", which was wrong twice.

Every workflow picked its restore source with `gh run list --status success
--limit 1`. A skipped run is recorded as a success with no artifact — and the
15:00 backup's job is skipped on every day the 13:30 run is clean — so the next
day's restore picked it, found nothing, exited 0 before the card-feed ledger
fallback, and started cold. A cold run is degraded, so red, so never a restore
source either: every later run started cold, pricing the season on autumn-2023
boxscores. And a degraded run's state — its growing cache, the snapshot it
froze and posted — was never restored, so a cold cache capped at 600 games a
run refetched the same 600 forever. Found by the failure-shape audit (3/3
refuters on each, including the skipped-run shape read off golf-betting-lab's
real run history).

These tests run the real `scripts/restore_state.py` as a subprocess with a
fake `gh` on PATH that replays a scenario — run lists, artifacts, failures —
and they run the Gameday Refresh restore step itself, from the workflow file,
under bash -e with fake `gh` and `git`.
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


SCRIPT = PROJECT_ROOT / "scripts" / "restore_state.py"

FAKE_GH = r'''#!{python}
import json, os, shutil, sys
from pathlib import Path
scenario = json.loads(Path(os.environ["FAKE_GH_SCENARIO"]).read_text())
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\n")
args = sys.argv[1:]
if args[:2] == ["run", "list"]:
    workflow = args[args.index("--workflow") + 1]
    print(json.dumps(scenario["runs"].get(workflow, [])))
    sys.exit(0)
if args[:2] == ["run", "download"]:
    run_id, name = args[2], args[args.index("--name") + 1]
    dest = Path(args[args.index("--dir") + 1])
    source = scenario["artifacts"].get(run_id, {{}}).get(name)
    if source is None or run_id in scenario.get("broken", []):
        print("no valid artifacts found to download", file=sys.stderr)
        sys.exit(1)
    shutil.copytree(source, dest, dirs_exist_ok=True)
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''


def _state(root: Path, *, boxscores: range, ledger_rows: int = 0,
           snapshots: tuple[str, ...] = (), card: str = "") -> Path:
    """An artifact as `Upload the state` lays it out, relative to data/."""
    box = root / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for game in boxscores:
        (box / f"{game}.json").write_text("{}", encoding="utf-8")
    if ledger_rows:
        processed = root / "processed"
        processed.mkdir(parents=True)
        (processed / "forward_evidence.csv").write_text(
            "snapshot_date,outcome\n"
            + "".join(f"2026-10-{i + 1:02d},won\n" for i in range(ledger_rows)),
            encoding="utf-8",
        )
    for day in snapshots:
        archive = root / "archive" / "priced_snapshots"
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f"{day}.csv").write_text("snapshot_date\n", encoding="utf-8")
    if card:
        (root / "outputs").mkdir(parents=True)
        (root / "outputs" / "gameday_card.json").write_text(card, encoding="utf-8")
    return root


def _env(tmp_path: Path, scenario: dict) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "FAKE_GH_SCENARIO": str(tmp_path / "scenario.json"),
        "FAKE_GH_LOG": str(tmp_path / "gh.log"),
    }


def _restore(tmp_path: Path, scenario: dict, *extra: str) -> tuple[Path, str]:
    dest = tmp_path / "data"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--artifact", "gameday-state",
         "--dest", str(dest), "--workflow", "gameday-refresh.yml",
         "--workflow", "historical-props-purchase.yml", *extra],
        env=_env(tmp_path, scenario), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return dest, result.stdout


def _count(dest: Path) -> int:
    return len(list((dest / "raw" / "nhl" / "boxscore").glob("*.json")))


def _run(run_id: int, conclusion: str, status: str = "completed") -> dict:
    return {"databaseId": run_id, "conclusion": conclusion, "status": status}


def test_a_skipped_backup_run_is_not_the_restore_source(tmp_path: Path) -> None:
    """The newest success is the skipped 15:00 run: no artifact at all."""
    good = _state(tmp_path / "a200", boxscores=range(1000), ledger_rows=5)
    scenario = {
        "runs": {"gameday-refresh.yml": [_run(201, "success"), _run(200, "success")]},
        "artifacts": {"200": {"gameday-state": str(good)}},
    }

    dest, out = _restore(tmp_path, scenario)

    assert _count(dest) == 1000
    assert "run 200" in out


def test_a_red_runs_state_is_restored_with_the_last_good_one_underneath(
    tmp_path: Path,
) -> None:
    """The red run grew the cache and froze today's snapshot; both survive,
    and nothing the older state held is lost."""
    red = _state(tmp_path / "a301", boxscores=range(600, 1200), ledger_rows=5,
                 snapshots=("2026-10-08",), card='{"day": "2026-10-08"}')
    good = _state(tmp_path / "a300", boxscores=range(600), ledger_rows=5,
                  snapshots=("2026-10-07",), card='{"day": "2026-10-07"}')
    scenario = {
        "runs": {"gameday-refresh.yml": [_run(301, "failure"), _run(300, "success")]},
        "artifacts": {"301": {"gameday-state": str(red)},
                      "300": {"gameday-state": str(good)}},
    }

    dest, out = _restore(tmp_path, scenario)
    snapshots = sorted(p.name for p in (dest / "archive" / "priced_snapshots").iterdir())

    assert _count(dest) == 1200
    assert snapshots == ["2026-10-07.csv", "2026-10-08.csv"]
    # Underneath, never over: the newer run's files win every collision.
    assert (dest / "outputs" / "gameday_card.json").read_text() == '{"day": "2026-10-08"}'
    assert "run 301 (failure)" in out and "run 300 (success) underneath" in out


def test_a_thin_red_state_cannot_shrink_the_ledger(tmp_path: Path) -> None:
    """A red run that itself started cold uploads a thin state; the ledger,
    which only grows, comes from whichever copy is longer."""
    thin = _state(tmp_path / "a401", boxscores=range(10), ledger_rows=2)
    good = _state(tmp_path / "a400", boxscores=range(1000), ledger_rows=40)
    scenario = {
        "runs": {"gameday-refresh.yml": [_run(401, "failure"), _run(400, "success")]},
        "artifacts": {"401": {"gameday-state": str(thin)},
                      "400": {"gameday-state": str(good)}},
    }

    dest, _ = _restore(tmp_path, scenario)
    ledger = (dest / "processed" / "forward_evidence.csv").read_text().splitlines()

    assert _count(dest) == 1000
    assert len(ledger) - 1 == 40


def test_a_download_that_fails_falls_back_to_the_next_run(tmp_path: Path) -> None:
    good = _state(tmp_path / "a500", boxscores=range(800))
    scenario = {
        "runs": {"gameday-refresh.yml": [_run(501, "success"), _run(500, "success")]},
        "artifacts": {"501": {"gameday-state": str(good)},
                      "500": {"gameday-state": str(good)}},
        "broken": ["501"],
    }

    dest, out = _restore(tmp_path, scenario)

    assert _count(dest) == 800 and "run 500" in out


def test_the_purchase_workflow_is_the_fallback_and_in_progress_runs_are_not(
    tmp_path: Path,
) -> None:
    bought = _state(tmp_path / "a900", boxscores=range(300))
    scenario = {
        "runs": {
            "gameday-refresh.yml": [_run(601, "", status="in_progress")],
            "historical-props-purchase.yml": [_run(900, "success")],
        },
        "artifacts": {"601": {"gameday-state": str(bought)},
                      "900": {"gameday-state": str(bought)}},
    }

    dest, out = _restore(tmp_path, scenario)

    assert _count(dest) == 300 and "historical-props-purchase.yml run 900" in out


def test_no_merge_takes_the_chosen_run_alone(tmp_path: Path) -> None:
    """Publish Site: an older card must never fill in for today's."""
    red = _state(tmp_path / "a701", boxscores=range(5))
    good = _state(tmp_path / "a700", boxscores=range(900), card="{}")
    scenario = {
        "runs": {"gameday-refresh.yml": [_run(701, "failure"), _run(700, "success")]},
        "artifacts": {"701": {"gameday-state": str(red)},
                      "700": {"gameday-state": str(good)}},
    }

    dest, _ = _restore(tmp_path, scenario, "--no-merge")

    assert _count(dest) == 5
    assert not (dest / "outputs" / "gameday_card.json").exists()


def test_nothing_to_restore_is_a_statement_not_an_error(tmp_path: Path) -> None:
    dest, out = _restore(tmp_path, {"runs": {}, "artifacts": {}})

    assert "this run starts without it" in out


# --------------------------------------------------------------------------
# The Gameday Refresh step itself.
# --------------------------------------------------------------------------

def _restore_step() -> str:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml").read_text(
            encoding="utf-8"
        )
    )
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "restore":
                return step["run"].replace(
                    "${{ github.repository }}", "owner/nhl-betting-lab"
                )
    raise AssertionError("no step with id: restore in gameday-refresh.yml")


@pytest.mark.parametrize("scenario_name", ["skipped-newest", "nothing-at-all"])
def test_the_step_always_reaches_the_ledger_fallback(
    tmp_path: Path, scenario_name: str
) -> None:
    """The old step exited 0 before the fallback whenever the download failed
    or no run was found, so a broken chain lost the ledger for good."""
    scenario = {
        "skipped-newest": {
            "runs": {"gameday-refresh.yml": [_run(801, "success")]},
            "artifacts": {},
        },
        "nothing-at-all": {"runs": {}, "artifacts": {}},
    }[scenario_name]
    env = _env(tmp_path, scenario)
    bin_dir = tmp_path / "bin"
    git = bin_dir / "git"
    git.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  fetch) exit 0;;\n"
        "  cat-file) exit 0;;\n"
        '  show) printf "snapshot_date,outcome\\n2026-10-01,won\\n"; exit 0;;\n'
        "esac\n"
        "exit 1\n",
        encoding="utf-8",
    )
    git.chmod(git.stat().st_mode | stat.S_IEXEC)
    work = tmp_path / "work"
    work.mkdir()
    (work / "scripts").mkdir()
    (work / "scripts" / "restore_state.py").write_text(
        SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    python_dir = Path(sys.executable).parent
    env["PATH"] = f"{bin_dir}:{python_dir}:{os.environ.get('PATH', '')}"
    env["GH_TOKEN"] = "not-a-token"

    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _restore_step()],
        cwd=work, env=env, capture_output=True, text=True,
    )
    ledger = work / "data" / "processed" / "forward_evidence.csv"

    assert result.returncode == 0, result.stderr
    assert ledger.is_file(), (
        "the card-feed ledger fallback was not reached: " + result.stdout
    )


def test_also_takes_the_second_artifact_from_the_same_run(tmp_path: Path) -> None:
    """Publish Site pairs the reports with the state they describe."""
    state = _state(tmp_path / "s", boxscores=range(3))
    newer_reports = tmp_path / "r2"
    (newer_reports).mkdir()
    (newer_reports / "gameday_card.md").write_text("today", encoding="utf-8")
    older_reports = tmp_path / "r1"
    older_reports.mkdir()
    (older_reports / "gameday_card.md").write_text("yesterday", encoding="utf-8")
    scenario = {
        "runs": {"gameday-refresh.yml": [_run(1002, "failure"), _run(1001, "success")]},
        "artifacts": {
            "1002": {"gameday-state": str(state), "gameday-reports": str(newer_reports)},
            "1001": {"gameday-state": str(state), "gameday-reports": str(older_reports)},
        },
    }

    dest, _ = _restore(tmp_path, scenario, "--no-merge",
                       "--also", f"gameday-reports={tmp_path / 'data' / 'outputs'}")

    assert (dest / "outputs" / "gameday_card.md").read_text() == "today"
