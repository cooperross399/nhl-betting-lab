"""The hits model Cooper asked to have dialled in (2026-10-25).

Synthetic league: six clubs, each skater with his own true hit rate (a
grinder at four a game, a skill winger at half of one), Poisson hits, and
one rink whose scorer records half as many hits again as every other.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from nhl_betting_lab.models.counts import measure_dispersion
from nhl_betting_lab.models.player_props import (
    HITS_OPTIONS,
    PlayerPropsModel,
    fit_hits_rink_factors,
)

CLUBS = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")
GENEROUS_RINK = "AAA"
RINK_BIAS = 1.5


def _league(seed: int = 7, rounds: int = 8) -> tuple[pd.DataFrame, dict[int, float]]:
    rng = np.random.default_rng(seed)
    true_rate: dict[int, float] = {}
    roster: dict[str, list[int]] = {}
    pid = 1
    for club in CLUBS:
        roster[club] = []
        for slot in range(10):
            true_rate[pid] = float(np.linspace(0.5, 4.0, 10)[slot])
            roster[club].append(pid)
            pid += 1
    rows = []
    game = 1
    day = pd.Timestamp("2024-10-01")
    for _ in range(rounds):
        for home, away in itertools.permutations(CLUBS, 2):
            bias = RINK_BIAS if home == GENEROUS_RINK else 1.0
            for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
                for player in roster[team]:
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
                        "goals": 0,
                        "assists": 0,
                        "points": 0,
                        "blocked_shots": int(rng.poisson(1.0)),
                        "hits": int(rng.poisson(true_rate[player] * bias)),
                        "power_play_goals": 0,
                        "saves": 0,
                        "shots_against": 0,
                    })
            game += 1
            day += pd.Timedelta(days=1)
    return pd.DataFrame(rows), true_rate


@pytest.fixture(scope="module")
def league():
    return _league()


def test_the_generous_rink_is_found_and_the_others_are_not(league):
    logs, _ = league
    factors = fit_hits_rink_factors(logs)
    assert factors[GENEROUS_RINK] > 1.3
    for club in CLUBS[1:]:
        assert 0.85 < factors[club] < 1.05


def test_tonights_rink_moves_the_hits_price_and_nothing_else(league):
    logs, _ = league
    model = PlayerPropsModel().fit(logs)
    grinder = 10  # AAA's four-a-game hitter
    at_home = model.expected_count(grinder, "hits", opponent="BBB", venue="home", team="AAA")
    on_road = model.expected_count(grinder, "hits", opponent="BBB", venue="away", team="AAA")
    assert at_home / on_road > 1.3
    # A BBB skater in AAA's rink is counted by AAA's scorer too.
    visitor = 20
    in_aaa = model.expected_count(visitor, "hits", opponent="AAA", venue="away", team="BBB")
    in_ccc = model.expected_count(visitor, "hits", opponent="CCC", venue="away", team="BBB")
    assert in_aaa / in_ccc > 1.25
    shots_home = model.expected_count(grinder, "shots_on_goal", opponent="BBB", venue="home", team="AAA")
    old = PlayerPropsModel(hits_options=frozenset()).fit(logs)
    assert shots_home == pytest.approx(
        old.expected_count(grinder, "shots_on_goal", opponent="BBB", venue="home", team="AAA")
    )


def test_the_spread_is_measured_inside_each_players_games(league):
    logs, _ = league
    old = PlayerPropsModel(hits_options=frozenset()).fit(logs)
    new = PlayerPropsModel().fit(logs)
    column = measure_dispersion(logs["hits"].tolist())
    assert old.dispersion["hits"].ratio == pytest.approx(column.ratio)
    # The league's spread is mostly grinder-versus-winger; inside a player's
    # own games these hits are Poisson, so the measured shape is close to it.
    assert column.r is not None and column.r < 5
    assert new.dispersion["hits"].r is None or new.dispersion["hits"].r > 10


def test_the_heavy_hitters_over_is_priced_where_it_lives(league):
    logs, true_rate = league
    old = PlayerPropsModel(hits_options=frozenset()).fit(logs)
    new = PlayerPropsModel().fit(logs)
    grinder = 20  # BBB, true 4.0 a game, priced on a neutral road rink
    kwargs = dict(opponent="CCC", venue="away", team="BBB")
    old_mean = old.expected_count(grinder, "hits", **kwargs)
    new_mean = new.expected_count(grinder, "hits", **kwargs)
    assert abs(new_mean - true_rate[grinder]) < abs(old_mean - true_rate[grinder])
    assert new.over_probability(grinder, "hits", 3.5, **kwargs) > old.over_probability(
        grinder, "hits", 3.5, **kwargs
    )
    assert new.hits_shrinkage_seconds["F"] < PlayerPropsModel.SHRINKAGE_SECONDS


def test_no_options_is_the_old_model():
    logs, _ = _league(rounds=4)
    old = PlayerPropsModel(hits_options=frozenset()).fit(logs)
    assert old.hits_rink_factors == {}
    assert old.hits_shrinkage_seconds == {}
    assert old.hits_rink_factor(GENEROUS_RINK) == 1.0


def test_the_card_fits_every_part_and_an_unknown_part_is_refused():
    assert PlayerPropsModel().hits_options == HITS_OPTIONS
    with pytest.raises(ValueError):
        PlayerPropsModel(hits_options={"vibes"})
