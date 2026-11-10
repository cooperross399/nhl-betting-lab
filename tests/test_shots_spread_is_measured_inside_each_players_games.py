"""Shots on goal's own-games spread (2026-11-10, the shots-over study).

Synthetic league: every skater shoots Poisson at his own rate, from half a
shot to four a game. Measured on the whole column the spread counts the gap
between shooters as game noise and comes out far too wide; measured inside
each player's own games it is near Poisson.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from nhl_betting_lab.backtest.walk_forward import generate_prop_samples
from nhl_betting_lab.models.player_props import (
    SOG_CARD_OPTIONS,
    SOG_OPTIONS,
    PlayerPropsModel,
)

CLUBS = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")


def _league(seed: int = 11, rounds: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rate: dict[int, float] = {}
    roster: dict[str, list[int]] = {}
    pid = 1
    for club in CLUBS:
        roster[club] = []
        for slot in range(10):
            rate[pid] = float(np.linspace(0.5, 4.0, 10)[slot])
            roster[club].append(pid)
            pid += 1
    rows = []
    game = 1
    day = pd.Timestamp("2024-10-01")
    for _ in range(rounds):
        for home, away in itertools.permutations(CLUBS, 2):
            for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
                for player in roster[team]:
                    rows.append({
                        "game_id": game, "date": day.strftime("%Y-%m-%d"),
                        "player_id": player, "player": f"Player {player}",
                        "role": "skater", "position": "C", "team": team,
                        "opponent": opponent, "venue": venue, "toi_seconds": 1080,
                        "shots_on_goal": int(rng.poisson(rate[player])),
                        "goals": 0, "assists": 0, "points": 0,
                        "blocked_shots": int(rng.poisson(1.0)),
                        "hits": int(rng.poisson(1.0)),
                        "power_play_goals": 0, "saves": 0, "shots_against": 0,
                    })
            game += 1
            day += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def logs():
    return _league()


def test_the_column_spread_is_wide_and_the_own_games_spread_is_not(logs):
    old = PlayerPropsModel(sog_options=frozenset()).fit(logs)
    new = PlayerPropsModel(sog_options=frozenset({"dispersion"})).fit(logs)
    old_r = old.dispersion["shots_on_goal"].r
    new_r = new.dispersion["shots_on_goal"].r
    assert old_r is not None and old_r < 5
    # Poisson inside each player's games: no overdispersion, or a very large r.
    assert new_r is None or new_r > 20


def test_the_measured_shrinkage_is_bounded_and_moves_only_shots(logs):
    old = PlayerPropsModel(sog_options=frozenset()).fit(logs)
    new = PlayerPropsModel(sog_options=SOG_OPTIONS).fit(logs)
    low, high = PlayerPropsModel.SOG_SHRINKAGE_RANGE
    assert set(new.sog_shrinkage_seconds) == {"F", "D"}
    assert all(low <= v <= high for v in new.sog_shrinkage_seconds.values())
    for pid, rates in new.skaters.items():
        before = old.skaters[pid].per60
        for stat, value in rates.per60.items():
            if stat != "shots_on_goal":
                assert value == pytest.approx(before[stat])
    # Real spread of shot rates is wide, so a high shooter keeps more of it.
    top = max(new.skaters, key=lambda p: new.skaters[p].per60["shots_on_goal"])
    assert new.skaters[top].per60["shots_on_goal"] >= old.skaters[top].per60["shots_on_goal"]


def test_the_high_line_over_thins(logs):
    old = PlayerPropsModel(sog_options=frozenset()).fit(logs)
    new = PlayerPropsModel(sog_options=SOG_OPTIONS).fit(logs)
    pid = 5  # a two-shot-a-game shooter
    where = {"opponent": "BBB", "venue": "home"}
    o = old.distribution(pid, "shots_on_goal", **where)
    n = new.distribution(pid, "shots_on_goal", **where)
    assert o is not None and n is not None
    assert n.over_probability(5.5) < o.over_probability(5.5)


def test_off_by_default_in_the_walk_forward_and_unknown_refused(logs):
    assert SOG_CARD_OPTIONS <= SOG_OPTIONS
    with pytest.raises(ValueError):
        PlayerPropsModel(sog_options={"recency"})
    plain, _ = generate_prop_samples(logs, lines={"shots_on_goal": (2.5,)}, minimum_history_games=60)
    explicit, _ = generate_prop_samples(
        logs, lines={"shots_on_goal": (2.5,)}, minimum_history_games=60, sog_options=frozenset()
    )
    pd.testing.assert_frame_equal(plain, explicit)
