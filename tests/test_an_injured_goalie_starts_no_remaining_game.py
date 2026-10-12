"""An injured goalie is given no start in a game he cannot play.

The Season page splits each team's remaining starts among its goalies by the
depth chart in ``data/season_sim/roster_notes.json``, leaned toward the
starts already made this season. Before 2026-10-12 that lean ran after the
injury list was read, so a starter hurt after a few starts kept a share of
games he would never play: Igor Shesterkin, out for the season with a knee
injury, was projected for 19 more Rangers starts. These tests hold the split
to the injury list on a synthetic schedule, with no network:

* a goalie out for the season starts none of the remaining games, whatever
  starts he made before the injury;
* a goalie out until a date starts nothing before it, and takes his share
  from that date on;
* every remaining game is still started by someone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from season_sim.model import _remaining_starts  # noqa: E402


def _games(days: list[str]) -> list[dict]:
    return [dict(date=d) for d in days]


SCHEDULE = _games([f"2026-10-{d:02d}" for d in range(13, 32)] + [f"2026-11-{d:02d}" for d in range(1, 21)])


def test_a_goalie_out_for_the_season_starts_nothing() -> None:
    # the injured starter's early starts lean him toward a big share
    weights = {"starter": 0.4, "backup": 0.3, "third": 0.3}
    starts = _remaining_starts(weights, {"starter": "season"}, SCHEDULE)
    assert starts["starter"] == 0.0
    assert sum(starts.values()) == pytest.approx(len(SCHEDULE))
    assert starts["backup"] == pytest.approx(starts["third"])


def test_a_goalie_out_until_a_date_starts_only_from_that_date() -> None:
    weights = {"a": 0.5, "b": 0.5}
    starts = _remaining_starts(weights, {"b": "2026-11-09"}, SCHEDULE)
    before = sum(1 for g in SCHEDULE if g["date"] < "2026-11-09")
    after = len(SCHEDULE) - before
    assert starts["b"] == pytest.approx(0.5 * after)
    assert starts["a"] == pytest.approx(before + 0.5 * after)


def test_a_night_with_no_fit_goalie_still_has_a_starter() -> None:
    weights = {"a": 0.6, "b": 0.4}
    starts = _remaining_starts(weights, {"a": "season", "b": "season"}, SCHEDULE)
    assert sum(starts.values()) == pytest.approx(len(SCHEDULE))
    assert starts["a"] == pytest.approx(0.6 * len(SCHEDULE))


def test_a_healthy_room_splits_by_the_weights() -> None:
    weights = {"a": 3.0, "b": 1.0}
    starts = _remaining_starts(weights, {}, SCHEDULE)
    assert starts["a"] == pytest.approx(0.75 * len(SCHEDULE))
    assert starts["b"] == pytest.approx(0.25 * len(SCHEDULE))
