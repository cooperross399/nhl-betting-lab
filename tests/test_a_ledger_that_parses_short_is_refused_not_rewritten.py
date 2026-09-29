"""A forward ledger that pandas reads short without an error is refused.

Sweep 5 (`forward-ledger-short-parse-rewritten-over`). `_read_ledger`
refused only a ledger that made pandas raise. One stray double quote in a
settled ledger instead made pandas read 4 rows as 3 garbled ones, with no
error. The shrink guard in `settle_snapshots` then compared the TOTAL after
the append (3 existing + 4 new) with the file's 4 lines, so the new day's
rows hid the swallowed ones, the garbled frame was written over the ledger,
and every row of the earlier day was gone for good while its `.settled`
marker stood. The pass read as normal and the runner exited 0.

`closing_lines.append_captures` had the same masked floor.

The other side of the line: a ledger whose fields legitimately hold a quoted
newline has more physical lines than rows, and must still be appended to.
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
from nhl_betting_lab.stores import CorruptStoreError, existing_row_count

TEAM_NAMES = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}
DAY_1, DAY_2 = "2026-10-08", "2026-10-10"


def _freeze(archive: Path, day: str, players: list[str], verdicts: str) -> None:
    rows = [
        {
            "commence_time": f"{day[:8]}{int(day[8:]) + 1:02d}T00:10:00Z",
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "market": "shots_on_goal",
            "player": player,
            "selection": "over",
            "line": 2.5,
            "american_odds": 120,
            "book": "DK",
        }
        for player in players
    ]
    probabilities = {
        selection_key(
            SimpleNamespace(**row), market=row["market"], selection="over", line=2.5
        ): 0.6
        for row in rows
    }
    assert fe.write_snapshot(
        pd.DataFrame(rows),
        probabilities,
        key_for=selection_key,
        verdicts_line=verdicts,
        snapshot_date=day,
        now=datetime.fromisoformat(f"{day}T15:00:00+00:00"),
        archive_dir=archive,
    )


def _logs(day: str, players: list[str]) -> list[dict]:
    return [
        {
            "date": day, "player_id": 100 + i, "player": player, "team": "TOR",
            "shots_on_goal": 3.0, "points": 0.0, "goals": 0.0, "assists": 0.0,
            "blocked_shots": 0.0, "hits": 0.0, "saves": 0.0,
            "toi_seconds": 1000.0,
        }
        for i, player in enumerate(players)
    ]


GAMES = pd.DataFrame([
    {"game_id": 1, "date": DAY_1, "home_team": "TOR", "away_team": "BOS",
     "home_goals": 3, "away_goals": 2, "regulation": True},
    {"game_id": 2, "date": DAY_2, "home_team": "TOR", "away_team": "BOS",
     "home_goals": 3, "away_goals": 2, "regulation": True},
])


def _settle(archive: Path, processed: Path, logs: pd.DataFrame, day: str):
    return fe.settle_snapshots(
        logs, GAMES, team_names=TEAM_NAMES, archive_dir=archive,
        processed_dir=processed,
        now=datetime.fromisoformat(f"{day}T15:00:00+00:00").replace(
            tzinfo=timezone.utc
        ),
    )


def _first_day_settled(tmp_path: Path, *, verdicts: str, day_2_players: int = 4):
    archive, processed = tmp_path / "archive", tmp_path / "processed"
    first = [f"Player {i}" for i in range(4)]
    second = [f"Skater {i}" for i in range(day_2_players)]
    logs = pd.DataFrame(_logs(DAY_1, first) + _logs(DAY_2, second))
    _freeze(archive, DAY_1, first, verdicts)
    _settle(archive, processed, logs, "2026-10-09")
    ledger = processed / fe.LEDGER_FILENAME
    assert len(pd.read_csv(ledger)) == 4
    _freeze(archive, DAY_2, second, verdicts)
    return archive, processed, logs, ledger


def _stray_quote(ledger: Path) -> None:
    """One stray `"` before row 1's settled_at: the damage the sweep measured."""
    stamp = pd.read_csv(ledger)["settled_at"].iloc[0]
    text = ledger.read_text(encoding="utf-8")
    assert f",{stamp}," in text
    ledger.write_text(
        text.replace(f",{stamp},", f',"{stamp},', 1), encoding="utf-8"
    )


def test_a_stray_quote_that_parses_short_is_refused_and_nothing_moves(tmp_path):
    archive, processed, logs, ledger = _first_day_settled(
        tmp_path, verdicts="team=off, props=in force"
    )
    _stray_quote(ledger)
    # The premise: pandas reads it short and says nothing.
    assert len(pd.read_csv(ledger)) < existing_row_count(ledger) == 4
    before = ledger.read_bytes()

    with pytest.raises(CorruptStoreError, match="parses to only 3 of its 4"):
        _settle(archive, processed, logs, "2026-10-11")

    assert ledger.read_bytes() == before
    marker = fe.snapshots_dir(archive) / f"{DAY_2}.settled"
    assert not marker.exists(), "a refused pass must leave the day pending"


def test_a_row_folded_in_with_only_its_date_showing_is_still_a_row(tmp_path):
    """A quote at the head of a row closes the field it folds into there, so
    the field ends in a newline and the row's bare date — no comma after it.
    That line is still a row, not a quoted newline."""
    archive, processed, logs, ledger = _first_day_settled(
        tmp_path, verdicts="team=off, props=in force"
    )
    _stray_quote(ledger)
    lines = ledger.read_text(encoding="utf-8").splitlines()
    lines[2] = f'"{lines[2]}'
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parsed = pd.read_csv(ledger)
    assert len(parsed) == 3
    assert parsed.map(
        lambda v: isinstance(v, str) and v.endswith(f"\n{DAY_1}")
    ).any().any()
    before = ledger.read_bytes()

    with pytest.raises(CorruptStoreError, match="parses to only 3 of its 4"):
        _settle(archive, processed, logs, "2026-10-11")
    assert ledger.read_bytes() == before


def test_the_shrink_guard_counts_the_existing_rows_not_the_total(
    tmp_path, monkeypatch
):
    """Any path that hands the append a short frame without raising — not
    only the read above — is refused at the write, however many new rows
    would otherwise hide the loss."""
    archive, processed, logs, ledger = _first_day_settled(
        tmp_path, verdicts="team=off"
    )
    before = ledger.read_bytes()
    read = fe._read_ledger
    monkeypatch.setattr(fe, "_read_ledger", lambda path: read(path).iloc[:-1])

    with pytest.raises(ValueError, match="Refusing to write"):
        _settle(archive, processed, logs, "2026-10-11")
    assert ledger.read_bytes() == before


def test_a_ledger_whose_fields_hold_quoted_newlines_is_still_appended_to(
    tmp_path,
):
    """Four rows on eight physical lines is a whole ledger, not a short one:
    pandas reads the quoted newline as part of the field."""
    archive, processed, logs, ledger = _first_day_settled(
        tmp_path, verdicts="team=off,\nprops=in force", day_2_players=1
    )
    assert existing_row_count(ledger) == 8 and len(pd.read_csv(ledger)) == 4

    result = _settle(archive, processed, logs, "2026-10-11")

    assert result.snapshots_settled == 1
    after = pd.read_csv(ledger)
    assert after["snapshot_date"].astype(str).value_counts().to_dict() == {
        DAY_1: 4, DAY_2: 1,
    }
    assert set(after["verdicts_in_force"]) == {"team=off,\nprops=in force"}


@pytest.mark.parametrize(
    "verdicts",
    [
        # A field that ends in a newline: its last line holds only the
        # closing quote, and is still a physical line.
        "team=off,props=in force\n",
        # An inner line of Unicode whitespace alone: blank to `str.strip`,
        # not to the byte count `existing_row_count` takes.
        "team=off,\n\u00a0\nprops=in force",
    ],
)
def test_every_line_a_legitimate_field_spans_is_counted_as_the_file_counts_it(
    tmp_path, verdicts
):
    archive, processed, logs, ledger = _first_day_settled(
        tmp_path, verdicts=verdicts, day_2_players=1
    )
    assert len(pd.read_csv(ledger)) == 4

    result = _settle(archive, processed, logs, "2026-10-11")

    assert result.snapshots_settled == 1
    assert len(pd.read_csv(ledger)) == 5


def test_a_quoted_newline_does_not_excuse_a_swallowed_row(tmp_path):
    """The allowance for quoted newlines is not a hole: a stray quote in a
    ledger that already holds them is refused all the same."""
    archive, processed, logs, ledger = _first_day_settled(
        tmp_path, verdicts="team=off,\nprops=in force"
    )
    # One stray quote cannot shorten this ledger without making pandas
    # raise; two can: before row 1's settled_at, and after row 2's date.
    _stray_quote(ledger)
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert lines[3].startswith(f"{DAY_1},")
    lines[3] = lines[3].replace(DAY_1, f'{DAY_1}"', 1)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parsed = pd.read_csv(ledger)
    assert len(parsed) == 3
    # The swallowed row now sits inside a field as a quoted newline would.
    assert parsed.map(lambda v: isinstance(v, str) and "\n" in v).any().any()
    before = ledger.read_bytes()

    with pytest.raises(CorruptStoreError, match="parses to only"):
        _settle(archive, processed, logs, "2026-10-11")
    assert ledger.read_bytes() == before


def _captures(n: int, stamp: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"captured_at": stamp, "commence_time": "2026-10-09T00:10:00Z",
             "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
             "market": "shots_on_goal", "player": f"P{i}", "selection": "over",
             "line": 2.5, "american_odds": 120.0, "book": "DK"}
            for i in range(n)
        ],
        columns=list(cl.CAPTURE_COLUMNS),
    )


def test_a_capture_store_that_parses_short_is_refused_not_rewritten(tmp_path):
    cl.append_captures(_captures(4, "2026-10-08T21:00:00+00:00"),
                       processed_dir=tmp_path)
    path = cl.captures_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace(",DK", ',"DK', 1)
    lines[3] = lines[3].replace(",DK", ',DK"', 1)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(pd.read_csv(path)) < existing_row_count(path) == 4
    before = path.read_bytes()

    with pytest.raises(CorruptStoreError, match="parses to only 2 of its 4"):
        cl.append_captures(_captures(4, "2026-10-08T23:00:00+00:00"),
                           processed_dir=tmp_path)
    assert path.read_bytes() == before
