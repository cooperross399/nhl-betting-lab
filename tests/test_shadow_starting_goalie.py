"""Tonight's starter in the shadow team ratings (Cooper, 2026-10-09).

The card rates goaltending on a team's goalies together. These hold the
starter variants to what they state: the starter is the goalie who faced the
most attempts, the projection reads only earlier days, a back-to-back turns
to the team's other recent starter, and a goalie's own factor follows him
through a trade and treats a relief appearance as part of a game.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from nhl_betting_lab.shadow.measurement import (
    LUCK_SHRINKAGE_GAMES,
    game_starters,
    goalie_factors,
    project_starters,
)


def _goalie_row(gid, goalie, team, fa, ga=0, xga=1.0, season=20252026, day="2025-10-10"):
    return {
        "game_id": gid, "season": season, "goalie_id": goalie, "team": team,
        "fa": fa, "sa": fa, "ga": ga, "xga": xga, "_date": date.fromisoformat(day),
    }


def test_the_starter_is_the_goalie_who_faced_the_most_attempts() -> None:
    table = pd.DataFrame(
        [
            _goalie_row(1, 30, "AAA", 25),
            _goalie_row(1, 31, "AAA", 6),
            _goalie_row(1, 40, "BBB", 33),
        ]
    )
    starters = game_starters(table)
    got = {(r.game_id, r.team): r.goalie_id for r in starters.itertuples()}
    assert got == {(1, "AAA"): 30, (1, "BBB"): 40}


def _schedule(rows):
    return pd.DataFrame(
        rows, columns=["game_id", "date", "home_team", "away_team", "home_b2b", "away_b2b"]
    )


def test_the_projection_is_last_games_starter_and_reads_no_later_day() -> None:
    games = _schedule(
        [
            (1, "2025-10-10", "AAA", "BBB", False, False),
            (2, "2025-10-12", "AAA", "CCC", False, False),
            (3, "2025-10-14", "DDD", "AAA", False, False),
        ]
    )
    starters = pd.DataFrame(
        [
            {"game_id": 1, "team": "AAA", "goalie_id": 30},
            {"game_id": 2, "team": "AAA", "goalie_id": 31},
            {"game_id": 3, "team": "AAA", "goalie_id": 30},
        ]
    )
    projected = project_starters(starters, games)
    assert (1, "AAA") not in projected  # no earlier game, no projection
    assert projected[(2, "AAA")] == 30
    assert projected[(3, "AAA")] == 31  # game 3's own starter is never read


def test_a_back_to_back_turns_to_the_teams_other_recent_starter() -> None:
    games = _schedule(
        [
            (1, "2025-10-08", "AAA", "BBB", False, False),
            (2, "2025-10-10", "AAA", "CCC", False, False),
            (3, "2025-10-11", "DDD", "AAA", False, True),
        ]
    )
    starters = pd.DataFrame(
        [
            {"game_id": 1, "team": "AAA", "goalie_id": 31},
            {"game_id": 2, "team": "AAA", "goalie_id": 30},
        ]
    )
    projected = project_starters(starters, games)
    assert projected[(3, "AAA")] == 31


def test_a_back_to_back_with_no_other_starter_keeps_last_games() -> None:
    games = _schedule(
        [
            (1, "2025-10-10", "AAA", "BBB", False, False),
            (2, "2025-10-11", "AAA", "CCC", True, False),
        ]
    )
    starters = pd.DataFrame([{"game_id": 1, "team": "AAA", "goalie_id": 30}])
    assert project_starters(starters, games)[(2, "AAA")] == 30


def test_a_goalies_own_factor_follows_him_and_is_regressed() -> None:
    # Goalie 30 lets in 4 against 2 expected in every full game, on two teams.
    rows = [
        _goalie_row(i, 30, "AAA" if i < 10 else "BBB", 30, ga=4, xga=2.0, day=f"2025-10-{10 + i:02d}")
        for i in range(20)
    ]
    # Goalie 31 matches expectation exactly.
    rows += [
        _goalie_row(100 + i, 31, "CCC", 30, ga=2, xga=2.0, day=f"2025-10-{10 + i:02d}")
        for i in range(20)
    ]
    factors = goalie_factors(pd.DataFrame(rows))
    assert factors[31] == pytest.approx(1.0)
    # Raw ratio 2.0, pulled most of the way back by the heavy regression.
    assert 1.0 < factors[30] < 1.0 + 20 / (20 + LUCK_SHRINKAGE_GAMES) + 1e-9


def test_a_relief_appearance_is_less_evidence_than_a_start() -> None:
    def factor(fa):
        rows = [
            _goalie_row(i, 30, "AAA", fa, ga=fa / 10, xga=fa / 20, day=f"2025-10-{10 + i:02d}")
            for i in range(10)
        ]
        # Another goalie's full games fix the league's attempts per game at 30.
        rows += [
            _goalie_row(200 + i, 99, "ZZZ", 30, ga=1, xga=1.0, day=f"2025-10-{10 + i:02d}")
            for i in range(10)
        ]
        return goalie_factors(pd.DataFrame(rows))[30]

    # Same raw ratio (2.0); the relief goalie is regressed harder.
    assert 1.0 < factor(6) < factor(30)


def test_recent_form_is_scored_for_every_skater_market_and_reads_no_later_game() -> None:
    from nhl_betting_lab.shadow.measurement import compare_prop_rates

    rows, metrics = [], []
    # One player: 40 quiet games last season, then a hot run this season.
    for i in range(60):
        gid = (2024020000 if i < 40 else 2025020000) + i + 1
        day = pd.Timestamp("2024-10-10" if i < 40 else "2025-10-10") + pd.Timedelta(days=2 * (i % 40))
        hot = i >= 40
        rows.append({
            "game_id": gid, "game_type": 2, "date": str(day.date()), "player_id": 7,
            "role": "skater", "position": "C", "toi_seconds": 1200,
            "shots_on_goal": 5 if hot else 1, "goals": 1 if hot else 0,
            "assists": 1 if hot else 0, "points": 2 if hot else 0,
        })
        metrics.append({"game_id": gid, "player_id": 7, "icf": 2, "iff": 2, "ixg": 0.3})
    frame, summaries = compare_prop_rates(
        pd.DataFrame(rows), pd.DataFrame(metrics),
        scored_seasons={20252026}, covered_games={r["game_id"] for r in rows},
    )
    assert set(summaries) == {"shots_on_goal", "goals", "assists", "points"}
    for stat in ("shots_on_goal", "goals", "assists", "points"):
        form = [e for e in summaries[stat] if e["variant"] == "form"]
        assert form and form[0]["rows"] == 20
        # A hot streak the long-run rate dilutes: form forecasts it better.
        assert form[0]["ll"]["per_1000"] > 0
    first = frame[(frame["variant"] == "form") & (frame["stat"] == "points")].iloc[0]
    current = frame[(frame["variant"] == "current") & (frame["stat"] == "points")].iloc[0]
    # The first hot game is forecast from quiet games only.
    assert first["ll"] == pytest.approx(current["ll"], abs=1e-9)
