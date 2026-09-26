"""A line-movement day file that cannot be read is named, never skipped without a word.

`load_movement_captures` read each `line_movement/<day>.csv` with a bare
`pd.read_csv` and `continue`d past a `ParserError`, an `EmptyDataError` or a
file missing a capture column. One ragged row therefore took the whole day's
closing prices with it, and `closing_line_value.md` reported that day's
opinions as "no closing price found" (or, when it was the only day, "Nothing
to measure yet ... the correct state and not a fault") while the prices sat
on disk. The runner exited 0. The dedicated capture store raises
`UnreadableCaptureStore` in the same situation, so the two stores disagreed on
whether damage is a fault.

The movement store is one file per league day, not one file, so raising for
one bad day would stop every good day being scored. The runner already has
a rule for exactly that shape, for damaged priced snapshots: every readable
day is still scored, the report names each damaged file above every count,
and the run exits 2. A damaged movement day now follows that rule.

What these tests hold, through the real `run_closing_line_value.main()`:

* each damaged shape (a ragged row, an unterminated quote, zero bytes, a
  file missing a capture column, stray quotes that shorten the parse) is
  named in the report and in an `::error::`, and the runner exits 2;
* the good day beside it is still read and still scored;
* "Nothing to measure yet ... not a fault" is never printed over a damaged
  day;
* undamaged day files still exit 0 and name nothing.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.reports.card_pricing import selection_key


GOOD_DAY = "2026-10-08"
BAD_DAY = "2026-10-09"
GAMES = {
    GOOD_DAY: {"commence_time": "2026-10-08T23:00:00Z",
               "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins"},
    BAD_DAY: {"commence_time": "2026-10-09T23:00:00Z",
              "home_team": "Montreal Canadiens", "away_team": "Ottawa Senators"},
}
ROUNDS = 10


def _price(day: str, odds: float, book: str = "DraftKings") -> dict:
    return {**GAMES[day], "market": "player_points", "player": "A Skater",
            "selection": "over", "line": 0.5, "american_odds": odds, "book": book}


def _freeze(archive: Path, day: str) -> None:
    """One opinion per day, over 0.5 points at +130, frozen by the real writer."""
    row = _price(day, 130.0)
    probabilities = {
        selection_key(SimpleNamespace(**row), market="player_points",
                      selection="over", line=0.5): 0.62
    }
    assert fe.write_snapshot(
        pd.DataFrame([row]), probabilities, key_for=selection_key,
        verdicts_line="x", snapshot_date=day,
        now=datetime.fromisoformat(f"{day}T15:00:00+00:00"),
        archive_dir=archive,
    ) is not None


def _movement_day(processed: Path, day: str) -> Path:
    """Ten capture rounds in the day's movement file, appended as the capture does."""
    path = processed / cl.MOVEMENT_DIRNAME / f"{day}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    for minute in range(ROUNDS):
        frame = pd.DataFrame([_price(day, 120.0 + minute)])
        frame["captured_at"] = f"{day}T22:{minute:02d}:00+00:00"
        frame.to_csv(path, mode="a", header=not path.is_file(), index=False,
                     lineterminator="\n")
    return path


def _ragged_row(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[ROUNDS // 2] += ",extra,extra,extra"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _unterminated_quote(path: Path) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write('"2026-10-09T23:00:00Z,Montreal\n')


def _zero_bytes(path: Path) -> None:
    path.write_bytes(b"")


def _missing_column(path: Path) -> None:
    pd.read_csv(path).drop(columns=["captured_at"]).to_csv(path, index=False)


def _stray_quotes(path: Path) -> None:
    """Parses without an error, and short: the quotes swallow the rows between."""
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[3] = lines[3].replace(",DraftKings", ',"DraftKings')
    lines[7] = lines[7].replace(",DraftKings", ',DraftKings"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(pd.read_csv(path)) < ROUNDS, "the damage must shorten the parse"


DAMAGE = [_ragged_row, _unterminated_quote, _zero_bytes, _missing_column, _stray_quotes]
IDS = ["ragged-row", "unterminated-quote", "zero-bytes", "missing-column", "stray-quotes"]


def _run(tmp_path: Path, capsys) -> tuple[int, str, str]:
    from test_scripts import load_script

    module = load_script("run_closing_line_value.py")
    code = module.main(["--processed-dir", str(tmp_path / "processed"),
                        "--archive-dir", str(tmp_path / "archive"),
                        "--output-dir", str(tmp_path / "out")])
    text = (tmp_path / "out" / cl.REPORT_FILENAME).read_text(encoding="utf-8")
    return code, text, capsys.readouterr().out


def test_undamaged_days_are_both_scored_and_nothing_is_named(tmp_path, capsys) -> None:
    """The control: both days read, both opinions close, a clean exit."""
    for day in (GOOD_DAY, BAD_DAY):
        _freeze(tmp_path / "archive", day)
        _movement_day(tmp_path / "processed", day)

    code, text, out = _run(tmp_path, capsys)

    assert code == 0
    assert "matched to a closing price: **2**" in text
    assert "could not be read" not in text
    assert "::error::" not in out


@pytest.mark.parametrize("damage", DAMAGE, ids=IDS)
def test_a_damaged_day_is_named_and_the_good_day_is_still_scored(
    tmp_path, capsys, damage
) -> None:
    for day in (GOOD_DAY, BAD_DAY):
        _freeze(tmp_path / "archive", day)
        _movement_day(tmp_path / "processed", day)
    bad = tmp_path / "processed" / cl.MOVEMENT_DIRNAME / f"{BAD_DAY}.csv"
    damage(bad)
    before = bad.read_bytes()

    code, text, out = _run(tmp_path, capsys)

    assert code == 2, "a day that cannot be read is a fault, not a clean run"
    assert "::error::" in out and bad.name in out
    assert f"`{bad.name}`" in text, "the report must name the damaged day"
    assert "line-movement" in text and "could not be read" in text
    # The good day is not held hostage by the bad one.
    assert "matched to a closing price: **1**" in text
    assert "## All opinions" in text
    assert bad.read_bytes() == before, "the reader must never rewrite the file"


@pytest.mark.parametrize("damage", DAMAGE, ids=IDS)
def test_a_lone_damaged_day_is_never_called_the_correct_state(
    tmp_path, capsys, damage
) -> None:
    _freeze(tmp_path / "archive", BAD_DAY)
    damage(_movement_day(tmp_path / "processed", BAD_DAY))

    code, text, _ = _run(tmp_path, capsys)

    assert code == 2
    assert "not a fault" not in text
    assert f"`{BAD_DAY}.csv`" in text


@pytest.mark.parametrize("damage", DAMAGE, ids=IDS)
def test_the_loader_names_the_day_and_keeps_the_good_one(tmp_path, damage) -> None:
    processed = tmp_path / "processed"
    _movement_day(processed, GOOD_DAY)
    damage(_movement_day(processed, BAD_DAY))

    unreadable: dict[str, str] = {}
    captures = cl.load_captures(processed, unreadable=unreadable)

    assert list(unreadable) == [f"{BAD_DAY}.csv"]
    assert unreadable[f"{BAD_DAY}.csv"], "the reason must be given"
    assert set(captures["commence_time"]) == {GAMES[GOOD_DAY]["commence_time"]}
    assert len(captures) == ROUNDS


def test_a_header_only_day_holds_nothing_to_lose(tmp_path) -> None:
    """The capture never writes one, but it has no row in it to lose."""
    processed = tmp_path / "processed"
    _movement_day(processed, GOOD_DAY)
    (processed / cl.MOVEMENT_DIRNAME / f"{BAD_DAY}.csv").write_text(
        ",".join(cl.CAPTURE_COLUMNS) + "\n", encoding="utf-8"
    )

    unreadable: dict[str, str] = {}
    captures = cl.load_movement_captures(processed, unreadable=unreadable)

    assert unreadable == {}
    assert len(captures) == ROUNDS
