"""CLV scored yesterday's capture store when today's fetch failed.

Gameday Refresh restores the `gameday-state` artifact before it does anything
else, and that artifact uploads `data/processed` whole. So the capture store
the previous run fetched from the `closing-lines` branch,
`data/processed/closing_line_captures.csv`, is already on disk when "Report
closing-line value" starts. That step fetched the branch and, when the fetch
did not succeed, printed "No capture store yet" and ran the report anyway.
A fetch that FAILED (the network, the token, GitHub itself) took the same
branch as a branch that does not exist, and the report then scored the
restored store as if it were today's, with nothing in the run saying so.
Confirmed on main d0cc593.

The step now removes any restored store before it looks at the branch, so
the report reads only what this run fetched, and it tells three states
apart:

* the branch does not exist: nothing to read, and not a fault. Closing Lines
  is disabled by the owner as of 2026-09-25, so this is the expected state
  and must stay a clean run;
* the branch could not be reached, or exists and could not be read: a fault,
  written to `run_degraded.txt` like every other fault the run records, so
  the run is degraded and the comment says what went wrong;
* the branch was read: the report scores exactly the branch's store.

These tests run the step's own `run:` block from the workflow under
`bash -eo pipefail`, with real git against a local bare repository standing
in for GitHub, and a `python` stub that records what store the report would
have read.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.closing_lines import CAPTURES_FILENAME
from nhl_betting_lab.config import PROJECT_ROOT


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
STEP = "Report closing-line value"
REPO = "o/r"
REMOTE = f"https://x-access-token:x@github.com/{REPO}"

STALE = "captured_at\nyesterday's store, restored from gameday-state\n"
TODAY = "captured_at\ntoday's store, on the closing-lines branch\n"
NOT_READ = "<no store on disk>"


def _block() -> str:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    (step,) = [
        step for job in jobs.values() for step in job.get("steps", [])
        if step.get("name") == STEP
    ]
    block = step["run"].replace("${{ github.repository }}", REPO)
    assert "${{" not in block, "the step reads an expression this test does not supply"
    return block


def _git(args: list[str], cwd: Path, env: dict, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, **kw)


@pytest.fixture
def rig(tmp_path: Path) -> dict:
    if not (shutil.which("git") and shutil.which("bash")):
        pytest.fail("this test needs git and bash, which every runner here has")
    bare, bin_dir, home, work = (
        tmp_path / d for d in ("remote.git", "bin", "home", "work")
    )
    for d in (bin_dir, home, work / "data" / "processed"):
        d.mkdir(parents=True)
    # The report itself is the stub: it records the store it would read.
    python = bin_dir / "python"
    python.write_text(
        "#!/bin/sh\n"
        f'if [ -f data/processed/{CAPTURES_FILENAME} ]; then\n'
        f'  cat data/processed/{CAPTURES_FILENAME} > report_read.txt\n'
        f'else echo "{NOT_READ}" > report_read.txt; fi\n'
    )
    python.chmod(python.stat().st_mode | stat.S_IEXEC)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.file://{bare}.insteadOf",
        "GIT_CONFIG_VALUE_0": REMOTE,
        "GH_TOKEN": "x",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    _git(["init", "-q", "--bare", str(bare)], tmp_path, env)
    _git(["init", "-q"], work, env)
    # What the restore of gameday-state left: the previous run's store.
    (work / "data" / "processed" / CAPTURES_FILENAME).write_text(STALE, encoding="utf-8")
    (work / "run_degraded.txt").write_text("", encoding="utf-8")
    return {"root": tmp_path, "bare": bare, "bin": bin_dir, "work": work, "env": env}


def _publish_branch(rig: dict, files: dict[str, str]) -> None:
    """A closing-lines branch holding `files`, pushed the way Closing Lines
    pushes it: a plumbing commit on a tree of its own."""
    seed = rig["root"] / "seed"
    seed.mkdir()
    env = rig["env"]
    _git(["init", "-q"], seed, env)
    lines = []
    for name, body in files.items():
        blob = _git(["hash-object", "-w", "--stdin"], seed, env,
                    input=body.encode()).stdout.decode().strip()
        lines.append(f"100644 blob {blob}\t{name}\n")
    tree = _git(["mktree"], seed, env, input="".join(lines).encode()).stdout.decode().strip()
    commit = _git(["commit-tree", tree, "-m", "captures"], seed, env).stdout.decode().strip()
    _git(["push", "-q", str(rig["bare"]), f"{commit}:refs/heads/closing-lines"], seed, env)


def _unreachable(rig: dict) -> None:
    """GitHub cannot be reached: every remote operation fails."""
    shutil.rmtree(rig["bare"])


def _fetch_fails(rig: dict) -> None:
    """The branch is listed, and then the fetch of it fails."""
    real = shutil.which("git", path=os.environ["PATH"])
    wrapper = rig["bin"] / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = fetch ]; then echo "fatal: the remote hung up" >&2; exit 128; fi\n'
        f'exec "{real}" "$@"\n'
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)


def _step(rig: dict) -> tuple[subprocess.CompletedProcess, str, str]:
    work = rig["work"]
    done = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _block()],
        cwd=work, env=rig["env"], capture_output=True, text=True,
    )
    read = (work / "report_read.txt").read_text(encoding="utf-8") \
        if (work / "report_read.txt").is_file() else "<the report never ran>"
    degraded = (work / "run_degraded.txt").read_text(encoding="utf-8")
    return done, read, degraded


def test_no_branch_is_a_clean_run_that_reads_no_store(rig) -> None:
    """Closing Lines is disabled, so the branch is absent: the expected
    state. The report reads nothing, not the restored store, and the run
    is not degraded."""
    done, read, degraded = _step(rig)

    assert done.returncode == 0, done.stderr
    assert read == f"{NOT_READ}\n"
    assert degraded == ""
    assert "No capture store yet" in done.stdout


def test_the_branch_is_read_in_place_of_the_restored_store(rig) -> None:
    _publish_branch(rig, {CAPTURES_FILENAME: TODAY})

    done, read, degraded = _step(rig)

    assert done.returncode == 0, done.stderr
    assert read == TODAY
    assert degraded == ""


@pytest.mark.parametrize(
    "fault",
    [
        pytest.param(_unreachable, id="github-unreachable"),
        pytest.param(_fetch_fails, id="branch-listed-then-fetch-fails"),
        pytest.param(lambda rig: _publish_branch(rig, {"other.csv": "x\n"}),
                     id="branch-without-a-store"),
    ],
)
def test_a_failed_fetch_is_a_degraded_run_that_reads_no_store(rig, fault) -> None:
    """The finding: a fetch that fails is not "no store yet". The report
    must not score yesterday's store, and the run says what went wrong."""
    if fault is _fetch_fails:
        _publish_branch(rig, {CAPTURES_FILENAME: TODAY})
    fault(rig)

    done, read, degraded = _step(rig)

    assert done.returncode == 0, done.stderr
    assert read == f"{NOT_READ}\n", "the report scored a store this run did not fetch"
    assert "closing-lines" in degraded and len(degraded.splitlines()) == 1, degraded
    assert "No capture store yet" not in done.stdout
