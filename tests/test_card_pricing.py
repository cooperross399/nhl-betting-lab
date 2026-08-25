from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.models.calibration import PlattCalibration
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.reports import card_pricing
from test_player_props_model import sample_logs
from test_team_model import balanced_league


def _prop_prices(rows: list[dict] | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        rows
        if rows is not None
        else [
            {
                "market": "shots_on_goal",
                "player": "Star TOR",
                "home_team": "TOR",
                "away_team": "BOS",
                "selection": "over",
                "line": 2.5,
                "american_odds": 120,
            }
        ]
    )


def test_a_prop_row_gets_a_model_probability() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    prices = _prop_prices()

    probabilities, unresolved = card_pricing.price_props(prices, model)

    assert unresolved == []
    assert len(probabilities) == 1
    assert 0.0 < next(iter(probabilities.values())) < 1.0


def test_an_unresolved_player_is_reported_not_guessed() -> None:
    """A fuzzy match produces a confident price for a bet nobody placed."""
    model = PlayerPropsModel().fit(sample_logs())
    prices = _prop_prices([dict(_prop_prices().iloc[0], player="A. Star")])

    probabilities, unresolved = card_pricing.price_props(prices, model)

    assert probabilities == {}
    assert unresolved == ["A. Star"]


def test_the_under_side_is_the_complement_of_the_over() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    over = _prop_prices().iloc[0].to_dict()
    under = dict(over, selection="under")

    probabilities, _ = card_pricing.price_props(
        pd.DataFrame([over, under]), model
    )
    values = list(probabilities.values())

    assert sum(values) == pytest.approx(1.0)


def test_a_calibration_correction_is_applied_when_supplied() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    prices = _prop_prices()
    correction = PlattCalibration(intercept=-1.0, slope=1.0, fitted_on=5000)

    raw, _ = card_pricing.price_props(prices, model)
    fixed, _ = card_pricing.price_props(
        prices, model, corrections={"shots_on_goal": correction}
    )

    assert next(iter(fixed.values())) < next(iter(raw.values()))


def test_the_players_own_team_decides_the_venue() -> None:
    """Getting this backwards applies the wrong venue factor to every prop.

    The synthetic league is symmetric, so the factors are forced apart here to
    make the routing observable — the point of the test is which factor gets
    picked, not how large it is.
    """
    model = PlayerPropsModel().fit(sample_logs())
    model.venue_factors["home"] = {"shots_on_goal": 1.30}
    model.venue_factors["away"] = {"shots_on_goal": 0.70}
    home_row = _prop_prices().iloc[0].to_dict()
    away_row = dict(home_row, home_team="BOS", away_team="TOR")

    at_home, _ = card_pricing.price_props(pd.DataFrame([home_row]), model)
    on_the_road, _ = card_pricing.price_props(pd.DataFrame([away_row]), model)

    # Star TOR plays for TOR: the first row is his home game, the second away.
    assert next(iter(at_home.values())) > next(iter(on_the_road.values()))


def test_the_players_own_team_decides_the_opponent() -> None:
    """A player is never priced against his own team's concession factor."""
    model = PlayerPropsModel().fit(sample_logs())
    model.opponent_factors["BOS"] = {"shots_on_goal": 1.40}
    model.opponent_factors["TOR"] = {"shots_on_goal": 0.60}
    row = _prop_prices().iloc[0].to_dict()

    probabilities, _ = card_pricing.price_props(pd.DataFrame([row]), model)
    baseline = model.over_probability(
        1, "shots_on_goal", 2.5, opponent="BOS", venue="home"
    )

    assert next(iter(probabilities.values())) == pytest.approx(baseline)


def test_a_prop_with_no_line_is_skipped() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    prices = _prop_prices([dict(_prop_prices().iloc[0], line=None)])

    probabilities, _ = card_pricing.price_props(prices, model)

    assert probabilities == {}


def test_a_team_market_row_is_not_priced_by_the_props_path() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    prices = pd.DataFrame(
        [
            {
                "market": "moneyline",
                "player": "",
                "home_team": "TOR",
                "away_team": "BOS",
                "selection": "home",
                "line": None,
                "american_odds": -130,
            }
        ]
    )

    probabilities, _ = card_pricing.price_props(prices, model)

    assert probabilities == {}


# -- team markets ------------------------------------------------------


def _team_prices(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_a_moneyline_row_gets_a_probability() -> None:
    model = TeamModel().fit(balanced_league())
    prices = _team_prices(
        [
            {
                "market": "moneyline",
                "player": "",
                "home_team": "STR",
                "away_team": "WEA",
                "selection": "home",
                "line": None,
                "american_odds": -180,
            }
        ]
    )

    probabilities = card_pricing.price_team_markets(prices, model)

    assert len(probabilities) == 1
    assert next(iter(probabilities.values())) > 0.5


def test_the_puck_line_sign_decides_which_side_is_laying_the_goals() -> None:
    """Reading the sign wrong flips every puck-line price on the card."""
    model = TeamModel().fit(balanced_league())
    laying = {
        "market": "puck_line",
        "player": "",
        "home_team": "STR",
        "away_team": "WEA",
        "selection": "home",
        "line": -1.5,
        "american_odds": 120,
    }
    taking = dict(laying, line=1.5)

    probabilities = card_pricing.price_team_markets(
        _team_prices([laying, taking]), model
    )
    values = list(probabilities.values())

    assert values[0] < values[1]  # -1.5 is harder than +1.5


def test_a_totals_row_gets_over_and_under() -> None:
    model = TeamModel().fit(balanced_league())
    over = {
        "market": "total_5_5",
        "player": "",
        "home_team": "AVA",
        "away_team": "AVB",
        "selection": "over",
        "line": 5.5,
        "american_odds": -110,
    }
    under = dict(over, selection="under")

    probabilities = card_pricing.price_team_markets(
        _team_prices([over, under]), model
    )

    assert sum(probabilities.values()) == pytest.approx(1.0)


def test_a_puck_line_row_with_no_line_is_skipped() -> None:
    model = TeamModel().fit(balanced_league())
    prices = _team_prices(
        [
            {
                "market": "puck_line",
                "player": "",
                "home_team": "STR",
                "away_team": "WEA",
                "selection": "home",
                "line": None,
                "american_odds": 120,
            }
        ]
    )

    assert card_pricing.price_team_markets(prices, model) == {}


def test_a_prop_row_is_not_priced_by_the_team_path() -> None:
    model = TeamModel().fit(balanced_league())

    assert card_pricing.price_team_markets(_prop_prices(), model) == {}


def test_an_empty_frame_prices_nothing() -> None:
    model = TeamModel().fit(balanced_league())
    empty = pd.DataFrame(columns=["market"])

    assert card_pricing.price_team_markets(empty, model) == {}
    props_model = PlayerPropsModel().fit(sample_logs())
    assert card_pricing.price_props(empty, props_model) == ({}, [])
