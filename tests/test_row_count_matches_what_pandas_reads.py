"""`existing_row_count` is the floor of every shrink guard; it must count rows.

It is deliberately a count of physical lines taken off the file rather than
the parse, because a stray quote makes pandas swallow rows into one field
without raising and only a line count sees them. But it counted blank lines,
which pandas skips, so a ledger ending in blank lines "held" more rows than it
did and every shrink guard refused an honest append — for the forward ledger,
on every run, until someone removed the blank lines. And it decoded the file
to count newlines, so one byte that is not UTF-8 raised `UnicodeDecodeError`
out of the guard instead of a count.

What these tests hold, each measured against `pd.read_csv`:

* on every blank-line shape pandas skips, the count equals the rows pandas
  reads, and a commas-only line is a row to both;
* a stray quote still leaves the count ABOVE the parse — the guard's purpose;
* undecodable bytes are counted, not raised;
* the forward ledger with trailing blank lines takes an honest append, while
  the short-read refusal in `tests/test_forward_evidence.py` still stands.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.stores import existing_row_count


HEAD = b"a,b,c\n1,2,3\n"

#: Each is a shape pandas reads without error, with what it skips or keeps.
SHAPES = {
    "empty line between rows": HEAD + b"\n4,5,6\n",
    "CRLF with an empty line": b"a,b,c\r\n1,2,3\r\n\r\n4,5,6\r\n",
    "spaces-only line": HEAD + b"   \n4,5,6\n",
    "tab-only line": HEAD + b"\t\n4,5,6\n",
    "commas-only line (a row to pandas)": HEAD + b",,\n4,5,6\n",
    "trailing blank lines": HEAD + b"\n\n\n",
    "blank line before the header": b"\n" + HEAD,
    "no newline at the end": b"a,b,c\n1,2,3\n4,5,6",
    "header only": b"a,b,c\n",
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_the_count_is_the_rows_pandas_reads(tmp_path: Path, name: str) -> None:
    path = tmp_path / "store.csv"
    path.write_bytes(SHAPES[name])

    assert existing_row_count(path) == len(pd.read_csv(io.BytesIO(SHAPES[name])))


def test_a_stray_quote_still_leaves_the_count_above_the_parse(
    tmp_path: Path,
) -> None:
    """The reason the floor is not the parse. Excluding blank lines must not
    cost this: every swallowed line has content, so every one is counted."""
    data = b'a,b,c\n1,"2,3\n4,5,6\n7,8,9\n10,11,"12\n13,14,15\n'
    path = tmp_path / "store.csv"
    path.write_bytes(data)

    parsed = len(pd.read_csv(io.BytesIO(data)))

    assert parsed == 2
    assert existing_row_count(path) == 5


def test_bytes_that_are_not_utf8_are_counted_not_raised(tmp_path: Path) -> None:
    path = tmp_path / "store.csv"
    path.write_bytes(HEAD + b"\xff\xfe,x,y\n")

    assert existing_row_count(path) == 2


def test_an_empty_or_absent_file_holds_no_rows(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")

    assert existing_row_count(empty) == 0
    assert existing_row_count(tmp_path / "absent.csv") == 0


# --------------------------------------------------------------------------
# The guard it feeds: the forward ledger.
# --------------------------------------------------------------------------

def _settle_one_day(tmp_path: Path, day: str, commence: str) -> None:
    row = {
        "commence_time": commence,
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "market": "moneyline",
        "player": "",
        "selection": "home",
        "line": None,
        "american_odds": -120,
        "book": "DraftKings",
    }
    fe.write_snapshot(
        pd.DataFrame([row]),
        {selection_key(SimpleNamespace(**row), market="moneyline",
                       selection="home", line=None): 0.62},
        key_for=selection_key,
        verdicts_line="x",
        snapshot_date=day,
        archive_dir=tmp_path / "archive",
    )
    fe.settle_snapshots(
        pd.DataFrame(columns=["date", "player_id", "player", "team"]),
        pd.DataFrame([{"game_id": 0, "date": day, "home_team": "TOR",
                       "away_team": "BOS", "home_goals": 4, "away_goals": 2,
                       "regulation": True}]),
        team_names={"toronto maple leafs": "TOR", "boston bruins": "BOS"},
        archive_dir=tmp_path / "archive",
        processed_dir=tmp_path / "processed",
        now=datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc),
    )


def test_a_ledger_ending_in_blank_lines_takes_an_honest_append(
    tmp_path: Path,
) -> None:
    """It held one row and three blank lines; the old count said four, so
    one new row made two, and the shrink guard refused two over four."""
    _settle_one_day(tmp_path, "2026-10-06", "2026-10-07T00:10:00Z")
    ledger = tmp_path / "processed" / fe.LEDGER_FILENAME
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write("\n\n\n")

    _settle_one_day(tmp_path, "2026-10-08", "2026-10-09T00:10:00Z")

    assert list(fe.load_ledger(tmp_path / "processed")["snapshot_date"]
                .astype(str)) == ["2026-10-06", "2026-10-08"]
    assert existing_row_count(ledger) == 2
