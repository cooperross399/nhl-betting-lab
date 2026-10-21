"""A market books post after the morning freeze still reaches the ledger.

Blocked shots, hits and goalie saves are posted late and picked game by
game. The afternoon re-price staked them while the day's snapshot, frozen
that morning, stood untouched: on 2026-10-19 the card staked 13 saves bets
and 5 blocks the forward ledger never saw. A later run now adds a late
market's rows for every game the snapshot holds none of that market for,
and touches nothing already frozen.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import GAME_BY_GAME_MARKETS

MORNING = datetime(2026, 10, 19, 13, 40, tzinfo=timezone.utc)
AFTERNOON = datetime(2026, 10, 19, 20, 30, tzinfo=timezone.utc)
DAY = "2026-10-19"


def _row(**overrides) -> dict:
    row = {
        "commence_time": "2026-10-19T23:10:00Z",
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "market": "shots_on_goal",
        "player": "Auston Matthews",
        "selection": "over",
        "line": 3.5,
        "american_odds": 120,
        "book": "DraftKings",
    }
    row.update(overrides)
    return row


def _write(tmp_path: Path, rows: list[dict], now: datetime, late=GAME_BY_GAME_MARKETS):
    probabilities = {
        selection_key(SimpleNamespace(**r), market=r["market"],
                      selection=r["selection"], line=float(r["line"])): 0.6
        for r in rows
    }
    tally: dict = {}
    path = fe.write_snapshot(
        pd.DataFrame(rows), probabilities, key_for=selection_key,
        verdicts_line="x", snapshot_date=DAY, now=now, archive_dir=tmp_path,
        tally=tally, late_markets=late,
    )
    return path, tally


def _saves(goalie: str, home: str = "Toronto Maple Leafs", away: str = "Boston Bruins", **kw) -> dict:
    return _row(market="goalie_saves", player=goalie, line=25.5,
                home_team=home, away_team=away, **kw)


def test_a_late_market_posted_in_the_afternoon_is_added(tmp_path: Path) -> None:
    first, _ = _write(tmp_path, [_row()], MORNING)
    morning_bytes = first.read_bytes()

    path, tally = _write(tmp_path, [_row(american_odds=200), _saves("Joseph Woll")], AFTERNOON)

    assert tally["state"] == "added" and tally["frozen"] == 1
    assert path.read_bytes().startswith(morning_bytes)
    frame = pd.read_csv(path)
    assert list(frame["market"]) == ["shots_on_goal", "goalie_saves"]
    # The frozen skater prop was not repriced.
    assert list(frame["american_odds"]) == [120, 120]


def test_a_game_already_holding_the_market_is_not_repriced(tmp_path: Path) -> None:
    _write(tmp_path, [_saves("Joseph Woll")], MORNING)
    other = dict(home="Carolina Hurricanes", away="New York Islanders")

    path, tally = _write(
        tmp_path,
        [_saves("Joseph Woll", american_odds=250), _saves("Anthony Stolarz"),
         _saves("Frederik Andersen", **other)],
        AFTERNOON,
    )

    assert tally["frozen"] == 1
    frame = pd.read_csv(path)
    assert list(frame["player"]) == ["Joseph Woll", "Frederik Andersen"]
    assert list(frame["american_odds"]) == [120, 120]


def test_other_markets_keep_the_first_snapshot_rule(tmp_path: Path) -> None:
    first, _ = _write(tmp_path, [_saves("Joseph Woll")], MORNING)
    before = first.read_bytes()

    path, tally = _write(tmp_path, [_row(market="points", line=0.5)], AFTERNOON)

    assert path is None and tally["state"] == "exists"
    assert first.read_bytes() == before


def test_without_late_markets_nothing_is_added(tmp_path: Path) -> None:
    first, _ = _write(tmp_path, [_row()], MORNING)
    before = first.read_bytes()
    path, tally = _write(tmp_path, [_saves("Joseph Woll")], AFTERNOON, late=frozenset())
    assert path is None and tally["state"] == "exists"
    assert first.read_bytes() == before


def test_a_settled_day_takes_no_rows(tmp_path: Path) -> None:
    first, _ = _write(tmp_path, [_row()], MORNING)
    before = first.read_bytes()
    (first.parent / f"{DAY}.settled").touch()
    path, _ = _write(tmp_path, [_saves("Joseph Woll")], AFTERNOON)
    assert path is None
    assert first.read_bytes() == before


def test_a_started_game_is_not_added(tmp_path: Path) -> None:
    _write(tmp_path, [_row()], MORNING)
    late_night = datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc)
    path, tally = _write(tmp_path, [_saves("Joseph Woll")], late_night)
    assert path is None and tally["started"] == 1


def _restore_state():
    path = Path(__file__).resolve().parents[1] / "scripts" / "restore_state.py"
    spec = importlib.util.spec_from_file_location("restore_state_late", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_restore_keeps_the_added_rows(tmp_path: Path) -> None:
    """An older carrier holding the morning file must not put it back over the
    restored copy that only added late rows to it."""
    rs = _restore_state()
    older, dest = tmp_path / "older", tmp_path / "dest"
    _write(older / "archive", [_row()], MORNING)
    _write(dest / "archive", [_row()], MORNING)
    added, _ = _write(dest / "archive", [_saves("Joseph Woll")], AFTERNOON)
    after = added.read_bytes()

    assert rs._first_opinions(older, dest, 1) == 0
    assert added.read_bytes() == after
