"""Tonight's referee crew moves the game's goals, and nothing else.

Cooper, 2026-10-21. `referees` reads who worked each past game and who works
tonight; these hold:

* a referee's factor is his games' total goals over the league's, shrunk;
  a crew is the mean of the referees with a record, clamped;
* the team model scales both sides by the crew, so the split stays;
* props move only goals, assists and points;
* a game with no crew posted, or no file at all, moves nothing;
* a right-rail without gameInfo is refused, not read as an empty crew.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import referees as rf
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel

_SPEC = importlib.util.spec_from_file_location(
    "_varied_logs_rf",
    Path(__file__).resolve().parent / "test_a_walk_forward_model_sees_only_earlier_games.py",
)
_VARIED = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_VARIED)

DAY = "2026-10-22"


def _games(totals: list[int]) -> pd.DataFrame:
    return pd.DataFrame([
        {"game_id": str(i), "season": "20252026", "home_team": "TOR", "away_team": "BOS",
         "home_goals": t // 2, "away_goals": t - t // 2, "date": f"2026-01-{1 + i % 28:02d}"}
        for i, t in enumerate(totals)
    ])


def test_a_referee_is_his_games_against_the_league_shrunk() -> None:
    games = _games([8] * 60 + [4] * 60)
    history = pd.DataFrame([
        {"game_id": str(i), "referees": json.dumps(["High Caller"] if i < 60 else ["Low Caller"])}
        for i in range(120)
    ])
    factors = rf.referee_factors(history, games)
    weight = 60 / (60 + rf.SHRINKAGE_GAMES)
    assert factors["High Caller"] == pytest.approx(1 + weight * (8 / 6 - 1))
    assert factors["Low Caller"] == pytest.approx(1 + weight * (4 / 6 - 1))
    assert rf.crew_factor(["High Caller", "Nobody"], factors) == pytest.approx(
        min(rf.FACTOR_RANGE[1], factors["High Caller"])
    )
    assert rf.crew_factor(["Nobody"], factors) == 1.0


def test_tonight_reads_the_latest_crew_per_game(tmp_path) -> None:
    games = _games([8] * 200)
    rf.append_rows(tmp_path / rf.HISTORY_FILENAME, [
        {"game_id": str(i), "date": "2026-01-01", "home_team": "TOR", "away_team": "BOS",
         "referees": json.dumps(["A", "B"])} for i in range(100)
    ], rf.HISTORY_COLUMNS)
    games.loc[games.index[:100], ["home_goals", "away_goals"]] = [5, 5]
    path = tmp_path / rf.TONIGHT_DIRNAME / f"{DAY}.csv"
    rf.append_rows(path, [
        {"date": DAY, "game_id": "9", "home_team": "TOR", "away_team": "BOS",
         "referees": "[]", "retrieved_at": "2026-10-22T12:00:00+00:00"},
        {"date": DAY, "game_id": "9", "home_team": "TOR", "away_team": "BOS",
         "referees": json.dumps(["A", "B"]), "retrieved_at": "2026-10-22T13:00:00+00:00"},
        {"date": DAY, "game_id": "8", "home_team": "MTL", "away_team": "OTT",
         "referees": "[]", "retrieved_at": "2026-10-22T13:00:00+00:00"},
    ], rf.TONIGHT_COLUMNS)
    factors = rf.tonight_factors(tmp_path, DAY, games)
    assert set(factors) == {frozenset({"TOR", "BOS"})}
    assert 1.0 < factors[frozenset({"TOR", "BOS"})] <= rf.FACTOR_RANGE[1]
    assert rf.tonight_factors(tmp_path, "2026-10-23", games) == {}


def test_the_crew_scales_the_total_not_the_split() -> None:
    model = TeamModel().fit(_VARIED.varied_games())
    home, away = model.expected_goals("TOR", "BOS")
    model.game_factors = {frozenset({"TOR", "BOS"}): 1.04}
    crewed = model.expected_goals("TOR", "BOS")
    assert crewed[0] == pytest.approx(home * 1.04) and crewed[1] == pytest.approx(away * 1.04)


def test_props_move_only_the_scoring_stats() -> None:
    model = PlayerPropsModel().fit(_VARIED.varied_logs())
    player = 1
    plain = {s: model.expected_count(player, s, opponent="BOS", venue="home") for s in ("points", "hits")}
    model.game_factors = {frozenset({model.skaters[player].team, "BOS"}): 1.05}
    assert model.expected_count(player, "points", opponent="BOS", venue="home") == pytest.approx(plain["points"] * 1.05)
    assert model.expected_count(player, "hits", opponent="BOS", venue="home") == pytest.approx(plain["hits"])


def test_a_right_rail_without_game_info_is_refused() -> None:
    with pytest.raises(ValueError):
        rf.referees_of({"message": "not found"})
    assert rf.referees_of({"gameInfo": {"referees": [{"default": "Wes McCauley"}, {"default": ""}]}}) == ["Wes McCauley"]


def test_the_right_rail_shape_the_nhl_serves_is_read():
    # Copied from the right-rail of game 2025020500, read 2026-10-21: the name
    # sits under fullName.default, beside a sweater number.
    payload = {"gameInfo": {
        "referees": [{"fullName": {"default": "Kyle Rehman"}, "sweaterNumber": 10},
                     {"fullName": {"default": "Corey Syvret"}, "sweaterNumber": 23}],
        "linesmen": [{"fullName": {"default": "Trent Knorr"}, "sweaterNumber": 74}],
    }}
    assert rf.referees_of(payload) == ["Kyle Rehman", "Corey Syvret"]
