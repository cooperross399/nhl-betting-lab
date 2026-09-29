"""A red run the fill passed over is asked for again, even when the run that
passed over it is green, and its day does not settle from a later opinion
while it is still being asked for.

Sweep 5 (restore_state.py `_fill_from_last_success`). A red run the fill
cannot download is a warning, not a record, so it does not make every
primary red and fire the 15:00 backup (a few hundred credits a run) for as
long as the artifact never downloads. The warning said "the next restore
asks for it again", and so did the test that pinned the choice: "the next
restore walks the same listing". That held only when the run that warned
was red. Day D: the 13:30 primary R2 goes red and freezes and posts
2026-10-07 (A); the backup's three downloads of R2 502, and it freezes its
own 15:00 opinion (B) under the same name. On D+1 the primary restores the
red backup, the fill asks for R2, R2 502s three times again: a warning. The
D+1 run is otherwise healthy, so green, and settles 2026-10-07 from B in the
same run. On D+2 the restore takes that green run alone — the fill runs only
under a red one — so R2 is never downloaded again; and had it been,
`_first_opinions` keeps a day that has settled. A never reaches the forward
ledger, and B settles in its place.

So the run the fill passed over is written into the restored state
(`processed/unlaid_runs.json`, inside `data/processed`, which the
gameday-state artifact uploads), every later restore asks for it again
whatever the conclusion of the run it restores, and while it is listed the
forward ledger settles no pending day: the day it may have frozen first
cannot be known without it. It leaves the list once laid, once gh says the
run holds no such artifact (expired), or after `UNLAID_TRIES` restores in all,
each with a line in the log saying so. Still a warning, never red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from test_a_cut_short_snapshot_never_stands import (
    DAY,
    LATER,
    TEAM_MAP,
    _games,
    _markers,
    _moneyline_day,
)
from test_a_red_runs_frozen_snapshot_is_laid_back import (
    LEDGER,
    REFRESH,
    SNAP,
    FakeGh,
    _held,
    _run,
    _restore,
    _the_backup_missed_the_primary,
    rs,
)

UNLAID = Path("processed") / "unlaid_runs.json"
RED_DAY = [_run(1, "failure"), _run(2, "failure"), _run(3, "success")]


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setenv("RESTORE_STATE_RETRY_SECONDS", "0")


def _listed(root: Path) -> list[int]:
    path = root / UNLAID
    if not path.is_file():
        return []
    return [entry["run"] for entry in json.loads(path.read_text())["runs"]]


def _green_day_after(tmp_path, monkeypatch, capsys):
    """D+1: R2 502s again under the red backup; the run is green (nothing
    recorded) and uploads its state as run 4."""
    artifacts = _the_backup_missed_the_primary(tmp_path, monkeypatch)
    capsys.readouterr()
    day1 = tmp_path / "day1"
    report = _restore(monkeypatch, day1, FakeGh(RED_DAY, artifacts, broken={2}))
    said = capsys.readouterr().out
    artifacts[4] = _held(day1)
    return artifacts, report, said, day1


def test_the_passed_over_run_is_asked_for_again_under_a_green_run(
    tmp_path, monkeypatch, capsys,
) -> None:
    artifacts, report, _, _ = _green_day_after(tmp_path, monkeypatch, capsys)
    assert report["unreached"] == [], "the passed-over red run made the run red"

    day2 = tmp_path / "day2"
    gh = FakeGh([_run(4, "success"), *RED_DAY], artifacts)
    after = _restore(monkeypatch, day2, gh)

    assert after["run"] == 4
    assert 2 in gh.downloads, "the red run passed over the day before was never asked for again"
    assert (day2 / SNAP / "2026-10-07.csv").read_text(encoding="utf-8") == (
        "primary 13:30\n"
    ), "the backup's later opinion stood in place of the primary's posted one"
    assert (day2 / "raw/nhl/boxscore/2.json").is_file()
    assert _listed(day2) == [] and not (day2 / UNLAID).exists(), (
        "a run that was laid is still listed as unlaid")
    assert after["unlaid"] == []


def test_the_run_that_passed_it_over_writes_it_down_and_stays_green(
    tmp_path, monkeypatch, capsys,
) -> None:
    _, report, said, day1 = _green_day_after(tmp_path, monkeypatch, capsys)

    assert report["unreached"] == []
    assert _listed(day1) == [2]
    assert report["unlaid"] == [2]
    assert "::warning::" in said and "run 2 (failure)" in said
    assert str(UNLAID) in said, "the warning does not say where the run is kept"
    assert "the next restore asks for it again" not in said, (
        "the old promise is still printed")


def test_it_stops_being_asked_for_after_a_bounded_number_of_restores(
    tmp_path, monkeypatch, capsys,
) -> None:
    """An artifact that never downloads again must not hold the ledger for
    the 90 days it is kept."""
    artifacts, _, _, _ = _green_day_after(tmp_path, monkeypatch, capsys)
    listing = [_run(4, "success"), *RED_DAY]
    newest = 4
    tries = 1
    while True:
        dest = tmp_path / f"after{newest}"
        gh = FakeGh(listing, artifacts, broken={2})
        report = _restore(monkeypatch, dest, gh)
        said = capsys.readouterr().out
        assert 2 in gh.downloads
        assert report["unreached"] == [], "an unlaid run made a restore red"
        tries += 1
        if not _listed(dest):
            break
        assert tries < rs.UNLAID_TRIES, "it was asked for more than UNLAID_TRIES times"
        newest += 1
        artifacts[newest] = _held(dest)
        listing = [_run(newest, "success"), *listing]
    assert tries == rs.UNLAID_TRIES
    assert "::warning::" in said and "run 2" in said and "no longer" in said, said


def test_a_run_whose_artifact_has_expired_leaves_the_list(
    tmp_path, monkeypatch, capsys,
) -> None:
    artifacts, _, _, _ = _green_day_after(tmp_path, monkeypatch, capsys)
    del artifacts[2]
    dest = tmp_path / "day2"
    report = _restore(monkeypatch, dest, FakeGh([_run(4, "success"), *RED_DAY], artifacts))

    assert _listed(dest) == [] and report["unlaid"] == []
    assert report["unreached"] == []
    assert "run 2" in capsys.readouterr().out.lower()


def test_a_run_the_fill_asks_for_anyway_is_asked_once(
    tmp_path, monkeypatch, capsys,
) -> None:
    """The day after is red too: its fill walks down past R2 itself."""
    artifacts, _, _, _ = _green_day_after(tmp_path, monkeypatch, capsys)
    dest = tmp_path / "day2"
    gh = FakeGh([_run(4, "failure"), *RED_DAY], artifacts)
    _restore(monkeypatch, dest, gh)

    assert gh.downloads.count(2) == 1, gh.downloads
    assert (dest / SNAP / "2026-10-07.csv").read_text(encoding="utf-8") == (
        "primary 13:30\n")
    assert _listed(dest) == []


def test_tries_carry_over_when_the_fill_asks_again(
    tmp_path, monkeypatch, capsys,
) -> None:
    artifacts, _, _, _ = _green_day_after(tmp_path, monkeypatch, capsys)
    dest = tmp_path / "day2"
    _restore(monkeypatch, dest, FakeGh([_run(4, "failure"), *RED_DAY], artifacts,
                                       broken={2}))

    entries = json.loads((dest / UNLAID).read_text())["runs"]
    assert [(e["run"], e["tries"]) for e in entries] == [(2, 2)]


def test_an_older_carriers_list_is_not_taken_up(
    tmp_path, monkeypatch, capsys,
) -> None:
    """Only the restored run's list is carried: a red run laid underneath,
    whose list the newer run already settled, must not bring it back."""
    artifacts = {
        1: {SNAP.joinpath("2026-10-08.csv").as_posix(): "r1\n"},
        2: {SNAP.joinpath("2026-10-07.csv").as_posix(): "r2\n",
            UNLAID.as_posix(): json.dumps({"runs": [
                {"run": 9, "workflow": REFRESH, "tries": 1}]})},
        3: {SNAP.joinpath("2026-10-06.csv").as_posix(): "s3\n"},
    }
    dest = tmp_path / "dest"
    gh = FakeGh(RED_DAY, artifacts)
    report = _restore(monkeypatch, dest, gh)

    assert 9 not in gh.downloads
    assert _listed(dest) == [] and report["unlaid"] == []


def test_the_refusing_restore_carries_the_list_without_asking(
    tmp_path, monkeypatch, capsys,
) -> None:
    """Historical Props Purchase restores gameday-state with
    --refuse-unreachable before it spends. A snapshot it never settles is no
    reason to refuse a purchase, so it carries the list forward untouched."""
    artifacts, _, _, day1 = _green_day_after(tmp_path, monkeypatch, capsys)
    before = (day1 / UNLAID).read_text()
    monkeypatch.setattr(rs, "_gh", gh := FakeGh([_run(4, "success"), *RED_DAY],
                                                 artifacts, broken={2}))
    dest = tmp_path / "purchase"
    rs.restore(artifact="gameday-state", dest=dest, workflows=[REFRESH],
               attempts=3, refuse_unreachable=True)

    assert gh.downloads == [4]
    assert (dest / UNLAID).read_text() == before


def test_a_restore_that_takes_the_run_alone_leaves_the_list_as_it_came(
    tmp_path, monkeypatch, capsys,
) -> None:
    """Publish Site's --no-merge restore settles nothing and uploads no state."""
    artifacts, _, _, day1 = _green_day_after(tmp_path, monkeypatch, capsys)
    monkeypatch.setattr(rs, "_gh", gh := FakeGh([_run(4, "success"), *RED_DAY],
                                                 artifacts))
    dest = tmp_path / "site"
    rs.restore(artifact="gameday-state", dest=dest, workflows=[REFRESH], merge=False)

    assert gh.downloads == [4]
    assert (dest / UNLAID).read_bytes() == (day1 / UNLAID).read_bytes()


# ---------------------------------------------------------------------------
# The ledger waits for it.
# ---------------------------------------------------------------------------

def _settle(tmp_path: Path) -> fe.SettlementResult:
    return fe.settle_snapshots(
        pd.DataFrame(columns=["date", "player_id", "player", "team"]),
        _games(DAY),
        team_names=TEAM_MAP,
        archive_dir=tmp_path / "archive",
        processed_dir=tmp_path / "processed",
        now=LATER,
    )


def _unlaid(tmp_path: Path, text: str) -> None:
    path = tmp_path / UNLAID
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_no_pending_day_settles_while_a_passed_over_run_is_listed(tmp_path) -> None:
    """The day it froze first is unknown until it is laid; settled from the
    later opinion, `_first_opinions` could never put the first one back."""
    _moneyline_day(tmp_path / "archive")
    _unlaid(tmp_path, json.dumps({"runs": [{"run": 2, "workflow": REFRESH, "tries": 1}]}))

    result = _settle(tmp_path)

    assert _markers(tmp_path / "archive") == []
    assert not (tmp_path / LEDGER).exists()
    assert result.snapshots_held == 1
    assert "run 2" in result.summary_line()


def test_the_day_settles_once_the_list_is_gone(tmp_path) -> None:
    _moneyline_day(tmp_path / "archive")
    _unlaid(tmp_path, json.dumps({"runs": [{"run": 2, "workflow": REFRESH, "tries": 1}]}))
    _settle(tmp_path)
    (tmp_path / UNLAID).unlink()

    result = _settle(tmp_path)

    assert _markers(tmp_path / "archive") == [DAY]
    assert result.snapshots_held == 0 and result.snapshots_settled == 1


def test_an_empty_list_holds_nothing(tmp_path) -> None:
    _moneyline_day(tmp_path / "archive")
    _unlaid(tmp_path, json.dumps({"runs": []}))

    assert _settle(tmp_path).snapshots_settled == 1


def test_a_list_that_cannot_be_read_holds_the_ledger(tmp_path) -> None:
    """Which run it names is unknown, so which day is unknown too; the next
    restore rewrites it."""
    _moneyline_day(tmp_path / "archive")
    _unlaid(tmp_path, "{not json")

    result = _settle(tmp_path)

    assert result.snapshots_held == 1
    assert _markers(tmp_path / "archive") == []


def test_both_sides_name_the_same_file() -> None:
    assert Path(rs.UNLAID) == UNLAID
    assert fe.UNLAID_RUNS_FILENAME == UNLAID.name


def test_the_state_artifact_uploads_it() -> None:
    from nhl_betting_lab.config import PROJECT_ROOT

    workflow = (PROJECT_ROOT / ".github/workflows/gameday-refresh.yml").read_text()
    upload = workflow.split("name: gameday-state", 1)[1].split("retention-days", 1)[0]
    assert "data/processed\n" in upload


def test_the_state_artifact_carries_the_staged_prices() -> None:
    """Publish Site builds the board from gameday-state alone, and the board
    reads its prices from data/staging. The upload carried everything but
    that folder, so from opening night every regular-season game was
    published unpriced, with no line and no pick, while the card held a best
    bet: the prices never left the runner that fetched them.

    The whole line, indentation included: `"data/staging\\n" in upload` was
    also true of a commented-out `# data/staging` and of the step comment
    that names the folder, so the line could go and the test stay green."""
    from nhl_betting_lab.config import PROJECT_ROOT

    workflow = (PROJECT_ROOT / ".github/workflows/gameday-refresh.yml").read_text()
    upload = workflow.split("name: gameday-state", 1)[1].split("retention-days", 1)[0]
    assert "\n            data/staging\n" in upload


def test_a_restored_run_s_staged_prices_do_not_outlive_the_restore() -> None:
    """Carrying data/staging in the state means Gameday Refresh restores the
    previous run's prices before it fetches, and the fetch replaces them only
    when it fetches. A skipped or failed fetch would leave them on disk and
    the upload would hand them to the board as today's; the card refuses
    them on age, the board reads no age. They are cleared straight after the
    restore, before anything fetches.

    The whole line, indentation included, so a commented-out `# rm -f ...`
    at the same place does not pass for the command."""
    from nhl_betting_lab.config import PROJECT_ROOT

    workflow = (PROJECT_ROOT / ".github/workflows/gameday-refresh.yml").read_text()
    restore = workflow.index("restore_state.py --artifact gameday-state")
    clear = workflow.index(
        "\n          rm -f data/staging/*.csv data/staging/staging_provenance.json\n"
    )
    fetch = workflow.index("name: Fetch prices into staging")
    assert restore < clear < fetch


def test_the_clear_is_a_command_of_the_restore_step_itself() -> None:
    """Character order across the file is not placement. The rm sat between
    the restore and the fetch just as well inside "Check the provider
    credential", which runs under the fetch's own `if:` — so on a
    `skip_provider_fetch` dispatch, the case the rm exists for, it would be
    skipped with the fetch and the restored quotes uploaded as today's. The
    step is read as YAML: the rm is a command line (not a comment) of the
    `id: restore` step's run block, after its restore command, and that
    step has no condition."""
    import yaml
    from nhl_betting_lab.config import PROJECT_ROOT

    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/gameday-refresh.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["refresh"]["steps"]
    restore = next(step for step in steps if step.get("id") == "restore")
    assert "if" not in restore, restore.get("if")
    lines = [line.strip() for line in restore["run"].splitlines()]
    clear = lines.index("rm -f data/staging/*.csv data/staging/staging_provenance.json")
    command = next(
        index for index, line in enumerate(lines)
        if line.startswith("python scripts/restore_state.py --artifact gameday-state")
    )
    assert command < clear
    fetch = next(index for index, step in enumerate(steps)
                 if step.get("name") == "Fetch prices into staging")
    assert steps.index(restore) < fetch



def test_a_held_settlement_is_a_warning_on_the_run_page(
    tmp_path, monkeypatch, capsys
) -> None:
    """A hold keeps the run green, so it is said where a reader looks."""
    from test_scripts import load_script

    runner = load_script("run_forward_evidence.py")
    held = fe.SettlementResult(snapshots_held=2, held_for=["run 2"])
    monkeypatch.setattr(runner, "settle_snapshots", lambda *a, **k: held)
    monkeypatch.setattr(runner, "load_player_logs", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(runner, "load_team_games", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(runner, "load_team_name_map", lambda *a, **k: {})

    try:
        runner.main([
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "out"),
            "--archive-dir", str(tmp_path / "archive"),
        ])
    except Exception:
        pass  # only what it said before restating the ledger is under test

    out = capsys.readouterr().out
    assert "::warning::Settlement held back 2 pending snapshot(s)" in out
    assert "run 2" in out and "unlaid_runs.json" in out
