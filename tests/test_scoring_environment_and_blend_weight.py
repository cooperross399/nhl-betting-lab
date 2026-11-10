"""The league scoring environment and the refitted PostHockey blend weight
(Cooper, 2026-11-10, "All").

Both are live on the card; both are off by default everywhere else, so every
committed walk-forward measurement stands.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import posthockey, scoring_env
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel, TeamRates


def _table(days: int, early_goals: float, late_goals: float, *, late_days: int = 21, per_day: int = 6):
    """A per-game league table: `early_goals` a game, then `late_goals` for
    the last `late_days` days before 2026-11-10."""
    rows = []
    end = date(2026, 11, 10)
    gid = 1
    for back in range(days, 0, -1):
        day = end - timedelta(days=back)
        goals = late_goals if back <= late_days else early_goals
        for _ in range(per_day):
            rows.append({"game_id": gid, "date": day.isoformat(), "total_goals": goals,
                         "goals": goals - 0.2, "assists": 1.7 * goals, "points": 2.7 * goals,
                         "shots_on_goal": 60.0, "blocked_shots": 28.0, "hits": 45.0})
            gid += 1
    return pd.DataFrame(rows)


def test_a_three_week_rise_moves_the_target_by_a_shrunk_share():
    table = _table(300, 6.0, 7.2)
    env = scoring_env.reading(table, "2026-11-10")
    assert env.active
    assert env.recent_games == 21 * 6
    weight = env.recent_games / (env.recent_games + scoring_env.ENV_SHRINKAGE_GAMES)
    ref = env.reference["total_goals"]
    assert env.recent["total_goals"] == pytest.approx(7.2)
    assert env.ratio["total_goals"] == pytest.approx(1 + weight * (7.2 / ref - 1))
    # Shots did not move, so nothing moves them.
    assert env.ratio["shots_on_goal"] == pytest.approx(1.0)


def test_the_reading_never_sees_tonight_or_later():
    table = _table(300, 6.0, 6.0)
    later = pd.DataFrame([{"game_id": 10**6, "date": "2026-11-10", "total_goals": 40.0, "goals": 40.0,
                           "assists": 1.0, "points": 1.0, "shots_on_goal": 1.0, "blocked_shots": 1.0,
                           "hits": 1.0}])
    a = scoring_env.reading(table, "2026-11-10")
    b = scoring_env.reading(pd.concat([table, later]), "2026-11-10")
    assert a.ratio == b.ratio


def test_too_few_recent_games_moves_nothing():
    table = _table(300, 6.0, 9.0, per_day=1)  # 21 recent games < 40
    env = scoring_env.reading(table, "2026-11-10")
    assert not env.active
    assert scoring_env.props_multipliers(env) == {}
    model = TeamModel()
    assert scoring_env.team_multiplier(env, model) == 1.0


def test_only_the_scoring_stats_move_and_the_multiplier_is_clamped():
    table = _table(300, 6.0, 30.0)
    env = scoring_env.reading(table, "2026-11-10")
    mult = scoring_env.props_multipliers(env)
    assert set(mult) == set(scoring_env.ENV_STATS)
    assert "hits" not in mult and "blocked_shots" not in mult
    assert mult["goals"] == scoring_env.ENV_RANGE[1]


def test_team_form_already_lifting_the_league_is_not_counted_twice():
    table = _table(300, 6.0, 7.2)
    env = scoring_env.reading(table, "2026-11-10")
    plain = scoring_env.props_multipliers(env)
    form = {club: {"goals": {"for": 1.03, "against": 1.03}} for club in ("AAA", "BBB")}
    lifted = scoring_env.props_multipliers(env, form)
    assert lifted["goals"] == pytest.approx(plain["goals"] / (1.03 * 1.03))


def test_the_team_multiplier_tops_the_model_up_to_the_target():
    table = _table(300, 6.0, 7.2)
    env = scoring_env.reading(table, "2026-11-10")
    model = TeamModel()
    model.league_goals_per_game = env.reference["total_goals"]
    model.teams = {t: TeamRates(team=t, games=20, attack=1.0, defence=1.0) for t in ("AAA", "BBB")}
    factor = scoring_env.team_multiplier(env, model)
    assert factor == pytest.approx(env.ratio["total_goals"])
    before = sum(model.expected_goals("AAA", "BBB"))
    model.environment = factor
    after = sum(model.expected_goals("AAA", "BBB"))
    assert after == pytest.approx(before * factor)


def test_the_models_default_to_no_environment():
    assert TeamModel().environment == 1.0
    assert PlayerPropsModel().scoring_env == {}


def test_the_walk_forward_prices_the_environment_only_when_asked():
    import inspect

    from nhl_betting_lab.backtest.walk_forward import generate_prop_samples

    assert inspect.signature(generate_prop_samples).parameters["scoring_env"].default is False


def test_the_card_applies_both_before_the_snapshot_is_frozen():
    source = Path(__file__).resolve().parents[1].joinpath("scripts", "run_gameday_card.py").read_text()
    freeze = source.index("written = write_snapshot(")
    assert source.index("props_model.scoring_env = scoring_env.props_multipliers(") < freeze
    assert source.index("team_model.environment = scoring_env.team_multiplier(") < freeze
    assert source.index('team_model.pregame_weight = blend_fit["weight"]') < freeze


# -- the blend weight --------------------------------------------------------


def _blend_frame(n: int, *, trust_posthockey: bool) -> pd.DataFrame:
    """Games where the outcome follows PostHockey (or the card) exactly."""
    rows = []
    for i in range(n):
        p_model, target = (0.35, 0.65) if i % 2 else (0.65, 0.35)
        truth = target if trust_posthockey else p_model
        won = int((i * 37 % 100) / 100 < truth)
        rows.append({"p_model": p_model, "target": target, "home_won": won})
    return pd.DataFrame(rows)


def test_the_best_weight_follows_whichever_opinion_the_outcomes_follow():
    assert posthockey.best_weight(_blend_frame(400, trust_posthockey=True)) >= 0.8
    assert posthockey.best_weight(_blend_frame(400, trust_posthockey=False)) <= 0.2


def test_the_weight_is_shrunk_toward_one_half_and_bounded():
    assert posthockey.blend_weight(1.0, 0) == posthockey.BLEND_WEIGHT
    assert posthockey.blend_weight(1.0, posthockey.BLEND_SHRINKAGE_GAMES) == pytest.approx(0.75)
    assert 0.0 <= posthockey.blend_weight(-5.0, 10**6) <= 1.0
    assert 0.0 <= posthockey.blend_weight(5.0, 10**6) <= 1.0


def _games(rows):
    return pd.DataFrame(rows, columns=["game_id", "game_type", "date", "home_team", "away_team",
                                       "home_goals", "away_goals", "regulation"])


def test_the_card_refits_on_its_own_record_and_the_ledger_backfill(tmp_path):
    processed = tmp_path
    # Ledger era: frozen home chance 0.55 blended at 0.5 toward a 0.60 read.
    (processed / posthockey.TONIGHT_DIRNAME).mkdir()
    pd.DataFrame([
        {"date": "2026-10-27", "game_id": "1", "home_team": "AAA", "away_team": "BBB", "p_home": 0.60,
         "goalie_home_status": "", "goalie_away_status": "", "retrieved_at": "2026-10-27T13:00:00+00:00"},
        {"date": "2026-10-27", "game_id": "1", "home_team": "AAA", "away_team": "BBB", "p_home": 0.70,
         "goalie_home_status": "", "goalie_away_status": "", "retrieved_at": "2026-10-27T22:00:00+00:00"},
    ]).to_csv(processed / posthockey.TONIGHT_DIRNAME / "2026-10-27.csv", index=False)
    ledger = pd.DataFrame([{"snapshot_date": "2026-10-27", "home_team": "AAA", "away_team": "BBB",
                            "market": "moneyline", "selection": "home", "model_probability": "0.55"}])
    # Record era.
    posthockey.record_blend(
        processed,
        [{"home": "CCC", "away": "DDD", "date": "2026-11-05",
          "steps": [{"key": "referees", "homeWin": 0.40}, {"key": "posthockey", "homeWin": 0.45}]}],
        {("CCC", "DDD"): 0.50}, 0.5, "2026-11-05T13:30:00+00:00",
    )
    games = _games([(1, 2, "2026-10-27", "AAA", "BBB", 3, 2, True),
                    (2, 2, "2026-11-05", "CCC", "DDD", 1, 4, True)])
    rows = posthockey.blend_rows(processed, games, {}, before="2026-11-10", ledger=ledger)
    assert len(rows) == 2
    backfilled = rows[rows["source"] == "ledger"].iloc[0]
    assert backfilled["target"] == pytest.approx(0.60)  # the morning read, not the evening one
    assert backfilled["p_model"] == pytest.approx(0.50)  # 2 x 0.55 - 0.60
    recorded = rows[rows["source"] == "record"].iloc[0]
    assert recorded["p_model"] == pytest.approx(0.40) and recorded["target"] == pytest.approx(0.50)
    fit = posthockey.fit_blend_weight(processed, games, {}, before="2026-11-10", ledger=ledger)
    assert fit["games"] == 2
    assert 0.0 <= fit["weight"] <= 1.0
    assert "Weight in force" in posthockey.render_blend_report(fit)
    # A game settled on or after the card's day is not read.
    assert posthockey.fit_blend_weight(processed, games, {}, before="2026-11-05", ledger=ledger)["games"] == 1


def test_a_game_is_recorded_once_with_its_first_opinion(tmp_path):
    game = {"home": "CCC", "away": "DDD", "date": "2026-11-05",
            "steps": [{"key": "referees", "homeWin": 0.40}, {"key": "posthockey", "homeWin": 0.45}]}
    assert posthockey.record_blend(tmp_path, [game], {("CCC", "DDD"): 0.5}, 0.5, "a") == 1
    later = dict(game, steps=[{"key": "referees", "homeWin": 0.30}, {"key": "posthockey", "homeWin": 0.4}])
    assert posthockey.record_blend(tmp_path, [later], {("CCC", "DDD"): 0.5}, 0.5, "b") == 0
    assert posthockey.read_record(tmp_path)["p_model"].tolist() == [0.40]
    # Not priced by PostHockey: not recorded.
    other = dict(game, home="EEE", away="FFF")
    assert posthockey.record_blend(tmp_path, [other], {}, 0.5, "c") == 0


def test_no_settled_game_keeps_the_prior(tmp_path):
    fit = posthockey.fit_blend_weight(tmp_path, _games([]), {}, before="2026-11-10", ledger=pd.DataFrame())
    assert fit["games"] == 0 and fit["weight"] == posthockey.BLEND_WEIGHT
