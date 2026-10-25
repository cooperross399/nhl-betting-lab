"""Tonight's listed starter replaces the team's goalies together in team markets.

Cooper, 2026-10-25 (PostHockey prices the listed goalie). These hold:

* a goalie's factor is his own record regressed toward an unseen goalie's,
  a little below average, and the plain team factor is unchanged;
* the card divides the team's goaltending out of its defence and multiplies
  the starter's in; an unknown goalie gets the unseen factor, a club with no
  listing and a file without the goalie tables move nothing;
* the starter's factor is clamped.
"""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from nhl_betting_lab.models import team_ratings as tr
from nhl_betting_lab.models.team_model import TeamModel, TeamRates
from nhl_betting_lab.shadow import measurement


def _history(goalie: int, games: int, ga: int, xga: float) -> pd.DataFrame:
    return pd.DataFrame([
        {"game_id": 2025020000 + i, "season": 20252026, "goalie_id": goalie, "team": "DAL",
         "fa": 40, "ga": ga, "xga": xga, "xga_adj": xga,
         "_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)}
        for i in range(games)
    ])


def test_a_goalie_is_regressed_toward_the_unseen_goalie() -> None:
    plain = measurement.goalie_factors(_history(1, 10, 3, 3.0))
    assert plain[1] == pytest.approx(1.0)
    anchored = measurement.goalie_factors(
        _history(1, 10, 3, 3.0), xga="xga_adj", anchor=measurement.UNSEEN_GOALIE_FACTOR
    )
    assert 1.0 < anchored[1] < measurement.UNSEEN_GOALIE_FACTOR
    long_record = measurement.goalie_factors(
        _history(1, 200, 3, 3.0), xga="xga_adj", anchor=measurement.UNSEEN_GOALIE_FACTOR
    )
    assert long_record[1] < anchored[1]


def _model() -> TeamModel:
    model = TeamModel()
    model.teams = {
        "DAL": TeamRates("DAL", 10, 1.0, 1.0 * 1.04),
        "NYI": TeamRates("NYI", 10, 1.0, 1.0),
    }
    return model


def _ratings(tmp_path, **extra) -> None:
    body = {"teams": {}, "last_game_date": "2026-10-24", **extra}
    (tmp_path / tr.RATINGS_FILE).write_text(json.dumps(body), encoding="utf-8")


def test_the_starter_replaces_the_teams_goaltending(tmp_path) -> None:
    _ratings(tmp_path, team_goalie={"DAL": 1.04, "NYI": 1.0},
             goalies={"8479979": 0.96}, unseen_goalie=1.02)
    model = _model()
    moved = tr.apply_starters(model, tmp_path, {"DAL": 8479979, "NYI": None})
    assert model.teams["DAL"].defence == pytest.approx(0.96)
    assert model.teams["NYI"].defence == pytest.approx(1.02)
    assert len(moved) == 2
    model = _model()
    tr.apply_starters(model, tmp_path, {"DAL": 1})  # no record: unseen
    assert model.teams["DAL"].defence == pytest.approx(1.02)
    assert model.teams["NYI"].defence == pytest.approx(1.0)


def test_a_wild_record_is_clamped_and_old_files_move_nothing(tmp_path) -> None:
    _ratings(tmp_path, team_goalie={"DAL": 1.04}, goalies={"7": 1.6})
    model = _model()
    tr.apply_starters(model, tmp_path, {"DAL": 7})
    assert model.teams["DAL"].defence == pytest.approx(tr.STARTER_FACTOR_RANGE[1])
    _ratings(tmp_path)
    model = _model()
    assert tr.apply_starters(model, tmp_path, {"DAL": 7}) == []
    assert model.teams["DAL"].defence == pytest.approx(1.04)


def test_an_old_goalie_is_aged_by_his_share_of_his_own_record(tmp_path) -> None:
    _ratings(tmp_path, team_goalie={"DAL": 1.04}, goalies={"7": 0.96, "8": 0.96},
             goalie_games={"7": 100.0, "8": 0.0}, goalie_shrinkage_games=100, unseen_goalie=1.02)
    model = _model()
    tr.apply_starters(model, tmp_path, {"DAL": 7}, birth_dates={7: "1990-10-25"}, day="2026-10-25")
    term = tr.goalie_age_term(36.0)
    assert term < 0
    assert model.teams["DAL"].defence == pytest.approx(0.96 * math.exp(-term * 0.5))
    model = _model()
    tr.apply_starters(model, tmp_path, {"DAL": 8}, birth_dates={8: "1990-10-25"}, day="2026-10-25")
    assert model.teams["DAL"].defence == pytest.approx(0.96)  # no record of his own, no age
    assert tr.goalie_age_term(24.0) == pytest.approx(0.031)
    assert tr.goalie_age_term(50.0) == pytest.approx(-0.094)
