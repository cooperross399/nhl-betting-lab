"""Line movement since the day's first card moves the model with the books.

Cooper, 2026-10-21. `price_movement` reads the day's first priced snapshot as
the open and this run's staged prices as now; these hold:

* the move is the median change in implied probability over books quoting
  the selection both times, and a selection no book quoted both times has
  none;
* the model moves half way with it, never more than five points, and a
  selection with no move keeps its probability;
* with no snapshot yet (the first card of the day) nothing moves.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab import price_movement as pm
from nhl_betting_lab.forward_evidence import snapshots_dir
from nhl_betting_lab.reports.card_pricing import selection_key

DAY = "2026-10-22"


def _rows(prices: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame([
        {"market": "shots_on_goal", "player": "Auston Matthews", "selection": selection,
         "line": 3.5, "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
         "commence_time": f"{DAY}T23:00:00Z", "book": book, "american_odds": odds}
        for book, selection, odds in prices
    ])


def _key(selection: str) -> tuple:
    row = _rows([("x", selection, 100)]).iloc[0]
    return selection_key(row, market="shots_on_goal", selection=selection, line=3.5)


def test_the_move_is_the_median_over_books_quoting_both_times() -> None:
    opened = _rows([("dk", "over", 100), ("fd", "over", 100), ("mgm", "over", 100)])
    now = _rows([("dk", "over", -150), ("fd", "over", -120), ("new", "over", -300), ("dk", "under", 120)])
    moves = pm.movement(opened, now, selection_key)
    # dk 0.5 -> 0.6, fd 0.5 -> 0.5455; "new" and "mgm" are not in both.
    assert moves[_key("over")] == pytest.approx((0.1 + 120 / 220 - 0.5) / 2)
    assert _key("under") not in moves


def test_the_model_moves_half_way_and_at_most_five_points() -> None:
    probabilities = {_key("over"): 0.55, _key("under"): 0.45, ("other",): 0.3}
    moved, count = pm.apply_movement(
        probabilities, {_key("over"): 0.04, _key("under"): -0.3, ("absent",): 0.1}
    )
    assert count == 2
    assert moved[_key("over")] == pytest.approx(0.57)
    assert moved[_key("under")] == pytest.approx(0.40)
    assert moved[("other",)] == 0.3 and ("absent",) not in moved


def test_the_first_card_of_the_day_sees_no_movement(tmp_path) -> None:
    assert pm.opening_snapshot(tmp_path, DAY) is None
    assert pm.movement(None, _rows([("dk", "over", -150)]), selection_key) == {}
    path = snapshots_dir(tmp_path) / f"{DAY}.csv"
    path.parent.mkdir(parents=True)
    path.write_text("not,a,snapshot\n1,2,3\n", encoding="utf-8")
    assert pm.opening_snapshot(tmp_path, DAY) is None
