"""The drought rule's backtest: the drought count and last season's totals."""
import importlib.util
from pathlib import Path

import pandas as pd

_spec = importlib.util.spec_from_file_location(
    "drought_rule_backtest", Path(__file__).resolve().parents[1] / "scripts" / "run_drought_rule_backtest.py")
drb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drb)


def test_drought_counts_games_before_this_one_and_resets_on_a_hit():
    assert drb.drought_before([0, 0, 1, 0, 0, 0]) == [0, 1, 2, 0, 1, 2]


def test_drought_carries_across_the_season_boundary_and_uses_last_seasons_totals():
    rows = []
    for i, (season, date, goals) in enumerate([(20232024, "2024-04-01", 3), (20232024, "2024-04-03", 0),
                                               (20242025, "2024-10-10", 0), (20242025, "2024-10-12", 0)]):
        rows.append({"game_id": i, "season": season, "game_type": 2, "date": date, "player_id": 9, "player": "A B",
                     "role": "skater", "goals": goals, "assists": 0, "points": goals})
    rows.append({**rows[0], "game_id": 99, "role": "goalie", "player_id": 1})
    out = drb.prepare_logs(pd.DataFrame(rows)).set_index("date")
    assert list(out.drought_goals) == [0, 0, 1, 2]
    assert out.loc["2024-10-12", "prior_goals"] == 3          # 2023-24 total applies to 2024-25
    assert pd.isna(out.loc["2024-04-01", "prior_goals"])       # no season before the first
    assert 1 not in set(out.player_id)                         # goalies never qualify


def test_qualifying_bars_are_the_ones_cooper_set():
    assert drb.THRESHOLDS == {"points": 70, "goals": 30, "assists": 30} and drb.MIN_DROUGHT == 5
