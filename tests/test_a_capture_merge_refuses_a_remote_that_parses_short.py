"""A remote capture store that pandas reads short is refused, not merged over.

`scripts/merge_capture_store.py` is the Closing Lines publish step's retry
merge. Its shrink floor was `max(len(theirs), existing_row_count(theirs))`,
but the check compared that floor with the merged TOTAL, `theirs + mine`.
Two stray quotes make pandas read a 4-row remote as 2 garbled rows without an
error, and four local rows then carried the merge to 6 >= 4: the guard passed,
a store missing two remote captures was written, and the workflow pushed it.
A capture dropped after puck drop cannot be taken again.

This is the class #266 closed in the forward ledger (`_read_ledger`) and in
`closing_lines.append_captures`: the floor comes from the file, and it is
compared with the part of the result that came FROM that file, never with a
total the new rows can pad.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab.stores import existing_row_count

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import merge_capture_store as script  # noqa: E402


def _captures(count: int, stamp: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "commence_time": "2026-10-09T00:10:00Z",
                "home_team": "Toronto Maple Leafs",
                "away_team": "Boston Bruins",
                "captured_at": stamp,
                "market": "shots_on_goal",
                "player": f"Player {i}",
                "selection": "over",
                "line": 2.5,
                "american_odds": 120.0,
                "book": "DK",
            }
            for i in range(count)
        ],
        columns=list(cl.CAPTURE_COLUMNS),
    )


def _write(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, lineterminator="\n")


def _stray_quotes(path: Path) -> None:
    """Two stray quotes: rows 1-3 fold into one field, and pandas says nothing."""
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace(",DK", ',"DK', 1)
    lines[3] = lines[3].replace(",DK", ',DK"', 1)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _files(tmp_path: Path, *, remote: int = 4, local: int = 4):
    theirs, mine, out = (tmp_path / name for name in ("theirs.csv", "mine.csv", "out.csv"))
    _write(_captures(remote, "2026-10-08T21:00:00Z"), theirs)
    _write(_captures(local, "2026-10-08T23:00:00Z"), mine)
    return theirs, mine, out


def _run(theirs: Path, mine: Path, out: Path) -> int:
    return script.main(["--mine", str(mine), "--theirs", str(theirs), "--out", str(out)])


def test_a_remote_that_parses_short_is_refused_even_when_new_rows_pad_the_total(
    tmp_path, capsys
):
    theirs, mine, out = _files(tmp_path)
    _stray_quotes(theirs)
    # The premise: pandas reads it short and raises nothing.
    assert len(pd.read_csv(theirs)) == 2 < existing_row_count(theirs) == 4

    code = _run(theirs, mine, out)

    assert code != 0, "a short read must fail the publish step"
    assert not out.exists(), "a refused merge must leave nothing behind to push"
    err = capsys.readouterr().err
    assert "::error::" in err
    assert "parses to only 2 of its 4" in err


def test_a_local_store_that_parses_short_is_refused_too(tmp_path, capsys):
    """`mine` is this run's captures; merging a garbled copy of them would
    publish fewer than were taken, and nothing downstream would notice."""
    theirs, mine, out = _files(tmp_path)
    _stray_quotes(mine)
    assert len(pd.read_csv(mine)) < existing_row_count(mine)

    assert _run(theirs, mine, out) != 0
    assert not out.exists()
    assert "::error::" in capsys.readouterr().err


def test_merge_compares_the_floor_with_the_remote_part_not_the_total():
    """The library call on its own: a parse short of the file's count is
    refused however many local rows arrive to make up the difference."""
    theirs = _captures(2, "2026-10-08T21:00:00Z")
    mine = _captures(4, "2026-10-08T23:00:00Z")

    with pytest.raises(ValueError, match="parses to only 2 of its 4"):
        script.merge(mine, theirs, remote_rows=4)


def test_a_clean_collision_still_merges_every_row(tmp_path, capsys):
    """The other side of the line: two healthy stores merge, exit 0, and keep
    every row either side held — the case the retry exists for."""
    theirs, mine, out = _files(tmp_path, remote=4, local=3)

    assert _run(theirs, mine, out) == 0
    assert len(pd.read_csv(out)) == 7
    assert "::error::" not in capsys.readouterr().err


def test_a_remote_with_trailing_blank_lines_is_not_a_short_read(tmp_path):
    """`existing_row_count` skips blank lines as pandas does, so a blank line
    at the end of an append-only file is not mistaken for a lost row."""
    theirs, mine, out = _files(tmp_path)
    theirs.write_text(theirs.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")

    assert _run(theirs, mine, out) == 0
    assert len(pd.read_csv(out)) == 8
