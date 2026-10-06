"""A run dispatched on a feature branch was a restore source for main.

`scripts/restore_state.py` chose its source with `gh run list --workflow W
--limit N --json databaseId,conclusion,status` and kept every completed run.
It passed no `--branch` and never asked for `headBranch`, so the newest
carrier on ANY branch became the state main's next run started from. Found
by the failure-shape audit and confirmed by two of three refuters. It now
asks `gh` for `--branch main` and checks each run's own `headBranch` too.

On real data it was already set to happen. On 2026-09-25 Line Movement's only
unexpired `line-movement` artifact was run 33691822845's, a
`workflow_dispatch` on branch `rehearse-the-line-fetch` (2026-09-02, one file,
`line_combinations/2026-09-02.csv`); the two main runs before it carried
none, so the first scheduled run would have seeded the season's capture chain
from the rehearsal. On the Gameday chain a branch dispatch's `gameday-state`
became main's next starting state: its snapshot stood as the day's first
opinion in the forward ledger, and Publish Site froze the public board from
it. Historical Props Purchase and Experiment Refresh restore through the same
function, and still do.

STAGE TWO (2026-10-05). Line Movement no longer restores from any public
artifact and no longer calls restore_state.py. "Restore today's captures"
pulls the chain from branch `movement` of the private repository, which only
default-branch rounds write ("Keep the captures privately" is gated on the
default branch; tests/test_the_movement_chain_is_kept_privately.py pins that
condition, this file does not), then unseals every unexpired
`line-movement-sealed-*` artifact, which `private_movement_chain.list_sealed`
takes only from runs whose `head_branch` is main (NHL_DEFAULT_BRANCH, when
set, names another) and whose `repository_id` and `head_repository_id` are
both present and equal. So the rehearsal's public artifact is never asked
for, and a sealed round from a branch is never folded in. The seal step never
runs on a branch (it runs only when the push or the check failed, and both
are skipped there; this file does not evaluate those `if:`s), so a
branch-sealed artifact takes a branch whose workflow was edited. The scenario
plants one, two rounds whose run names no branch (`head_branch` null, and
the key missing altogether) and a fork's round that calls its branch main;
each fails one check and passes the others. Beside them is a main round that
must come back, so no check can pass by folding in nothing. The restore runs with the
env GitHub would give it, the workflow's and the job's `env:` beneath the
step's own, so an NHL_DEFAULT_BRANCH set at any level reaches it.
restore_state.py's `--union` has no workflow caller since stage two; its
branch checks are still run here because the option is still in the script.

These tests run the real scripts, and the steps themselves taken from the
workflow files under `bash --noprofile --norc -eo pipefail`, against an
offline `gh` that honours `--branch`, `--json`, `--status`, `--limit`, the one
`--jq` each call uses, and the two artifact endpoints `unseal` asks. One
scenario runs a `gh` that ignores `--branch`, so restore_state.py's
client-side check is exercised on its own. The private repository is a local
bare repository reached through git's `url.<base>.insteadOf`, under
`GIT_ALLOW_PROTOCOL=file`, so a URL the redirect misses fails instead of
reaching GitHub. A sealed round is made by the workflow's own seal step and
zipped under the name, and in the layout, its upload step gives it; the seal
step lists the private tip with the chain token, so it runs under the same
redirect.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT


SCRIPT = PROJECT_ROOT / "scripts" / "restore_state.py"
WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"

#: The real Line Movement run history on 2026-09-25, newest first.
REHEARSAL = 33691822845  # rehearse-the-line-fetch, workflow_dispatch, carries it
REHEARSAL_BRANCH = "rehearse-the-line-fetch"
MAIN_BEFORE_IT = (33691644979, 33252075234)  # main, workflow_dispatch, no artifact

FEATURE = "try-new-edge-bar"

#: What a step's `${{ }}` expressions stand for in these replays.
REPOSITORY = "owner/nhl-betting-lab"
CHAIN_TOKEN = "not-a-token"
#: At least private_movement_chain.MIN_KEY_CHARS (32), or seal and unseal
#: refuse it before anything is sealed or opened.
FALLBACK_KEY = "a-test-key-and-not-coopers-padded-to-39"
EXPRESSIONS = {
    "github.repository": REPOSITORY,
    "github.token": "not-a-token",
    "secrets.NHL_CLOSING_LINES_TOKEN": CHAIN_TOKEN,
    "secrets.NHL_CHAIN_FALLBACK_KEY": FALLBACK_KEY,
}
#: The private repository's remote as the chain script builds it from the
#: token; the scenarios redirect exactly this to a local bare repository.
CHAIN_REMOTE = (f"https://x-access-token:{CHAIN_TOKEN}@github.com/"
                "cooperross399/nhl-closing-lines.git")
GIT_ISOLATION = {
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}

LM_RESTORE = "Restore today's captures"
LM_SEAL = "Seal this round when the private chain did not take it"
LM_KEEP_SEALED = "Keep the sealed round"

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
if args[:1] == ["api"]:
    # The two calls private_movement_chain.unseal makes: the repository's
    # artifact listing, one JSON object per line, and one artifact's zip.
    path = [a for a in args[1:] if a != "--paginate"][0]
    artifacts = json.loads(Path(os.environ["FAKE_GH_ARTIFACTS"]).read_text())
    prefix = "repos/" + os.environ["FAKE_GH_REPO"] + "/actions/artifacts"
    jq = value("--jq")
    if path == prefix + "?per_page=100" and jq == ".artifacts[]":
        for item in artifacts:
            print(json.dumps({{k: v for k, v in item.items() if k != "zip"}}))
        sys.exit(0)
    if path.startswith(prefix + "/") and path.endswith("/zip") and jq is None:
        wanted = path[len(prefix) + 1:-len("/zip")]
        item = next((a for a in artifacts if str(a["id"]) == wanted), None)
        if item is None:
            print("gh: Not Found (HTTP 404)", file=sys.stderr)
            sys.exit(1)
        sys.stdout.buffer.write(Path(item["zip"]).read_bytes())
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


def _env(tmp_path: Path, registry: list[dict], *, ignores_branch: bool = False,
         artifacts: list[dict] | None = None, real_git: bool = False) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    # The Gameday restore reads card-feed only when no ledger came back; a
    # git that answers nothing keeps that fallback out of these scenarios.
    # The private chain is read with git itself, so its scenarios keep it.
    git = bin_dir / "git"
    if real_git:
        git.unlink(missing_ok=True)
    else:
        git.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        git.chmod(git.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (tmp_path / "artifacts.json").write_text(json.dumps(artifacts or []), encoding="utf-8")
    return {
        # The default branch the scripts honour is the workflow's to set
        # (`_step_env`), never this shell's.
        **{k: v for k, v in os.environ.items() if k != "NHL_DEFAULT_BRANCH"},
        "PATH": f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
        "GH_TOKEN": "not-a-token",
        "FAKE_GH_REGISTRY": str(tmp_path / "registry.json"),
        "FAKE_GH_ARTIFACTS": str(tmp_path / "artifacts.json"),
        "FAKE_GH_REPO": REPOSITORY,
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


def _located(workflow: str, name: str) -> tuple[dict, dict, dict]:
    """The workflow, the job holding the step named `name`, and the step."""
    document = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    found = [
        (document, job, step) for job in document["jobs"].values()
        for step in job.get("steps", []) if step.get("name") == name
    ]
    assert len(found) == 1, f"exactly one step named {name!r} in {workflow}"
    return found[0]


def _step_node(workflow: str, name: str) -> dict:
    return _located(workflow, name)[2]


def _expand(text: str, name: str, values: dict[str, str] | None = None) -> str:
    for expression, value in {**EXPRESSIONS, **(values or {})}.items():
        text = text.replace("${{ " + expression + " }}", value)
    assert "${{" not in text, f"an unstubbed expression is left in {name!r}: {text}"
    return text


def _step(workflow: str, name: str) -> str:
    return _expand(_step_node(workflow, name)["run"], name)


def _step_env(workflow: str, name: str) -> dict[str, str]:
    """The env the step runs with, as GitHub builds it: the workflow's
    `env:`, then its job's, then the step's own, each overriding the one
    before; secrets and tokens stood in for. Reading the step's alone missed
    an NHL_DEFAULT_BRANCH set on the job, which would point list_sealed at
    another branch's sealed rounds in every round."""
    document, job, step = _located(workflow, name)
    env = {**(document.get("env") or {}), **(job.get("env") or {}),
           **(step.get("env") or {})}
    return {key: _expand(str(value), name) for key, value in env.items()}


def _run_step(tmp_path: Path, block: str, registry: list[dict]) -> tuple[Path, str]:
    """The step's own run block, as the runner runs it, in a fresh checkout."""
    work = tmp_path / "work"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts" / "restore_state.py").write_text(
        SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return work, _bash(block, work, _env(tmp_path, registry)).stdout


def _bash(block: str, work: Path, env: dict) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=work, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _gh_calls(tmp_path: Path) -> list[str]:
    return (tmp_path / "gh.log").read_text(encoding="utf-8").splitlines()


def _downloaded(tmp_path: Path) -> list[str]:
    return [line.split()[2] for line in _gh_calls(tmp_path)
            if line.startswith("run download ")]


def _ledger(dest: Path) -> list[str]:
    path = dest / "processed" / "forward_evidence.csv"
    return path.read_text(encoding="utf-8").splitlines()[1:]


def _snapshots(dest: Path) -> list[str]:
    return sorted(p.name for p in (dest / "archive" / "priced_snapshots").iterdir())


# --------------------------------------------------------------------------
# The real Line Movement history: the rehearsal must not seed the season.
# --------------------------------------------------------------------------

REHEARSAL_LINES = {
    "line_combinations/2026-09-02.csv": [
        "team,player,group,source",
        "TOR,Auston Matthews,F1,2026 Offseason (Projected)",
        "TOR,Matthew Knies,F1,2026 Offseason (Projected)",
    ],
}

MOVEMENT_DAY = "line_movement/2026-10-04.csv"
UNITS_DAY = "line_combinations/2026-10-04.csv"
MOVEMENT_HEADER = "date,provider_event_id,market,selection,line,american_odds,book,captured_at"


def _movement(captured_at: str, book: str = "BetMGM") -> str:
    return f"2026-10-04,ev1,player_points,over,0.5,-110,{book},{captured_at}"


UNITS = ["team,player,group,source", "TOR,Auston Matthews,F1,Daily Faceoff"]
EARLIER = [_movement("2026-10-04T14:00:00Z"), _movement("2026-10-04T18:00:00Z")]
#: Main's 21:00 round, whose private push failed: what it restored, plus its
#: own row, sealed.
MAIN_SEALED = {
    MOVEMENT_DAY: [MOVEMENT_HEADER, *EARLIER, _movement("2026-10-04T21:00:00Z")],
    UNITS_DAY: UNITS,
}
#: Branch `movement` of the private repository after main's 23:00 round,
#: which could not list the sealed rounds and so pushed without the 21:00
#: one. Each source then holds a row the other lacks.
MAIN_CHAIN = {
    MOVEMENT_DAY: [MOVEMENT_HEADER, *EARLIER, _movement("2026-10-04T23:00:00Z")],
    UNITS_DAY: UNITS,
}
#: A round sealed on the rehearsal branch, by a workflow edited to seal there.
BRANCH_SEALED = {
    MOVEMENT_DAY: [MOVEMENT_HEADER, *EARLIER,
                   _movement("2026-10-04T22:30:00Z", book=REHEARSAL_BRANCH)],
    **REHEARSAL_LINES,
}
#: Main's every round, in capture order, and nothing of the branch's.
MAIN_RESTORED = [MOVEMENT_HEADER, *EARLIER, _movement("2026-10-04T21:00:00Z"),
                 _movement("2026-10-04T23:00:00Z")]

#: A sealed round's run, as GitHub's artifacts API lists it, when main's own
#: code in this repository uploaded it.
MAIN_RUN = {"head_branch": "main", "repository_id": 1, "head_repository_id": 1}
#: Sealed rounds list_sealed must leave out. Each fails one of its checks and
#: passes the others, so each check is exercised on its own.
REFUSED_RUNS = {
    # Another branch: a workflow edited to seal on the rehearsal branch.
    REHEARSAL_BRANCH: {**MAIN_RUN, "head_branch": REHEARSAL_BRANCH},
    # No branch: GitHub's null, and the key missing altogether.
    "branch-null": {**MAIN_RUN, "head_branch": None},
    "branch-key-missing": {k: v for k, v in MAIN_RUN.items() if k != "head_branch"},
    # A fork's pull request, run in this repository's context from a branch
    # it calls main: the code is the fork's.
    "fork-calls-it-main": {**MAIN_RUN, "head_repository_id": 2},
}


def _refused_rows(label: str, minute: int) -> dict[str, list[str]]:
    """What a refused round sealed: the day as main had it, plus a row of
    its own, booked under its label, so a fold of it shows on disk."""
    if label == REHEARSAL_BRANCH:
        return BRANCH_SEALED
    return {MOVEMENT_DAY: [MOVEMENT_HEADER, *EARLIER,
                           _movement(f"2026-10-04T22:{minute:02d}:00Z", book=label)]}


def _line_movement_history(tmp_path: Path) -> list[dict]:
    rehearsal = _captures(tmp_path / "a-rehearsal", REHEARSAL_LINES)
    return [
        _run(REHEARSAL, workflow="line-movement.yml", branch=REHEARSAL_BRANCH,
             event="workflow_dispatch", artifacts={"line-movement": rehearsal}),
        *(_run(run_id, workflow="line-movement.yml", event="workflow_dispatch")
          for run_id in MAIN_BEFORE_IT),
    ]


def _git(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                   env={**os.environ, **GIT_ISOLATION})


def _private_chain(tmp_path: Path, rows: dict[str, list[str]]) -> Path:
    """A local bare repository standing in for the private one, holding
    `rows` on branch `movement`: the chain exists, as it has since
    2026-10-02 (a missing branch is a fault, which these scenarios are not
    about)."""
    bare = tmp_path / "nhl-closing-lines.git"
    _git(["init", "-q", "--bare", "-b", "main", str(bare)])
    seed = _captures(tmp_path / "chain-seed", rows)
    _git(["init", "-q", "-b", "movement"], cwd=seed)
    _git(["add", "-A"], cwd=seed)
    _git(["commit", "-qm", "main's rounds"], cwd=seed)
    _git(["push", "-q", str(bare), "movement:refs/heads/movement"], cwd=seed)
    return bare


def _chain_redirect(bare: Path) -> dict[str, str]:
    """The private repository is the bare one; any other URL is refused by
    git before it leaves the machine."""
    return {
        **GIT_ISOLATION,
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.file://{bare}.insteadOf",
        "GIT_CONFIG_VALUE_0": CHAIN_REMOTE,
    }


def _line_movement_checkout(work: Path) -> Path:
    """A checkout as Line Movement's steps see it: scripts/ and src/ (the
    steps set PYTHONPATH=src) at the paths they name them by."""
    work.mkdir(parents=True)
    (work / "scripts").symlink_to(PROJECT_ROOT / "scripts", target_is_directory=True)
    (work / "src").symlink_to(PROJECT_ROOT / "src", target_is_directory=True)
    return work


def _sealed_round(tmp_path: Path, bare: Path, *, artifact_id: int, run_id: int,
                  workflow_run: dict, rows: dict[str, list[str]],
                  created_at: str) -> dict:
    """A round sealed by the workflow's own seal step, zipped under the name
    and in the layout its upload step gives it (one file, rooted at its own
    folder), listed as GitHub's artifacts API lists it, its run's fields
    `workflow_run`. The seal step lists the private tip with the chain token
    to leave out what is already home, so it reads `bare` and nothing else."""
    home = tmp_path / f"run-{run_id}"
    work = _line_movement_checkout(home / "work")
    _captures(work / "data" / "processed", rows)
    runner_temp = home / "runner-temp"
    _bash(_step("line-movement.yml", LM_SEAL), work, {
        **{k: v for k, v in os.environ.items() if k != "NHL_DEFAULT_BRANCH"},
        "PATH": f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
        "PYTHONDONTWRITEBYTECODE": "1",
        **_step_env("line-movement.yml", LM_SEAL),
        **_chain_redirect(bare),
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_WORKSPACE": str(work),
    })
    upload = _step_node("line-movement.yml", LM_KEEP_SEALED)["with"]
    values = {"github.run_attempt": "1", "runner.temp": str(runner_temp)}
    sealed = Path(_expand(upload["path"], LM_KEEP_SEALED, values))
    archive = home / "artifact.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.write(sealed, arcname=sealed.name)
    return {
        "id": artifact_id, "name": _expand(upload["name"], LM_KEEP_SEALED, values),
        "expired": False, "created_at": created_at,
        "workflow_run": {"id": run_id, **workflow_run},
        "zip": str(archive),
    }


def test_the_branch_rehearsal_does_not_seed_the_seasons_capture_chain(
    tmp_path: Path,
) -> None:
    """Line Movement's own restore step, with the rehearsal's public artifact
    still on GitHub, main's rounds on the private chain, and five sealed
    rounds: main's 21:00, whose push failed, then one from the rehearsal
    branch, two whose run names no branch, and a fork's that calls its
    branch main. Main's chain and main's sealed round both come back;
    nothing of the other four does (not one of them is even downloaded), and
    no public run artifact is asked for."""
    bare = _private_chain(tmp_path, MAIN_CHAIN)
    main_round = _sealed_round(tmp_path, bare, artifact_id=4101, run_id=9601,
                               workflow_run=MAIN_RUN, rows=MAIN_SEALED,
                               created_at="2026-10-05T01:10:00Z")
    refused = {
        label: _sealed_round(tmp_path, bare, artifact_id=4102 + n, run_id=9602 + n,
                             workflow_run=run, rows=_refused_rows(label, 30 + 5 * n),
                             created_at=f"2026-10-05T02:{30 + 5 * n:02d}:00Z")
        for n, (label, run) in enumerate(REFUSED_RUNS.items())
    }
    work = _line_movement_checkout(tmp_path / "work")
    env = {
        **_env(tmp_path, _line_movement_history(tmp_path),
               artifacts=[main_round, *refused.values()], real_git=True),
        **_step_env("line-movement.yml", LM_RESTORE),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_WORKSPACE": str(work),
        **_chain_redirect(bare),
    }

    result = _bash(_step("line-movement.yml", LM_RESTORE), work, env)

    processed = work / "data" / "processed"
    out = result.stdout + result.stderr
    assert not (processed / "line_combinations" / "2026-09-02.csv").exists(), (
        "the rehearse-the-line-fetch capture was restored into main's chain\n" + out
    )
    assert (work / "restore_problem.txt").read_text(encoding="utf-8") == "", out
    assert (processed / UNITS_DAY).read_text().splitlines() == UNITS, out
    assert (processed / MOVEMENT_DAY).read_text().splitlines() == MAIN_RESTORED, (
        "main's chain with main's sealed 21:00 round folded in, and no row of a "
        "refused round\n" + out
    )
    calls = _gh_calls(tmp_path)
    assert not [call for call in calls if call.startswith("run ")], (
        f"the restore asked for a public run artifact: {calls}"
    )
    downloaded = [label for label, artifact in refused.items()
                  if f"api repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip" in calls]
    assert downloaded == [], f"sealed rounds list_sealed should have left out: {downloaded}"
    assert f"api repos/{REPOSITORY}/actions/artifacts/{main_round['id']}/zip" in calls


def test_the_rehearsal_is_restored_only_when_its_branch_is_asked_for(
    tmp_path: Path,
) -> None:
    """restore_state.py still reaches a branch's artifact on purpose: naming
    its branch takes it, so its default refusal (the scenarios below) is the
    filter's doing, not an artifact the script cannot read. No workflow
    restores Line Movement with it since stage two."""
    dest, out = _script(
        tmp_path, _line_movement_history(tmp_path), "--artifact", "line-movement",
        "--workflow", "line-movement.yml", "--union", "3",
        "--branch", REHEARSAL_BRANCH,
    )

    assert (dest / "line_combinations" / "2026-09-02.csv").is_file()
    assert f"run {REHEARSAL}" in out and REHEARSAL_BRANCH in out


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
