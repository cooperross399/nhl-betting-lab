"""A test promised that CLV reads the handed-over store, and it never read it.

In tests/test_the_closing_prices_reach_the_clv_store.py,
`test_the_store_format_is_the_one_clv_reads` said "The hand-off carries what
`best_prices` writes, which `load_captures` reads." It never called
`load_captures`. The failure-shape audit found this (finding 87): four
breaks took CLV from 1 of 1 matched to 0 of 1 and that test passed under all
of them. A later round found the same hole one writer further on, because the
hand-off tests counted lines.

So these tests run the chain the way production does. Since stage two of the
chain's move (2026-10-05) both halves live only in the private repository
cooperross399/nhl-closing-lines: Line Movement's capture chain on branch
`movement`, the closing-line store on `main`. The chain has existed since
2026-10-02, so each test starts from a private repository that already
holds it: an earlier day's round, written by the real `write_round` and
pushed once by the real `push --allow-new-chain`, as the first seed was. The
chain is:

1. Line Movement, one run per round, each on a fresh runner: its "Restore
   today's captures" block as written, under the shell GitHub uses (the real
   `private_movement_chain.py pull` and `unseal`; `gh` is a stub that lists
   the sealed rounds this test kept); its round, written by the real
   `capture_line_movement.write_round` on rows from the real
   `normalize_event`; then "Keep the captures privately" (`push`) and "Check
   the private chain holds this round" (`verify`) with the workflow's exact
   arguments. When either fails, "Seal this round when the private chain did
   not take it" runs as written, and its upload is modelled from "Keep the
   sealed round"'s own `name` and `path`. Last, the two gates "Fail the run
   when the previous captures were not restored" and "Fail the run when the
   private chain was not kept" run as written, on the outcomes those steps
   had.
2. Closing Lines' hand-off block as written, pulling the chain from
   `movement` onto its runner. A missing `movement` branch is a red run
   there, never "nothing yet": the chain is the only copy, so a missing
   branch means it was deleted or renamed.
3. Closing Lines' publish: `private_closing_store.py push` with the
   workflow's exact arguments.
4. Gameday Refresh: the store pulled, and the real `run_closing_line_value`
   pointed at it alone, scoring opinions frozen by the real `write_snapshot`.
   Where the union of store and chain matters, or a missing chain, its
   "Report closing-line value" block runs as written, with both real pulls
   and the real report; only a runner's own folders and clock are appended
   to the report's arguments. A missing chain is a red fault there too,
   which does not degrade the run.

The private repository is a local bare repository reached through the real
URL the scripts build. Only the GitHub API's privacy answer is replaced, so
the pushes run in process, and the checks beside them; the pulls, the seal
and the unseal run as the steps run them. Every script gets its step's own arguments, relative
paths included, from the runner's working directory. The steps' `if:`
conditions are not evaluated here: each scenario runs the steps it reaches.

Until 2026-10-05 the hand-off unpacked Line Movement's public
`line-movement` artifact with `gh run download`; that artifact and the
re-run fold (`restore_state.py --fold-run`) are gone. A re-run's second
attempt runs the same restore block as the next round, which folds in every
unexpired sealed round, so the sealed-round tests below cover that path too.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.reports.card_pricing import selection_key

from test_scripts import load_script

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import private_closing_store as store  # noqa: E402
import private_movement_chain as chain  # noqa: E402

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
LINE_MOVEMENT = WORKFLOWS / "line-movement.yml"
CLOSING_LINES = WORKFLOWS / "closing-lines.yml"
GAMEDAY = WORKFLOWS / "gameday-refresh.yml"
RESTORE = "Restore today's captures"
PRIVATE_PUSH = "Keep the captures privately"
CHECK = "Check the private chain holds this round"
SEAL = "Seal this round when the private chain did not take it"
SEALED_UPLOAD = "Keep the sealed round"
RESTORE_GATE = "Fail the run when the previous captures were not restored"
CHAIN_GATE = "Fail the run when the private chain was not kept"
HANDOFF = "Take the chain from the private repository"
PUBLISH = "Publish to the private store"
CLV_STEP = "Report closing-line value"
REPO = "owner/lab"
TOKEN = "rehearsal-token"
# As long as the seal and the unseal require: a short key is refused.
FALLBACK_KEY = "rehearsal-fallback-key-" + "0123456789abcdef" * 2
# What Line Movement's restore and Closing Lines' hand-off say when the
# private repository has no `movement` branch.
NO_CHAIN = ("The private repository has no movement branch. The chain has existed since "
            "2026-10-02, so it was deleted or renamed; restore it from its history.")
SEALED_GATE = ("::error::The private chain did not take this round (push: failure, check: failure).\n"
               "::error::It was sealed with NHL_CHAIN_FALLBACK_KEY as line-movement-sealed-1, "
               "and the next round folds it in.\n")

# The chain's first seed: an earlier day's round, another game.
SEED_DAY = "2026-10-14"
SEED_AT = f"{SEED_DAY}T21:00:00+00:00"
SEED_GAME = {"event_id": "evt0", "start": f"{SEED_DAY}T23:00:00Z", "player": "Nick Suzuki",
             "home": "Ottawa Senators", "away": "Montreal Canadiens"}

DAY = "2026-10-15"
START = f"{DAY}T23:00:00Z"  # 19:00 ET
CARD_AT = datetime(2026, 10, 15, 13, 30, tzinfo=timezone.utc)  # 09:30 ET
# After every game here: unplayed games are left out.
REPORT_NOW = "2027-06-01T00:00:00+00:00"
PLAYER = "Auston Matthews"
MATCHED_BOTH = "matched to a closing price: **2**; no closing price found: **0**"

# Shots on goal 2.5, (over, under) by book.
CARD_BOARD = {"DraftKings": (-110, -110), "FanDuel": (-115, -105)}
# One Line Movement run per round. The last is the face-off snapshot, which is
# a live price and never the close.
RUNS = (
    (f"{DAY}T14:00:00+00:00", {"DraftKings": (-115, -105), "FanDuel": (-120, -102)}),
    (f"{DAY}T21:00:00+00:00", {"DraftKings": (105, -135), "FanDuel": (100, -130)}),
    (f"{DAY}T23:00:00+00:00", {"DraftKings": (150, -190), "FanDuel": (140, -180)}),
)
# The 21:00 round's best price per side.
CLOSES = {
    "over": (105.0, "DraftKings", f"{DAY}T21:00:00+00:00"),
    "under": (-130.0, "FanDuel", f"{DAY}T21:00:00+00:00"),
}


def _event(
    board: dict[str, tuple[int, int]], *, event_id: str = "evt1", start: str = START,
    player: str = PLAYER, home: str = "Toronto Maple Leafs", away: str = "Boston Bruins",
) -> dict:
    """One provider event payload, every book quoting both sides."""
    return {
        "id": event_id, "commence_time": start,
        "home_team": home, "away_team": away,
        "bookmakers": [
            {"key": book.lower(), "title": book, "markets": [{
                "key": "player_shots_on_goal",
                "outcomes": [
                    {"name": "Over", "description": player, "price": over, "point": 2.5},
                    {"name": "Under", "description": player, "price": under, "point": 2.5},
                ],
            }]}
            for book, (over, under) in board.items()
        ],
    }


def _step(workflow: Path, name: str) -> dict:
    jobs = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"].values()
    (step,) = [step for job in jobs for step in job.get("steps", []) if step.get("name") == name]
    return step


def _render(text: str, values: dict[str, str] | None = None) -> str:
    """Fill the `${{ }}` expressions a test supplies; refuse any it does not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        assert expression in (values or {}), f"reads an expression this test does not supply: {expression}"
        return (values or {})[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, text)


def _bash(block: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    """A `run:` block under the shell GitHub uses."""
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def _python_stub(path: Path) -> None:
    """`python scripts/<name>.py ...` as a step calls it: this repository's
    script, under the interpreter running the tests."""
    path.write_text(
        "#!/bin/bash\n"
        'script="$1"; shift\n'
        'case "$script" in\n'
        "  scripts/private_movement_chain.py|scripts/private_closing_store.py)\n"
        f'    exec "{sys.executable}" "{PROJECT_ROOT}/$script" "$@" ;;\n'
        "  scripts/run_closing_line_value.py)\n"
        "    # Each folder the step hands the report, kept for the test before\n"
        "    # the step deletes it.\n"
        '    n=0; previous=""\n'
        '    for arg in "$@"; do\n'
        '      if [ "$previous" = --captures-dir ]; then\n'
        '        n=$((n + 1)); mkdir -p "$CLV_HANDED/$n"; cp -R "$arg/." "$CLV_HANDED/$n/"\n'
        "      fi\n"
        '      previous="$arg"\n'
        "    done\n"
        "    # Only what a runner supplies by being one: its folders and its clock.\n"
        f'    exec "{sys.executable}" "{PROJECT_ROOT}/$script" "$@" \\\n'
        '      --processed-dir "$CLV_PROCESSED" --archive-dir "$CLV_ARCHIVE" \\\n'
        '      --output-dir "$CLV_OUTPUT" --now "$CLV_NOW" ;;\n'
        "esac\n"
        'echo "this test does not run: python $script $*" >&2\n'
        "exit 97\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _gh_stub(path: Path) -> None:
    """`gh api` answering for the sealed rounds this test kept, as GitHub
    would: the artifact listing one object per line, and an artifact's zip."""
    path.write_text(
        "#!/bin/bash\n"
        '[ "$1" = api ] || { echo "this test does not run: gh $*" >&2; exit 97; }\n'
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        '    */actions/artifacts/*/zip) id="${arg%/zip}"; exec cat "$SEALED_DIR/${id##*/}.zip" ;;\n'
        '    *"/actions/artifacts?"*) cat "$SEALED_DIR/listing.jsonl" 2>/dev/null; exit 0 ;;\n'
        "  esac\n"
        "done\n"
        'echo "this test does not run: gh $*" >&2\n'
        "exit 97\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    if not (shutil.which("git") and shutil.which("bash") and shutil.which("openssl")):
        pytest.fail("this test needs git, bash and openssl, which every runner here has")
    home, bare, stub, seed, sealed = (
        tmp_path / d for d in ("home", "private.git", "bin", "seed", "sealed-artifacts")
    )
    for d in (home, stub, seed, sealed):
        d.mkdir()
    redirect = {
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.file://{bare}.insteadOf",
        "GIT_CONFIG_VALUE_0": store.remote_url(store.PRIVATE_REPO, TOKEN),
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    for key, value in redirect.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv(store.TOKEN_ENV, TOKEN)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(store, "repo_is_private", lambda repo, token: repo == store.PRIVATE_REPO)
    monkeypatch.setattr(store, "utc_now", lambda: datetime(2026, 10, 16, 2, tzinfo=timezone.utc))
    _python_stub(stub / "python")
    _gh_stub(stub / "gh")
    # What every step's subprocess sees on a runner of this repository.
    env = {
        **os.environ,
        "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "GH_TOKEN": "x",
        "GITHUB_REPOSITORY": REPO,
        chain.KEY_ENV: FALLBACK_KEY,
        "SEALED_DIR": str(sealed),
    }
    # The private repository as it was seeded: a README and an empty folder.
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, env=env)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=seed, check=True, env=env)
    (seed / "README.md").write_text("private\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=seed, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=seed, check=True, env=env)
    subprocess.run(["git", "push", "-q", str(bare), "HEAD:refs/heads/main"], cwd=seed, check=True, env=env)
    # The movement chain as it has stood since 2026-10-02: seeded once, by
    # hand, with the only flag that lets a push start the branch.
    seed_processed = tmp_path / "chain-seed" / "data" / "processed"
    rows = odds_api.normalize_event(
        _event({"DraftKings": (-120, 100), "FanDuel": (-118, -102)}, **SEED_GAME), fetched_at=SEED_AT,
    )
    load_script("capture_line_movement.py").write_round(
        rows, captured_at=SEED_AT, day=SEED_DAY, processed=seed_processed,
    )
    assert chain.main(["push", "--processed-dir", str(seed_processed), "--allow-new-chain"]) == chain.EXIT_OK
    rig = {"root": tmp_path, "bare": bare, "env": env, "sealed": sealed, "seed": seed_processed}
    assert _chain_tip(rig), "the seed did not start the movement branch"
    return rig


def _chain_tip(rig) -> str:
    """The private repository's `movement` branch: its commit, or ""."""
    done = subprocess.run(
        ["git", "--git-dir", str(rig["bare"]), "rev-parse", "--verify", "-q",
         f"refs/heads/{chain.CHAIN_BRANCH}"],
        capture_output=True, text=True, env=rig["env"],
    )
    return done.stdout.strip()


def _lines(path: Path) -> list[str]:
    return sorted(path.read_text(encoding="utf-8").splitlines()) if path.is_file() else []


def _github_down(repo: str, token: str) -> bool:
    raise store.Unreachable("Could not resolve host: api.github.com")


def _keep_sealed_round(rig, temp: Path, *, run_id: int, attempt: int) -> None:
    """"Keep the sealed round" as upload-artifact keeps one file: at the root
    of an artifact called what its `name` says, from where its `path` says."""
    step = _step(LINE_MOVEMENT, SEALED_UPLOAD)
    values = {"runner.temp": str(temp), "github.run_attempt": str(attempt)}
    sealed_file = Path(_render(step["with"]["path"], values))
    assert sealed_file.is_file(), f"{SEALED_UPLOAD} would upload nothing: no {sealed_file}"
    artifacts = rig["sealed"]
    artifact_id = len(list(artifacts.glob("*.zip"))) + 1
    with zipfile.ZipFile(artifacts / f"{artifact_id}.zip", "w") as zipped:
        zipped.write(sealed_file, arcname=sealed_file.name)
    entry = {
        "id": artifact_id, "name": _render(step["with"]["name"], values), "expired": False,
        "created_at": f"{DAY}T{artifact_id:02d}:00:00Z",
        "workflow_run": {"id": run_id, "head_branch": "main", "repository_id": 1, "head_repository_id": 1},
    }
    with (artifacts / "listing.jsonl").open("a", encoding="utf-8") as listing:
        listing.write(json.dumps(entry) + "\n")


def _chain_argv(name: str) -> list[str]:
    """A Line Movement step's own `private_movement_chain.py` arguments."""
    argv = shlex.split(_render(_step(LINE_MOVEMENT, name)["run"]))
    assert argv[:2] == ["python", "scripts/private_movement_chain.py"], name
    return argv[2:]


def _outcome(code: int) -> str:
    """A continue-on-error step's `outcome`: what it exited, before GitHub
    lets the job carry on."""
    return "success" if code == 0 else "failure"


def _line_movement_run(
    rig, monkeypatch, run_id: int, captured_at: str, board: dict, *,
    day_so_far: list[str], push_fails: bool = False, chain_missing: bool = False,
) -> Path:
    """One Line Movement run on a fresh runner: restore, round, private push
    and check, the seal and its upload when either failed, then the two
    gates that read them. `day_so_far` is the day file the restore must lay
    down (sorted lines); `push_fails` cuts the push off from GitHub;
    `chain_missing` says the private repository has no `movement` branch.
    The runner's data/processed."""
    capture = load_script("capture_line_movement.py")
    work = rig["root"] / f"line-movement-{run_id}"
    temp = rig["root"] / f"line-movement-{run_id}-temp"
    work.mkdir()
    temp.mkdir()
    env = {**rig["env"], "RUNNER_TEMP": str(temp), "GITHUB_WORKSPACE": str(work)}
    processed = work / "data" / "processed"

    restore = _bash(_render(_step(LINE_MOVEMENT, RESTORE)["run"]), work, env)
    assert restore.returncode == 0, f"{RESTORE}: {restore.stdout}{restore.stderr}"
    problem = (work / "restore_problem.txt").read_text(encoding="utf-8")
    if chain_missing:
        # A fault, never "no chain yet": the chain is the only copy.
        assert problem == f"{NO_CHAIN} This round's files start from what was on disk.\n", \
            restore.stdout + restore.stderr
    else:
        assert problem == "", restore.stdout + restore.stderr
    # The day so far, before this round appends.
    day_file = capture.capture_path(DAY, processed_dir=processed)
    assert _lines(day_file) == day_so_far, f"run {run_id}'s restore did not lay down the day so far"

    rows = odds_api.normalize_event(_event(board), fetched_at=captured_at)
    capture.write_round(rows, captured_at=captured_at, day=DAY, processed=processed)

    monkeypatch.chdir(work)
    # The push writes its exit to its step's outputs, which the gate reads.
    push_output = work / "push_github_output.txt"
    with monkeypatch.context() as outage:
        outage.setenv("GITHUB_OUTPUT", str(push_output))
        if push_fails:
            outage.setattr(store, "repo_is_private", _github_down)
        pushed = chain.main(_chain_argv(PRIVATE_PUSH))
    recorded = dict(line.split("=", 1) for line in push_output.read_text(encoding="utf-8").splitlines())
    assert recorded == {"exit": str(pushed)}, recorded
    checked = chain.main(_chain_argv(CHECK))
    if chain_missing:
        # No thin chain in its place: the push refuses to start the branch,
        # which stays missing for a person to restore from its history.
        assert (pushed, checked) == (chain.EXIT_REFUSED, chain.EXIT_EMPTY)
        assert not _chain_tip(rig), f"{PRIVATE_PUSH} started a new movement branch holding one round"
    elif push_fails:
        # The tip GitHub could not be asked about lacks this round.
        assert (pushed, checked) == (chain.EXIT_FAILED, chain.EXIT_DAMAGED)
    else:
        assert (pushed, checked) == (chain.EXIT_OK, chain.EXIT_OK), \
            f"{PRIVATE_PUSH} and {CHECK}, with the workflow's arguments, exited {pushed} and {checked}"
    taken = pushed == chain.EXIT_OK and checked == chain.EXIT_OK
    outcomes = {
        "steps.restore.outcome": _outcome(restore.returncode),
        "steps.private_push.outcome": _outcome(pushed),
        "steps.private_push.outputs.exit": recorded["exit"],
        "steps.private_verify.outcome": _outcome(checked),
        "steps.seal.outcome": "skipped",
        "steps.sealed_upload.outcome": "skipped",
        "github.run_attempt": "1",
    }
    # The seal's `if:`: the check decides, not the push.
    if checked != chain.EXIT_OK:
        sealed = _bash(_render(_step(LINE_MOVEMENT, SEAL)["run"]), work, env)
        assert sealed.returncode == 0, f"{SEAL}: {sealed.stdout}{sealed.stderr}"
        outcomes["steps.seal.outcome"] = "success"
        _keep_sealed_round(rig, temp, run_id=run_id, attempt=1)
        outcomes["steps.sealed_upload.outcome"] = "success"

    restore_gate = _bash(_render(_step(LINE_MOVEMENT, RESTORE_GATE)["run"], outcomes), work, env)
    if chain_missing:
        expected_gate = (1, f"::error::{NO_CHAIN} This round's files start from what was on disk. \n")
    else:
        expected_gate = (0, "The previous captures were restored.\n")
    assert (restore_gate.returncode, restore_gate.stdout) == expected_gate, restore_gate.stderr
    chain_gate = _bash(_render(_step(LINE_MOVEMENT, CHAIN_GATE)["run"], outcomes), work, env)
    expected_gate = (0, "") if taken else (1, SEALED_GATE)
    assert (chain_gate.returncode, chain_gate.stdout) == expected_gate, chain_gate.stderr
    return processed


def _closing_lines_run(rig, run_id: int, monkeypatch, *, chain_missing: bool = False) -> None:
    """One Closing Lines run on a fresh checkout: hand-off, then publish.
    With no `movement` branch the hand-off is red, and the publish, whose
    `if:` holds no `always()`, does not run."""
    work = rig["root"] / f"closing-lines-{run_id}"
    work.mkdir()
    output = rig["root"] / f"github-output-{run_id}.txt"
    env = {**rig["env"], "GITHUB_OUTPUT": str(output), "GITHUB_WORKSPACE": str(work)}
    done = _bash(_render(_step(CLOSING_LINES, HANDOFF)["run"]), work, env)
    handed = output.read_text(encoding="utf-8") if output.is_file() else ""
    if chain_missing:
        assert done.returncode == 1, f"{HANDOFF} with no movement branch: {done.stdout}{done.stderr}"
        assert f"::error::{NO_CHAIN}" in done.stdout.splitlines(), done.stdout + done.stderr
        assert "empty=true" not in handed, "a missing chain was handed off as nothing yet"
        return
    assert done.returncode == 0, f"{HANDOFF}: {done.stdout}{done.stderr}"
    # Publish runs only when the hand-off carried rows (its `if:`).
    assert "empty=true" not in handed
    argv = shlex.split(_render(_step(CLOSING_LINES, PUBLISH)["run"]))
    assert argv[:2] == ["python", "scripts/private_closing_store.py"]
    monkeypatch.chdir(work)
    assert store.main(argv[2:]) == store.EXIT_OK


def _day_so_far(*runners: Path) -> list[str]:
    """The day file every runner in `runners` held, as the union keeps it:
    each line once per copy that has it, at most."""
    capture = load_script("capture_line_movement.py")
    kept: Counter = Counter()
    for processed in runners:
        kept |= Counter(_lines(capture.capture_path(DAY, processed_dir=processed)))
    return sorted(kept.elements())


def _rounds(rig, monkeypatch, runs=RUNS, *, closing_after=None, failed_push=()) -> list[Path]:
    """Each Line Movement round, and the Closing Lines run its completion
    triggers (every round's, or only those in `closing_after`). Line
    Movement's runners' folders, in order."""
    runners: list[Path] = []
    for run_id, (captured_at, board) in enumerate(runs, start=1):
        runners.append(_line_movement_run(
            rig, monkeypatch, run_id, captured_at, board,
            day_so_far=_day_so_far(*runners[-1:]), push_fails=run_id in failed_push,
        ))
        if closing_after is None or run_id in closing_after:
            _closing_lines_run(rig, run_id, monkeypatch)
    return runners


def _pull_store(rig) -> Path:
    """The store as Gameday Refresh pulls it, into its runner's temp folder."""
    pulled = rig["root"] / "runner_temp" / "private-closing-store"
    assert store.main(["pull", "--out", str(pulled / cl.CAPTURES_FILENAME)]) == store.EXIT_OK
    return pulled


def _freeze(archive: Path) -> None:
    """The card's morning snapshot of both sides, by the real writer."""
    rows = odds_api.normalize_event(_event(CARD_BOARD), fetched_at="2026-10-15T13:25:00+00:00")
    probabilities = {
        selection_key(SimpleNamespace(**row), market=row["market"],
                      selection=row["selection"], line=row["line"]): 0.55
        for row in rows
    }
    assert fe.write_snapshot(
        odds_api.to_frame(rows), probabilities, key_for=selection_key,
        verdicts_line="", snapshot_date=DAY, now=CARD_AT, archive_dir=archive,
    ) is not None


def _closes(processed: Path, archive: Path, *dirs: Path) -> dict:
    """The close each opinion meets in the union of `dirs`, as the report
    computes it."""
    runner = load_script("run_closing_line_value.py")
    captures = runner.union_of_captures([cl.load_captures(d) for d in dirs])
    rows, _ = cl.clv_rows(runner._opinions(processed, archive), captures)
    return {
        row.selection: (row.closing_odds, row.closing_book, row.closed_at)
        for row in rows.itertuples()
    }


def _clv(pulled: Path, tmp_path: Path) -> tuple[str, dict]:
    """The real report pointed at the pulled store alone, and the closes it used."""
    archive = tmp_path / "archive"
    processed = tmp_path / "gameday" / "data" / "processed"
    processed.mkdir(parents=True)
    _freeze(archive)
    runner = load_script("run_closing_line_value.py")
    code = runner.main(["--processed-dir", str(processed), "--archive-dir", str(archive),
                        "--captures-dir", str(pulled),
                        "--output-dir", str(tmp_path / "outputs"), "--now", REPORT_NOW])
    assert code == 0
    page = (tmp_path / "outputs" / cl.REPORT_FILENAME).read_text(encoding="utf-8")
    return page, _closes(processed, archive, pulled)


def _gameday_clv(rig, name: str = "gameday") -> SimpleNamespace:
    """Gameday Refresh's "Report closing-line value" block as written, on a
    fresh runner: what it exited, what it wrote to $GITHUB_OUTPUT, the page,
    each folder it handed the report (in order), and the runner's
    workspace."""
    root = rig["root"]
    work, temp, handed, archive, output = (
        root / f"{name}-{d}" for d in ("runner", "temp", "handed", "archive", "outputs")
    )
    processed = work / "data" / "processed"
    for d in (processed, temp, handed):
        d.mkdir(parents=True)
    _freeze(archive)
    github_output = root / f"{name}-github-output.txt"
    env = {
        **rig["env"], "RUNNER_TEMP": str(temp), "GITHUB_WORKSPACE": str(work),
        "GITHUB_OUTPUT": str(github_output),
        "CLV_HANDED": str(handed), "CLV_PROCESSED": str(processed),
        "CLV_ARCHIVE": str(archive), "CLV_OUTPUT": str(output), "CLV_NOW": REPORT_NOW,
    }
    done = _bash(_render(_step(GAMEDAY, CLV_STEP)["run"]), work, env)
    page = output / cl.REPORT_FILENAME
    return SimpleNamespace(
        done=done, page=page.read_text(encoding="utf-8") if page.is_file() else "",
        outputs=github_output.read_text(encoding="utf-8") if github_output.is_file() else "",
        handed=sorted(handed.iterdir(), key=lambda d: int(d.name)),
        processed=processed, archive=archive, work=work,
    )


def test_clv_closes_every_opinion_from_the_private_store(rig, tmp_path, monkeypatch) -> None:
    """Three rounds: the first starts the day's file in the chain (which
    already holds an earlier day) and in the store, and the next two merge
    into both. The close is the 21:00 round's best price. It is not the
    14:00 round, and not the face-off round's longer price."""
    _rounds(rig, monkeypatch)

    page, closes = _clv(_pull_store(rig), tmp_path)

    assert MATCHED_BOTH in page
    assert closes == CLOSES


def test_the_first_run_alone_is_a_store_clv_reads(rig, tmp_path, monkeypatch) -> None:
    _rounds(rig, monkeypatch, runs=RUNS[1:2])

    page, closes = _clv(_pull_store(rig), tmp_path)

    assert "matched to a closing price: **2**" in page
    assert closes == CLOSES


def test_the_private_store_is_exactly_what_line_movement_wrote_for_closing(
    rig, monkeypatch
) -> None:
    """Full-record equality with the dedicated store each Line Movement round
    writes on its own runner from the same fetch (`write_round`), which no
    step keeps: the store CLV loads holds the producer's rows, under the
    producer's columns, with the producer's values. It is not a count of
    lines. The chain's seed round, an earlier day's, is published with
    them: Closing Lines publishes every day the chain holds."""
    runners = _rounds(rig, monkeypatch)
    written = pd.concat([pd.read_csv(cl.captures_path(p)) for p in [rig["seed"], *runners]],
                        ignore_index=True)

    def ordered(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.sort_values(["captured_at", "selection"]).reset_index(drop=True)

    loaded = cl.load_captures(_pull_store(rig))
    assert len(loaded) == 2 * (len(RUNS) + 1), "one best-price row per side per round, the seed's too"
    pd.testing.assert_frame_equal(ordered(loaded), ordered(written))


def test_the_report_scores_the_union_when_the_store_lags_the_chain(rig, monkeypatch) -> None:
    """Closing Lines published after the 14:00 round only; Line Movement kept
    all three rounds in the chain. Gameday Refresh's step, as written, pulls
    both and closes every opinion at the 21:00 round. The store it handed the
    report could not have, alone."""
    _rounds(rig, monkeypatch, closing_after={1})

    clv = _gameday_clv(rig)

    assert clv.done.returncode == 0, clv.done.stdout + clv.done.stderr
    assert MATCHED_BOTH in clv.page
    stores = [d for d in clv.handed if (d / cl.CAPTURES_FILENAME).is_file()]
    chains = [d for d in clv.handed if (d / cl.MOVEMENT_DIRNAME).is_dir()]
    assert (len(stores), len(chains)) == (1, 1), "the report was not handed the store and the chain"
    assert _closes(clv.processed, clv.archive, *clv.handed) == CLOSES
    assert _closes(clv.processed, clv.archive, *stores) != CLOSES


def test_a_round_the_private_push_missed_is_sealed_and_still_closes(rig, tmp_path, monkeypatch) -> None:
    """The 21:00 round's push could not reach GitHub, and its check found the
    tip without the round. Its run sealed the round with the fallback key and
    kept it as a sealed artifact, and its gate said so; the 23:00 round's
    restore opened it, that round's push carried it into the chain, Closing
    Lines published it, and CLV closes on it. Lost, no opinion would close:
    the 14:00 round is too far before face-off to count, and the face-off
    round never does."""
    _rounds(rig, monkeypatch, failed_push={2})

    page, closes = _clv(_pull_store(rig), tmp_path)

    assert MATCHED_BOTH in page
    assert closes == CLOSES


def test_a_deleted_chain_is_a_fault_everywhere_and_its_round_still_closes(
    rig, tmp_path, monkeypatch
) -> None:
    """Branch `movement` is deleted after the 14:00 round. The chain is the
    only copy, so a missing branch is never "no chain yet":

    * the 21:00 round's restore names the missing branch and its gate is
      red; the round starts from an empty disk; the push refuses to start a
      new branch holding one round, the check has no chain to check, and the
      round is sealed, as its gate says;
    * Closing Lines' hand-off is red and publishes nothing;
    * Gameday Refresh's CLV step is red (`store_fault=missing-chain`) without
      degrading the run, and names what it scored: the store alone.

    Once the branch is restored from its history, the 23:00 round's restore
    is clean and folds the sealed round in, its push carries it home, and CLV
    closes on the 21:00 round, which only the sealed round held."""
    (first, deleted, last) = RUNS
    round_one = _line_movement_run(rig, monkeypatch, 1, *first, day_so_far=[])
    _closing_lines_run(rig, 1, monkeypatch)
    history = _chain_tip(rig)
    subprocess.run(["git", "--git-dir", str(rig["bare"]), "update-ref", "-d",
                    f"refs/heads/{chain.CHAIN_BRANCH}"], check=True, env=rig["env"])

    round_two = _line_movement_run(rig, monkeypatch, 2, *deleted, day_so_far=[], chain_missing=True)
    _closing_lines_run(rig, 2, monkeypatch, chain_missing=True)
    clv = _gameday_clv(rig, "gameday-no-chain")

    assert clv.done.returncode == 2, clv.done.stdout + clv.done.stderr
    assert ("::error::The private repository has no movement branch; the chain has existed since "
            "2026-10-02, so it was deleted or renamed: restore it from its history; the "
            "closing-line value report scored the store alone.") in clv.done.stdout.splitlines()
    assert clv.outputs == "store_fault=missing-chain\n"
    assert not (clv.work / "run_degraded.txt").exists(), "a missing chain degraded the run"
    assert "matched to a closing price: **0**" in clv.page

    subprocess.run(["git", "--git-dir", str(rig["bare"]), "update-ref",
                    f"refs/heads/{chain.CHAIN_BRANCH}", history], check=True, env=rig["env"])
    _line_movement_run(rig, monkeypatch, 3, *last, day_so_far=_day_so_far(round_one, round_two))
    _closing_lines_run(rig, 3, monkeypatch)

    page, closes = _clv(_pull_store(rig), tmp_path)
    assert MATCHED_BOTH in page
    assert closes == CLOSES
