"""One damaged priced snapshot stopped the closing-line report, or vanished from it unnamed.

`scripts/run_closing_line_value.py::_opinions` read every
`priced_snapshots/*.csv` with a bare `pd.read_csv` and caught only
`OSError`, `EmptyDataError` and `ParserError`. Settlement reads the same
files through `forward_evidence`'s snapshot reader, which since #146 also
catches `UnicodeDecodeError` and rejects a frame missing snapshot columns,
and names every file it could not read. The CLV reader got neither change.

Found by the failure-shape audit (finding f2, confirmed by all three
refuters). They froze two days of 64 rows each (128 opinions) with the real
`write_snapshot`, with players spelled as the books spell them
("Alexis Lafrenière", "David Pastrňák"), and damaged one day:

* cut inside a multi-byte character (a 12,930-byte snapshot cut to 6,841
  bytes), or re-saved as Latin-1: the runner died in `_opinions` with a
  UnicodeDecodeError, exited 1 and wrote no `closing_line_value.md`. On the
  same directories `run_forward_evidence.py` named the file, wrote its report
  and exited 2;
* an unclosed quote, zero bytes, or half a header: the runner exited 0 and
  reported "64 frozen opinion(s)" of the 128, naming nothing, while
  settlement named the same file and exited 2;
* once both days had settled and one file was then damaged,
  `run_forward_evidence.py` exited 0 ("0 pending snapshot file(s) could not
  be read"), because it never re-reads a settled day. The CLV report is the
  only reader of that file, and it crashed.

The step runs `continue-on-error` and the damaged file travels in the
gameday-state artifact, so every later run lost the report too, and
`latest_closing_line_value.md` fell off card-feed while the run stayed green.

What these tests hold, through the real `run_closing_line_value.main()`:

* for every damage shape, on a pending day and on a settled one, the runner
  returns rather than raises, writes the report, names the file and why in
  the report and in an `::error::` line, counts every row of the intact day,
  exits 2, and leaves the damaged file as it found it;
* the report says whether any row frozen that day is still counted: on a
  settled day the forward ledger holds all 64, and those are counted; on a
  pending day none is. With no capture store yet it never calls the run
  "the correct state and not a fault";
* a damaged capture store and a damaged snapshot are both named in the one
  report;
* an intact archive, pending or settled, counts all 128 rows, names nothing
  and exits 0.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.reports.card_pricing import selection_key


DAMAGED_DAY = "2026-10-07"
INTACT_DAY = "2026-10-08"
#: Well after both days, with both days' finals on disk.
LATER = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)
#: The shape `verdicts.describe` returns: it holds commas, so the CSV quotes it.
VERDICTS = "by_toi=off, props_b2b=in force, team_b2b=in force"
#: Keyed the way `load_team_name_map` returns it: normalized name -> abbrev.
TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}
#: Three spelled outside ASCII, as the books spell them, so a cut can split a
#: character. Every one fits in Latin-1, so the file can be re-saved in it.
PLAYERS = ("Alexis Lafrenière", "Tim Stützle", "Juraj Slafkovský", "Auston Matthews")
SELECTIONS = ("over", "under")
LINES = (1.5, 2.5)
BOOKS = {"DraftKings": -120.0, "FanDuel": -110.0, "BetMGM": 100.0, "Caesars": 110.0}
#: Every (player, selection, line, book) once: no two rows are repeats.
ROWS_PER_DAY = len(PLAYERS) * len(SELECTIONS) * len(LINES) * len(BOOKS)


def _face_off(day: str) -> str:
    """00:10Z the next morning is 20:10 ET, so the league date is `day`."""
    return f"{(date.fromisoformat(day) + timedelta(days=1)).isoformat()}T00:10:00Z"


def _price(day: str, player: str, selection: str, line: float, book: str) -> dict:
    return {
        "commence_time": _face_off(day),
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "market": "shots_on_goal",
        "player": player,
        "selection": selection,
        "line": line,
        "american_odds": BOOKS[book],
        "book": book,
    }


def _freeze(archive: Path, day: str) -> Path:
    """The day's slate, frozen by the real writer with the card's own key."""
    rows = [
        _price(day, player, selection, line, book)
        for player in PLAYERS
        for selection in SELECTIONS
        for line in LINES
        for book in BOOKS
    ]
    probabilities = {
        selection_key(SimpleNamespace(**row), market=row["market"],
                      selection=row["selection"], line=row["line"]): 0.55
        for row in rows
    }
    path = fe.write_snapshot(
        pd.DataFrame(rows), probabilities, key_for=selection_key,
        verdicts_line=VERDICTS, snapshot_date=day,
        now=datetime.fromisoformat(f"{day}T12:00:00+00:00"), archive_dir=archive,
    )
    assert path is not None
    assert len(pd.read_csv(path)) == ROWS_PER_DAY
    return path


def _settle(tmp_path: Path) -> None:
    """Both days settle through the real settlement. No player log is on
    disk, so every prop voids, and every row still goes to the ledger."""
    games = pd.DataFrame(
        [
            {"game_id": i, "date": day, "home_team": "TOR", "away_team": "BOS",
             "home_goals": 4, "away_goals": 2, "regulation": True}
            for i, day in enumerate((DAMAGED_DAY, INTACT_DAY))
        ]
    )
    result = fe.settle_snapshots(
        pd.DataFrame(columns=["date", "player_id", "player", "team"]),
        games,
        team_names=TEAM_MAP,
        archive_dir=tmp_path / "archive",
        processed_dir=tmp_path / "processed",
        now=LATER,
    )
    assert result.snapshots_settled == 2
    ledger = fe.load_ledger(tmp_path / "processed")
    assert (ledger["snapshot_date"].astype(str) == DAMAGED_DAY).sum() == ROWS_PER_DAY


# --------------------------------------------------------------------------
# How a snapshot already on disk can be damaged, and what reading it raises.
# --------------------------------------------------------------------------

def _half_a_character(path: Path) -> None:
    whole = path.read_bytes()
    path.write_bytes(whole[: whole.rindex(b"\xc3") + 1])


def _a_latin1_resave(path: Path) -> None:
    path.write_bytes(path.read_text(encoding="utf-8").encode("latin-1"))


def _an_unclosed_quote(path: Path) -> None:
    whole = path.read_bytes()
    path.write_bytes(whole[: whole.rindex(b'"by_toi') + 8])


def _no_bytes_at_all(path: Path) -> None:
    path.write_bytes(b"")


def _half_a_header(path: Path) -> None:
    path.write_bytes(path.read_bytes()[:30])


def _not_a_file(path: Path) -> None:
    path.unlink()
    path.mkdir()


#: shape -> (damage, the start of the reason the report must give).
DAMAGE = {
    "half_a_character": (_half_a_character, "UnicodeDecodeError"),
    "a_latin1_resave": (_a_latin1_resave, "UnicodeDecodeError"),
    "an_unclosed_quote": (_an_unclosed_quote, "ParserError"),
    "no_bytes_at_all": (_no_bytes_at_all, "EmptyDataError"),
    "half_a_header": (_half_a_header, "missing column(s)"),
    "not_a_file": (_not_a_file, "IsADirectoryError"),
}


def _fingerprint(path: Path) -> object:
    return "directory" if path.is_dir() else path.read_bytes()


def _archive(tmp_path: Path, state: str) -> Path:
    """Two frozen days; with `settled`, both already in the ledger."""
    archive = tmp_path / "archive"
    damaged = _freeze(archive, DAMAGED_DAY)
    _freeze(archive, INTACT_DAY)
    (tmp_path / "processed").mkdir(exist_ok=True)
    if state == "settled":
        _settle(tmp_path)
    return damaged


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    from test_scripts import load_script

    module = load_script("run_closing_line_value.py")
    code = module.main(["--processed-dir", str(tmp_path / "processed"),
                        "--archive-dir", str(tmp_path / "archive"),
                        "--output-dir", str(tmp_path / "out")])
    report = tmp_path / "out" / cl.REPORT_FILENAME
    assert report.is_file(), "no closing_line_value.md was written"
    return code, report.read_text(encoding="utf-8"), capsys.readouterr().out


@pytest.fixture(autouse=True)
def _no_real_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No default directory can rescue or break these runs."""
    monkeypatch.setattr(fe, "DATA_DIR", tmp_path / "default_data")


@pytest.mark.parametrize("state", ["pending", "settled"])
@pytest.mark.parametrize("shape", sorted(DAMAGE))
def test_a_damaged_snapshot_is_named_and_the_report_is_still_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], shape: str, state: str
) -> None:
    damaged = _archive(tmp_path, state)
    damage, reason = DAMAGE[shape]
    damage(damaged)
    before = _fingerprint(damaged)
    name = damaged.name

    code, text, out = _run(tmp_path, capsys)

    assert code == 2, "a snapshot that cannot be read is a fault, not a clean run"
    assert f"`{name}` ({reason}" in text, text
    assert any(
        line.startswith("::error::") and name in line for line in out.splitlines()
    ), out
    held = ROWS_PER_DAY if state == "settled" else 0
    # Every row of the intact day, plus what the ledger still holds of the
    # damaged one.
    assert f"{ROWS_PER_DAY + held} frozen opinion(s)" in out, out
    if held:
        assert (
            f"the forward ledger holds {held} row(s) frozen that day, and "
            "those are counted" in text
        ), text
    else:
        assert "no row frozen that day is counted" in text, text
    assert "not a fault" not in text, "a damaged evidence file is a fault"
    assert _fingerprint(damaged) == before, "the evidence file itself was touched"


@pytest.mark.parametrize("state", ["pending", "settled"])
def test_an_intact_archive_counts_every_row_and_names_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    """The control: the same two days, undamaged."""
    _archive(tmp_path, state)

    code, text, out = _run(tmp_path, capsys)

    assert code == 0
    assert f"{2 * ROWS_PER_DAY} frozen opinion(s)" in out, out
    assert "could not be read" not in text
    assert "::error::" not in out
    assert "this is the\ncorrect state and not a fault." in text


def test_a_damaged_store_and_a_damaged_snapshot_are_both_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The capture-store fault writes its own report. It must still name the
    snapshot that could not be read."""
    damaged = _archive(tmp_path, "pending")
    _half_a_character(damaged)
    processed = tmp_path / "processed"
    cl.append_captures(
        cl.best_prices(
            pd.DataFrame([_price(INTACT_DAY, PLAYERS[0], "over", 1.5, "FanDuel")]),
            captured_at=f"{INTACT_DAY}T23:30:00+00:00",
        ),
        processed_dir=processed,
    )
    with cl.captures_path(processed).open("a", encoding="utf-8") as handle:
        handle.write(f'"{INTACT_DAY}T23:40:00+00:00,{_face_off(INTACT_DAY)},Toronto\n')

    code, text, out = _run(tmp_path, capsys)

    assert code == 2
    assert "## The capture store could not be read" in text
    assert f"`{damaged.name}` (UnicodeDecodeError" in text, text
    assert any(
        line.startswith("::error::") and damaged.name in line
        for line in out.splitlines()
    ), out
