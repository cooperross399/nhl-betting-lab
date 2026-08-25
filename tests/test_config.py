from __future__ import annotations

from datetime import date

import pytest

from nhl_betting_lab import config


def test_season_rolls_over_in_august() -> None:
    assert config.current_season_id(date(2026, 7, 31)) == 20252026
    assert config.current_season_id(date(2026, 8, 1)) == 20262027


def test_a_season_in_progress_keeps_its_own_id_through_the_spring() -> None:
    assert config.current_season_id(date(2027, 4, 15)) == 20262027
    assert config.current_season_id(date(2026, 10, 8)) == 20262027


def test_recent_seasons_are_oldest_first_and_end_with_the_current_one() -> None:
    seasons = config.recent_season_ids(4, today=date(2026, 10, 1))

    assert seasons == [20232024, 20242025, 20252026, 20262027]
    assert seasons[-1] == config.current_season_id(date(2026, 10, 1))


def test_a_season_history_of_zero_is_refused_rather_than_silently_empty() -> None:
    with pytest.raises(ValueError):
        config.recent_season_ids(0)


def test_season_label_is_human_readable() -> None:
    assert config.season_label(20262027) == "2026-27"
    assert config.season_label(19992000) == "1999-00"


def test_season_label_refuses_a_malformed_id() -> None:
    with pytest.raises(ValueError):
        config.season_label(2026)


def test_the_prop_edge_bar_is_higher_than_the_team_bar() -> None:
    """Props are priced before the lineup is known; books reprice on it."""
    assert config.MIN_PROP_EDGE > config.MIN_EDGE


def test_the_juice_limit_matches_the_stated_preference() -> None:
    assert config.MAX_DEFAULT_JUICE == -160


def test_the_sport_key_is_the_provider_nhl_key() -> None:
    assert config.ODDS_API_SPORT_KEY == "icehockey_nhl"


def test_every_data_path_sits_under_the_repository() -> None:
    for path in (
        config.DATA_DIR,
        config.RAW_DIR,
        config.PROCESSED_DIR,
        config.MANUAL_DIR,
        config.STAGING_DIR,
        config.OUTPUTS_DIR,
    ):
        assert path.is_relative_to(config.PROJECT_ROOT)


def test_regular_season_is_the_fitted_game_type() -> None:
    assert config.REGULAR_SEASON_GAME_TYPE == 2
    assert config.PLAYOFF_GAME_TYPE == 3
