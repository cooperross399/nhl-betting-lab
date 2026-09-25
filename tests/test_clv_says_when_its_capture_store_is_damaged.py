"""A damaged capture store was read as an empty one, and the report called that correct.

`load_captures` read `closing_line_captures.csv` with the forgiving reader,
which returns an empty frame for a file that will not parse, and then fell
back to the movement store. Gameday Refresh never has a movement store, so
the result was 0 captures, and `closing_line_value.md` said "## Nothing to
measure yet ... this is the correct state and not a fault." That page is
published to card-feed as `latest_closing_line_value.md`. Found by the
failure-shape audit (finding 62, confirmed by two of three refuters). One
refuter's store held a capture that matched an opinion, plus an unterminated
quote at the end. The report said "matched to a closing price: 0; no closing
price found: 1" while the closing price was sitting on disk. The same store
without the damage matched 1 of 1.

`stores.py` allows a reader to "treat that as absent and say so". This
reader said nothing. A second shape was just as silent: two stray quotes
make pandas swallow rows into one field without an error, so a 10-row store
read as 6.

What these tests hold, through the real `run_closing_line_value.main()`:

* each damaged shape (an unterminated quote at the end, a ragged row, stray
  quotes that shorten the parse) produces a report that names the store and
  its row count, never says "Nothing to measure yet" or "not a fault", and
  counts no opinion as having no close. The runner exits non-zero after
  writing that report, and the store is left untouched;
* a damaged dedicated store is refused even when a movement store sits
  beside it, because scoring from the other store would swap the data
  source without saying so;
* an absent, zero-byte or header-only store is still "Nothing to measure
  yet". There is nothing in it to lose.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.reports.card_pricing import selection_key


GAME = {
    "commence_time": "2026-10-08T23:00:00Z",
    "home_team": "Toronto Maple Leafs",
    "away_team": "Boston Bruins",
}
FROZEN_AT = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
CLEAN_ROWS = 10


def _price(selection: str, odds: float, book: str = "DraftKings") -> dict:
    return {**GAME, "market": "moneyline", "player": "", "selection": selection,
            "line": None, "american_odds": odds, "book": book}


def _freeze(archive: Path) -> None:
    """One opinion, moneyline away at +130, frozen by the real writer."""
    rows = [_price("away", 130.0)]
    probabilities = {
        selection_key(SimpleNamespace(**rows[0]), market="moneyline",
                      selection="away", line=None): 0.62
    }
    assert fe.write_snapshot(
        pd.DataFrame(rows), probabilities, key_for=selection_key,
        verdicts_line="x", snapshot_date="2026-10-08", now=FROZEN_AT,
        archive_dir=archive,
    ) is not None


def _store(processed: Path) -> Path:
    """Ten capture rounds by the real writer. The last one closes the opinion."""
    for minute in range(CLEAN_ROWS):
        cl.append_captures(
            cl.best_prices(pd.DataFrame([_price("away", 120.0 + minute)]),
                           captured_at=f"2026-10-08T22:{minute:02d}:00+00:00"),
            processed_dir=processed,
        )
    return cl.captures_path(processed)


def _unterminated_quote(path: Path) -> int:
    with path.open("a", encoding="utf-8") as handle:
        handle.write('"2026-10-08T22:40:00+00:00,2026-10-08T23:00:00Z,Toronto\n')
    return CLEAN_ROWS + 1


def _ragged_row(path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[CLEAN_ROWS // 2] += ",extra,extra,extra"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return CLEAN_ROWS


def _stray_quotes(path: Path) -> int:
    """Parses without an error, and short: the quotes swallow the rows between."""
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[3] = lines[3].replace(",DraftKings", ',"DraftKings')
    lines[7] = lines[7].replace(",DraftKings", ',DraftKings"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(pd.read_csv(path)) < CLEAN_ROWS, "the damage must shorten the parse"
    return CLEAN_ROWS


def _run(tmp_path: Path, capsys) -> tuple[int, str, str]:
    from test_scripts import load_script

    module = load_script("run_closing_line_value.py")
    code = module.main(["--processed-dir", str(tmp_path / "processed"),
                        "--archive-dir", str(tmp_path / "archive"),
                        "--output-dir", str(tmp_path / "out")])
    text = (tmp_path / "out" / cl.REPORT_FILENAME).read_text(encoding="utf-8")
    return code, text, capsys.readouterr().out


def test_the_healthy_store_matches_the_opinion(tmp_path, capsys) -> None:
    """The control: the same store, undamaged, closes the opinion."""
    _freeze(tmp_path / "archive")
    _store(tmp_path / "processed")

    code, text, _ = _run(tmp_path, capsys)

    assert code == 0
    assert "matched to a closing price: **1**" in text
    assert "## All opinions" in text


@pytest.mark.parametrize(
    ("damage", "diagnosis"),
    [
        (_unterminated_quote, "it does not parse"),
        (_ragged_row, "it does not parse"),
        (_stray_quotes, "only 6 of them parse"),
    ],
    ids=["unterminated-quote", "ragged-row", "stray-quotes"],
)
def test_a_damaged_store_is_named_and_never_called_the_correct_state(
    tmp_path, capsys, damage, diagnosis
) -> None:
    _freeze(tmp_path / "archive")
    path = _store(tmp_path / "processed")
    rows_on_disk = damage(path)
    before = path.read_bytes()

    code, text, out = _run(tmp_path, capsys)

    assert "Nothing to measure yet" not in text
    assert "not a fault" not in text
    assert "no closing price found" not in text, "the closing price may be on disk"
    assert "## The capture store could not be read" in text
    assert f"`{cl.CAPTURES_FILENAME}` holds {rows_on_disk} row(s) on disk, and {diagnosis}." in text
    assert code != 0, "a store that cannot be read is a fault, not a clean run"
    assert "::error::" in out and cl.CAPTURES_FILENAME in out
    assert path.read_bytes() == before, "the reader must never rewrite the store"


def test_a_damaged_store_is_not_replaced_by_the_movement_store(tmp_path, capsys) -> None:
    """Scoring from the other store would swap the source without saying so."""
    _freeze(tmp_path / "archive")
    processed = tmp_path / "processed"
    _ragged_row(_store(processed))
    movement = processed / cl.MOVEMENT_DIRNAME
    movement.mkdir()
    pd.DataFrame([{**_price("away", 110.0), "captured_at": "2026-10-08T22:30:00+00:00"}]
                 ).to_csv(movement / "2026-10-08.csv", index=False)

    code, text, _ = _run(tmp_path, capsys)

    assert "## All opinions" not in text, "scored from the movement store"
    assert "## The capture store could not be read" in text
    assert code != 0


@pytest.mark.parametrize("shape", ["absent", "zero-byte", "header-only"])
def test_an_empty_store_is_still_nothing_to_measure(tmp_path, capsys, shape) -> None:
    """There is nothing in these to lose, so they are the pre-season state."""
    _freeze(tmp_path / "archive")
    processed = tmp_path / "processed"
    processed.mkdir()
    path = cl.captures_path(processed)
    if shape == "zero-byte":
        path.write_bytes(b"")
    elif shape == "header-only":
        path.write_text(",".join(cl.CAPTURE_COLUMNS) + "\n", encoding="utf-8")

    code, text, _ = _run(tmp_path, capsys)

    assert code == 0
    assert "## Nothing to measure yet" in text
    assert "could not be read" not in text
