"""A test promised that CLV reads the handed-over store, and it never read it.

In tests/test_the_closing_prices_reach_the_clv_store.py,
`test_the_store_format_is_the_one_clv_reads` said "The hand-off carries what
`best_prices` writes, which `load_captures` reads." It never called
`load_captures`. The failure-shape audit found this (finding 87): `load_captures`
raising, ignoring the store, `CAPTURE_COLUMNS` losing `captured_at`, and
`best_prices` writing decimal odds each took CLV from 1 of 1 matched to 0 of 1,
and that test passed under all four. A later round found the same hole one
writer further on: a merge that renamed `captured_at` matched 0 of 1 and the
whole suite stayed green, because the hand-off tests counted lines.

So these tests run the chain the way production does. Since 2026-10-01 the
store is the private repository cooperross399/nhl-closing-lines, and the
chain is:

1. Line Movement's own writes (`capture_line_movement.write_round`), on rows
   from the real `normalize_event`, into the day file its `line-movement`
   artifact carries. Each run restores the day so far and appends its round.
2. Closing Lines' hand-off `run:` block as written, under the shell GitHub
   uses, with `gh` a stub that unpacks that artifact.
3. Closing Lines' publish: `scripts/private_closing_store.py push` with the
   workflow's exact arguments, against a local bare repository reached
   through the real URL the script builds. Only the GitHub API's privacy
   answer is replaced.
4. Gameday Refresh's read: `private_closing_store.py pull` into a temp
   directory, then the real `run_closing_line_value.main` pointed at it,
   scoring opinions frozen by the real `write_snapshot`.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
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

CLOSING_LINES = PROJECT_ROOT / ".github" / "workflows" / "closing-lines.yml"
HANDOFF = "Take the captures Line Movement kept"
PUBLISH = "Publish to the private store"
REPO = "owner/lab"
TOKEN = "rehearsal-token"

DAY = "2026-10-15"
START = f"{DAY}T23:00:00Z"  # 19:00 ET
CARD_AT = datetime(2026, 10, 15, 13, 30, tzinfo=timezone.utc)  # 09:30 ET
PLAYER = "Auston Matthews"

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


def _block(name: str) -> str:
    (job,) = yaml.safe_load(CLOSING_LINES.read_text(encoding="utf-8"))["jobs"].values()
    (step,) = [step for step in job["steps"] if step.get("name") == name]
    block = step["run"].replace("${{ github.repository }}", REPO)
    assert "${{" not in block, f"{name!r} reads an expression this test does not supply"
    return block


@pytest.fixture
def rig(tmp_path, monkeypatch):
    if not (shutil.which("git") and shutil.which("bash")):
        pytest.fail("this test needs git and bash, which every runner here has")
    home, bare, stub, seed = (tmp_path / d for d in ("home", "private.git", "bin", "seed"))
    for d in (home, stub, seed):
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
    monkeypatch.setattr(store, "repo_is_private", lambda repo, token: repo == store.PRIVATE_REPO)
    monkeypatch.setattr(store, "utc_now", lambda: datetime(2026, 10, 16, 2, tzinfo=timezone.utc))
    env = {**os.environ, "GH_TOKEN": "x", "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
    # The private repository as it was seeded: a README and an empty folder.
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, env=env)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=seed, check=True, env=env)
    (seed / "README.md").write_text("private\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=seed, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=seed, check=True, env=env)
    subprocess.run(["git", "push", "-q", str(bare), "HEAD:refs/heads/main"], cwd=seed, check=True, env=env)
    # `gh run download --name line-movement --dir D` unpacks the artifact
    # into D, rooted where line-movement.yml roots it.
    (stub / "gh").write_text(
        "#!/bin/bash\n"
        'if [ "$1" = api ]; then echo 1; exit 0; fi\n'
        'if [ "$1" = run ] && [ "$2" = download ]; then\n'
        '  while [ $# -gt 0 ]; do [ "$1" = --dir ] && dir="$2"; shift; done\n'
        '  mkdir -p "$dir" && cp -R "$KEPT_DIR/." "$dir/"; exit $?\n'
        "fi\nexit 2\n"
    )
    (stub / "gh").chmod(0o755)
    return {"root": tmp_path, "bare": bare, "env": env}


def _closing_lines_run(rig, kept: Path, run_id: int, monkeypatch) -> None:
    """One Closing Lines run on a fresh checkout: hand-off, then publish."""
    work = rig["root"] / f"closing-lines-{run_id}"
    work.mkdir()
    output = rig["root"] / f"github-output-{run_id}.txt"
    env = {**rig["env"], "RUN_ID": str(run_id), "GITHUB_OUTPUT": str(output),
           "KEPT_DIR": str(kept)}
    done = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _block(HANDOFF)],
        cwd=work, env=env, capture_output=True, text=True,
    )
    assert done.returncode == 0, f"{HANDOFF}: {done.stdout}{done.stderr}"
    # Publish runs only when the hand-off carried rows (its `if:`).
    assert "empty=true" not in (output.read_text() if output.is_file() else "")
    argv = shlex.split(_block(PUBLISH))
    assert argv[:2] == ["python", "scripts/private_closing_store.py"]
    monkeypatch.chdir(work)
    assert store.main(argv[2:]) == store.EXIT_OK


def _publish(rig, monkeypatch, runs=RUNS) -> tuple[Path, Path]:
    """Each Line Movement round kept and published, then pulled as Gameday
    Refresh pulls it. The pulled store's folder, and Line Movement's runner."""
    capture = load_script("capture_line_movement.py")
    line_movement = rig["root"] / "line-movement" / "data" / "processed"
    for run_id, (captured_at, board) in enumerate(runs, start=1):
        rows = odds_api.normalize_event(_event(board), fetched_at=captured_at)
        capture.write_round(rows, captured_at=captured_at, day=DAY, processed=line_movement)
        # The artifact this run keeps: its line_movement folder, as uploaded.
        kept = rig["root"] / f"kept-{run_id}"
        shutil.copytree(line_movement / cl.MOVEMENT_DIRNAME, kept / cl.MOVEMENT_DIRNAME)
        _closing_lines_run(rig, kept, run_id, monkeypatch)
    pulled = rig["root"] / "runner_temp" / "private-closing-store"
    assert store.main(["pull", "--out", str(pulled / cl.CAPTURES_FILENAME)]) == store.EXIT_OK
    return pulled, line_movement


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


def _clv(pulled: Path, tmp_path: Path) -> tuple[str, dict]:
    """Gameday Refresh's CLV step on the pulled store, and the closes it used."""
    archive = tmp_path / "archive"
    processed = tmp_path / "gameday" / "data" / "processed"
    processed.mkdir(parents=True)
    _freeze(archive)
    runner = load_script("run_closing_line_value.py")
    code = runner.main(["--processed-dir", str(processed), "--archive-dir", str(archive),
                        "--captures-dir", str(pulled),
                        "--output-dir", str(tmp_path / "outputs"),
                        # After every game here: unplayed games are left out.
                        "--now", "2027-06-01T00:00:00+00:00"])
    assert code == 0
    page = (tmp_path / "outputs" / cl.REPORT_FILENAME).read_text(encoding="utf-8")
    rows, _ = cl.clv_rows(runner._opinions(processed, archive), cl.load_captures(pulled))
    closes = {
        row.selection: (row.closing_odds, row.closing_book, row.closed_at)
        for row in rows.itertuples()
    }
    return page, closes


def test_clv_closes_every_opinion_from_the_private_store(rig, tmp_path, monkeypatch) -> None:
    """Three runs: the first establishes the store's day file and the next two
    merge into it. The close is the 21:00 run's best price. It is not the
    14:00 run, and not the face-off run's longer price."""
    pulled, _ = _publish(rig, monkeypatch)

    page, closes = _clv(pulled, tmp_path)

    assert "matched to a closing price: **2**; no closing price found: **0**" in page
    assert closes == CLOSES


def test_the_first_run_alone_is_a_store_clv_reads(rig, tmp_path, monkeypatch) -> None:
    pulled, _ = _publish(rig, monkeypatch, runs=RUNS[1:2])

    page, closes = _clv(pulled, tmp_path)

    assert "matched to a closing price: **2**" in page
    assert closes == CLOSES


def test_the_private_store_is_exactly_what_line_movement_wrote_for_closing(
    rig, monkeypatch
) -> None:
    """Full-record equality with the dedicated store Line Movement writes on
    its own runner from the same fetch (`write_round`), which is never
    published: the store CLV loads holds the producer's rows, under the
    producer's columns, with the producer's values. It is not a count of
    lines."""
    pulled, line_movement = _publish(rig, monkeypatch)
    written = pd.read_csv(cl.captures_path(line_movement))

    def ordered(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.sort_values(["captured_at", "selection"]).reset_index(drop=True)

    loaded = cl.load_captures(pulled)
    assert len(loaded) == 2 * len(RUNS), "one best-price row per side per run"
    pd.testing.assert_frame_equal(ordered(loaded), ordered(written))
