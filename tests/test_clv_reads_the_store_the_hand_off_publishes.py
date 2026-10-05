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
`movement`, the closing-line store on `main`. The chain is:

1. Line Movement, one run per round, each on a fresh runner: its "Restore
   today's captures" block as written, under the shell GitHub uses (the real
   `private_movement_chain.py pull` and `unseal`; `gh` is a stub that lists
   the sealed rounds this test kept); its round, written by the real
   `capture_line_movement.write_round` on rows from the real
   `normalize_event`; then "Keep the captures privately" with the workflow's
   exact arguments. A round whose push fails runs "Seal this round when the
   private push failed" as written, and its upload is modelled from "Keep the
   sealed round"'s own `name` and `path`.
2. Closing Lines' hand-off block as written, pulling the chain from
   `movement` onto its runner.
3. Closing Lines' publish: `private_closing_store.py push` with the
   workflow's exact arguments.
4. Gameday Refresh: the store pulled, and the real `run_closing_line_value`
   pointed at it alone, scoring opinions frozen by the real `write_snapshot`.
   Where the union of store and chain matters, its "Report closing-line
   value" block runs as written, with both real pulls and the real report;
   only a runner's own folders and clock are appended to the report's
   arguments.

The private repository is a local bare repository reached through the real
URL the scripts build. Only the GitHub API's privacy answer is replaced, so
the pushes run in process; the pulls, the seal and the unseal run as the
steps run them. Every script gets its step's own arguments, relative paths
included, from the runner's working directory. The steps' `if:` conditions
are not evaluated here: each scenario runs the steps it reaches.

Until 2026-10-05 the hand-off unpacked Line Movement's public
`line-movement` artifact with `gh run download`; that artifact and the
re-run fold (`restore_state.py --fold-run`) are gone. A re-run's second
attempt runs the same restore block as the next round, which folds in every
unexpired sealed round, so the sealed-round test below covers that path too.
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
SEAL = "Seal this round when the private chain did not take it"
SEALED_UPLOAD = "Keep the sealed round"
HANDOFF = "Take the chain from the private repository"
PUBLISH = "Publish to the private store"
CLV_STEP = "Report closing-line value"
REPO = "owner/lab"
TOKEN = "rehearsal-token"
FALLBACK_KEY = "rehearsal-fallback-key"

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


def _event(board: dict[str, tuple[int, int]]) -> dict:
    """One provider event payload, every book quoting both sides."""
    return {
        "id": "evt1", "commence_time": START,
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "bookmakers": [
            {"key": book.lower(), "title": book, "markets": [{
                "key": "player_shots_on_goal",
                "outcomes": [
                    {"name": "Over", "description": PLAYER, "price": over, "point": 2.5},
                    {"name": "Under", "description": PLAYER, "price": under, "point": 2.5},
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
    return {"root": tmp_path, "bare": bare, "env": env, "sealed": sealed}


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


def _line_movement_run(
    rig, monkeypatch, run_id: int, captured_at: str, board: dict, *,
    previous: Path | None, push_fails: bool = False,
) -> Path:
    """One Line Movement run on a fresh runner: restore, round, private push
    (and the seal, when the push fails). The runner's data/processed."""
    capture = load_script("capture_line_movement.py")
    work = rig["root"] / f"line-movement-{run_id}"
    temp = rig["root"] / f"line-movement-{run_id}-temp"
    work.mkdir()
    temp.mkdir()
    env = {**rig["env"], "RUNNER_TEMP": str(temp), "GITHUB_WORKSPACE": str(work)}
    processed = work / "data" / "processed"

    restore = _bash(_render(_step(LINE_MOVEMENT, RESTORE)["run"]), work, env)
    assert restore.returncode == 0, f"{RESTORE}: {restore.stdout}{restore.stderr}"
    assert (work / "restore_problem.txt").read_text(encoding="utf-8") == "", restore.stdout + restore.stderr
    # The day so far, as the previous round left it, before this round appends.
    day_file = capture.capture_path(DAY, processed_dir=processed)
    expected = _lines(capture.capture_path(DAY, processed_dir=previous)) if previous else []
    assert _lines(day_file) == expected, f"run {run_id}'s restore did not lay down the day so far"

    rows = odds_api.normalize_event(_event(board), fetched_at=captured_at)
    capture.write_round(rows, captured_at=captured_at, day=DAY, processed=processed)

    argv = shlex.split(_render(_step(LINE_MOVEMENT, PRIVATE_PUSH)["run"]))
    assert argv[:2] == ["python", "scripts/private_movement_chain.py"]
    monkeypatch.chdir(work)
    with monkeypatch.context() as outage:
        if push_fails:
            outage.setattr(store, "repo_is_private", _github_down)
        pushed = chain.main(argv[2:])
    if not push_fails:
        assert pushed == chain.EXIT_OK, f"{PRIVATE_PUSH}, with the workflow's arguments, exited {pushed}"
        return processed
    assert pushed != chain.EXIT_OK
    sealed = _bash(_render(_step(LINE_MOVEMENT, SEAL)["run"]), work, env)
    assert sealed.returncode == 0, f"{SEAL}: {sealed.stdout}{sealed.stderr}"
    _keep_sealed_round(rig, temp, run_id=run_id, attempt=1)
    return processed


def _closing_lines_run(rig, run_id: int, monkeypatch) -> None:
    """One Closing Lines run on a fresh checkout: hand-off, then publish."""
    work = rig["root"] / f"closing-lines-{run_id}"
    work.mkdir()
    output = rig["root"] / f"github-output-{run_id}.txt"
    env = {**rig["env"], "GITHUB_OUTPUT": str(output), "GITHUB_WORKSPACE": str(work)}
    done = _bash(_render(_step(CLOSING_LINES, HANDOFF)["run"]), work, env)
    assert done.returncode == 0, f"{HANDOFF}: {done.stdout}{done.stderr}"
    # Publish runs only when the hand-off carried rows (its `if:`).
    assert "empty=true" not in (output.read_text() if output.is_file() else "")
    argv = shlex.split(_render(_step(CLOSING_LINES, PUBLISH)["run"]))
    assert argv[:2] == ["python", "scripts/private_closing_store.py"]
    monkeypatch.chdir(work)
    assert store.main(argv[2:]) == store.EXIT_OK


def _rounds(rig, monkeypatch, runs=RUNS, *, closing_after=None, failed_push=()) -> list[Path]:
    """Each Line Movement round, and the Closing Lines run its completion
    triggers (every round's, or only those in `closing_after`). Line
    Movement's runners' folders, in order."""
    runners: list[Path] = []
    for run_id, (captured_at, board) in enumerate(runs, start=1):
        runners.append(_line_movement_run(
            rig, monkeypatch, run_id, captured_at, board,
            previous=runners[-1] if runners else None, push_fails=run_id in failed_push,
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


def _gameday_clv(rig) -> SimpleNamespace:
    """Gameday Refresh's "Report closing-line value" block as written, on a
    fresh runner: what it exited, the page, and each folder it handed the
    report, in order."""
    root = rig["root"]
    work, temp, handed, archive, output = (
        root / d for d in ("gameday-runner", "gameday-temp", "gameday-handed",
                           "gameday-archive", "gameday-outputs")
    )
    processed = work / "data" / "processed"
    for d in (processed, temp, handed):
        d.mkdir(parents=True)
    _freeze(archive)
    env = {
        **rig["env"], "RUNNER_TEMP": str(temp), "GITHUB_WORKSPACE": str(work),
        "GITHUB_OUTPUT": str(root / "gameday-github-output.txt"),
        "CLV_HANDED": str(handed), "CLV_PROCESSED": str(processed),
        "CLV_ARCHIVE": str(archive), "CLV_OUTPUT": str(output), "CLV_NOW": REPORT_NOW,
    }
    done = _bash(_render(_step(GAMEDAY, CLV_STEP)["run"]), work, env)
    page = output / cl.REPORT_FILENAME
    return SimpleNamespace(
        done=done, page=page.read_text(encoding="utf-8") if page.is_file() else "",
        handed=sorted(handed.iterdir(), key=lambda d: int(d.name)),
        processed=processed, archive=archive,
    )


def test_clv_closes_every_opinion_from_the_private_store(rig, tmp_path, monkeypatch) -> None:
    """Three rounds: the first establishes the chain's day file and the
    store's, and the next two merge into both. The close is the 21:00
    round's best price. It is not the 14:00 round, and not the face-off
    round's longer price."""
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
    lines."""
    runners = _rounds(rig, monkeypatch)
    written = pd.concat([pd.read_csv(cl.captures_path(p)) for p in runners], ignore_index=True)

    def ordered(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.sort_values(["captured_at", "selection"]).reset_index(drop=True)

    loaded = cl.load_captures(_pull_store(rig))
    assert len(loaded) == 2 * len(RUNS), "one best-price row per side per run"
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
    """The 21:00 round's push could not reach GitHub. Its run sealed the round
    with the fallback key and kept it as a sealed artifact; the 23:00 round's
    restore opened it, that round's push carried it into the chain, Closing
    Lines published it, and CLV closes on it. Lost, no opinion would close:
    the 14:00 round is too far before face-off to count, and the face-off
    round never does."""
    _rounds(rig, monkeypatch, failed_push={2})

    page, closes = _clv(_pull_store(rig), tmp_path)

    assert MATCHED_BOTH in page
    assert closes == CLOSES
