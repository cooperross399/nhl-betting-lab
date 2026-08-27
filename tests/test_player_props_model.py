from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.models import counts
from nhl_betting_lab.models.player_props import (
    GOALIE_STAT,
    PlayerPropsModel,
    SKATER_STATS,
    fit_opponent_shot_factors,
    position_group,
)


def _skater_row(
    *,
    game: int,
    day: int,
    player_id: int,
    name: str,
    team: str,
    opponent: str,
    venue: str,
    position: str = "C",
    toi: int = 1200,
    sog: int = 3,
    goals: int = 0,
    assists: int = 1,
    blocked: int = 1,
    pp_goals: int = 0,
) -> dict:
    return {
        "game_id": game,
        "date": f"2025-01-{day:02d}",
        "player_id": player_id,
        "player": name,
        "role": "skater",
        "position": position,
        "team": team,
        "opponent": opponent,
        "venue": venue,
        "toi_seconds": toi,
        "shots_on_goal": sog,
        "goals": goals,
        "assists": assists,
        "points": goals + assists,
        "blocked_shots": blocked,
        "hits": 2,
        "power_play_goals": pp_goals,
        "saves": 0,
        "shots_against": 0,
    }


def _goalie_row(
    *,
    game: int,
    day: int,
    player_id: int,
    name: str,
    team: str,
    opponent: str,
    venue: str,
    toi: int = 3600,
    saves: int = 27,
    shots: int = 30,
) -> dict:
    return {
        "game_id": game,
        "date": f"2025-01-{day:02d}",
        "player_id": player_id,
        "player": name,
        "role": "goalie",
        "position": "G",
        "team": team,
        "opponent": opponent,
        "venue": venue,
        "toi_seconds": toi,
        "shots_on_goal": 0,
        "goals": 0,
        "assists": 0,
        "points": 0,
        "blocked_shots": 0,
        "hits": 0,
        "power_play_goals": 0,
        "saves": saves,
        "shots_against": shots,
    }


def sample_logs(games: int = 40) -> pd.DataFrame:
    """A small two-team league with enough games to clear every minimum."""
    rows: list[dict] = []
    for index in range(games):
        day = 1 + index % 28
        home, away = ("TOR", "BOS") if index % 2 == 0 else ("BOS", "TOR")
        for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
            offset = 0 if team == "TOR" else 100
            rows.append(
                _skater_row(
                    game=index,
                    day=day,
                    player_id=1 + offset,
                    name=f"Star {team}",
                    team=team,
                    opponent=opponent,
                    venue=venue,
                    toi=1300,
                    sog=4,
                    goals=1 if index % 3 == 0 else 0,
                    assists=1,
                    blocked=1,
                    pp_goals=1 if index % 5 == 0 else 0,
                )
            )
            rows.append(
                _skater_row(
                    game=index,
                    day=day,
                    player_id=2 + offset,
                    name=f"Blueliner {team}",
                    team=team,
                    opponent=opponent,
                    venue=venue,
                    position="D",
                    toi=1400,
                    sog=2,
                    goals=0,
                    assists=0 if index % 4 else 1,
                    blocked=3,
                    pp_goals=0,
                )
            )
            rows.append(
                _goalie_row(
                    game=index,
                    day=day,
                    player_id=9 + offset,
                    name=f"Netminder {team}",
                    team=team,
                    opponent=opponent,
                    venue=venue,
                    saves=26 + index % 5,
                    shots=29 + index % 5,
                )
            )
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("position", "group"),
    [("C", "F"), ("L", "F"), ("R", "F"), ("D", "D"), ("G", "G"), ("", "")],
)
def test_position_groups_split_forwards_from_defencemen(
    position: str, group: str
) -> None:
    assert position_group(position) == group


def test_fitting_needs_every_settlement_column() -> None:
    model = PlayerPropsModel()

    with pytest.raises(KeyError, match="missing columns"):
        model.fit(pd.DataFrame({"player_id": [1]}))


def test_fitting_on_nothing_is_an_error_not_an_empty_model() -> None:
    logs = sample_logs(2)
    logs["toi_seconds"] = 0

    with pytest.raises(ValueError, match="No usable appearances"):
        PlayerPropsModel().fit(logs)


def test_a_fitted_model_prices_the_regulars() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    assert model.report.skaters_priced == 4
    assert model.report.goalies_priced == 2
    assert "skaters priced" in model.report.summary_line()


def test_a_player_below_the_game_minimum_is_not_priced_at_all() -> None:
    """A prop priced on "average forward" is not an opinion worth staking."""
    logs = sample_logs()
    cameo = _skater_row(
        game=999,
        day=1,
        player_id=555,
        name="Call Up",
        team="TOR",
        opponent="BOS",
        venue="home",
    )
    model = PlayerPropsModel().fit(
        pd.concat([logs, pd.DataFrame([cameo])], ignore_index=True)
    )

    assert 555 not in model.skaters
    assert model.report.skaters_below_minimum >= 1
    assert (
        model.expected_count(555, "shots_on_goal", opponent="BOS", venue="home")
        is None
    )


def test_rates_are_per_sixty_minutes_so_ice_time_drives_the_count() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    half = model.expected_count(
        1, "shots_on_goal", opponent="BOS", venue="home", expected_toi_seconds=600
    )
    double = model.expected_count(
        1, "shots_on_goal", opponent="BOS", venue="home", expected_toi_seconds=1200
    )

    assert double == pytest.approx(2 * half, rel=1e-9)


def test_zero_expected_ice_time_produces_no_opinion() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    assert (
        model.expected_count(
            1, "shots_on_goal", opponent="BOS", venue="home", expected_toi_seconds=0
        )
        is None
    )


def test_a_defenceman_blocks_more_and_scores_less_than_a_forward() -> None:
    """A single league baseline would shrink everyone toward nobody."""
    model = PlayerPropsModel().fit(sample_logs())

    forward = model.skaters[1]
    defender = model.skaters[2]

    assert defender.per60["blocked_shots"] > forward.per60["blocked_shots"]
    assert defender.per60["goals"] < forward.per60["goals"]


def test_shrinkage_pulls_a_thin_record_toward_the_position_baseline() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    rates = model.skaters[1]
    baseline = model.baselines[rates.group]["shots_on_goal"]
    raw = 4.0 / (1300 / 3600.0)

    assert min(baseline, raw) <= rates.per60["shots_on_goal"] <= max(baseline, raw)


def test_an_unknown_stat_is_refused_rather_than_returning_none() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    with pytest.raises(KeyError, match="Unknown prop stat"):
        model.expected_count(1, "hat_tricks", opponent="BOS", venue="home")


def test_the_power_play_proxy_can_nudge_but_never_dominate() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    low, high = model.PP_MULTIPLIER_RANGE
    rates = model.skaters[1]

    assert low <= model.pp_multiplier(rates, "goals") <= high


def test_the_power_play_proxy_does_not_touch_blocked_shots() -> None:
    """A player on the power play is taking shots, not blocking them."""
    model = PlayerPropsModel().fit(sample_logs())

    assert model.pp_multiplier(model.skaters[1], "blocked_shots") == 1.0
    assert model.pp_multiplier(model.skaters[1], "shots_on_goal") == 1.0


def test_an_unknown_opponent_is_league_average_not_an_error() -> None:
    """A team the model has never seen is a real early-season state."""
    model = PlayerPropsModel().fit(sample_logs())

    known = model.expected_count(1, "shots_on_goal", opponent="BOS", venue="home")
    unknown = model.expected_count(1, "shots_on_goal", opponent="SEA", venue="home")

    assert unknown is not None and known is not None
    assert model.opponent_shot_factor("SEA") == 1.0


def test_over_probabilities_fall_as_the_line_rises() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    probabilities = [
        model.over_probability(1, "shots_on_goal", line, opponent="BOS", venue="home")
        for line in (0.5, 1.5, 2.5, 3.5, 4.5)
    ]

    assert probabilities == sorted(probabilities, reverse=True)


def test_anytime_scorer_is_goals_over_half_and_not_a_second_market() -> None:
    """Two names for one thing would let them disagree on the same card."""
    model = PlayerPropsModel().fit(sample_logs())

    assert model.anytime_scorer_probability(
        1, opponent="BOS", venue="home"
    ) == pytest.approx(
        model.over_probability(1, "goals", 0.5, opponent="BOS", venue="home")
    )


def test_an_unpriced_player_yields_no_probability_rather_than_a_default() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    assert (
        model.over_probability(
            424242, "shots_on_goal", 2.5, opponent="BOS", venue="home"
        )
        is None
    )


def test_goalie_saves_are_shots_against_times_save_rate() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    rates = model.goalies[9]

    expected = model.expected_saves(9, opponent="BOS", venue="away")
    shots = rates.shots_against_per60 * (rates.expected_toi_seconds / 3600.0)

    assert expected == pytest.approx(
        shots * rates.save_rate * model.opponent_shot_factor("BOS")
    )


def test_a_goalie_facing_a_heavier_shooting_team_is_expected_to_make_more_saves() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    model.opponent_shot_factors["HEAVY"] = 1.30
    model.opponent_shot_factors["LIGHT"] = 0.80

    heavy = model.expected_saves(9, opponent="HEAVY", venue="home")
    light = model.expected_saves(9, opponent="LIGHT", venue="home")

    assert heavy > light


def test_a_goalie_below_the_appearance_minimum_is_not_priced() -> None:
    logs = sample_logs()
    spot_start = _goalie_row(
        game=998, day=2, player_id=77, name="Backup", team="TOR", opponent="BOS",
        venue="home",
    )
    model = PlayerPropsModel().fit(
        pd.concat([logs, pd.DataFrame([spot_start])], ignore_index=True)
    )

    assert 77 not in model.goalies
    assert model.expected_saves(77, opponent="BOS", venue="home") is None


def test_saves_use_the_goalie_route_even_through_the_generic_entry_point() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    assert model.expected_count(
        9, GOALIE_STAT, opponent="BOS", venue="away"
    ) == pytest.approx(model.expected_saves(9, opponent="BOS", venue="away"))


def test_dispersion_is_measured_for_every_priced_stat() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    for stat in (*SKATER_STATS, GOALIE_STAT):
        assert stat in model.dispersion


def test_the_distribution_reflects_the_measured_dispersion() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    shape = model.distribution(1, "shots_on_goal", opponent="BOS", venue="home")

    assert isinstance(shape, (counts.Poisson, counts.NegativeBinomial))


def test_a_provider_name_resolves_to_a_fitted_player() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    assert model.resolve_player("Star TOR") == 1
    assert model.resolve_player("  star tor  ") == 1


def test_an_unknown_provider_name_resolves_to_nothing_rather_than_guessing() -> None:
    """A fuzzy match produces a confident price for a bet nobody placed."""
    model = PlayerPropsModel().fit(sample_logs())

    assert model.resolve_player("Star TOR Jr") is None
    assert model.resolve_player("S. Tor") is None
    assert model.resolve_player("") is None


def test_opponent_shot_factors_centre_on_one() -> None:
    factors = fit_opponent_shot_factors(sample_logs())

    assert set(factors) == {"TOR", "BOS"}
    assert sum(factors.values()) / len(factors) == pytest.approx(1.0, abs=0.05)


def test_opponent_shot_factors_on_a_season_with_no_games_are_empty() -> None:
    """The right-shaped frame with no rows: opening night, before puck drop."""
    empty = sample_logs(2).iloc[0:0]

    assert fit_opponent_shot_factors(empty) == {}


# -- name resolution ----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Alexis Lafrenière", "alexis lafreniere"),
        ("Aatu Räty", "aatu raty"),
        ("J.T. Miller", "j t miller"),
        ("JT Miller", "jt miller"),
        ("Drew O'Connor", "drew o connor"),
        ("  Auston   MATTHEWS  ", "auston matthews"),
    ],
)
def test_player_normalisation_removes_representation_only(
    raw: str, expected: str
) -> None:
    """Fifty-one of the league's thirteen hundred players carry an accent, a
    hyphen, an apostrophe or a full stop. Matching raw strings loses them."""
    from nhl_betting_lab.models.player_props import normalize_player_name

    assert normalize_player_name(raw) == expected


def test_normalisation_does_not_make_two_players_the_same() -> None:
    from nhl_betting_lab.models.player_props import normalize_player_name

    assert normalize_player_name("J. Miller") != normalize_player_name("JT Miller")


def test_a_parenthesised_nickname_is_indexed_as_the_name_books_print() -> None:
    """The registry carries `Anthony-John (AJ) Greer`; a book prints AJ Greer."""
    from nhl_betting_lab.models.player_props import player_name_aliases

    aliases = player_name_aliases("Anthony-John (AJ) Greer")

    assert "aj greer" in aliases
    assert "anthony john greer" in aliases


def test_an_accented_registry_name_resolves_from_the_plain_provider_spelling() -> None:
    logs = sample_logs()
    logs.loc[logs["player_id"] == 1, "player"] = "Alexis Lafrenière"
    model = PlayerPropsModel().fit(logs)

    assert model.resolve_player("Alexis Lafreniere") == 1
    assert model.resolve_player("Alexis Lafrenière") == 1


def test_a_name_two_players_share_resolves_to_neither() -> None:
    """Live examples: two Elias Petterssons, two Sebastian Ahos."""
    logs = sample_logs()
    logs.loc[logs["player_id"].isin([1, 101]), "player"] = "Sebastian Aho"
    model = PlayerPropsModel().fit(logs)

    assert model.resolve_player("Sebastian Aho") is None
    assert "sebastian aho" in model.ambiguous_names


def test_a_shared_name_resolves_when_the_teams_differ() -> None:
    """Team is not a looser match, it is another field that must agree."""
    logs = sample_logs()
    logs.loc[logs["player_id"] == 1, "player"] = "Sebastian Aho"
    logs.loc[logs["player_id"] == 101, "player"] = "Sebastian Aho"
    model = PlayerPropsModel().fit(logs)

    tor = model.resolve_player("Sebastian Aho", team="TOR")
    bos = model.resolve_player("Sebastian Aho", team="BOS")

    assert tor == 1
    assert bos == 101
    assert tor != bos


def test_resolving_within_a_game_picks_the_side_that_matches() -> None:
    logs = sample_logs()
    logs.loc[logs["player_id"] == 1, "player"] = "Sebastian Aho"
    logs.loc[logs["player_id"] == 101, "player"] = "Sebastian Aho"
    model = PlayerPropsModel().fit(logs)

    assert model.resolve_player_in_game("Sebastian Aho", home="TOR", away="MTL") == 1
    assert model.resolve_player_in_game("Sebastian Aho", home="BOS", away="MTL") == 101


def test_a_shared_name_on_both_sides_of_one_game_resolves_to_neither() -> None:
    """Carolina hosting the Islanders is a real fixture."""
    logs = sample_logs()
    logs.loc[logs["player_id"] == 1, "player"] = "Sebastian Aho"
    logs.loc[logs["player_id"] == 101, "player"] = "Sebastian Aho"
    model = PlayerPropsModel().fit(logs)

    assert model.resolve_player_in_game("Sebastian Aho", home="TOR", away="BOS") is None


def test_two_players_of_one_name_on_one_team_resolve_to_neither() -> None:
    """Both Elias Petterssons play for Vancouver, and nothing in a prop row
    separates them."""
    logs = sample_logs()
    logs.loc[logs["player_id"].isin([1, 2]), "player"] = "Elias Pettersson"
    model = PlayerPropsModel().fit(logs)

    assert model.resolve_player("Elias Pettersson", team="TOR") is None
    assert model.resolve_player_in_game(
        "Elias Pettersson", home="TOR", away="BOS"
    ) is None


def test_an_unambiguous_name_does_not_need_a_team() -> None:
    model = PlayerPropsModel().fit(sample_logs())

    assert model.resolve_player("Star TOR") == 1
    assert model.resolve_player_in_game("Star TOR", home="TOR", away="BOS") == 1


def test_a_parenthesised_number_is_a_disambiguator_not_a_nickname() -> None:
    """The provider writes "Elias Pettersson (2004)" precisely because two
    players share the name. Erasing it re-creates the collision the provider
    prevented, and put one wrong-player bet into a shipped measurement."""
    from nhl_betting_lab.models.player_props import player_name_aliases

    aliases = player_name_aliases("Elias Pettersson (2004)")

    assert "elias pettersson" not in aliases
    assert aliases == ("elias pettersson 2004",)
