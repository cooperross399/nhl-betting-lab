"""The points and assists fixes (Cooper, 2026-11-10).

On the forward ledger the props model priced points and assists about 8% and
12% below what landed, worst for the best players, while goals sat level.
Two parts (`player_props.SCORING_OPTIONS`): a power-play proxy centred on 1.0,
and a shrinkage measured from the real spread of points and assists rates.
These tests build a league where both defects are visible and check each part
moves the mean toward the truth and touches nothing else.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from nhl_betting_lab.backtest.walk_forward import generate_prop_samples
from nhl_betting_lab.models.player_props import (
    SCORING_OPTION_STATS,
    SCORING_OPTIONS,
    SHIPPED_SCORING_OPTIONS,
    PlayerPropsModel,
)

CLUBS = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")


def _league(seed: int = 11, rounds: int = 8) -> tuple[pd.DataFrame, dict[int, float]]:
    """Ten forwards a club, assists from 0.1 to 1.0 a game, Poisson inside
    each player's games; the top two take every power-play goal."""
    rng = np.random.default_rng(seed)
    assist_rate: dict[int, float] = {}
    roster: dict[str, list[int]] = {}
    pid = 1
    for club in CLUBS:
        roster[club] = []
        for slot in range(10):
            assist_rate[pid] = float(np.linspace(0.1, 1.0, 10)[slot])
            roster[club].append(pid)
            pid += 1
    rows = []
    game = 1
    day = pd.Timestamp("2024-10-01")
    for _ in range(rounds):
        for home, away in itertools.permutations(CLUBS, 2):
            for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
                for slot, player in enumerate(roster[team]):
                    goals = int(rng.poisson(0.2))
                    assists = int(rng.poisson(assist_rate[player]))
                    rows.append({
                        "game_id": game,
                        "date": day.strftime("%Y-%m-%d"),
                        "player_id": player,
                        "player": f"Player {player}",
                        "role": "skater",
                        "position": "C",
                        "team": team,
                        "opponent": opponent,
                        "venue": venue,
                        "toi_seconds": 1080,
                        "shots_on_goal": int(rng.poisson(2.0)),
                        "goals": goals,
                        "assists": assists,
                        "points": goals + assists,
                        "blocked_shots": int(rng.poisson(1.0)),
                        "hits": int(rng.poisson(1.5)),
                        "power_play_goals": goals if slot >= 8 else 0,
                        "saves": 0,
                        "shots_against": 0,
                    })
            game += 1
            day += pd.Timedelta(days=1)
    return pd.DataFrame(rows), assist_rate


@pytest.fixture(scope="module")
def league():
    return _league()


def _mean(model: PlayerPropsModel, player: int, stat: str) -> float:
    return float(model.expected_count(player, stat, opponent="CCC", venue="away", team="BBB"))


def test_the_best_passer_is_priced_nearer_what_he_produces(league):
    logs, rate = league
    old = PlayerPropsModel(scoring_options=frozenset()).fit(logs)
    new = PlayerPropsModel(scoring_options={"shrinkage"}).fit(logs)
    best = 18  # BBB's 0.8-a-game passer, no power-play goals of his own
    assert abs(_mean(new, best, "assists") - rate[best]) < abs(_mean(old, best, "assists") - rate[best])
    assert new.scoring_shrinkage_seconds["F"]["assists"] < PlayerPropsModel.SHRINKAGE_SECONDS


def test_the_power_play_proxy_no_longer_lowers_the_league(league):
    logs, _ = league
    old = PlayerPropsModel(scoring_options=frozenset()).fit(logs)
    new = PlayerPropsModel(scoring_options={"pp_centred"}).fit(logs)
    players = [p for p in new.skaters if new.skaters[p].team == "BBB"]
    for stat in SCORING_OPTION_STATS:
        old_total = sum(_mean(old, p, stat) for p in players)
        new_total = sum(_mean(new, p, stat) for p in players)
        assert new_total > old_total
        multipliers = [new.pp_multiplier(new.skaters[p], stat) for p in new.skaters]
        assert np.mean(multipliers) == pytest.approx(1.0, abs=1e-9)
    # Goals keep the uncentred proxy: they were level on the ledger.
    assert _mean(new, 11, "goals") == pytest.approx(_mean(old, 11, "goals"))


def test_neither_part_touches_another_market(league):
    logs, _ = league
    old = PlayerPropsModel(scoring_options=frozenset()).fit(logs)
    new = PlayerPropsModel(scoring_options=SCORING_OPTIONS).fit(logs)
    for stat in ("goals", "shots_on_goal", "blocked_shots", "hits"):
        for player in (1, 15, 30):
            assert _mean(new, player, stat) == pytest.approx(_mean(old, player, stat))


def test_no_options_is_the_old_model(league):
    logs, _ = league
    old = PlayerPropsModel(scoring_options=frozenset()).fit(logs)
    assert old.pp_centre == {}
    assert old.scoring_shrinkage_seconds == {}


def test_the_card_fits_what_shipped_and_the_walk_forward_fits_nothing(league):
    assert PlayerPropsModel().scoring_options == SHIPPED_SCORING_OPTIONS
    assert SHIPPED_SCORING_OPTIONS <= SCORING_OPTIONS
    with pytest.raises(ValueError):
        PlayerPropsModel(scoring_options={"vibes"})
    logs, _ = _league(rounds=3)
    default, _ = generate_prop_samples(logs, lines={"assists": (0.5,)}, minimum_history_games=20, use_rest=False)
    old, _ = generate_prop_samples(
        logs, lines={"assists": (0.5,)}, minimum_history_games=20, use_rest=False,
        scoring_options=frozenset(),
    )
    assert default["mean"].tolist() == pytest.approx(old["mean"].tolist())
