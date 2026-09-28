"""A board built on an earlier day's card is shown, and never frozen.

Publish Site's cron build can start before today's Gameday Refresh finishes;
it then restores YESTERDAY's run, whose board has no back-to-back flags and a
model fitted without last night's games (430 of 430 sides, 40 flipped winners
on 2025-26). The day's first frozen board is the record Results grades, and
it is never edited, so a stale build must not become it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("_site_history_under_test", ROOT / "web" / "site_history.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


site_history = _module()


def _board(**overrides) -> dict:
    board = {
        "phase": "regular",
        "boardDate": "2026-10-15",
        "games": [{"id": "1", "startUtc": "2026-10-15T23:00:00Z"}],
        # 09:31 New York on the board's own day.
        "cardGeneratedAt": "2026-10-15T13:31:00+00:00",
    }
    board.update(overrides)
    return board


def test_a_board_built_on_todays_card_is_fresh() -> None:
    assert site_history.built_on_stale_state(_board()) is False


def test_a_board_built_on_yesterdays_card_is_stale() -> None:
    assert site_history.built_on_stale_state(_board(cardGeneratedAt="2026-10-14T13:31:00Z")) is True


def test_the_day_is_new_yorks_not_utcs() -> None:
    """00:30 UTC on the 16th is 20:30 on the 15th in New York: still today's."""
    late = _board(cardGeneratedAt="2026-10-16T00:30:00Z")
    early = _board(cardGeneratedAt="2026-10-15T03:30:00Z")  # 23:30 on the 14th in New York
    assert site_history.built_on_stale_state(late) is False
    assert site_history.built_on_stale_state(early) is True


@pytest.mark.parametrize("stamp", ["", "not a time", "2026-10-15T09:31:00"])
def test_an_unreadable_card_time_is_stale(stamp) -> None:
    """Doubt falls on not freezing: a card that cannot say when it was
    generated cannot say it was today's."""
    assert site_history.built_on_stale_state(_board(cardGeneratedAt=stamp)) is True


def test_a_board_with_no_card_is_not_stale() -> None:
    """The lab's no-state path publishes and freezes the schedule alone, so
    Results can say the board carried no projection. That is not this rule's
    to change."""
    assert site_history.built_on_stale_state(_board(cardGeneratedAt=None)) is False


def test_preseason_and_empty_boards_are_never_stale() -> None:
    """No card stands behind them, and Gameday does not run for them: the
    cron build is their only build, and it must still freeze."""
    assert site_history.built_on_stale_state(_board(phase="preseason", cardGeneratedAt=None)) is False
    assert site_history.built_on_stale_state(_board(games=[], cardGeneratedAt=None)) is False


def _run(data: Path, board: dict) -> None:
    (data / "board.json").write_text(json.dumps(board), encoding="utf-8")
    site_history.main(["--data", str(data)])


def test_the_publish_step_does_not_freeze_a_stale_board(tmp_path: Path) -> None:
    _run(tmp_path, _board(cardGeneratedAt="2026-10-14T13:31:00Z"))

    assert not (tmp_path / "history" / "2026-10-15.json").exists()


def test_the_build_after_todays_run_freezes_the_day_and_then_it_stands(tmp_path: Path) -> None:
    """The first FRESH board is the record, and a later one never edits it."""
    _run(tmp_path, _board(cardGeneratedAt="2026-10-14T13:31:00Z"))
    _run(tmp_path, _board(cardGeneratedAt="2026-10-15T13:31:00Z", notice="first fresh"))
    _run(tmp_path, _board(cardGeneratedAt="2026-10-15T19:00:00Z", notice="later"))

    frozen = json.loads((tmp_path / "history" / "2026-10-15.json").read_text(encoding="utf-8"))
    assert frozen["notice"] == "first fresh"
