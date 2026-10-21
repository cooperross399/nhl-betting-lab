"""Each club's last five games are factored into its props, not relied on.

Cooper, 2026-10-21: "I want to make sure the model is learning from itself
each night too ... how every team is playing in their last five games", then
"i dont want to completely rely on the last 5 games i just want it to be
factored in". So `PlayerPropsModel` multiplies a skater's expected count by
his own club's last-five production and tonight's opponent's last-five
concession, each against that club's longer record, shrunk at
`TEAM_FORM_SHRINKAGE_GAMES` (five games keep a quarter of the move) and
clamped to `TEAM_FORM_RANGE`. These hold:

* steady play moves nothing; a hot or cold five moves the mean by about a
  quarter of its deviation, and never past the clamp;
* only games before the night count, so the walk-forward that prices form
  (`team_form=True`) re-reads it night by night and never sees tonight;
* the walk-forward without form prices exactly as every committed
  measurement did, whatever `fit` computed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.backtest import walk_forward as wf
from nhl_betting_lab.models.player_props import (
    PlayerPropsModel,
    team_form_factors,
    team_game_totals,
)

_SPEC = importlib.util.spec_from_file_location(
    "_varied_logs",
    Path(__file__).resolve().parent / "test_a_walk_forward_model_sees_only_earlier_games.py",
)
_VARIED = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_VARIED)
varied_logs = _VARIED.varied_logs

K = PlayerPropsModel.TEAM_FORM_SHRINKAGE_GAMES
LOW, HIGH = PlayerPropsModel.TEAM_FORM_RANGE


def _flat_totals(team_shots: dict[str, list[float]]) -> pd.DataFrame:
    """One row per team-game, every stat 1.0 except shots for, as given."""
    rows = []
    for team, values in team_shots.items():
        for i, shots in enumerate(values):
            row = {"team": team, "game_id": i, "date": f"2025-01-{i + 1:02d}"}
            for stat in ("shots_on_goal", "goals", "assists", "points", "blocked_shots", "hits"):
                row[f"for_{stat}"] = shots if stat == "shots_on_goal" else 1.0
                row[f"against_{stat}"] = 1.0
            rows.append(row)
    return pd.DataFrame(rows)


def test_steady_play_moves_nothing_and_a_hot_five_moves_a_quarter() -> None:
    totals = _flat_totals({"AAA": [30.0] * 20, "BBB": [30.0] * 15 + [36.0] * 5})
    form = team_form_factors(totals)
    assert form["AAA"]["shots_on_goal"] == {"for": 1.0, "against": 1.0}
    level = (30.0 * 15 + 36.0 * 5) / 20
    expected = 1.0 + 5 / (5 + K) * (36.0 / level - 1.0)
    assert form["BBB"]["shots_on_goal"]["for"] == pytest.approx(expected)
    assert 1.0 < expected < 1.0 + (36.0 / level - 1.0)  # factored in, not relied on


def test_a_wild_five_is_held_at_the_clamp() -> None:
    totals = _flat_totals({"HOT": [10.0] * 30 + [80.0] * 5, "COLD": [30.0] * 30 + [0.0] * 5})
    form = team_form_factors(totals)
    assert form["HOT"]["shots_on_goal"]["for"] == HIGH
    assert form["COLD"]["shots_on_goal"]["for"] == LOW


def test_only_games_before_the_night_count() -> None:
    totals = _flat_totals({"BBB": [30.0] * 15 + [36.0] * 5})
    before_the_hot_run = team_form_factors(totals, before="2025-01-16")
    assert before_the_hot_run["BBB"]["shots_on_goal"]["for"] == pytest.approx(1.0)


def test_the_expected_count_carries_own_form_and_the_opponents() -> None:
    logs = varied_logs()
    model = PlayerPropsModel().fit(logs)
    player = 1  # TOR's centre
    model.team_form = {}
    plain = model.expected_count(player, "shots_on_goal", opponent="BOS", venue="home")
    model.team_form = {
        "TOR": {"shots_on_goal": {"for": 1.1, "against": 1.0}},
        "BOS": {"shots_on_goal": {"for": 1.0, "against": 1.05}},
    }
    formed = model.expected_count(player, "shots_on_goal", opponent="BOS", venue="home")
    assert formed == pytest.approx(plain * 1.1 * 1.05)
    # The card names the player's club from tonight's roster.
    moved = model.expected_count(
        player, "shots_on_goal", opponent="BOS", venue="home", team="MTL"
    )
    assert moved == pytest.approx(plain * 1.05)


def test_fit_reads_the_logs_last_five() -> None:
    logs = varied_logs()
    model = PlayerPropsModel().fit(logs)
    assert model.team_form == team_form_factors(team_game_totals(logs))
    assert set(model.team_form) == {"TOR", "BOS", "MTL", "OTT"}


def test_the_walk_forward_without_form_prices_as_before() -> None:
    logs = varied_logs()
    plain, _ = wf.generate_prop_samples(
        logs, refit_days=30, minimum_history_games=50, use_rest=False
    )
    model = PlayerPropsModel().fit(logs)
    assert model.team_form  # fit computed it, and the walk-forward clears it
    formed, _ = wf.generate_prop_samples(
        logs, refit_days=30, minimum_history_games=50, use_rest=False, team_form=True
    )
    assert len(plain) == len(formed)
    assert not (plain["mean"].to_numpy() == formed["mean"].to_numpy()).all()


def test_the_walk_forward_form_never_sees_tonight() -> None:
    logs = varied_logs()
    night = "2025-04-15"
    rewritten = logs.copy()
    later = rewritten["date"] >= night
    rewritten.loc[later, "shots_on_goal"] = 40
    a, _ = wf.generate_prop_samples(
        logs, refit_days=30, minimum_history_games=50, use_rest=False, team_form=True
    )
    b, _ = wf.generate_prop_samples(
        rewritten, refit_days=30, minimum_history_games=50, use_rest=False, team_form=True
    )
    upto = a["date"] <= night
    assert a.loc[upto, "mean"].tolist() == b.loc[b["date"] <= night, "mean"].tolist()
    after = a["date"] > night
    assert a.loc[after, "mean"].tolist() != b.loc[b["date"] > night, "mean"].tolist()
