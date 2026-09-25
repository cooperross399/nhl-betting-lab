"""A test promised that CLV reads the handed-over store, and it never read it.

In tests/test_the_closing_prices_reach_the_clv_store.py,
`test_the_store_format_is_the_one_clv_reads` says "The hand-off carries what
`best_prices` writes, which `load_captures` reads." It never called
`load_captures`. It checked that `best_prices` returns the columns in
`CAPTURE_COLUMNS`, and `best_prices` projects onto exactly that constant. It
also ran a regex on the file name. The failure-shape audit found this (finding
87, confirmed by two of three refuters). One refuter drove the real chain and
broke it four ways:

* `load_captures` raised whenever it was called;
* `load_captures` ignored the handed-over store;
* `CAPTURE_COLUMNS` lost `captured_at`;
* `best_prices` wrote decimal odds into `american_odds`.

Each one took CLV from 1 of 1 opinions matched to 0 of 1, or a crash. That
test passed under all four.

Re-derived on d418e57. Since the audit, #156 added tests that run the real
producer (`best_prices`, then `append_captures`) into the real reader
(`run_closing_line_value.main`, which calls `load_captures` and
`closing_prices`). Those tests kill nine producer and reader mutants,
including the four above. But they skip the writer of the file CLV actually
reads. On every hand-off after the first, Gameday Refresh restores a file
written by `scripts/merge_capture_store.py`, which Closing Lines' "Publish the
store" step runs. `append_captures` did not write that file. A merge that
wrote `captured_at` under another name made the real chain match 0 of 1
opinions, and the whole suite still passed, 2197 of 2197. The executed hand-off
tests count the lines of the branch file, and a renamed column keeps every
line.

So these tests run the chain the way production does:

1. Line Movement's own writes (`capture_line_movement.py:110-111` and
   `:132-133`), on rows from the real `normalize_event`. Each run hands over
   only its own rows.
2. The hand-off and publish `run:` blocks from closing-lines.yml, run as
   written under the shell GitHub uses. `gh` is a stub, and the branch is a
   local bare repository.
3. The branch file restored the way Gameday Refresh restores it: `git show`
   of the tip's blob.
4. The real `run_closing_line_value.main`, scoring opinions frozen by the real
   `write_snapshot`.
"""

from __future__ import annotations

import os
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


CLOSING_LINES = PROJECT_ROOT / ".github" / "workflows" / "closing-lines.yml"
HANDOFF = "Take the closing prices Line Movement handed over"
PUBLISH = "Publish the store"
REPO = "owner/lab"
TOKEN = "rehearsal-token"
BRANCH_FILE = f"refs/heads/closing-lines:{cl.CAPTURES_FILENAME}"

DAY = "2026-10-15"
START = f"{DAY}T23:00:00Z"  # 19:00 ET
CARD_AT = datetime(2026, 10, 15, 13, 30, tzinfo=timezone.utc)  # 09:30 ET
PLAYER = "Auston Matthews"

# Shots on goal 2.5, (over, under) by book. The opinion is a prop because Line
# Movement asks for the per-event markets only: a moneyline never closes here.
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


def _line_movement_run(runner: Path, captured_at: str, board) -> Path:
    """What one Line Movement run writes to the file it hands over.

    `capture_line_movement.py:110-111` and `:132-133` on the real functions.
    The script itself needs --live, which no test may pass. The runner starts
    with no dedicated store: the artifact is "this run's rows only".
    """
    frame = pd.DataFrame(odds_api.normalize_event(_event(board), fetched_at=captured_at))
    frame["captured_at"] = captured_at
    cl.append_captures(cl.best_prices(frame, captured_at=captured_at), processed_dir=runner)
    return cl.captures_path(runner)


def _block(name: str) -> str:
    (job,) = yaml.safe_load(CLOSING_LINES.read_text(encoding="utf-8"))["jobs"].values()
    (step,) = [step for step in job["steps"] if step.get("name") == name]
    block = step["run"].replace("${{ github.repository }}", REPO)
    assert "${{" not in block, f"{name!r} reads an expression this test does not supply"
    return block


@pytest.fixture
def rig(tmp_path):
    if not (shutil.which("git") and shutil.which("bash")):
        pytest.fail("this test needs git and bash, which every runner here has")
    home, bare, stub = (tmp_path / d for d in ("home", "remote.git", "bin"))
    home.mkdir()
    stub.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GH_TOKEN": TOKEN,
        "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
    }
    for command in (
        ["git", "init", "-q", "--bare", str(bare)],
        ["git", "config", "--global", f"url.file://{bare}.insteadOf",
         f"https://x-access-token:{TOKEN}@github.com/{REPO}"],
    ):
        subprocess.run(command, cwd=tmp_path, env=env, check=True)
    (stub / "python").write_text(f'#!/bin/bash\nexec "{sys.executable}" "$@"\n')
    # The artifact holds the one file Line Movement uploaded; `gh run
    # download` puts it in --dir under its own name.
    (stub / "gh").write_text(
        "#!/bin/bash\n"
        'if [ "$1" = api ]; then echo 1; exit 0; fi\n'
        'if [ "$1" = run ] && [ "$2" = download ]; then\n'
        '  while [ $# -gt 0 ]; do [ "$1" = --dir ] && dir="$2"; shift; done\n'
        f'  mkdir -p "$dir" && cp "$HANDED_FILE" "$dir/{cl.CAPTURES_FILENAME}"; exit $?\n'
        "fi\nexit 2\n"
    )
    for tool in ("python", "gh"):
        (stub / tool).chmod(0o755)
    return {"root": tmp_path, "bare": bare, "env": env}


def _closing_lines_run(rig, handed: Path, run_id: int) -> None:
    """One Closing Lines run on a fresh checkout: hand-off, then publish."""
    work = rig["root"] / f"closing-lines-{run_id}"
    work.mkdir()
    shutil.copytree(PROJECT_ROOT / "scripts", work / "scripts")
    (work / "src").symlink_to(PROJECT_ROOT / "src")
    output = rig["root"] / f"github-output-{run_id}.txt"
    env = {**rig["env"], "RUN_ID": str(run_id), "GITHUB_OUTPUT": str(output),
           "HANDED_FILE": str(handed)}
    subprocess.run(["git", "init", "-q"], cwd=work, env=env, check=True)
    for name in (HANDOFF, PUBLISH):
        done = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _block(name)],
            cwd=work, env=env, capture_output=True, text=True,
        )
        assert done.returncode == 0, f"{name}: {done.stdout}{done.stderr}"
        # Publish runs only when the hand-off carried rows (its `if:`).
        assert "empty=true" not in (output.read_text() if output.is_file() else "")


def _publish(rig, runs=RUNS) -> Path:
    """Each run handed over and published, then restored as Gameday Refresh does."""
    for run_id, (captured_at, board) in enumerate(runs, start=1):
        handed = _line_movement_run(rig["root"] / f"line-movement-{run_id}",
                                    captured_at, board)
        _closing_lines_run(rig, handed, run_id)
    processed = rig["root"] / "gameday" / "data" / "processed"
    processed.mkdir(parents=True)
    shown = subprocess.run(["git", "--git-dir", str(rig["bare"]), "show", BRANCH_FILE],
                           capture_output=True, check=True)
    cl.captures_path(processed).write_bytes(shown.stdout)
    return processed


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


def _clv(processed: Path, tmp_path: Path) -> tuple[str, dict]:
    """Gameday Refresh's CLV step on the restored store, and the closes it used."""
    archive = tmp_path / "archive"
    _freeze(archive)
    runner = load_script("run_closing_line_value.py")
    code = runner.main(["--processed-dir", str(processed), "--archive-dir", str(archive),
                        "--output-dir", str(tmp_path / "outputs")])
    assert code == 0
    page = (tmp_path / "outputs" / cl.REPORT_FILENAME).read_text(encoding="utf-8")
    rows, _ = cl.clv_rows(runner._opinions(processed, archive), cl.load_captures(processed))
    closes = {
        row.selection: (row.closing_odds, row.closing_book, row.closed_at)
        for row in rows.itertuples()
    }
    return page, closes


def test_clv_closes_every_opinion_from_the_store_the_hand_offs_published(
    rig, tmp_path
) -> None:
    """Three runs: the first establishes the branch and the next two merge
    into it. The close is the 21:00 run's best price. It is not the 14:00
    run, and not the face-off run's longer price."""
    processed = _publish(rig)

    page, closes = _clv(processed, tmp_path)

    assert "matched to a closing price: **2**; no closing price found: **0**" in page
    assert closes == CLOSES


def test_the_first_hand_off_alone_is_a_store_clv_reads(rig, tmp_path) -> None:
    """With no branch yet, the published file is the artifact as handed over,
    not merged. That is what `best_prices` and `append_captures` wrote, and
    what the audited test promised `load_captures` reads."""
    processed = _publish(rig, runs=RUNS[1:2])

    page, closes = _clv(processed, tmp_path)

    assert "matched to a closing price: **2**" in page
    assert closes == CLOSES


def test_the_published_store_is_every_row_line_movement_handed_over(rig) -> None:
    """Full-record equality: the store CLV loads holds the producer's rows,
    under the producer's columns, with the producer's values. It is not a
    count of lines."""
    processed = _publish(rig)
    handed = pd.concat(
        [pd.read_csv(cl.captures_path(rig["root"] / f"line-movement-{run_id}"))
         for run_id in range(1, len(RUNS) + 1)],
        ignore_index=True,
    )

    def ordered(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.sort_values(["captured_at", "selection"]).reset_index(drop=True)

    loaded = cl.load_captures(processed)
    assert len(loaded) == 2 * len(RUNS), "one best-price row per side per run"
    pd.testing.assert_frame_equal(ordered(loaded), ordered(handed))
