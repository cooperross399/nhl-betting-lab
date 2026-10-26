"""Every row on All results comes from a frozen board in the archive.

tracker.json is summed from each settled night's frozen board, so a row whose
date has no `history/<date>.json` (and no entry in the archive index) would
be a bet nobody could look up. Built end to end: one board, then the morning
it settles.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import importlib.util

from test_site_never_calls_an_unpriced_game_a_pass import BOARD_DAY, build, make_lab

ROOT = Path(__file__).resolve().parents[1]


def _index(data: Path) -> dict:
    """history/index.json as the publish run writes it (web/site_history.py)."""
    spec = importlib.util.spec_from_file_location("site_history", ROOT / "web" / "site_history.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--data", str(data)]) == 0
    return json.loads((data / "history" / "index.json").read_text(encoding="utf-8"))


def test_each_tracked_row_has_a_frozen_board(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    out = tmp_path / "out"
    build(lab, out, monkeypatch)
    build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)
    tracker = json.loads((out / "tracker.json").read_text(encoding="utf-8"))
    assert tracker["rows"], "the settled best bet is tracked"
    archived = {e["date"] for e in _index(out)["dates"]}
    for row in tracker["rows"]:
        assert (out / "history" / f"{row['date']}.json").is_file(), row
        assert row["date"] in archived, (row["date"], sorted(archived))


def test_the_record_scores_totals_and_puck_lines_once_settled(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    out = tmp_path / "out"
    build(lab, out, monkeypatch)
    record = json.loads((out / "record.json").read_text(encoding="utf-8"))
    assert "markets" not in record and "dueList" not in record, "nothing has settled"
    build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)
    record = json.loads((out / "record.json").read_text(encoding="utf-8"))
    assert "sealed" not in record
    total = record["markets"]["total"]
    assert total["games"] == sum(b["games"] for b in total["buckets"]) > 0
    for b in total["buckets"]:
        assert b["low"] <= b["predicted"] <= b["high"] and 0 <= b["actual"] <= 1 and len(b["interval"]) == 2
