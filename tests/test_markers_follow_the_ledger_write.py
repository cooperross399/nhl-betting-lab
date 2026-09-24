"""A day was marked settled before its rows reached the ledger.

`settle_snapshots` touched each day's `{day}.settled` marker inside the
per-day loop, and wrote the ledger only after it. Two refusals sit between
the two: `read_store(..., for_append=True)` raises on a damaged ledger, and
the append-only shrink guard raises when the frame would be shorter than the
file. Either way every day processed in that pass was already marked, its rows
never written, and the marker stopped it from ever being retried — permanent
loss from a ledger that cannot be rebuilt, caused by the guards that exist to
prevent loss.

Which damage reaches that far was measured, not assumed. The top of
`settle_snapshots` reads the ledger's `snapshot_date` column before the loop,
and invalid UTF-8 or an unclosed quote make that read raise before any marker
is touched. A row with one field too many does not: `usecols` parses it, and
`read_store` refuses it only after the loop. That is the damaged ledger used
here. The shrink guard is reached by a read that comes back short without
raising, modelled as `tests/test_forward_evidence.py` models it.

What these tests hold:

* a write refused for either reason marks no day, empty days included, and
  leaves the ledger byte-identical;
* the day is retried and settles once the ledger is repaired;
* a successful pass marks exactly the days it settled or found empty, and
  never a day still waiting for results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.stores import CorruptStoreError


TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}
LATER = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)


def _moneyline(
    commence: str = "2026-10-09T00:10:00Z", **overrides
) -> dict:
    """A Toronto-Boston moneyline row. Commence 00:10Z is the day before."""
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
    row.update(overrides)
    return row


def _snapshot(archive: Path, rows: list[dict], day: str) -> None:
    """Freeze rows the way the card does, each with a model opinion."""
    probabilities = {}
    for raw in rows:
        line = raw.get("line")
        probabilities[
            selection_key(
                SimpleNamespace(**raw),
                market=raw["market"],
                selection=raw["selection"],
                line=None if line is None else float(line),
            )
        ] = 0.62
    assert fe.write_snapshot(
        pd.DataFrame(rows, columns=list(_moneyline())),
        probabilities,
        key_for=selection_key,
        verdicts_line="team_b2b=in force",
        snapshot_date=day,
        archive_dir=archive,
    ) is not None


def _games(*days: str) -> pd.DataFrame:
    """Toronto beating Boston 4-2 on each league date given."""
    return pd.DataFrame(
        [
            {"game_id": i, "date": day, "home_team": "TOR", "away_team": "BOS",
             "home_goals": 4, "away_goals": 2, "regulation": True}
            for i, day in enumerate(days)
        ],
        columns=["game_id", "date", "home_team", "away_team", "home_goals",
                 "away_goals", "regulation"],
    )


def _settle(tmp_path: Path, games: pd.DataFrame, now: datetime = LATER):
    return fe.settle_snapshots(
        pd.DataFrame(columns=["date", "player_id", "player", "team"]),
        games,
        team_names=TEAM_MAP,
        archive_dir=tmp_path / "archive",
        processed_dir=tmp_path / "processed",
        now=now,
    )


def _markers(tmp_path: Path) -> list[str]:
    return sorted(
        p.name.removesuffix(".settled")
        for p in fe.snapshots_dir(tmp_path / "archive").glob("*.settled")
    )


def _ledger(tmp_path: Path) -> Path:
    return tmp_path / "processed" / fe.LEDGER_FILENAME


def _settled_before(tmp_path: Path, rows: int = 1) -> bytes:
    """A ledger that already holds `rows` honestly settled rows for 10-06."""
    _snapshot(
        tmp_path / "archive",
        [_moneyline(commence="2026-10-07T00:10:00Z", book=f"Book{i}")
         for i in range(rows)],
        day="2026-10-06",
    )
    _settle(tmp_path, _games("2026-10-06"))
    assert _markers(tmp_path) == ["2026-10-06"]
    assert len(fe.load_ledger(tmp_path / "processed")) == rows
    return _ledger(tmp_path).read_bytes()


def _pending_today(tmp_path: Path) -> None:
    """One day with a row to settle, and one empty day, both pending."""
    _snapshot(tmp_path / "archive", [_moneyline()], day="2026-10-08")
    _snapshot(tmp_path / "archive", [], day="2026-10-09")


def _damage(ledger: Path) -> None:
    """One row with a field too many: the top read parses it, the append
    read refuses it. (Invalid UTF-8 or an unclosed quote would fail the top
    read first, before any marker — measured.)"""
    last = ledger.read_text(encoding="utf-8").splitlines()[-1]
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(last + ",EXTRA\n")


# --------------------------------------------------------------------------
# A refused write marks nothing.
# --------------------------------------------------------------------------

def test_a_damaged_ledger_marks_no_day_and_the_day_is_retried(
    tmp_path: Path,
) -> None:
    clean = _settled_before(tmp_path)
    _pending_today(tmp_path)
    _damage(_ledger(tmp_path))
    damaged = _ledger(tmp_path).read_bytes()

    with pytest.raises(CorruptStoreError):
        _settle(tmp_path, _games("2026-10-06", "2026-10-08"))

    assert _markers(tmp_path) == ["2026-10-06"], (
        "a day was marked settled although its rows never reached the ledger"
    )
    assert _ledger(tmp_path).read_bytes() == damaged

    # Repaired from wherever it came from, the same day settles.
    _ledger(tmp_path).write_bytes(clean)
    retried = _settle(tmp_path, _games("2026-10-06", "2026-10-08"))
    ledger = fe.load_ledger(tmp_path / "processed")

    assert retried.snapshots_settled == 2
    assert _markers(tmp_path) == ["2026-10-06", "2026-10-08", "2026-10-09"]
    assert sorted(ledger["snapshot_date"].astype(str)) == [
        "2026-10-06", "2026-10-08",
    ]


def test_a_refused_shrink_marks_no_day_and_the_day_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The quiet failure: the append read comes back short without raising,
    so the line count off the file is what the guard refuses on."""
    before = _settled_before(tmp_path, rows=3)
    _pending_today(tmp_path)
    real_read = fe.read_store
    monkeypatch.setattr(
        fe, "read_store", lambda *a, **k: real_read(*a, **k).head(0)
    )

    with pytest.raises(ValueError, match="append-only"):
        _settle(tmp_path, _games("2026-10-06", "2026-10-08"))

    assert _markers(tmp_path) == ["2026-10-06"], (
        "a day was marked settled although its rows never reached the ledger"
    )
    assert _ledger(tmp_path).read_bytes() == before

    monkeypatch.setattr(fe, "read_store", real_read)
    _settle(tmp_path, _games("2026-10-06", "2026-10-08"))

    assert _markers(tmp_path) == ["2026-10-06", "2026-10-08", "2026-10-09"]
    assert len(fe.load_ledger(tmp_path / "processed")) == 4


def test_an_empty_day_is_not_marked_by_a_pass_whose_write_refused(
    tmp_path: Path,
) -> None:
    """An empty day has a marker and no rows, so nothing but ordering says
    whether its pass completed — and a pass whose write refused did not."""
    _settled_before(tmp_path)
    _snapshot(tmp_path / "archive", [], day="2026-10-07")
    _snapshot(tmp_path / "archive", [_moneyline()], day="2026-10-08")
    _damage(_ledger(tmp_path))

    with pytest.raises(CorruptStoreError):
        _settle(tmp_path, _games("2026-10-06", "2026-10-08"))

    assert "2026-10-07" not in _markers(tmp_path)


# --------------------------------------------------------------------------
# A pass that succeeds marks exactly what it finished.
# --------------------------------------------------------------------------

def test_a_successful_pass_marks_the_days_it_finished_and_no_other(
    tmp_path: Path,
) -> None:
    _snapshot(tmp_path / "archive", [], day="2026-10-07")
    _snapshot(tmp_path / "archive", [_moneyline()], day="2026-10-08")
    # No result for this one yet, and it is inside patience: it waits.
    _snapshot(
        tmp_path / "archive",
        [_moneyline(commence="2026-10-29T23:10:00Z")],
        day="2026-10-29",
    )

    result = _settle(tmp_path, _games("2026-10-08"))

    assert result.snapshots_settled == 2
    assert result.snapshots_waiting == 1
    assert _markers(tmp_path) == ["2026-10-07", "2026-10-08"]
    assert list(fe.load_ledger(tmp_path / "processed")["snapshot_date"]
                .astype(str)) == ["2026-10-08"]

    again = _settle(tmp_path, _games("2026-10-08"))

    assert again.snapshots_seen == 1  # only the waiting day
    assert len(fe.load_ledger(tmp_path / "processed")) == 1
