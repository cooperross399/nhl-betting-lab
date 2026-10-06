"""A Line Movement run whose restore could not ask is a red run.

HISTORY. "Restore today's captures" once made one attempt at each call and
turned any failure into a `::warning::`. A failed `gh run list` started every
day file afresh and finished green, and three such runs in a row left every
earlier capture outside the union's window (sweep 5,
line-movement-three-thin-carriers-drop-the-season). It was then made to
retry, and to write what it still could not reach to `restore_problem.txt`,
which a gate at the end turns red.

STAGE TWO (2026-10-05). The chain's only home is branch `movement` of the
private repository, and the restore asks two things:
`private_movement_chain.py pull` (the chain: exit 0 folded in, anything else
a problem) and `unseal` (every unexpired `line-movement-sealed-N` round that
a failed push left sealed: anything but 0 a problem). Each problem becomes
one sentence in `restore_problem.txt`, which is emptied first. The gate,
placed after every step that keeps the round, turns that file, or a restore
that did not finish, into a red run.

A MISSING CHAIN IS A FAULT (4f2b1db). The pull's exit 4, the private
repository answering with no `movement` branch, was once "no chain yet" and
green. The chain has existed since 2026-10-02, so a missing branch now means
it was deleted or renamed, and the restore writes a sentence of its own for
it ("...has no movement branch..."). The push no longer creates the branch
either (it refuses without `--allow-new-chain`, which no workflow passes).
A branch that exists and holds no day file yet is still a clean pull (exit 0).

A thin restore does not by itself cost the chain anything, because a push
that succeeds merges into the private tip
(test_the_movement_chain_is_kept_privately.py). It is still red, because the
day's files and the ladder scan saw a thin chain. The restore's sentences
and its gate say nothing about the push: the restore is written before the
push runs, and whether the round reached the private chain is the next
gate's to say. A sealed copy that cannot be merged with the one on disk is
parked under data/processed/unmerged/, where the push keeps it, and is red.
A re-run is no longer a special case either. Its attempt 2 restores attempt
1's round like any later round does: from the chain if attempt 1 pushed it,
or from attempt 1's sealed artifact. The last replays below run the second
path from the seal step to the next restore. The offline `gh` lists every
artifact a test registers, so one thing is assumed here, not tested: that
GitHub's artifact listing shows attempt 1's artifact while attempt 2 of the
same run is still in progress.

HOW. The workflow's own restore step, seal step and gate run under bash. In
the replay's folder, `scripts/private_movement_chain.py` is a shim. It runs
the real script, with a local bare repository standing in for the private one
(passed as `--remote` to pull, seal and unseal, and only when the step gave
it a token, so a step that stops passing the token stops reaching the
stand-in) and an offline `gh` standing in for GitHub's artifact API. Or it
exits with a chosen code to drive the step's own branches. Git in a replay
may use local repositories only (`GIT_ALLOW_PROTOCOL=file`), so no step can
reach GitHub. Each step's `env:` block is that replay's environment, so a
test fails if a step stops passing a secret. The retries happen inside the
script (`fetch_chain`, `download_sealed`); the pull's are tested in-process,
the download's through the replay's `gh` log.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import private_movement_chain as movement_chain  # noqa: E402

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
REAL_SCRIPT = PROJECT_ROOT / "scripts" / "private_movement_chain.py"
RESTORE_STEP = "Restore today's captures"
SEAL_STEP = "Seal this round when the private chain did not take it"
SEALED_UPLOAD = "Keep the sealed round"
GATE = "Fail the run when the previous captures were not restored"
PROBLEM_FILE = "restore_problem.txt"
#: The opening words of the three sentences the restore step can write.
PULL_PROBLEM = "The private movement chain could not be restored"
MISSING_CHAIN = "The private repository has no movement branch."
UNSEAL_PROBLEM = "A sealed fallback round could not be folded in"
#: Seal and unseal refuse a key shorter than this (exit 5).
FALLBACK_KEY = "test-fallback-key-not-a-real-one-0123456789"
assert len(FALLBACK_KEY) >= movement_chain.MIN_KEY_CHARS

#: What the runner fills into the steps' `${{ }}` expressions. An unset
#: secret renders as the empty string.
SECRETS = {
    "secrets.NHL_CLOSING_LINES_TOKEN": "test-token-not-a-real-one",
    "secrets.NHL_CHAIN_FALLBACK_KEY": FALLBACK_KEY,
    "github.token": "test-github-token",
}

HEADER = ("date,commence_time,provider_event_id,home_team,away_team,market,player,"
          "selection,line,american_odds,book,fetched_at,captured_at\n")
LM = "line_movement/2026-10-15.csv"
DP = "deployment/2026-10-15.csv"
YESTERDAY_LM = "line_movement/2026-10-14.csv"


def _row(n: int) -> str:
    return (f"2026-10-15,2026-10-15T23:00:00Z,ev1,Toronto Maple Leafs,Boston Bruins,"
            f"player_points,P{n},over,0.5,{100 + n},BetMGM,2026-10-15T14:00:00Z,"
            f"2026-10-15T14:00:00Z\n")


FAKE_GH = r'''#!{python}
"""`gh api`, offline: lists and serves the artifacts a test registered."""
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
if not os.environ.get("GH_TOKEN"):
    print("gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN "
          "environment variable.", file=sys.stderr)
    sys.exit(4)
mode = os.environ.get("FAKE_GH_MODE", "")
if mode == "down":
    print("HTTP 502: Bad Gateway", file=sys.stderr)
    sys.exit(1)
artifacts = json.loads(Path(os.environ["FAKE_GH_ARTIFACTS"]).read_text())
path = next((a for a in args[1:] if a.startswith("repos/")), "")
if args[:1] == ["api"] and path.endswith("/actions/artifacts?per_page=100"):
    for item in artifacts:
        print(json.dumps(item["listing"]))
    sys.exit(0)
if args[:1] == ["api"] and path.endswith("/zip"):
    wanted = path.split("/")[-2]
    item = next((a for a in artifacts if str(a["listing"]["id"]) == wanted), None)
    if item is None or mode == "broken":
        print("HTTP 500: Internal Server Error", file=sys.stderr)
        sys.exit(1)
    sys.stdout.buffer.write(Path(item["zip"]).read_bytes())
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''

SHIM = r'''"""The real private_movement_chain.py, with the private repository's
stand-in as --remote for every command that reads the chain, when the step
gave it a token, and no pause between attempts; or the exit code a test
chose."""
import importlib.util, os, sys
args = sys.argv[1:]
with open(os.environ["SHIM_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
forced = os.environ.get("SHIM_EXIT_" + args[0].upper(), "")
if forced:
    sys.exit(int(forced))
sys.path.insert(0, {src!r})
spec = importlib.util.spec_from_file_location("private_movement_chain", {script!r})
real = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real)
real.sleep = lambda seconds: None
if args[0] in ("pull", "seal", "unseal") and os.environ.get("NHL_CLOSING_LINES_TOKEN", "").strip():
    args += ["--remote", os.environ["SHIM_REMOTE"]]
sys.exit(real.main(args))
'''


def _capture_steps() -> list[dict]:
    """The steps of the job that restores, in order."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = [job["steps"] for job in document["jobs"].values()
            if any(step.get("name") == RESTORE_STEP for step in job["steps"])]
    assert len(jobs) == 1, f"exactly one job runs {RESTORE_STEP!r}"
    return jobs[0]


def _step(name: str) -> dict:
    matches = [step for step in _capture_steps() if step.get("name") == name]
    assert len(matches) == 1, f"exactly one step named {name!r}"
    return matches[0]


def _render(text: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions a test names; refuse any it did not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, text)


def _bash(script: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    """A run block as GitHub runs it (`shell: bash`)."""
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


def _gate(work: Path, restore: str = "success") -> subprocess.CompletedProcess:
    """The gate's run block, with the restore step's outcome filled in."""
    script = _render(_step(GATE)["run"], {"steps.restore.outcome": restore})
    return _bash(script, work, dict(os.environ))


def _write(processed: Path, rel: str, body: str) -> None:
    path = processed / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


class Runner:
    """Runners on one machine: their folders, the private repository's
    stand-in, and the artifacts GitHub holds for the workflow."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            # Local repositories only: nothing in a replay may reach GitHub,
            # whatever remote a script builds from the fake token.
            "GIT_ALLOW_PROTOCOL": "file",
        }
        self.store = tmp_path / "store.git"
        self._git(["init", "-q", "--bare", "-b", "main", str(self.store)], tmp_path)
        self.remote = f"file://{self.store}"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.path = f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"
        self.gh_log = tmp_path / "gh.log"
        self.shim_log = tmp_path / "shim.log"
        self.gh_mode = ""
        self.forced: dict[str, int] = {}
        self.secrets = dict(SECRETS)
        self.artifacts: list[dict] = []
        self.count = 0
        self.log = ""

    def _git(self, args: list[str], cwd: Path) -> None:
        subprocess.run(["git", *args], cwd=cwd, env=self.git_env, check=True,
                       capture_output=True, text=True)

    def chain(self, files: dict[str, str]) -> None:
        """Make `files` the tip of the stand-in's `movement` branch."""
        seed = self.tmp / "seed"
        seed.mkdir()
        self._git(["init", "-q", "-b", "movement"], seed)
        for rel, body in files.items():
            _write(seed, rel, body)
        self._git(["add", "-A"], seed)
        self._git(["commit", "-qm", "earlier rounds"], seed)
        self._git(["push", "-q", str(self.store), "HEAD:refs/heads/movement"], seed)

    def workspace(self) -> Path:
        self.count += 1
        work = self.tmp / f"run{self.count}"
        (work / "scripts").mkdir(parents=True)
        (work / "scripts" / "private_movement_chain.py").write_text(
            SHIM.format(src=str(PROJECT_ROOT / "src"), script=str(REAL_SCRIPT)),
            encoding="utf-8",
        )
        return work

    def run_step(self, name: str, work: Path, temp: Path) -> subprocess.CompletedProcess:
        """One step's run block in `work`, its `env:` rendered as GitHub would."""
        step = _step(name)
        registry = self.tmp / "artifacts.json"
        registry.write_text(json.dumps(self.artifacts), encoding="utf-8")
        env = {key: value for key, value in self.git_env.items()
               if key not in ("NHL_CLOSING_LINES_TOKEN", "NHL_CHAIN_FALLBACK_KEY",
                              "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_STEP_SUMMARY",
                              "NHL_DEFAULT_BRANCH")
               and not key.startswith("SHIM_EXIT_")}
        env.update({
            "PATH": self.path,
            "GITHUB_REPOSITORY": "cooperross399/nhl-betting-lab",
            "GITHUB_WORKSPACE": str(work),
            "RUNNER_TEMP": str(temp),
            "FAKE_GH_LOG": str(self.gh_log),
            "FAKE_GH_MODE": self.gh_mode,
            "FAKE_GH_ARTIFACTS": str(registry),
            "SHIM_LOG": str(self.shim_log),
            "SHIM_REMOTE": self.remote,
        })
        env.update({f"SHIM_EXIT_{command.upper()}": str(code)
                    for command, code in self.forced.items()})
        env.update({key: _render(str(value), self.secrets)
                    for key, value in (step.get("env") or {}).items()})
        return _bash(step["run"], work, env)

    def restore(self, *, stale: str = "") -> Path:
        """A new runner's restore step. Returns its working directory."""
        work = self.workspace()
        if stale:
            (work / PROBLEM_FILE).write_text(stale, encoding="utf-8")
        temp = self.tmp / f"temp{self.count}"
        temp.mkdir()
        done = self.run_step(RESTORE_STEP, work, temp)
        self.log = done.stdout + done.stderr
        # `continue-on-error: true`: whatever it returned, the job goes on.
        return work

    def sealed_round(self, files: dict[str, str], attempt: str = "1") -> Path:
        """A round whose private push failed: the workflow's seal step seals
        it, and the sealed upload keeps it as upload-artifact would. Returns
        the sealed file the upload keeps."""
        work = self.workspace()
        for rel, body in files.items():
            _write(work / "data" / "processed", rel, body)
        temp = self.tmp / f"temp{self.count}"
        temp.mkdir()
        done = self.run_step(SEAL_STEP, work, temp)
        assert done.returncode == 0, done.stdout + done.stderr
        given = _step(SEALED_UPLOAD)["with"]
        values = {"github.run_attempt": attempt, "runner.temp": str(temp)}
        name = _render(str(given["name"]), values)
        kept = Path(_render(str(given["path"]), values))
        assert kept.is_file(), f"the upload keeps {kept}, which the seal step did not write"
        archive = self.tmp / f"{name}.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            # One file: the artifact roots at its folder.
            zipped.write(kept, arcname=kept.name)
        self.artifacts.append({"zip": str(archive), "listing": {
            "id": 7000 + len(self.artifacts), "name": name, "expired": False,
            "created_at": "2026-10-15T18:05:00Z",
            "workflow_run": {"id": 1001, "head_branch": "main", "repository_id": 1, "head_repository_id": 1},
        }})
        return kept

    def asked(self) -> list[str]:
        return _lines(self.shim_log) if self.shim_log.is_file() else []


@pytest.fixture
def runner(tmp_path: Path) -> Runner:
    return Runner(tmp_path)


def _problems(work: Path) -> list[str]:
    return _lines(work / PROBLEM_FILE)


# --------------------------------------------------------------------------
# What the restore could not ask is a red run.
# --------------------------------------------------------------------------

def _private_repository_unreachable(runner: Runner) -> None:
    runner.remote = f"file://{runner.tmp / 'nowhere.git'}"


def _no_token_for_the_private_repository(runner: Runner) -> None:
    runner.secrets["secrets.NHL_CLOSING_LINES_TOKEN"] = ""


def _artifact_api_down(runner: Runner) -> None:
    runner.gh_mode = "down"


def _sealed_round_will_not_download(runner: Runner) -> None:
    runner.sealed_round({LM: HEADER + _row(3)})
    runner.gh_mode = "broken"


def _sealed_round_without_its_key(runner: Runner) -> None:
    runner.sealed_round({LM: HEADER + _row(3)})
    runner.secrets["secrets.NHL_CHAIN_FALLBACK_KEY"] = ""


def _sealed_round_with_a_short_key(runner: Runner) -> None:
    """Sealed with the real key; the restore is given one too short to be it."""
    runner.sealed_round({LM: HEADER + _row(3)})
    runner.secrets["secrets.NHL_CHAIN_FALLBACK_KEY"] = FALLBACK_KEY[:movement_chain.MIN_KEY_CHARS - 1]


def _sealed_round_with_a_padded_key(runner: Runner) -> None:
    """The right key with a trailing newline, as a pasted secret can carry:
    openssl would read the newline as part of the key."""
    runner.sealed_round({LM: HEADER + _row(3)})
    runner.secrets["secrets.NHL_CHAIN_FALLBACK_KEY"] = FALLBACK_KEY + "\n"


@pytest.mark.parametrize(("fault", "sentence", "code"), [
    (_private_repository_unreachable, PULL_PROBLEM, movement_chain.EXIT_FAILED),
    (_no_token_for_the_private_repository, PULL_PROBLEM, movement_chain.EXIT_NO_TOKEN),
    (_artifact_api_down, UNSEAL_PROBLEM, movement_chain.EXIT_FAILED),
    (_sealed_round_will_not_download, UNSEAL_PROBLEM, movement_chain.EXIT_DAMAGED),
    (_sealed_round_without_its_key, UNSEAL_PROBLEM, movement_chain.EXIT_NO_TOKEN),
    (_sealed_round_with_a_short_key, UNSEAL_PROBLEM, movement_chain.EXIT_REFUSED),
    (_sealed_round_with_a_padded_key, UNSEAL_PROBLEM, movement_chain.EXIT_REFUSED),
], ids=["private-repo-unreachable", "no-token", "artifact-api-down",
        "sealed-round-will-not-download", "sealed-round-without-its-key",
        "sealed-round-with-a-short-key", "sealed-round-with-a-padded-key"])
def test_a_restore_that_could_not_ask_turns_the_run_red(
    runner: Runner, fault, sentence: str, code: int,
) -> None:
    """The sentence says what the restore could not do and nothing about the
    push: it is written before the push runs."""
    runner.chain({YESTERDAY_LM: HEADER + _row(1)})
    fault(runner)
    work = runner.restore()

    problems = _problems(work)
    assert len(problems) == 1, runner.log
    assert problems[0].startswith(sentence), problems
    assert f"(exit {code})" in problems[0], problems
    assert "merge" not in problems[0] and "push" not in problems[0], problems
    gate = _gate(work)
    assert gate.returncode != 0
    assert f"::error::{problems[0]}" in gate.stdout


def test_a_sealed_round_that_will_not_download_is_asked_for_three_times(
    runner: Runner,
) -> None:
    """`download_sealed` retries the zip like every other `gh` call, so one
    HTTP 500 does not leave the only copy of a round outside this restore.
    The replay's `gh` refuses every zip, so the log shows each ask."""
    runner.chain({YESTERDAY_LM: HEADER + _row(1)})
    _sealed_round_will_not_download(runner)
    work = runner.restore()

    zips = [line for line in _lines(runner.gh_log) if line.endswith("/zip")]
    assert len(zips) == movement_chain.GH_ATTEMPTS == 3, zips
    assert zips == ["api repos/cooperross399/nhl-betting-lab/actions/artifacts/7000/zip"] * 3
    assert _problems(work)[0].startswith(UNSEAL_PROBLEM)


def test_a_restore_that_reached_the_private_chain_leaves_the_run_green(
    runner: Runner,
) -> None:
    """The step passes the pull its token and unseal the run's token; the
    pull brings yesterday's day file back byte for byte."""
    runner.chain({YESTERDAY_LM: HEADER + _row(1) + _row(2)})
    work = runner.restore()

    restored = work / "data" / "processed" / YESTERDAY_LM
    assert restored.read_text(encoding="utf-8") == HEADER + _row(1) + _row(2), runner.log
    assert (work / PROBLEM_FILE).read_text(encoding="utf-8") == ""
    assert any("actions/artifacts" in line for line in _lines(runner.gh_log)), (
        "unseal never asked GitHub for sealed rounds"
    )
    gate = _gate(work)
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert "::error::" not in gate.stdout


def test_a_private_repository_with_no_movement_branch_is_a_red_run(
    runner: Runner,
) -> None:
    """The private repository answers, and has no `movement` branch (pull
    exit 4). That was once the first run of the season and green; the chain
    has existed since 2026-10-02, so now it means the branch was deleted or
    renamed, and a run that started thin from it is red and says so."""
    work = runner.restore()

    assert runner.asked() == ["pull --dest data/processed", "unseal --dest data/processed"]
    assert not (work / "data" / "processed" / "line_movement").exists()
    problems = _problems(work)
    assert len(problems) == 1, runner.log
    assert problems[0].startswith(MISSING_CHAIN), problems
    assert "deleted or renamed" in problems[0], problems
    assert "merge" not in problems[0] and "push" not in problems[0], problems
    gate = _gate(work)
    assert gate.returncode != 0
    assert f"::error::{problems[0]}" in gate.stdout


def test_a_movement_branch_with_no_day_file_yet_is_green(runner: Runner) -> None:
    """A chain that exists and holds nothing yet is a clean pull (exit 0):
    "nothing yet" now lives there, not in a missing branch."""
    runner.chain({"README.md": "the movement chain\n"})
    work = runner.restore()

    assert not (work / "data" / "processed" / "line_movement").exists()
    assert (work / PROBLEM_FILE).read_text(encoding="utf-8") == "", runner.log
    gate = _gate(work)
    assert gate.returncode == 0, gate.stdout + gate.stderr


@pytest.mark.parametrize(("pull", "unseal", "expected"), [
    (0, 0, []),
    (4, 0, [(MISSING_CHAIN, None)]),
    (9, 0, [(PULL_PROBLEM, 9)]),
    (0, 9, [(UNSEAL_PROBLEM, 9)]),
    # A missing chain still unseals: a sealed round may be the only copy.
    (4, 9, [(MISSING_CHAIN, None), (UNSEAL_PROBLEM, 9)]),
    # A failed pull still unseals, and unseal has no "nothing yet" exit, so
    # its 4 is a problem too: both sentences are written.
    (5, 4, [(PULL_PROBLEM, 5), (UNSEAL_PROBLEM, 4)]),
], ids=["clean", "missing-chain", "pull-other-exit", "unseal-other-exit",
        "missing-chain-and-unseal", "both"])
def test_any_other_exit_is_recorded_and_unseal_runs_whatever_the_pull_did(
    runner: Runner, pull: int, unseal: int, expected: list[tuple[str, int | None]],
) -> None:
    runner.forced = {"pull": pull, "unseal": unseal}
    work = runner.restore()

    assert runner.asked() == ["pull --dest data/processed", "unseal --dest data/processed"]
    problems = _problems(work)
    assert len(problems) == len(expected), problems
    for line, (sentence, code) in zip(problems, expected):
        assert line.startswith(sentence), problems
        assert code is None or f"(exit {code})" in line, problems
    assert (_gate(work).returncode != 0) == bool(expected)


def test_a_problem_left_by_an_earlier_run_is_never_read_as_this_runs(
    runner: Runner,
) -> None:
    runner.forced = {"pull": 0, "unseal": 0}
    work = runner.restore(stale="The private movement chain could not be restored (exit 1).\n")

    assert (work / PROBLEM_FILE).read_text(encoding="utf-8") == ""
    assert _gate(work).returncode == 0


def test_the_restore_asks_the_private_chain_three_times_before_it_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retries the step used to ask for with `--attempts 3` now live in
    the script: an unreachable GitHub is asked three times, 5 s and 10 s
    apart, and only then is the pull's exit 1, the step's sentence."""
    asked, waited = [], []

    def unreachable(work, remote, token):
        asked.append(remote)
        raise movement_chain.store.Unreachable("HTTP 502")

    monkeypatch.setattr(movement_chain, "fetch_chain_once", unreachable)
    monkeypatch.setattr(movement_chain, "sleep", waited.append)
    code = movement_chain.main(["pull", "--dest", str(tmp_path / "processed"),
                                "--remote", f"file://{tmp_path / 'store.git'}"])

    assert code == movement_chain.EXIT_FAILED
    assert len(asked) == 3
    assert waited == [5, 10]


def test_a_private_chain_that_answers_on_the_third_ask_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The third ask's answer is taken, not turned into exit 1. The answer
    here is "no movement branch" (exit 4), which the restore step then
    reports as a missing chain."""
    answers = [movement_chain.store.Unreachable("HTTP 502"),
               movement_chain.store.Unreachable("HTTP 502"), None]

    def flaky(work, remote, token):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(movement_chain, "fetch_chain_once", flaky)
    monkeypatch.setattr(movement_chain, "sleep", lambda seconds: None)
    code = movement_chain.main(["pull", "--dest", str(tmp_path / "processed"),
                                "--remote", f"file://{tmp_path / 'store.git'}"])

    assert answers == []
    assert code == movement_chain.EXIT_EMPTY


# --------------------------------------------------------------------------
# The gate, and the step's bounds.
# --------------------------------------------------------------------------

#: The steps that keep this round: the private push, the seal and its
#: upload, and the check that the private tip holds it.
KEEPERS = ("private_push", "seal", "sealed_upload", "private_verify")


def test_the_gate_runs_after_every_step_that_keeps_the_round() -> None:
    steps = _capture_steps()
    names = [step.get("name") for step in steps]
    gate = names.index(GATE)
    keepers = [
        index for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
        or step.get("id") in KEEPERS
    ]
    assert {steps[index].get("id") for index in keepers} >= set(KEEPERS)
    assert max(keepers) < gate
    step = steps[gate]
    assert str(step.get("if", "")).startswith("always()")
    assert "continue-on-error" not in step


def test_a_restore_that_timed_out_is_red_though_it_wrote_no_problem(
    tmp_path: Path,
) -> None:
    """A step killed at its time limit writes nothing to the problem file;
    its outcome is what says it did not finish. The message claims nothing
    about the push, which may have failed or (off the default branch) never
    run: it once said "Its push still merged into the private chain" either
    way. The private-chain gate after it says whether the round is home, and
    `_gate` fills only the restore's outcome, so this gate reading any other
    step's outcome fails here as an unfilled expression."""
    work = tmp_path / "run"
    work.mkdir()
    (work / PROBLEM_FILE).write_text("", encoding="utf-8")

    gate = _gate(work, restore="failure")
    assert gate.returncode != 0
    assert "::error::Restore today's captures did not finish" in gate.stdout
    assert "merge" not in gate.stdout, gate.stdout
    assert "private-chain gate" in gate.stdout, gate.stdout
    assert _gate(work, restore="success").returncode == 0


def test_the_restore_is_bounded_and_never_stops_the_capture() -> None:
    """The paid fetch comes after it. The pull pauses 5 s and 10 s between
    its three asks, and unseal downloads every sealed round. Unbounded, an
    outage could eat the job's 20 minutes, and the job would be cancelled
    after it spent credits and wrote nothing. A restore cut off at its limit
    writes no sentence, so the gate reads `id: restore`."""
    step = _step(RESTORE_STEP)
    assert step.get("id") == "restore"
    assert 0 < int(step.get("timeout-minutes", 0)) <= 5
    assert step.get("continue-on-error") is True
    names = [s.get("name") for s in _capture_steps()]
    assert names.index(RESTORE_STEP) < names.index("Capture prices")
    assert "steps.restore" not in str(_step("Capture prices").get("if", ""))


# --------------------------------------------------------------------------
# A round its push could not keep comes home through the next restore.
# --------------------------------------------------------------------------

def test_a_round_sealed_by_a_failed_push_comes_home_through_the_next_restore(
    runner: Runner,
) -> None:
    """Attempt 1 restored only P1 (the chain also held P2), captured P3, and
    could not push, so its seal step sealed its files. Attempt 2, or any later
    round, pulls the chain and unseals attempt 1's artifact. Every row is
    there once, so the next push carries attempt 1's round home."""
    runner.sealed_round({LM: HEADER + _row(1) + _row(3), DP: "team,player\nTOR,X\n"})
    runner.chain({LM: HEADER + _row(1) + _row(2)})
    work = runner.restore()

    processed = work / "data" / "processed"
    lines = _lines(processed / LM)
    assert lines[0] == HEADER.strip(), runner.log
    assert sorted(lines[1:]) == sorted((_row(1) + _row(2) + _row(3)).splitlines())
    assert (processed / DP).read_text(encoding="utf-8") == "team,player\nTOR,X\n"
    assert (work / PROBLEM_FILE).read_text(encoding="utf-8") == "", runner.log
    assert _gate(work).returncode == 0


def _sealed_members(sealed: Path, tmp_path: Path) -> set[str]:
    """The day files a sealed round holds, opened with the fallback key."""
    bundle = tmp_path / "opened.tar"
    done = subprocess.run(
        ["openssl", "enc", "-d", *movement_chain.OPENSSL_CIPHER, "-pass", "env:KEY",
         "-in", str(sealed), "-out", str(bundle)],
        env={**os.environ, "KEY": FALLBACK_KEY}, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    with tarfile.open(bundle) as tar:
        return {member.name for member in tar.getmembers() if member.isfile()}


@pytest.mark.parametrize(("token", "expected"), [
    ("test-token-not-a-real-one", {LM}),
    ("", {LM, YESTERDAY_LM}),
], ids=["tip-listed", "no-token"])
def test_the_seal_step_leaves_out_what_the_private_tip_already_holds(
    runner: Runner, tmp_path: Path, token: str, expected: set[str],
) -> None:
    """The seal step is given the private token only to list the tip, so a
    seal holds what the chain lacks instead of growing to the season, which
    every later round downloads. Yesterday's file is on the tip byte for
    byte and is left out; today's is not on the tip and is sealed. Without
    the token the tip cannot be listed and everything is sealed."""
    runner.chain({YESTERDAY_LM: HEADER + _row(1)})
    runner.secrets["secrets.NHL_CLOSING_LINES_TOKEN"] = token
    sealed = runner.sealed_round({YESTERDAY_LM: HEADER + _row(1), LM: HEADER + _row(3)})

    assert _sealed_members(sealed, tmp_path) == expected


def test_a_sealed_round_that_cannot_be_merged_is_red_and_parked_for_the_push(
    runner: Runner,
) -> None:
    """A sealed copy whose header differs from the copy on disk cannot be
    folded. It is parked under data/processed/unmerged/<store>/<day>/, named
    by its blob id, where the next push keeps it on the private branch, so
    its rows never strand in an artifact that expires. The copy on disk is
    kept as it was, and the run is red."""
    other_header = HEADER.replace(",captured_at\n", ",captured_at,source\n")
    sealed_copy = other_header + _row(3).replace("\n", ",replay\n")
    runner.sealed_round({LM: sealed_copy})
    runner.chain({LM: HEADER + _row(1)})
    work = runner.restore()

    processed = work / "data" / "processed"
    assert (processed / LM).read_text(encoding="utf-8") == HEADER + _row(1), runner.log
    parked = sorted((processed / "unmerged").rglob("*"))
    parked = [path for path in parked if path.is_file()]
    blob = subprocess.run(["git", "hash-object", "--stdin"], input=sealed_copy,
                          capture_output=True, text=True, check=True).stdout.strip()
    rel = f"unmerged/line_movement/2026-10-15/{blob}.csv"
    assert [path.relative_to(processed).as_posix() for path in parked] == [rel], runner.log
    assert movement_chain.local_sidecars(processed) == {rel: processed / rel}
    assert (processed / rel).read_text(encoding="utf-8") == sealed_copy
    problems = _problems(work)
    assert len(problems) == 1, runner.log
    assert problems[0].startswith(UNSEAL_PROBLEM), problems
    assert f"(exit {movement_chain.EXIT_DAMAGED})" in problems[0], problems
    assert _gate(work).returncode != 0
