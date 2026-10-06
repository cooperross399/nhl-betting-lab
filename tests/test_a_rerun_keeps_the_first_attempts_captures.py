"""Re-running a Line Movement run never throws away the first attempt's captures.

A Line Movement run goes red on purpose when the line units or the scratch
list were not captured, and the error says that data "cannot be collected
later", which invites a click on Re-run. The re-run must not lose the round
it was clicked to rescue.

History, short. Until stage two the chain was the public, run-scoped
`line-movement` artifact. A re-run's restore could not see its own first
attempt (GitHub lists a re-running run as in progress, and only completed
runs were restore sources), and its `overwrite: true` upload deleted attempt
1's artifact; `restore_state.py --fold-run` folded that artifact in first.

Stage two (2026-10-05) removed the public artifact and that fold. The
chain's only home is branch `movement` of the private repository, and a
re-run keeps attempt 1's round in three ways, each run here:

* attempt 1 pushes its round straight after its captures ("Keep the
  captures privately"). The chain belongs to no run, so attempt 2's "Restore
  today's captures" pulls it as it pulls any earlier round;
* when that push failed, or "Check the private chain holds this round"
  found the tip short, attempt 1 sealed into `line-movement-sealed-1` the
  day files the tip lacks. The attempt number in the name, and no upload in
  the job using `overwrite: true` for a capture, mean attempt 2 never
  replaces it, and attempt 2's restore unseals every sealed round, attempt
  1's included;
* attempt 2's push merges into the private tip, so an attempt 2 whose
  restore came back thin never deletes attempt 1's rows.

The chain itself must already exist. It has since 2026-10-02, so a private
repository with no `movement` branch means it was deleted or renamed: the
restore says so in restore_problem.txt (the run is red), and a push refuses
to start a thin chain in its place. `--allow-new-chain` is a manual first
seed that no workflow step passes; these tests seed the stand-in with it,
once, before the run under test.

A sealed round that cannot be listed or fetched is a sentence in
restore_problem.txt, and the gate after it turns the run red. One whose day
file cannot be merged with the copy on disk is a sentence too, and is parked
as a sidecar under data/processed/unmerged/, which attempt 2's push keeps on
the private branch.

How: "Restore today's captures" and "Seal this round when the private chain
did not take it" are taken from the workflow and run under `bash --noprofile
--norc -eo pipefail` with their own `env:` blocks, against a local bare
repository standing in for the private one (git's `insteadOf` points the
steps' GitHub URL at it, and `GIT_ALLOW_PROTOCOL=file` refuses every other
transport; the seal reads the tip too, to leave out what is already home),
an offline `gh`, and the machine's openssl. The push and the check run
in-process with their steps' own arguments plus `--remote` aimed at that
repository, because the push asks api.github.com whether the store is
private; that answer is replaced. Their folder, which the steps name
relative to the workspace, is handed over absolute except in
test_the_push_and_the_check_read_the_folder_their_steps_name, which runs it
as written. Nothing reaches the network, and no provider credit is spent.

Not shown here, because no replay can show it: that GitHub's artifact
listing shows `unseal` a sealed artifact of the run that is re-running (the
offline `gh` serves it), and that upload-artifact keeps two differently
named artifacts of one run side by side.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from collections import Counter
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT

from test_a_blocked_card_is_a_degraded_run import _render
from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
CHAIN = "private_movement_chain.py"
ARTIFACT = "line-movement"
RUN_ID = "4242"
DAY = "2026-10-15"
LM = f"line_movement/{DAY}.csv"
DP = f"deployment/{DAY}.csv"
#: The private repository as the restore's pull names it, with the token
#: the test hands the step. git rewrites exactly this URL to the local
#: stand-in; any other URL meets GIT_ALLOW_PROTOCOL=file and is refused.
TOKEN = "not-a-real-token"
PRIVATE_URL = f"https://x-access-token:{TOKEN}@github.com/cooperross399/nhl-closing-lines.git"
#: What the steps' `${{ }}` expressions stand for on this offline runner.
#: The seal and unseal refuse a key shorter than 32 characters, so this one
#: is long enough to be used and is still nobody's real key.
FALLBACK_KEY = "not-coopers-key-only-for-this-offline-test"
EXPRESSIONS = {
    "secrets.NHL_CLOSING_LINES_TOKEN": TOKEN,
    "secrets.NHL_CHAIN_FALLBACK_KEY": FALLBACK_KEY,
    "github.token": "not-a-github-token",
}

HEADER = "captured_at,market,player,american_odds\n"
#: What the rounds before this run left on the chain: 14:00.
BASE = HEADER + "2026-10-15T14:00:00+00:00,shots_on_goal,Auston Matthews,-110\n"
#: Attempt 1 of this run captured the 18:00 round, and a scratch list.
ROUND_1 = "2026-10-15T18:00:00+00:00,shots_on_goal,Auston Matthews,-125\n"
DEPLOYMENT = "captured_at,game_id,player,status\n2026-10-15T18:00:00+00:00,1,A,scratched\n"
#: Attempt 2 captured the 21:00 round on top of what it restored.
ROUND_2 = "2026-10-15T21:00:00+00:00,shots_on_goal,Auston Matthews,-130\n"

#: The repository's artifact listing holds every workflow's artifacts, the
#: expired ones too. `unseal` must open neither of these; the offline `gh`
#: holds no zip for them, so a download of either fails the restore.
OTHER_ARTIFACTS = [
    {"id": 1, "name": "ladder-coherence", "expired": False, "created_at": "2026-10-15T14:05:00Z",
     "workflow_run": {"id": 4100, "head_branch": "main", "repository_id": 1, "head_repository_id": 1}},
    {"id": 2, "name": "line-movement-sealed-1", "expired": True, "created_at": "2026-10-01T14:05:00Z",
     "workflow_run": {"id": 3900, "head_branch": "main", "repository_id": 1, "head_repository_id": 1}},
]

FAKE_GH = r'''#!{python}
import json, os, re, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
if not os.environ.get("GH_TOKEN"):
    print("gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN environment variable.",
          file=sys.stderr)
    sys.exit(4)
mode = os.environ["FAKE_GH_MODE"]
artifacts = "repos/" + os.environ["GITHUB_REPOSITORY"] + "/actions/artifacts"
if args == ["api", "--paginate", artifacts + "?per_page=100", "--jq", ".artifacts[]"]:
    if mode == "list-down":
        print("HTTP 502: Bad Gateway", file=sys.stderr)
        sys.exit(1)
    for item in json.loads(Path(os.environ["FAKE_GH_LISTING"]).read_text()):
        print(json.dumps(item))
    sys.exit(0)
wanted = re.fullmatch(re.escape(artifacts) + r"/(\d+)/zip", args[1]) if len(args) == 2 and args[0] == "api" else None
if wanted:
    archive = Path(os.environ["FAKE_GH_ZIPS"]) / (wanted.group(1) + ".zip")
    if mode == "zip-flaky":
        # The first download of each artifact breaks off half-written with a
        # 502; every later one answers.
        asked = archive.with_suffix(".asked")
        first = not asked.exists()
        asked.write_text("asked\n")
        if first:
            sys.stdout.buffer.write(b"half an archive")
            print("HTTP 502: Bad Gateway", file=sys.stderr)
            sys.exit(1)
    if mode == "zip-down" or not archive.is_file():
        print("HTTP 502: Bad Gateway", file=sys.stderr)
        sys.exit(1)
    sys.stdout.buffer.write(archive.read_bytes())
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["capture"]["steps"]


def _step(step_id: str) -> tuple[int, dict]:
    matches = [(index, step) for index, step in enumerate(_steps()) if step.get("id") == step_id]
    assert len(matches) == 1, f"exactly one step has the id {step_id}"
    return matches[0]


def _named(name: str) -> tuple[int, dict]:
    matches = [(index, step) for index, step in enumerate(_steps()) if step.get("name") == name]
    assert len(matches) == 1, f"exactly one step is named {name!r}"
    return matches[0]


def _uploads() -> list[dict]:
    return [step for step in _steps()
            if str(step.get("uses", "")).startswith("actions/upload-artifact")]


def _bash(block: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    if shutil.which("bash") is None:
        pytest.fail("this test needs bash, which every runner here has")
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


def _read(work: Path, rel: str) -> str:
    return (work / "data" / "processed" / rel).read_text(encoding="utf-8")


def _append(work: Path, rel: str, rows: str) -> None:
    with (work / "data" / "processed" / rel).open("a", encoding="utf-8") as handle:
        handle.write(rows)


def _restore_gate(work: Path) -> subprocess.CompletedProcess:
    """'Fail the run when the previous captures were not restored', run in
    the workspace the restore wrote restore_problem.txt into, after a
    restore step that finished."""
    _, gate = _named("Fail the run when the previous captures were not restored")
    return _bash(_render(gate["run"], {"steps.restore.outcome": "success"}), work, dict(os.environ))


class Lab:
    """One offline Line Movement: the private repository's stand-in, the
    runners' workspaces, and the steps that move a round between them."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp = tmp_path
        self.monkeypatch = monkeypatch
        self.bare = tmp_path / "nhl-closing-lines.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.bare)],
                       check=True, capture_output=True)
        self.chain = load_script(CHAIN)
        monkeypatch.setattr(self.chain.store, "repo_is_private", lambda repo, token: True)
        monkeypatch.setattr(self.chain, "sleep", lambda seconds: None)
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH.replace("{python}", sys.executable), encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.zips = tmp_path / "zips"
        self.zips.mkdir()
        self.log = tmp_path / "gh.log"
        self.listing: list[dict] = list(OTHER_ARTIFACTS)
        self.sealed: dict[str, Path] = {}

    def workspace(self, name: str, files: dict[str, str]) -> Path:
        """A runner's checkout: the project's scripts and src, and
        data/processed holding `files`."""
        work = self.tmp / name
        (work / "data" / "processed").mkdir(parents=True)
        (work / "scripts").symlink_to(PROJECT_ROOT / "scripts", target_is_directory=True)
        (work / "src").symlink_to(PROJECT_ROOT / "src", target_is_directory=True)
        for rel, body in files.items():
            path = work / "data" / "processed" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return work

    def keep(self, work: Path, step_id: str = "private_push", *, as_written: bool = False,
             seed: bool = False) -> int:
        """The push (or, with `private_verify`, the check) with its step's own
        arguments, in-process from `work`, against the stand-in. The step
        names its folder relative to the workspace; that folder is handed
        over absolute unless `as_written`, so that only
        test_the_push_and_the_check_read_the_folder_their_steps_name fails
        when a relative folder cannot be read. `seed` adds
        `--allow-new-chain`, the manual first seed no step passes: only
        _chain_before_this_run uses it, to stand up the chain that has
        existed since 2026-10-02."""
        argv = shlex.split(_step(step_id)[1]["run"])
        assert argv[:2] == ["python", f"scripts/{CHAIN}"], argv
        args = argv[2:]
        if not as_written:
            flag = args.index("--processed-dir") + 1
            args[flag] = str(work / args[flag])
        if seed:
            assert "--allow-new-chain" not in args, "the push step itself seeds a new chain"
            args.append("--allow-new-chain")
        self.monkeypatch.chdir(work)
        return self.chain.main([*args, "--remote", f"file://{self.bare}"])

    def has_chain(self) -> bool:
        """The stand-in has a `movement` branch."""
        return subprocess.run(
            ["git", "--git-dir", str(self.bare), "rev-parse", "--verify", "-q", "refs/heads/movement"],
            capture_output=True,
        ).returncode == 0

    def reach_the_stand_in(self, env: dict) -> None:
        """Point the GitHub URL a step builds from its token at the stand-in."""
        env.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.file://{self.bare}.insteadOf",
            "GIT_CONFIG_VALUE_0": PRIVATE_URL,
        })

    def env(self, step: dict, work: Path, attempt: str) -> dict:
        """A runner's environment for `step`: none of this machine's
        credentials or git config, GitHub's variables for attempt `attempt`
        of run RUN_ID, and the step's own `env:` block."""
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("GIT_", "GITHUB_", "RUNNER_", "GH_", "NHL_"))}
        env.update({
            "PATH": os.pathsep.join([str(self.bin), str(Path(sys.executable).parent),
                                     os.environ.get("PATH", "")]),
            "GITHUB_REPOSITORY": "cooperross399/nhl-betting-lab",
            "GITHUB_RUN_ID": RUN_ID,
            "GITHUB_RUN_ATTEMPT": attempt,
            "GITHUB_WORKSPACE": str(work),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ALLOW_PROTOCOL": "file",
            "FAKE_GH_LOG": str(self.log),
            "FAKE_GH_MODE": "up",
            "FAKE_GH_LISTING": str(self.tmp / "listing.json"),
            "FAKE_GH_ZIPS": str(self.zips),
        })
        env.update({key: _render(str(value), EXPRESSIONS)
                    for key, value in (step.get("env") or {}).items()})
        return env

    def restore(self, work: Path, *, mode: str = "up") -> subprocess.CompletedProcess:
        """'Restore today's captures' as the runner runs it, in `work`."""
        _, step = _step("restore")
        env = self.env(step, work, attempt="2")
        self.reach_the_stand_in(env)
        env["FAKE_GH_MODE"] = mode
        (self.tmp / "listing.json").write_text(json.dumps(self.listing), encoding="utf-8")
        return _bash(_render(step["run"], {}), work, env)

    def seal(self, attempt: str, files: dict[str, str]) -> dict:
        """Attempt `attempt` of run RUN_ID, which the private chain did not
        take: its seal step run as the runner runs it (reading the stand-in's
        tip with the step's own token, to leave out what is already home),
        and its upload added to the listing as the artifact upload-artifact
        would make of it. The sealed file is kept in `self.sealed[attempt]`."""
        work = self.workspace(f"attempt{attempt}-sealed", files)
        runner_temp = self.tmp / f"runner-temp-{attempt}"
        runner_temp.mkdir()
        _, step = _step("seal")
        env = self.env(step, work, attempt)
        self.reach_the_stand_in(env)
        env["RUNNER_TEMP"] = str(runner_temp)
        done = _bash(_render(step["run"], {}), work, env)
        assert done.returncode == 0, done.stdout + done.stderr
        _, upload = _step("sealed_upload")
        values = {"github.run_attempt": attempt, "runner.temp": str(runner_temp)}
        [kept] = [Path(line.strip()) for line in _render(str(upload["with"]["path"]), values).splitlines()
                  if line.strip()]
        assert kept.is_file(), "the sealed upload keeps the file the seal step wrote"
        self.sealed[attempt] = kept
        artifact_id = 100 + int(attempt)
        # One file is rooted at its own folder: the zip holds it by its name.
        with zipfile.ZipFile(self.zips / f"{artifact_id}.zip", "w") as zipped:
            zipped.write(kept, arcname=kept.name)
        artifact = {
            "id": artifact_id,
            "name": _render(str(upload["with"]["name"]), values),
            "expired": False,
            "created_at": f"2026-10-15T18:{10 * int(attempt):02d}:00Z",
            "workflow_run": {"id": int(RUN_ID), "head_branch": "main", "repository_id": 1, "head_repository_id": 1},
        }
        self.listing.append(artifact)
        return artifact

    def tip(self, rel: str) -> str:
        return subprocess.run(
            ["git", "--git-dir", str(self.bare), "show", f"movement:{rel}"],
            check=True, capture_output=True, text=True,
        ).stdout


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Lab:
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                       "GIT_ALLOW_PROTOCOL": "file"}.items():
        monkeypatch.setenv(key, value)
    for key in ("GITHUB_REPOSITORY", "GITHUB_WORKSPACE", "GITHUB_STEP_SUMMARY",
                "NHL_CLOSING_LINES_TOKEN", "NHL_CHAIN_FALLBACK_KEY"):
        monkeypatch.delenv(key, raising=False)
    return Lab(tmp_path, monkeypatch)


def _chain_before_this_run(lab: Lab) -> None:
    """The private chain as the rounds before this run left it: 14:00. It
    is seeded once with `--allow-new-chain`, as the real chain was on
    2026-10-02; every push after this is the step's own, which refuses to
    start a chain."""
    assert not lab.has_chain()
    assert lab.keep(lab.workspace("earlier", {LM: BASE}), seed=True) == 0
    assert lab.has_chain()


# --------------------------------------------------------------------------
# A re-run's restore brings attempt 1's round back, from either home.
# --------------------------------------------------------------------------

def test_a_rerun_restores_the_round_its_first_attempt_pushed(lab: Lab) -> None:
    _chain_before_this_run(lab)
    assert lab.keep(lab.workspace("attempt1", {LM: BASE + ROUND_1, DP: DEPLOYMENT})) == 0
    # Attempt 2 runs on a fresh runner: nothing on disk.
    second = lab.workspace("attempt2", {})
    done = lab.restore(second)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (second / "restore_problem.txt").read_text(encoding="utf-8") == ""
    assert _read(second, LM) == BASE + ROUND_1
    assert _read(second, DP) == DEPLOYMENT
    # Its own round on top, kept: every row of both attempts, once each, in
    # capture order.
    _append(second, LM, ROUND_2)
    assert lab.keep(second) == 0
    assert lab.tip(LM) == BASE + ROUND_1 + ROUND_2
    assert lab.tip(DP) == DEPLOYMENT


def test_a_rerun_restores_the_round_its_first_attempt_sealed(lab: Lab) -> None:
    """Attempt 1's push failed, so the chain still ends at 14:00 and its
    round, scratch list included, is only in its sealed artifact."""
    _chain_before_this_run(lab)
    sealed = lab.seal("1", {LM: BASE + ROUND_1, DP: DEPLOYMENT})
    second = lab.workspace("attempt2", {})
    done = lab.restore(second)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (second / "restore_problem.txt").read_text(encoding="utf-8") == ""
    # The 14:00 row is on the chain and in the sealed round: once, not twice.
    assert _read(second, LM) == BASE + ROUND_1
    assert _read(second, DP) == DEPLOYMENT
    assert f"actions/artifacts/{sealed['id']}/zip" in lab.log.read_text(encoding="utf-8")
    # And attempt 2's push carries attempt 1's round home.
    _append(second, LM, ROUND_2)
    assert lab.keep(second) == 0
    assert lab.tip(LM) == BASE + ROUND_1 + ROUND_2
    assert lab.tip(DP) == DEPLOYMENT


def test_a_seal_leaves_out_what_the_chain_holds_and_a_rerun_still_gets_the_whole_round(
        lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
    """Attempt 1's price capture went red, so its line_movement file is
    byte for byte the tip's, and only its scratch list is new; its push
    failed. Its seal step reads the tip with the token its step is given and
    seals the scratch list alone, and attempt 2 still restores the whole
    round: the day file from the chain, the scratch list from the seal."""
    _chain_before_this_run(lab)
    lab.seal("1", {LM: BASE, DP: DEPLOYMENT})
    monkeypatch.setenv(lab.chain.KEY_ENV, FALLBACK_KEY)
    opened = lab.tmp / "opened.tar"
    assert lab.chain._openssl(["-d"], lab.sealed["1"], opened).returncode == 0
    with tarfile.open(opened) as tar:
        assert tar.getnames() == [DP], "the seal kept a day file the private tip already holds"
    second = lab.workspace("attempt2", {})
    done = lab.restore(second)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (second / "restore_problem.txt").read_text(encoding="utf-8") == ""
    assert _read(second, LM) == BASE
    assert _read(second, DP) == DEPLOYMENT


def test_a_rerun_whose_first_attempt_kept_nothing_is_not_a_fault(lab: Lab) -> None:
    """The chain is there and holds nothing of attempt 1's, because attempt 1
    kept nothing: nothing is wrong, and the restore gate is green. A chain
    that is not there at all is the next test."""
    _chain_before_this_run(lab)
    second = lab.workspace("attempt2", {})
    done = lab.restore(second)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (second / "restore_problem.txt").read_text(encoding="utf-8") == ""
    gate = _restore_gate(second)
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert _read(second, LM) == BASE
    assert not (second / "data" / "processed" / "deployment").exists()


def test_a_rerun_that_finds_no_chain_is_red_and_starts_no_thin_one(lab: Lab) -> None:
    """The private repository has no `movement` branch: it was deleted or
    renamed, since the chain has existed since 2026-10-02. Attempt 1's push
    refuses to start a new chain and its round is sealed. Attempt 2's
    restore says the branch is missing (red), still folds in attempt 1's
    sealed round, and its push refuses too, so neither attempt replaces the
    season with a chain one round long."""
    first = lab.workspace("attempt1", {LM: HEADER + ROUND_1, DP: DEPLOYMENT})
    assert lab.keep(first) == lab.chain.EXIT_REFUSED
    assert not lab.has_chain(), "a push started a new chain where the season's was missing"
    lab.seal("1", {LM: HEADER + ROUND_1, DP: DEPLOYMENT})
    second = lab.workspace("attempt2", {})
    done = lab.restore(second)
    assert done.returncode == 0, done.stdout + done.stderr
    problem = (second / "restore_problem.txt").read_text(encoding="utf-8")
    # One sentence, the missing branch's: the sealed round folded in cleanly.
    assert len(problem.splitlines()) == 1, problem
    assert "has no movement branch" in problem
    assert "deleted or renamed" in problem
    gate = _restore_gate(second)
    assert gate.returncode != 0, gate.stdout + gate.stderr
    assert "::error::" in gate.stdout
    assert problem.strip() in gate.stdout
    assert "merged into the private" not in gate.stdout
    assert _read(second, LM) == HEADER + ROUND_1
    assert _read(second, DP) == DEPLOYMENT
    _append(second, LM, ROUND_2)
    assert lab.keep(second) == lab.chain.EXIT_REFUSED
    assert not lab.has_chain(), "a re-run's push started a new chain where the season's was missing"


@pytest.mark.parametrize("mode", ["list-down", "zip-down"])
def test_a_sealed_round_that_cannot_be_fetched_makes_the_run_red(lab: Lab, mode: str) -> None:
    """Could not ask is not nothing there: attempt 1's sealed round stays
    outside the chain, so the run says so in red. The restore itself never
    stops the paid capture after it."""
    _chain_before_this_run(lab)
    lab.seal("1", {LM: BASE + ROUND_1, DP: DEPLOYMENT})
    second = lab.workspace("attempt2", {})
    done = lab.restore(second, mode=mode)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "502" in done.stdout + done.stderr
    problem = (second / "restore_problem.txt").read_text(encoding="utf-8")
    assert problem.strip(), "a sealed round that could not be fetched left no sentence"
    gate = _restore_gate(second)
    assert gate.returncode != 0, gate.stdout + gate.stderr
    assert "::error::" in gate.stdout
    assert problem.strip() in gate.stdout
    # What the chain held still came back.
    assert _read(second, LM) == BASE
    assert not (second / "data" / "processed" / "deployment").exists()


def test_a_sealed_round_whose_download_breaks_off_once_still_comes_home(lab: Lab) -> None:
    """One 502 mid-download is asked again, from an empty file: attempt 1's
    sealed round is the only copy of a round the chain did not take, so a
    single transient failure must not leave it out of attempt 2."""
    _chain_before_this_run(lab)
    sealed = lab.seal("1", {LM: BASE + ROUND_1, DP: DEPLOYMENT})
    second = lab.workspace("attempt2", {})
    done = lab.restore(second, mode="zip-flaky")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (second / "restore_problem.txt").read_text(encoding="utf-8") == ""
    assert _read(second, LM) == BASE + ROUND_1
    assert _read(second, DP) == DEPLOYMENT
    asked = [line for line in lab.log.read_text(encoding="utf-8").splitlines()
             if line.endswith(f"actions/artifacts/{sealed['id']}/zip")]
    assert len(asked) == 2, asked


def test_a_sealed_round_that_cannot_be_merged_is_red_and_parked_for_the_push(lab: Lab) -> None:
    """A day file the union cannot read safely leaves the copy on disk as it
    was; the rest of the sealed round still comes in, and the run is red.
    The sealed copy is not left to expire with its artifact: it is parked as
    a sidecar under data/processed/unmerged/, named by its blob id, and
    attempt 2's push keeps it on the private branch beside the day file,
    which it leaves as it was."""
    _chain_before_this_run(lab)
    unmergeable = "captured_at,market\n" + ROUND_1
    lab.seal("1", {LM: unmergeable, DP: DEPLOYMENT})
    second = lab.workspace("attempt2", {})
    done = lab.restore(second)
    out = done.stdout + done.stderr
    assert done.returncode == 0, out
    assert LM in out
    assert (second / "restore_problem.txt").read_text(encoding="utf-8").strip()
    assert _read(second, LM) == BASE
    assert _read(second, DP) == DEPLOYMENT
    gate = _restore_gate(second)
    assert gate.returncode != 0, gate.stdout + gate.stderr
    blob = subprocess.run(["git", "hash-object", "--stdin"], input=unmergeable, check=True,
                          capture_output=True, text=True).stdout.strip()
    sidecar = f"unmerged/line_movement/{DAY}/{blob}.csv"
    parked = sorted(p.relative_to(second / "data" / "processed").as_posix()
                    for p in (second / "data" / "processed" / "unmerged").rglob("*") if p.is_file())
    assert parked == [sidecar], "the sealed copy that could not be merged was not parked"
    assert _read(second, sidecar) == unmergeable
    assert lab.keep(second) == 0
    assert lab.tip(sidecar) == unmergeable
    assert lab.tip(LM) == BASE
    assert lab.tip(DP) == DEPLOYMENT
    assert lab.keep(second, "private_verify") == 0


def test_the_push_and_the_check_read_the_folder_their_steps_name(lab: Lab) -> None:
    """Attempt 1's round reaches the chain only if its push can read the
    folder its step names, `data/processed` relative to the workspace,
    exactly as written; and the check must read it too, or every round is
    red. The other tests hand both that folder absolute, so this is the one
    that runs them as the runner does."""
    _chain_before_this_run(lab)
    first = lab.workspace("attempt1", {LM: BASE + ROUND_1, DP: DEPLOYMENT})
    assert lab.keep(first, as_written=True) == 0, \
        "the push cannot read the folder its step names, relative to the workspace"
    assert lab.tip(LM) == BASE + ROUND_1
    assert lab.tip(DP) == DEPLOYMENT
    assert lab.keep(first, "private_verify", as_written=True) == 0, \
        "the check cannot read the folder its step names, relative to the workspace"


def test_a_thin_rerun_never_deletes_the_first_attempts_round_from_the_chain(lab: Lab) -> None:
    """Attempt 2's restore could not reach the chain, so its day file holds
    its own round alone. Its push merges into the tip instead of replacing
    it, and the check then passes on what attempt 2 has on disk."""
    _chain_before_this_run(lab)
    assert lab.keep(lab.workspace("attempt1", {LM: BASE + ROUND_1, DP: DEPLOYMENT})) == 0
    second = lab.workspace("attempt2", {LM: HEADER + ROUND_2})
    assert lab.keep(second) == 0
    assert lab.tip(LM) == BASE + ROUND_1 + ROUND_2
    assert lab.tip(DP) == DEPLOYMENT
    assert lab.keep(second, "private_verify") == 0


def test_two_attempts_that_both_sealed_both_come_home(lab: Lab) -> None:
    """Both attempts' pushes failed, and attempt 2 could not fold attempt 1's
    sealed round in. Each is kept under its own name, and the next round's
    restore folds in both, not only the newest."""
    _chain_before_this_run(lab)
    first = lab.seal("1", {LM: BASE + ROUND_1, DP: DEPLOYMENT})
    second = lab.seal("2", {LM: BASE + ROUND_2})
    assert first["name"] != second["name"]
    following = lab.workspace("next-run", {})
    done = lab.restore(following)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (following / "restore_problem.txt").read_text(encoding="utf-8") == ""
    day_file = _read(following, LM)
    assert day_file.startswith(HEADER)
    # Every row of both attempts, once each. Two sealed copies that diverged
    # are unioned oldest artifact first, so 18:00 and 21:00 need not be in
    # capture order.
    assert Counter(day_file.splitlines()) == Counter((BASE + ROUND_1 + ROUND_2).splitlines())
    assert _read(following, DP) == DEPLOYMENT


def test_folding_a_run_reads_no_other_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No workflow calls `restore_state.py --fold-run` since stage two. While
    the script still ships it, it lists nothing and downloads only the run it
    names."""
    module = load_script("restore_state.py")
    asked: list[tuple[str, ...]] = []

    def gh(*args: str) -> subprocess.CompletedProcess:
        asked.append(args)
        return subprocess.CompletedProcess(args, 1, "", module.NO_SUCH_ARTIFACT)

    monkeypatch.setattr(module, "_gh", gh)
    code = module.main(["--fold-run", "77", "--artifact", ARTIFACT,
                        "--dest", str(tmp_path)])
    assert code == 0
    assert [a[:3] for a in asked] == [("run", "download", "77")]


# --------------------------------------------------------------------------
# The workflow: every attempt restores and keeps alike, and nothing that
# holds a round is uploaded under a name a later attempt reuses.
# --------------------------------------------------------------------------

def test_every_attempt_restores_before_the_paid_fetch_and_keeps_its_round_after_the_captures() -> None:
    restore_index, restore = _step("restore")
    captures = [_named(name)[0] for name in
                ("Capture prices", "Capture deployment", "Capture line combinations")]
    push_index, push = _step("private_push")
    verify_index, verify = _step("private_verify")
    seal_index, seal = _step("seal")
    upload_index, upload = _step("sealed_upload")
    assert restore_index < min(captures)
    # The check before the seal: a push that exited 0 but left the tip short
    # is sealed too.
    assert max(captures) < push_index < verify_index < seal_index < upload_index
    # Attempt 2 restores, keeps, checks and seals as attempt 1 did: nothing
    # here asks which attempt is running.
    for step in (restore, push, verify, seal, upload):
        assert "run_attempt" not in str(step.get("if", "")), step["name"]
    # Kept whatever the captures did: a red price capture still leaves a
    # scratch list and line units that no re-run can capture again.
    assert "always()" in str(push.get("if", ""))
    assert "always()" in str(verify.get("if", ""))
    assert "always()" in str(seal.get("if", ""))
    assert "steps.private_push.outcome == 'failure'" in str(seal.get("if", ""))
    assert "steps.private_verify.outcome == 'failure'" in str(seal.get("if", ""))
    assert "always()" in str(upload.get("if", ""))
    assert "steps.seal.outcome == 'success'" in str(upload.get("if", ""))
    # None of them can stop the job before the round is kept and the gates run.
    for step in (restore, push, verify, seal):
        assert step.get("continue-on-error") is True, step["name"]
    for step in (restore, push, verify, seal, upload):
        assert "NHL_ODDS_API_KEY" not in json.dumps(step), step["name"]
    # No step may start a new chain: a missing one was deleted or renamed.
    for step in _steps():
        assert "allow-new-chain" not in str(step.get("run", "")), step.get("name")


def test_no_upload_that_holds_a_round_reuses_an_earlier_attempt_s_name() -> None:
    """An upload-artifact v4 artifact belongs to the run, not the attempt.
    Any upload that can hold a capture is named per attempt and never
    overwrites, so attempt 2 cannot replace what attempt 1 kept."""
    carriers = []
    for step in _uploads():
        values = {"github.run_attempt": "1", "runner.temp": "/home/runner/work/_temp"}
        paths = [line.strip() for line in _render(str(step["with"]["path"]), values).splitlines()
                 if line.strip()]
        if all(path.startswith("data/outputs/") for path in paths):
            continue  # the ladder scan's report: no capture in it
        carriers.append(step.get("id"))
        names = {_render(str(step["with"]["name"]), {**values, "github.run_attempt": attempt})
                 for attempt in ("1", "2")}
        assert len(names) == 2, f"{step['name']}: attempt 2 uploads under attempt 1's name"
        assert step["with"].get("overwrite") is not True, step["name"]
    assert "sealed_upload" in carriers, "the sealed round is one of them, or nothing was checked"
