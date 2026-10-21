"""Rest, travel and the opponent's matchup by position reach the card.

Cooper, 2026-10-21, asked for the model to carry rest days, travel and time
zones, and what tonight's opponent allows by position. These hold:

* a club with three to ten days off is rested, one that crossed two or more
  time zones since its last rink travelled, and an unknown fact is neither;
* the team model fits both from its training games, moves who scores and
  never the expected total, and prices nothing differently when no state is
  set (so every committed measurement stands);
* the card sets tonight's state for each game it prices and clears it after;
* props read the opponent's concession for the player's own position group,
  falling back to the all-skater table, and the walk-forward clears the
  split unless asked for it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.backtest import team_walk_forward as twf
from nhl_betting_lab.backtest import walk_forward as wf
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.rest import schedule_state

_SPEC = importlib.util.spec_from_file_location(
    "_varied_logs_rt",
    Path(__file__).resolve().parent / "test_a_walk_forward_model_sees_only_earlier_games.py",
)
_VARIED = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_VARIED)


def test_rest_and_travel_read_the_schedule() -> None:
    assert schedule_state(("2025-01-01", "BOS"), "2025-01-04", "BOS") == {
        "long_rest": True, "travelled": False,
    }
    assert schedule_state(("2025-01-01", "BOS"), "2025-01-02", "VAN") == {
        "long_rest": False, "travelled": True,
    }
    # Across the summer is a season break, not rest, and not travel either.
    assert schedule_state(("2025-04-15", "BOS"), "2025-10-08", "VAN") == {
        "long_rest": False, "travelled": False,
    }
    assert schedule_state(None, "2025-01-02", "VAN") == {
        "long_rest": False, "travelled": False,
    }
    assert schedule_state(("2025-01-01", "XXX"), "2025-01-02", "VAN")["travelled"] is False


def test_the_team_model_moves_who_scores_not_the_total() -> None:
    model = TeamModel().fit(_VARIED.varied_games())
    plain = model.expected_goals("TOR", "BOS")
    model.schedule_factors = {
        "rest_for": 1.1, "rest_against": 0.95, "travel_for": 0.9, "travel_against": 1.05,
    }
    assert model.expected_goals("TOR", "BOS") == plain  # no state, no change
    model.schedule_state = {"TOR": {"long_rest": True, "travelled": False}}
    home, away = model.expected_goals("TOR", "BOS")
    assert home > plain[0] and away < plain[1]
    assert home + away == pytest.approx(sum(plain))
    model.schedule_state = {"BOS": {"long_rest": False, "travelled": True}}
    home, away = model.expected_goals("TOR", "BOS")
    assert away < plain[1] and home + away == pytest.approx(sum(plain))


def test_the_team_model_fits_the_factors() -> None:
    model = TeamModel().fit(_VARIED.varied_games())
    assert set(model.schedule_factors) == {
        "rest_for", "rest_against", "travel_for", "travel_against",
    }
    assert all(0.5 < v < 1.5 for v in model.schedule_factors.values())


def test_the_team_walk_forward_prices_schedule_only_when_asked() -> None:
    games = _VARIED.varied_games()
    plain, _ = twf.generate_team_samples(games, refit_days=30, minimum_history_games=50)
    again, _ = twf.generate_team_samples(games, refit_days=30, minimum_history_games=50)
    pd.testing.assert_frame_equal(plain, again)
    scheduled, _ = twf.generate_team_samples(
        games, refit_days=30, minimum_history_games=50, schedule=True
    )
    assert len(plain) == len(scheduled)


def test_props_read_the_opponents_concession_by_position() -> None:
    logs = _VARIED.varied_logs()
    model = PlayerPropsModel().fit(logs)
    assert set(model.opponent_group_factors["BOS"]) == {"F", "D"}
    model.team_form = {}
    centre, defenceman = 1, 2  # TOR's two skaters
    model.opponent_group_factors = {
        "BOS": {"F": {"hits": 1.2}, "D": {"hits": 0.8}},
    }
    model.opponent_factors = {"BOS": {"hits": 1.0, "shots_on_goal": 1.1}}
    assert model.opponent_factor("BOS", "F", "hits") == 1.2
    assert model.opponent_factor("BOS", "D", "hits") == 0.8
    assert model.opponent_factor("BOS", "F", "shots_on_goal") == 1.1  # fallback
    assert model.opponent_factor("MTL", "F", "hits") == 1.0
    forward = model.expected_count(centre, "hits", opponent="BOS", venue="home")
    model.opponent_group_factors = {}
    assert forward == pytest.approx(
        model.expected_count(centre, "hits", opponent="BOS", venue="home") * 1.2
    )
    assert model.skaters[defenceman].group == "D"


def test_the_props_walk_forward_splits_by_position_only_when_asked() -> None:
    logs = _VARIED.varied_logs()
    plain, _ = wf.generate_prop_samples(
        logs, refit_days=30, minimum_history_games=50, use_rest=False
    )
    split, _ = wf.generate_prop_samples(
        logs, refit_days=30, minimum_history_games=50, use_rest=False,
        position_matchup=True,
    )
    assert len(plain) == len(split)
    assert not (plain["mean"].to_numpy() == split["mean"].to_numpy()).all()
