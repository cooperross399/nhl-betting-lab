"""Team ratings read shooter-adjusted xG weighted for the score it came at.

Cooper, 2026-10-25 (PostHockey's score & venue adjustment). These hold:

* in every season and even-strength score state, the weighted home share of
  xG equals the season's home share at that strength, and each state's total
  is unchanged;
* power-play, penalty-kill and extra-attacker attempts keep weight 1, and so
  does a state too thin to read;
* the ratings file is built on the adjusted columns when the table carries
  them, says so, and is built as before when it does not.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nhl_betting_lab.shadow import measurement, metrics

_SPEC = importlib.util.spec_from_file_location(
    "_board_ratings_sva",
    Path(__file__).resolve().parent / "test_the_board_is_rated_on_expected_goals.py",
)
_BOARD = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_BOARD)


def _shots() -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(7)
    for i in range(4000):
        is_home = bool(rng.random() < 0.5)
        # Home trails in a quarter of the attempts and shoots more when it does.
        home_diff = int(rng.choice([-2, -1, 0, 0, 1, 2]))
        if home_diff < 0 and rng.random() < 0.3:
            is_home = True
        strength = "PP" if i % 10 == 0 else "5v5"
        rows.append({
            "game_id": 2025020001 + i // 60, "is_home": is_home,
            "score_diff": home_diff if is_home else -home_diff,
            "strength": strength, "xg_sh": 0.08,
        })
    return pd.DataFrame(rows)


def test_each_state_is_levelled_to_the_seasons_home_share() -> None:
    shots = _shots()
    w = metrics.score_weights(shots)
    even = shots[shots["strength"] == "5v5"]
    overall = even.loc[even["is_home"], "xg_sh"].sum() / even["xg_sh"].sum()
    home_diff = np.where(even["is_home"], even["score_diff"], -even["score_diff"])
    for state in sorted(set(home_diff)):
        cell = even[home_diff == state]
        weighted = cell["xg_sh"] * w[cell.index]
        assert weighted.sum() == pytest.approx(cell["xg_sh"].sum())
        assert weighted[cell["is_home"]].sum() / weighted.sum() == pytest.approx(overall)
    # Trailing home attempts are weighted down, leading ones up.
    trailing = even[(home_diff < 0) & even["is_home"]]
    assert w[trailing.index].iloc[0] < 1.0
    assert (w[shots["strength"] == "PP"] == 1.0).all()


def test_a_thin_state_keeps_weight_one() -> None:
    shots = _shots().head(50)
    assert (metrics.score_weights(shots) == 1.0).all()


def test_the_ratings_use_the_adjusted_columns_when_present() -> None:
    games, table = _BOARD._games_and_metrics()
    plain = measurement.xg_team_ratings(1.0, games, table)
    assert plain["score_adjusted"] is False
    adjusted_table = table.assign(xgf_sva=table["xgf_adj"] * 0.9, xga_sva=table["xga_adj"])
    adjusted = measurement.xg_team_ratings(1.0, games, adjusted_table)
    assert adjusted["score_adjusted"] is True
    assert adjusted["variant"] == measurement.RATINGS_VARIANT_KEY
    assert adjusted["teams"] != plain["teams"]
