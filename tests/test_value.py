from __future__ import annotations

import math

import pytest

from nhl_betting_lab.models import value


@pytest.mark.parametrize(
    ("price", "expected"),
    [(-110, 0.5238), (100, 0.5), (150, 0.4), (-200, 0.6667), (300, 0.25)],
)
def test_implied_probability_matches_the_arithmetic(price: int, expected: float) -> None:
    assert value.american_to_implied(price) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize(
    ("price", "expected"), [(-110, 1.9091), (100, 2.0), (150, 2.5), (-200, 1.5)]
)
def test_decimal_odds_match_the_arithmetic(price: int, expected: float) -> None:
    assert value.american_to_decimal(price) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize("price", [0, 50, -99, 99, -1])
def test_a_price_inside_the_impossible_band_is_refused(price: int) -> None:
    """There is no such thing as a price between -100 and +100."""
    with pytest.raises(value.OddsError):
        value.american_to_implied(price)


@pytest.mark.parametrize("price", ["", None, "abc", float("nan"), float("inf"), True])
def test_a_non_numeric_price_is_refused_rather_than_guessed(price: object) -> None:
    with pytest.raises(value.OddsError):
        value.american_to_implied(price)


def test_a_numeric_string_price_is_accepted() -> None:
    assert value.american_to_implied("-110") == pytest.approx(0.5238, abs=1e-4)


def test_fair_price_round_trips_through_implied_probability() -> None:
    for probability in (0.2, 0.35, 0.5, 0.65, 0.8):
        price = value.implied_to_american(probability)
        assert value.american_to_implied(price) == pytest.approx(probability, abs=0.01)


@pytest.mark.parametrize("probability", [0.0, 1.0, -0.1, 1.5])
def test_a_fair_price_needs_a_real_probability(probability: float) -> None:
    with pytest.raises(value.OddsError):
        value.implied_to_american(probability)


def test_an_even_money_probability_produces_a_minus_price() -> None:
    """At exactly 50% the convention is -100, not +100."""
    assert value.implied_to_american(0.5) == -100


def test_profit_on_win_is_profit_not_total_return() -> None:
    assert value.profit_on_win(150, stake=2.0) == pytest.approx(3.0)
    assert value.profit_on_win(-200, stake=2.0) == pytest.approx(1.0)


def test_devig_makes_two_sides_sum_to_one() -> None:
    over, under = value.devig_two_way(-110, -110)

    assert over + under == pytest.approx(1.0)
    assert over == pytest.approx(0.5)


def test_devig_preserves_the_ordering_of_a_lopsided_market() -> None:
    over, under = value.devig_two_way(-250, 200)

    assert over > under
    assert over + under == pytest.approx(1.0)


def test_a_one_sided_quote_reports_that_no_devig_is_available() -> None:
    """Pretending a one-sided quote can be devigged invents a fair price."""
    assert value.no_vig_available(-130, None) is False
    assert value.no_vig_available(-130, 110) is True


def test_no_vig_available_is_false_when_either_side_is_unusable() -> None:
    assert value.no_vig_available(-130, "n/a") is False
    assert value.no_vig_available("", 110) is False


def test_edge_is_model_probability_minus_implied() -> None:
    assert value.edge(0.60, -110) == pytest.approx(0.60 - 0.5238, abs=1e-4)


def test_a_vigged_one_sided_price_understates_the_edge() -> None:
    """The conservative direction, and every report says so."""
    vigged = value.edge(0.60, -130)
    fair_side, _ = value.devig_two_way(-130, 110)

    assert vigged < 0.60 - fair_side


def test_expected_value_is_zero_at_the_fair_price() -> None:
    price = value.implied_to_american(0.4)
    fair = value.american_to_implied(price)

    assert value.expected_value(fair, price) == pytest.approx(0.0, abs=1e-3)


def test_expected_value_is_negative_when_the_model_agrees_with_a_vigged_price() -> None:
    assert value.expected_value(0.5238, -110) < 0


@pytest.mark.parametrize("probability", [-0.01, 1.01])
def test_expected_value_refuses_an_impossible_probability(probability: float) -> None:
    with pytest.raises(value.OddsError):
        value.expected_value(probability, -110)


@pytest.mark.parametrize(
    ("price", "heavy"),
    [(-180, True), (-160, False), (-159, False), (-200, True), (150, False), (100, False)],
)
def test_heavy_juice_is_measured_against_the_configured_limit(
    price: int, heavy: bool
) -> None:
    assert value.is_heavy_juice(price, -160) is heavy


def test_plus_money_is_never_heavy_juice() -> None:
    assert value.is_heavy_juice(2500, -160) is False


def test_implied_probabilities_of_a_two_way_market_exceed_one() -> None:
    """The overround is the vig; this is what devigging removes."""
    total = value.american_to_implied(-110) + value.american_to_implied(-110)

    assert total > 1.0
    assert math.isclose(total, 1.0476, abs_tol=1e-4)
