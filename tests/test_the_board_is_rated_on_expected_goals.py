"""The public board is rated on expected goals and goaltending.

Cooper asked on 2026-10-05 for the site's projections to be built on the
modern stats, not shown beside them. `scripts/run_shadow_stats.py
--tables-only` writes `shadow_team_ratings.json` (`measurement.xg_team_ratings`,
the `xg_luck` stack: recent xG, a finishing factor on attack and a GSAx factor
on defence), and `web/build_site_json.py::rate_on_xg` puts those ratings into
the fitted team model, so every probability the board publishes reads off
them. These hold:

* the ratings are the measurement's own factors, combined the way the
  measurement scored them;
* a table covering too few of the model's games yields no ratings;
* the board uses ratings built through the model's latest game, and falls
  back to goals, saying so, when the file is missing or stale.

The card never reads these (tests/test_the_shadow_model_cannot_reach_the_card.py).
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.shadow import measurement

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "web" / "build_site_json.py"


def _builder():
    spec = importlib.util.spec_from_file_location("_site_builder_xg", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _games_and_metrics(n_rounds: int = 30):
    """AAA out-chances everyone; BBB gets outscored by its xG (bad goalie)."""
    teams = ["AAA", "BBB", "CCC", "DDD"]
    games, metrics = [], []
    day = date(2024, 10, 10)
    number = 1
    for _ in range(n_rounds):
        for i, home in enumerate(teams):
            for away in teams[i + 1:]:
                gid = int(f"202402{number:04d}")
                number += 1
                day += timedelta(days=1)
                xg = {t: 3.4 if t == "AAA" else 2.6 for t in (home, away)}
                goals = {home: 3, away: 3}
                if "BBB" in (home, away):
                    other = away if home == "BBB" else home
                    goals[other] = 5
                games.append({"game_id": gid, "season": 20242025, "game_type": 2, "date": day.isoformat(),
                              "home_team": home, "away_team": away, "home_goals": goals[home],
                              "away_goals": goals[away], "regulation": True})
                for team, opp, is_home in ((home, away, True), (away, home, False)):
                    metrics.append({"game_id": gid, "season": 20242025, "team": team, "opponent": opp,
                                    "is_home": is_home, "xgf": xg[team], "xga": xg[opp],
                                    "gf": goals[team], "ga": goals[opp],
                                    "goalie_xga": xg[opp], "goalie_ga": goals[opp]})
    return pd.DataFrame(games), pd.DataFrame(metrics)


def test_the_ratings_are_the_measurements_own_factors() -> None:
    games, metrics = _games_and_metrics()
    model = TeamModel().fit(games)
    ratings = measurement.xg_team_ratings(model.home_advantage, games, metrics)
    assert ratings["variant"] == "xg_luck"
    assert ratings["last_game_date"] == games["date"].max()
    teams = ratings["teams"]
    assert teams["AAA"]["attack"] > max(teams["CCC"]["attack"], teams["DDD"]["attack"])
    assert teams["BBB"]["defence"] > teams["CCC"]["defence"]  # conceding above its xG
    variant = next(v for v in measurement.TEAM_VARIANTS if v.key == "xg_luck")
    dated = metrics.merge(games.assign(_date=pd.to_datetime(games["date"]).dt.date)[["game_id", "_date"]])
    factors = measurement.shadow_factors(dated, variant, model.home_advantage)
    for team, f in factors.items():
        assert teams[team]["attack"] == pytest.approx(f["attack"] * f["finishing"])
        assert teams[team]["defence"] == pytest.approx(f["defence"] * f["goalie"])


def test_a_table_missing_games_yields_no_ratings() -> None:
    games, metrics = _games_and_metrics()
    kept = metrics[metrics["game_id"].isin(games["game_id"].iloc[: len(games) // 2])]
    with pytest.raises(ValueError, match="covers"):
        measurement.xg_team_ratings(1.0, games, kept)


def test_the_board_reads_the_ratings_and_falls_back_to_goals(tmp_path, capsys) -> None:
    games, metrics = _games_and_metrics()
    builder = _builder()
    goals_model = TeamModel().fit(games)
    goals_win = goals_model.moneyline_probabilities("AAA", "DDD")["home"]

    assert builder.rate_on_xg(TeamModel().fit(games), games, tmp_path) == "goals"
    assert "rated on goals" in capsys.readouterr().out

    ratings = measurement.xg_team_ratings(goals_model.home_advantage, games, metrics)
    path = tmp_path / builder.SHADOW_RATINGS
    path.write_text(json.dumps({**ratings, "last_game_date": "2024-01-01"}), encoding="utf-8")
    stale = TeamModel().fit(games)
    assert builder.rate_on_xg(stale, games, tmp_path) == "goals"
    assert stale.moneyline_probabilities("AAA", "DDD")["home"] == pytest.approx(goals_win)

    path.write_text(json.dumps(ratings), encoding="utf-8")
    rated = TeamModel().fit(games)
    assert builder.rate_on_xg(rated, games, tmp_path) == "xg"
    for team, rate in ratings["teams"].items():
        assert rated.teams[team].attack == pytest.approx(rate["attack"])
        assert rated.teams[team].defence == pytest.approx(rate["defence"])
    # AAA's goals are average; its chances are not, so the xG board likes it more.
    assert rated.moneyline_probabilities("AAA", "DDD")["home"] > goals_win


def test_the_price_backtest_rates_each_window_on_earlier_games_only() -> None:
    """`--price-backtest` prices the xG ratings walk-forward, as the site rates."""
    from nhl_betting_lab.backtest.team_walk_forward import generate_team_samples

    spec = importlib.util.spec_from_file_location(
        "_shadow_script_xg", PROJECT_ROOT / "scripts" / "run_shadow_stats.py"
    )
    script = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(script)

    games, metrics = _games_and_metrics()
    seen: list[date] = []
    rater = script.xg_rater(games, metrics)

    def spy(model, start):
        seen.append(start)
        rater(model, start)
        # Only games before the window reached the ratings: rebuild them by hand.
        dated = metrics.merge(games.assign(_date=pd.to_datetime(games["date"]).dt.date)[["game_id", "_date"]])
        variant = next(v for v in measurement.TEAM_VARIANTS if v.key == "xg_luck")
        factors = measurement.shadow_factors(dated[dated["_date"] < start], variant, model.home_advantage)
        assert model.teams["AAA"].attack == pytest.approx(factors["AAA"]["attack"] * factors["AAA"]["finishing"])

    goals, _ = generate_team_samples(games, minimum_history_games=30, use_rest=False)
    xg, walk = generate_team_samples(games, minimum_history_games=30, use_rest=False, rate=spy)
    assert seen and walk.refits == len(seen)
    assert set(xg["game_id"]) == set(goals["game_id"])
    moneyline = lambda s: s[(s["market"] == "moneyline") & (s["selection"] == "home")].set_index("game_id")["model_probability"]  # noqa: E731
    assert not moneyline(xg).equals(moneyline(goals))


def test_a_window_the_ratings_refuse_is_skipped_and_counted() -> None:
    from nhl_betting_lab.backtest.team_walk_forward import generate_team_samples

    games, _ = _games_and_metrics()

    def refuse(model, start):
        raise ValueError("no play-by-play")

    samples, walk = generate_team_samples(games, minimum_history_games=30, use_rest=False, rate=refuse)
    assert samples.empty and walk.refits == 0 and walk.windows_skipped_for_history > 0
