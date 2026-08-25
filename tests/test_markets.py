from __future__ import annotations

import pytest

from nhl_betting_lab import markets


def test_every_prop_market_the_brief_names_is_priced() -> None:
    keys = set(markets.prop_market_keys())

    assert {
        "shots_on_goal",
        "points",
        "goals",
        "assists",
        "goalie_saves",
        "blocked_shots",
    } <= keys


def test_every_team_market_the_brief_names_is_priced() -> None:
    assert set(markets.team_market_keys()) == {
        "moneyline",
        "puck_line",
        "total_goals",
    }


def test_every_prop_settles_on_a_real_log_column() -> None:
    from nhl_betting_lab.data.build_datasets import PLAYER_LOG_COLUMNS

    for market in markets.PROP_MARKETS:
        assert market.settles_on in PLAYER_LOG_COLUMNS, market.key


def test_no_team_market_claims_to_settle_on_a_player_column() -> None:
    for market in markets.TEAM_MARKETS:
        assert market.settles_on == ""


def test_every_prop_is_a_per_event_market() -> None:
    """Props cost one credit per market per event; the cost model depends on it."""
    assert all(market.per_event for market in markets.PROP_MARKETS)
    assert not any(market.per_event for market in markets.TEAM_MARKETS)


def test_provider_keys_are_unique() -> None:
    keys = [market.provider_key for market in markets.ALL_MARKETS]

    assert len(keys) == len(set(keys))


def test_the_provider_key_for_shots_is_the_nhl_one_not_the_soccer_one() -> None:
    """`player_shots_on_target` is football; NHL is `player_shots_on_goal`."""
    assert markets.market_for("shots_on_goal").provider_key == "player_shots_on_goal"


def test_a_known_market_resolves() -> None:
    assert markets.market_for("goalie_saves").provider_key == "player_total_saves"


def test_an_unknown_market_names_the_ones_that_exist() -> None:
    with pytest.raises(KeyError, match="Known markets"):
        markets.market_for("player_hat_trick")


def test_a_provider_key_maps_back_to_a_project_market() -> None:
    assert markets.market_for_provider_key("h2h").key == "moneyline"
    assert markets.market_for_provider_key("player_points").key == "points"


def test_alternate_ladders_map_to_the_same_project_market() -> None:
    """The whole EPL `total_2_5` lesson lives in this line."""
    assert markets.market_for_provider_key("alternate_totals").key == "total_goals"
    assert markets.market_for_provider_key("alternate_spreads").key == "puck_line"


def test_an_unmapped_provider_market_is_ignored_not_an_error() -> None:
    """A response carries markets we do not price; each is not a failure."""
    assert markets.market_for_provider_key("team_totals") is None
    assert markets.market_for_provider_key("") is None


def test_per_event_provider_keys_are_exactly_the_prop_keys() -> None:
    assert set(markets.per_event_provider_keys()) == {
        market.provider_key for market in markets.PROP_MARKETS
    }


def test_anytime_scorer_is_the_goals_market_at_half() -> None:
    """One name for one thing, so two cannot disagree on the same card."""
    assert markets.ANYTIME_SCORER_LINE == 0.5
    assert "anytime" in markets.market_for("goals").label.lower()


def test_case_and_whitespace_do_not_change_a_lookup() -> None:
    assert markets.market_for("  GOALS  ").key == "goals"


def test_the_totals_key_does_not_name_a_line_it_may_not_hold() -> None:
    """It was `total_5_5` and carries 6.5 and 7.5 from the alternate ladder.
    A key naming a line it does not always hold is the same lie as a column
    called `power_play_points` holding a count of goals."""
    assert "total_goals" in markets.MARKETS_BY_KEY
    assert not any("5_5" in key for key in markets.MARKETS_BY_KEY)


def test_no_market_key_hardcodes_a_line() -> None:
    import re

    for key in markets.MARKETS_BY_KEY:
        assert not re.search(r"\d_\d", key), key


def test_the_typical_total_line_is_reporting_only() -> None:
    """The line a price is judged against comes from the response."""
    assert markets.TYPICAL_TOTAL_LINE == 5.5
