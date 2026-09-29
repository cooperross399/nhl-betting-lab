"""A red run's frozen snapshot that one restore could not download is laid back
by the next one, and the first opinion of the day still stands.

Sweep 4 (restore_state.py `_fill_from_last_success`). The 13:30 Gameday
Refresh run R2 is degraded, so red; it still froze and posted 2026-10-07's
snapshot and uploaded its state. The 15:00 backup's restore gets HTTP 502 on
all three downloads of R2's artifact, records the problem (so the backup is
red too) and restores the success before it. The backup finds no 2026-10-07
snapshot and freezes its own 15:00 opinion under the same name. The next
day's restore takes the backup (the newest carrier) and, because it is red,
lays "the last successful state" underneath — and the fill skipped every run
that was not a success, so R2 was never asked for again: its posted opinion
never reached the forward ledger, and the backup's later one settled in its
place. The workflow comment and the health step's note both promised the
missed snapshot comes back; that held only when the missed run was green,
and the backup runs only after a red primary.

So every carrier between the restored run and the newest success is now laid
underneath, newest first, and for a snapshot both copies hold, the older
carrier's copy — frozen first, since runs are serialised and a run that had
restored it would hold the same file — replaces the newer one unless the day
has already settled here.

The gh stand-in is replaced in-process (`restore_state._gh`), as the
restore's unit tests elsewhere in this directory do with a subprocess fake.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from nhl_betting_lab.config import PROJECT_ROOT


SPEC = importlib.util.spec_from_file_location(
    "restore_state_under_test", PROJECT_ROOT / "scripts" / "restore_state.py")
rs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rs)

SNAP = Path("archive") / "priced_snapshots"
LEDGER = Path("processed") / "forward_evidence.csv"
REFRESH = "gameday-refresh.yml"


def _run(run_id: int, conclusion: str) -> dict:
    return {"databaseId": run_id, "conclusion": conclusion,
            "status": "completed", "headBranch": "main"}


class FakeGh:
    """`gh run list` answers `runs`; `gh run download` lays `artifacts[id]`
    ({relative path: text}) or fails with a 502 for a run in `broken`."""

    def __init__(self, runs, artifacts, broken=()):
        self.runs, self.artifacts, self.broken = runs, artifacts, set(broken)
        self.downloads: list[int] = []

    def __call__(self, *args):
        if args[:2] == ("run", "list"):
            return subprocess.CompletedProcess(args, 0, json.dumps(self.runs), "")
        if args[:2] == ("run", "download"):
            run_id = int(args[2])
            self.downloads.append(run_id)
            dest = Path(args[args.index("--dir") + 1])
            if run_id in self.broken:
                return subprocess.CompletedProcess(
                    args, 1, "", "error downloading gameday-state: HTTP 502: Bad Gateway")
            held = self.artifacts.get(run_id)
            if not held:
                return subprocess.CompletedProcess(
                    args, 1, "", "no valid artifacts found to download")
            for rel, text in held.items():
                path = dest / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)


def _restore(monkeypatch, dest: Path, gh: FakeGh) -> dict:
    monkeypatch.setattr(rs, "_gh", gh)
    return rs.restore(artifact="gameday-state", dest=dest, workflows=[REFRESH],
                      attempts=3)


def _held(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


def _snap(day: str) -> str:
    return (SNAP / f"{day}.csv").as_posix()


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setenv("RESTORE_STATE_RETRY_SECONDS", "0")


def _the_backup_missed_the_primary(tmp_path, monkeypatch) -> dict[int, dict]:
    """S3 (success) froze 10-06. R2 (red primary, 13:30) froze and posted
    10-07. The backup R1's download of R2 502s three times; it restores S3,
    freezes its own 15:00 opinion as 10-07, and uploads."""
    artifacts = {
        3: {_snap("2026-10-06"): "d0\n", LEDGER.as_posix(): "h\n"},
        2: {_snap("2026-10-06"): "d0\n", _snap("2026-10-07"): "primary 13:30\n",
            LEDGER.as_posix(): "h\n", "raw/nhl/boxscore/2.json": "r2\n"},
    }
    backup = tmp_path / "backup"
    report = _restore(monkeypatch, backup,
                      FakeGh([_run(2, "failure"), _run(3, "success")], artifacts,
                             broken={2}))
    assert report["run"] == 3 and report["unreached"], report
    (backup / SNAP / "2026-10-07.csv").write_text("backup 15:00\n", encoding="utf-8")
    artifacts[1] = _held(backup)
    return artifacts


def test_the_primarys_snapshot_the_backup_missed_comes_back_and_stands(
    tmp_path, monkeypatch,
) -> None:
    artifacts = _the_backup_missed_the_primary(tmp_path, monkeypatch)
    nextday = tmp_path / "nextday"
    gh = FakeGh([_run(1, "failure"), _run(2, "failure"), _run(3, "success")],
                artifacts)
    report = _restore(monkeypatch, nextday, gh)

    assert report["run"] == 1 and report["unreached"] == [], report
    assert 2 in gh.downloads, "the red run the backup passed over was never asked for"
    assert (nextday / SNAP / "2026-10-07.csv").read_text(encoding="utf-8") == (
        "primary 13:30\n"
    ), "the backup's later opinion stood in place of the primary's posted one"
    assert (nextday / "raw/nhl/boxscore/2.json").is_file(), (
        "what only the passed-over red run carried was not laid underneath")
    assert report["filled_from"] == 3


def test_a_day_already_settled_here_keeps_the_snapshot_it_settled(
    tmp_path, monkeypatch,
) -> None:
    """Replacing a settled day's snapshot would leave the ledger holding one
    opinion and the archive another; the settled one stays."""
    artifacts = _the_backup_missed_the_primary(tmp_path, monkeypatch)
    artifacts[1][(SNAP / "2026-10-07.settled").as_posix()] = ""
    nextday = tmp_path / "nextday"
    _restore(monkeypatch, nextday,
             FakeGh([_run(1, "failure"), _run(2, "failure"), _run(3, "success")],
                    artifacts))

    assert (nextday / SNAP / "2026-10-07.csv").read_text(encoding="utf-8") == (
        "backup 15:00\n")


def test_a_newer_file_that_is_not_a_snapshot_is_never_overwritten(
    tmp_path, monkeypatch,
) -> None:
    """The first-opinion rule is for snapshots only: a red run's cache and
    card stay the restored run's, as the fill has always laid them."""
    artifacts = {
        1: {"outputs/gameday_card.json": "newest\n", _snap("2026-10-08"): "r1\n"},
        2: {"outputs/gameday_card.json": "older\n", _snap("2026-10-07"): "r2\n"},
        3: {"outputs/gameday_card.json": "success\n"},
    }
    dest = tmp_path / "dest"
    _restore(monkeypatch, dest,
             FakeGh([_run(1, "failure"), _run(2, "failure"), _run(3, "success")],
                    artifacts))

    assert (dest / "outputs/gameday_card.json").read_text(encoding="utf-8") == "newest\n"
    assert (dest / SNAP / "2026-10-07.csv").read_text(encoding="utf-8") == "r2\n"


def test_an_older_success_snapshot_wins_over_a_red_runs_later_freeze(
    tmp_path, monkeypatch,
) -> None:
    """The same rule for the success laid underneath, which the fill used to
    lay with the newer copy winning."""
    artifacts = {
        1: {_snap("2026-10-07"): "later\n"},
        3: {_snap("2026-10-07"): "first\n"},
    }
    dest = tmp_path / "dest"
    _restore(monkeypatch, dest,
             FakeGh([_run(1, "failure"), _run(3, "success")], artifacts))

    assert (dest / SNAP / "2026-10-07.csv").read_text(encoding="utf-8") == "first\n"


def _a_passed_over_red_run_that_502s() -> FakeGh:
    artifacts = {1: {_snap("2026-10-08"): "r1\n"}, 2: {_snap("2026-10-07"): "r2\n"},
                 3: {_snap("2026-10-06"): "s3\n"}}
    return FakeGh([_run(1, "failure"), _run(2, "failure"), _run(3, "success")],
                  artifacts, broken={2})


def test_a_passed_over_red_run_that_cannot_be_downloaded_is_a_warning_not_red(
    tmp_path, monkeypatch, capsys,
) -> None:
    """Named, but not recorded as unreached: recorded, the run went red, the
    15:00 backup fired, and one artifact that never downloads again would
    have made every primary red and fired every backup (a few hundred credits
    a run) until it expired 90 days later. It is written into the state for
    the next restores to ask for again, and the ledger waits for it
    (tests/test_a_passed_over_red_run_is_asked_for_again.py)."""
    dest = tmp_path / "dest"
    report = _restore(monkeypatch, dest, _a_passed_over_red_run_that_502s())

    assert report["unreached"] == [], report
    said = capsys.readouterr().out
    assert "::warning::" in said and "run 2 (failure)" in said, said
    assert report["filled_from"] == 3, "the success underneath was not laid"
    assert (dest / SNAP / "2026-10-06.csv").is_file()


def test_the_success_underneath_that_cannot_be_downloaded_is_still_red(
    tmp_path, monkeypatch,
) -> None:
    artifacts = {1: {_snap("2026-10-08"): "r1\n"}, 3: {_snap("2026-10-06"): "s3\n"}}
    report = _restore(monkeypatch, tmp_path / "dest",
                      FakeGh([_run(1, "failure"), _run(3, "success")], artifacts,
                             broken={3}))

    assert any("run 3" in sentence for sentence in report["unreached"]), report


def test_the_refusing_restore_still_refuses_a_passed_over_red_run(
    tmp_path, monkeypatch,
) -> None:
    """Historical Props Purchase restores with --refuse-unreachable, before
    it spends: it refuses rather than go on without that run's state."""
    monkeypatch.setattr(rs, "_gh", _a_passed_over_red_run_that_502s())
    with pytest.raises(rs.Unreachable, match="run 2"):
        rs.restore(artifact="gameday-state", dest=tmp_path / "dest",
                   workflows=[REFRESH], attempts=3, refuse_unreachable=True)


def test_a_day_in_the_restored_ledger_keeps_the_snapshot_it_settled(
    tmp_path, monkeypatch,
) -> None:
    """`settle_snapshots` counts a day as settled when the ledger holds it,
    marker or not (a crash between the ledger write and the marker leaves
    exactly that). Replacing its snapshot would leave the ledger's rows
    settled from one opinion and the archive holding another."""
    artifacts = _the_backup_missed_the_primary(tmp_path, monkeypatch)
    ledger = "snapshot_date,outcome\n2026-10-06,won\n2026-10-07,lost\n"
    artifacts[1][LEDGER.as_posix()] = ledger
    nextday = tmp_path / "nextday"
    _restore(monkeypatch, nextday,
             FakeGh([_run(1, "failure"), _run(2, "failure"), _run(3, "success")],
                    artifacts))

    assert (nextday / SNAP / "2026-10-07.csv").read_text(encoding="utf-8") == (
        "backup 15:00\n")
    assert (nextday / LEDGER).read_text(encoding="utf-8") == ledger


def test_the_fill_stops_at_the_newest_success(tmp_path, monkeypatch) -> None:
    artifacts = {1: {_snap("2026-10-08"): "r1\n"}, 2: {_snap("2026-10-07"): "r2\n"},
                 3: {_snap("2026-10-06"): "s3\n"}, 4: {_snap("2026-10-05"): "s4\n"}}
    gh = FakeGh([_run(1, "failure"), _run(2, "failure"), _run(3, "success"),
                 _run(4, "success")], artifacts)
    _restore(monkeypatch, tmp_path / "dest", gh)

    assert gh.downloads == [1, 2, 3]


def test_a_ledger_that_cannot_be_read_replaces_no_snapshot(
    tmp_path, monkeypatch,
) -> None:
    """Which days it settled is unknown, so none is assumed unsettled."""
    artifacts = _the_backup_missed_the_primary(tmp_path, monkeypatch)
    for run in (1, 2, 3):
        artifacts[run].pop(LEDGER.as_posix(), None)
    nextday = tmp_path / "nextday"
    (nextday / LEDGER).parent.mkdir(parents=True)
    (nextday / LEDGER).write_bytes(b"snapshot_date\n\xff\xfe2026-10-07\n")
    _restore(monkeypatch, nextday,
             FakeGh([_run(1, "failure"), _run(2, "failure"), _run(3, "success")],
                    artifacts))

    assert (nextday / SNAP / "2026-10-07.csv").read_text(encoding="utf-8") == (
        "backup 15:00\n")
