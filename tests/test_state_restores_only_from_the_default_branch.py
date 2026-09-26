"""A run dispatched on a feature branch was a restore source for main.

`scripts/restore_state.py` chose its source with `gh run list --workflow W
--limit N --json databaseId,conclusion,status` and kept every completed run.
It passed no `--branch` and never asked for `headBranch`, so the newest
carrier on ANY branch became the state main's next run started from. Found
by the failure-shape audit and confirmed by two of three refuters.

It was already set to happen on real data. Line Movement's only unexpired
`line-movement` artifact belongs to run 33691822845: a `workflow_dispatch` on
branch `rehearse-the-line-fetch`, 2026-09-02T22:44Z, 20,111 bytes, expiring
2026-12-01, holding one file, `line_combinations/2026-09-02.csv` (32 teams,
1,236 role rows). The two main runs before it, 33691644979 and 33252075234,
carry no artifact. So the first scheduled Line Movement run, 2026-09-29, would
have taken the branch rehearsal as the newest carrier and seeded the season's
append-only capture chain from it; every later upload carries it forward.

The Gameday chain has more at stake. A branch dispatch freezes that day's
priced snapshot with the branch's code and uploads `gameday-state`; the next
main Gameday Refresh restored it as the newest carrier, so the branch
snapshot stood as the day's first opinion (the first snapshot of a day is
never replaced) and settled into the pre-registered forward ledger; and
Publish Site, whose `workflow_run` has no branch filter, restored the same
run and froze the public board from it. Historical Props Purchase and
Experiment Refresh restore through the same function. Measured run history
(`gh run list --limit 200`): Gameday Refresh 11 of 11 runs on main, Historical
Props Purchase 11 of 11, Experiment Refresh 9 of 9, Publish Site 16 of 16,
Line Movement 2 of 3 — its third is the rehearsal. `gh run list --branch main`
returns exactly the unfiltered list for Gameday Refresh and Historical Props
Purchase, so the filter drops no main carrier this lab has.

These tests run the real script, and the restore steps themselves taken from
the workflow files under `bash --noprofile --norc -eo pipefail`, against an
offline `gh` that honours `--branch`, `--json`, `--status`, `--limit` and the
one `--jq` a step uses, as `gh run list --help` documents them. One scenario
runs a `gh` that ignores `--branch`, so the client-side check is exercised on
its own rather than masked by the server-side filter in front of it.
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
WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"

#: The real Line Movement run history on 2026-09-25, newest first.
REHEARSAL = 33691822845  # rehearse-the-line-fetch, workflow_dispatch, carries it
MAIN_BEFORE_IT = (33691644979, 33252075234)  # main, workflow_dispatch, no artifact

FEATURE = "try-new-edge-bar"

FAKE_GH = r'''#!{python}
import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
registry = json.loads(Path(os.environ["FAKE_GH_REGISTRY"]).read_text())

def value(flag, default=None):
    return args[args.index(flag) + 1] if flag in args else default

if args[:2] == ["run", "list"]:
    runs = [r for r in registry if r["workflow"] == value("--workflow")]
    branch = value("--branch")
    if branch is not None and os.environ.get("FAKE_GH_IGNORES_BRANCH") != "1":
        runs = [r for r in runs if r["headBranch"] == branch]
    status = value("--status")
    if status:
        # As `gh run list --help` documents it: a status or a conclusion.
        runs = [r for r in runs if status in (r["status"], r["conclusion"])]
    runs = runs[: int(value("--limit", "20"))]
    fields = [f for f in value("--json", "").split(",") if f]
    rows = [{{k: r[k] for k in fields}} for r in runs]
    jq = value("--jq")
    if jq is None:
        print(json.dumps(rows))
    elif jq == ".[0].databaseId // empty":
        if rows:
            print(rows[0]["databaseId"])
    else:
        print("fake gh: unsupported --jq " + jq, file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
if args[:2] == ["run", "download"]:
    run_id, name, dest = args[2], value("--name"), Path(value("--dir"))
    run = next((r for r in registry if str(r["databaseId"]) == run_id), {{}})
    source = (run.get("artifacts") or {{}}).get(name)
    if source is None:
        print("no valid artifacts found to download", file=sys.stderr)
        sys.exit(1)
    shutil.copytree(source, dest, dirs_exist_ok=True)
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''


# --------------------------------------------------------------------------
# Scenario builders.
# --------------------------------------------------------------------------

def _run(run_id: int, *, workflow: str, branch: str = "main",
         event: str = "schedule", conclusion: str = "success",
         artifacts: dict[str, Path] | None = None) -> dict:
    """One row of `gh run list`, plus what `gh run download` can fetch."""
    return {
        "databaseId": run_id, "workflow": workflow, "status": "completed",
        "conclusion": conclusion, "headBranch": branch, "event": event,
        "artifacts": {name: str(path) for name, path in (artifacts or {}).items()},
    }


def _gameday_state(root: Path, *, built_on: str, day: str, ledger_rows: int,
                   boxscores: range = range(3)) -> Path:
    """A `gameday-state` artifact as `Upload the state` lays it out."""
    box = root / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for game in boxscores:
        (box / f"{game}.json").write_text("{}", encoding="utf-8")
    processed = root / "processed"
    processed.mkdir(parents=True)
    (processed / "forward_evidence.csv").write_text(
        "snapshot_date,built_on\n"
        + "".join(f"2026-10-{i + 1:02d},{built_on}\n" for i in range(ledger_rows)),
        encoding="utf-8",
    )
    archive = root / "archive" / "priced_snapshots"
    archive.mkdir(parents=True)
    (archive / f"{day}.csv").write_text(
        f"snapshot_date,built_on\n{day},{built_on}\n", encoding="utf-8"
    )
    (root / "outputs").mkdir(parents=True)
    (root / "outputs" / "gameday_card.json").write_text(
        json.dumps({"date": day, "built_on": built_on}), encoding="utf-8"
    )
    return root


def _gameday_reports(root: Path, *, built_on: str) -> Path:
    root.mkdir(parents=True)
    (root / "gameday_card.md").write_text(f"card built on {built_on}", encoding="utf-8")
    return root


def _captures(root: Path, rows: dict[str, list[str]]) -> Path:
    """A `line-movement` artifact: append-only CSV stores under data/processed."""
    for relative, lines in rows.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return root


def _env(tmp_path: Path, registry: list[dict], *, ignores_branch: bool = False) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    # The Gameday restore reads card-feed only when no ledger came back; a
    # git that answers nothing keeps that fallback out of these scenarios.
    git = bin_dir / "git"
    git.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    git.chmod(git.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
        "GH_TOKEN": "not-a-token",
        "FAKE_GH_REGISTRY": str(tmp_path / "registry.json"),
        "FAKE_GH_LOG": str(tmp_path / "gh.log"),
        "FAKE_GH_IGNORES_BRANCH": "1" if ignores_branch else "0",
    }


def _script(tmp_path: Path, registry: list[dict], *args: str,
            ignores_branch: bool = False) -> tuple[Path, str]:
    """The real script, as a subprocess, into tmp_path/data."""
    dest = tmp_path / "data"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dest", str(dest), *args],
        env=_env(tmp_path, registry, ignores_branch=ignores_branch),
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return dest, result.stdout


def _step(workflow: str, name: str) -> str:
    document = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    found = [
        step["run"] for job in document["jobs"].values()
        for step in job.get("steps", []) if step.get("name") == name
    ]
    assert len(found) == 1, f"exactly one step named {name!r} in {workflow}"
    block = found[0].replace("${{ github.repository }}", "owner/nhl-betting-lab")
    assert "${{" not in block, f"an unstubbed expression is left in {name!r}"
    return block


def _run_step(tmp_path: Path, block: str, registry: list[dict]) -> tuple[Path, str]:
    """The step's own run block, as the runner runs it, in a fresh checkout."""
    work = tmp_path / "work"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts" / "restore_state.py").write_text(
        SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=work, env=_env(tmp_path, registry), capture_output=True, text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return work, result.stdout


def _downloaded(tmp_path: Path) -> list[str]:
    log = (tmp_path / "gh.log").read_text(encoding="utf-8").splitlines()
    return [line.split()[2] for line in log if line.startswith("run download ")]


def _ledger(dest: Path) -> list[str]:
    path = dest / "processed" / "forward_evidence.csv"
    return path.read_text(encoding="utf-8").splitlines()[1:]


def _snapshots(dest: Path) -> list[str]:
    return sorted(p.name for p in (dest / "archive" / "priced_snapshots").iterdir())


# --------------------------------------------------------------------------
# The real Line Movement history: the rehearsal must not seed the season.
# --------------------------------------------------------------------------

def _line_movement_history(tmp_path: Path) -> list[dict]:
    rehearsal = _captures(tmp_path / "a-rehearsal", {
        "line_combinations/2026-09-02.csv": [
            "team,player,group,source",
            "TOR,Auston Matthews,F1,2026 Offseason (Projected)",
            "TOR,Matthew Knies,F1,2026 Offseason (Projected)",
        ],
    })
    return [
        _run(REHEARSAL, workflow="line-movement.yml", branch="rehearse-the-line-fetch",
             event="workflow_dispatch", artifacts={"line-movement": rehearsal}),
        *(_run(run_id, workflow="line-movement.yml", event="workflow_dispatch")
          for run_id in MAIN_BEFORE_IT),
    ]


def test_the_branch_rehearsal_does_not_seed_the_seasons_capture_chain(
    tmp_path: Path,
) -> None:
    """Line Movement's own restore step on the history GitHub holds today:
    no main run carries the artifact, so the 09-29 run starts clean."""
    block = _step("line-movement.yml", "Restore today's captures")

    work, out = _run_step(tmp_path, block, _line_movement_history(tmp_path))

    processed = work / "data" / "processed"
    assert not (processed / "line_combinations" / "2026-09-02.csv").exists(), (
        "the rehearse-the-line-fetch capture was restored into main's chain"
    )
    assert str(REHEARSAL) not in _downloaded(tmp_path)
    assert "No completed run of line-movement.yml" in out, out


def test_the_rehearsal_is_restored_only_when_its_branch_is_asked_for(
    tmp_path: Path,
) -> None:
    """The artifact is still reachable on purpose: naming its branch takes it."""
    dest, out = _script(
        tmp_path, _line_movement_history(tmp_path), "--artifact", "line-movement",
        "--workflow", "line-movement.yml", "--union", "3",
        "--branch", "rehearse-the-line-fetch",
    )

    assert (dest / "line_combinations" / "2026-09-02.csv").is_file()
    assert f"run {REHEARSAL}" in out and "rehearse-the-line-fetch" in out


# --------------------------------------------------------------------------
# The Gameday chain and the public site.
# --------------------------------------------------------------------------

def _gameday_history(tmp_path: Path) -> list[dict]:
    """The finding's scenario. A branch dispatch on 10-08 froze the day with
    its own code and pushed a clean card-feed status, so both scheduled main
    runs after it skipped (success, no artifact). Main's last carrier is 10-07."""
    branch_state = _gameday_state(tmp_path / "a9002", built_on=FEATURE,
                                  day="2026-10-08", ledger_rows=6)
    main_state = _gameday_state(tmp_path / "a9001", built_on="main",
                                day="2026-10-07", ledger_rows=5)
    return [
        _run(9004, workflow="gameday-refresh.yml"),
        _run(9003, workflow="gameday-refresh.yml"),
        _run(9002, workflow="gameday-refresh.yml", branch=FEATURE,
             event="workflow_dispatch", artifacts={
                 "gameday-state": branch_state,
                 "gameday-reports": _gameday_reports(tmp_path / "r9002",
                                                     built_on=FEATURE)}),
        _run(9001, workflow="gameday-refresh.yml", artifacts={
            "gameday-state": main_state,
            "gameday-reports": _gameday_reports(tmp_path / "r9001", built_on="main")}),
    ]


def test_the_next_gameday_run_does_not_start_from_a_branch_dispatch(
    tmp_path: Path,
) -> None:
    block = _step("gameday-refresh.yml", "Restore the previous state")

    work, out = _run_step(tmp_path, block, _gameday_history(tmp_path))

    data = work / "data"
    assert _snapshots(data) == ["2026-10-07.csv"], (
        "the branch's 10-08 snapshot would stand as the day's first opinion"
    )
    assert _ledger(data) == [f"2026-10-{i + 1:02d},main" for i in range(5)]
    assert json.loads((work / "previous_card.json").read_text())["built_on"] == "main"
    assert "9002" not in _downloaded(tmp_path)
    assert "gameday-refresh.yml run 9001" in out, out


def test_publish_site_does_not_publish_a_branch_dispatchs_board(tmp_path: Path) -> None:
    history = _gameday_history(tmp_path)
    site = tmp_path / "a8001"
    site.mkdir()
    (site / "index.json").write_text('{"dates": []}', encoding="utf-8")
    history.append(_run(8001, workflow="publish-site.yml",
                        artifacts={"site-history": site}))
    # #175 split this step: the lab's state, then the site's history (which
    # restore_state.py also reads from main only). The board is built from
    # the first.
    block = _step("publish-site.yml", "Restore the lab's latest state")

    work, _ = _run_step(tmp_path, block, history)

    outputs = work / "data" / "outputs"
    assert (outputs / "gameday_card.md").read_text() == "card built on main"
    assert json.loads((outputs / "gameday_card.json").read_text())["built_on"] == "main"
    assert _snapshots(work / "data") == ["2026-10-07.csv"]


# --------------------------------------------------------------------------
# Each half of the filter, with the other unable to do its work.
# --------------------------------------------------------------------------

def test_branch_runs_cannot_crowd_main_out_of_the_listing(tmp_path: Path) -> None:
    """`--limit` counts what `gh` returns. Filtered only after listing, a
    burst of branch dispatches pushes every main carrier out of the window
    and the run starts cold; filtered by `gh`, the window is main's."""
    registry = [
        _run(9100 + n, workflow="gameday-refresh.yml", branch=f"{FEATURE}-{n}",
             event="workflow_dispatch", artifacts={"gameday-state": _gameday_state(
                 tmp_path / f"a{9100 + n}", built_on=FEATURE, day="2026-10-08",
                 ledger_rows=6)})
        for n in (4, 3, 2)
    ]
    registry.append(_run(9101, workflow="gameday-refresh.yml", artifacts={
        "gameday-state": _gameday_state(tmp_path / "a9101", built_on="main",
                                        day="2026-10-07", ledger_rows=5)}))

    dest, out = _script(tmp_path, registry, "--artifact", "gameday-state",
                        "--workflow", "gameday-refresh.yml", "--limit", "3")

    assert _snapshots(dest) == ["2026-10-07.csv"], out
    assert _ledger(dest) == [f"2026-10-{i + 1:02d},main" for i in range(5)]


def test_a_gh_that_ignores_the_branch_filter_still_cannot_leak_a_branch_run(
    tmp_path: Path,
) -> None:
    """The run's own `headBranch` is checked as well, so the restore does not
    rest on one flag it cannot see honoured. Main's carrier here is a manual
    dispatch, as all 11 real Gameday Refresh runs are: a manual run of
    reviewed code is a legitimate source; the branch is what disqualifies."""
    registry = [
        _run(9202, workflow="gameday-refresh.yml", branch=FEATURE,
             event="workflow_dispatch", artifacts={"gameday-state": _gameday_state(
                 tmp_path / "a9202", built_on=FEATURE, day="2026-10-08",
                 ledger_rows=6)}),
        _run(9201, workflow="gameday-refresh.yml", event="workflow_dispatch",
             artifacts={"gameday-state": _gameday_state(
                 tmp_path / "a9201", built_on="main", day="2026-10-07",
                 ledger_rows=5)}),
    ]

    dest, out = _script(tmp_path, registry, "--artifact", "gameday-state",
                        "--workflow", "gameday-refresh.yml", ignores_branch=True)

    assert _snapshots(dest) == ["2026-10-07.csv"], out
    assert _ledger(dest) == [f"2026-10-{i + 1:02d},main" for i in range(5)]
    assert "9202" not in _downloaded(tmp_path)
    assert "::warning::" in out and FEATURE in out, out


# --------------------------------------------------------------------------
# The older carriers are main's too: the union and the fill underneath.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ignores_branch", [False, True], ids=["gh-filters", "gh-ignores"])
def test_the_union_never_folds_in_a_branch_runs_rows(
    tmp_path: Path, ignores_branch: bool,
) -> None:
    header = "captured_at,built_on"
    registry = [
        _run(9303, workflow="line-movement.yml", artifacts={"line-movement": _captures(
            tmp_path / "a9303", {"deployment/2026-10-15.csv": [
                header, "2026-10-15T21:00:00+00:00,main"]})}),
        _run(9302, workflow="line-movement.yml", branch=FEATURE,
             event="workflow_dispatch", artifacts={"line-movement": _captures(
                 tmp_path / "a9302", {"deployment/2026-10-15.csv": [
                     header, "2026-10-15T18:00:00+00:00," + FEATURE]})}),
        _run(9301, workflow="line-movement.yml", artifacts={"line-movement": _captures(
            tmp_path / "a9301", {"deployment/2026-10-15.csv": [
                header, "2026-10-15T14:00:00+00:00,main"]})}),
    ]

    dest, out = _script(tmp_path, registry, "--artifact", "line-movement",
                        "--workflow", "line-movement.yml", "--union", "3",
                        ignores_branch=ignores_branch)

    assert (dest / "deployment" / "2026-10-15.csv").read_text().splitlines() == [
        header, "2026-10-15T14:00:00+00:00,main", "2026-10-15T21:00:00+00:00,main",
    ], out
    assert "9302" not in _downloaded(tmp_path)


@pytest.mark.parametrize("ignores_branch", [False, True], ids=["gh-filters", "gh-ignores"])
def test_a_red_main_run_is_filled_from_main_not_from_a_branch(
    tmp_path: Path, ignores_branch: bool,
) -> None:
    """The last success laid under a red run, and the longer ledger kept:
    a branch run's longer ledger is not main's, however long it is."""
    registry = [
        _run(9403, workflow="gameday-refresh.yml", conclusion="failure",
             artifacts={"gameday-state": _gameday_state(
                 tmp_path / "a9403", built_on="main", day="2026-10-09",
                 ledger_rows=2)}),
        _run(9402, workflow="gameday-refresh.yml", branch=FEATURE,
             event="workflow_dispatch", artifacts={"gameday-state": _gameday_state(
                 tmp_path / "a9402", built_on=FEATURE, day="2026-10-08",
                 ledger_rows=50)}),
        _run(9401, workflow="gameday-refresh.yml", artifacts={
            "gameday-state": _gameday_state(tmp_path / "a9401", built_on="main",
                                            day="2026-10-07", ledger_rows=40)}),
    ]

    dest, out = _script(tmp_path, registry, "--artifact", "gameday-state",
                        "--workflow", "gameday-refresh.yml",
                        ignores_branch=ignores_branch)

    assert _snapshots(dest) == ["2026-10-07.csv", "2026-10-09.csv"], out
    assert _ledger(dest) == [f"2026-10-{i + 1:02d},main" for i in range(40)]
    assert "run 9401 (success) underneath" in out, out
