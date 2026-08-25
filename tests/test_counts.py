from __future__ import annotations

import math

import pytest

from nhl_betting_lab.models import counts


def test_a_poisson_pmf_sums_to_one() -> None:
    poisson = counts.Poisson(2.5)

    assert sum(poisson.pmf(k) for k in range(60)) == pytest.approx(1.0, abs=1e-9)


def test_a_negative_binomial_pmf_sums_to_one() -> None:
    negbin = counts.NegativeBinomial(mean=25.0, r=8.0)

    assert sum(negbin.pmf(k) for k in range(400)) == pytest.approx(1.0, abs=1e-9)


def test_a_negative_binomial_has_the_variance_it_claims() -> None:
    negbin = counts.NegativeBinomial(mean=10.0, r=5.0)
    mass = [(k, negbin.pmf(k)) for k in range(300)]
    mean = sum(k * p for k, p in mass)
    variance = sum((k - mean) ** 2 * p for k, p in mass)

    assert mean == pytest.approx(10.0, abs=1e-6)
    assert variance == pytest.approx(10.0 + 100.0 / 5.0, abs=1e-4)


@pytest.mark.parametrize("k", [-1, -10])
def test_a_negative_count_has_no_mass(k: int) -> None:
    assert counts.Poisson(2.0).pmf(k) == 0.0
    assert counts.NegativeBinomial(2.0, 3.0).pmf(k) == 0.0


def test_a_half_point_line_has_no_push() -> None:
    poisson = counts.Poisson(2.5)

    assert poisson.push_probability(2.5) == 0.0
    assert poisson.over_probability(2.5) == pytest.approx(poisson.sf(2))


def test_a_whole_number_line_prices_the_push_out() -> None:
    """A book settling "over 2.0" refunds a 2; the bet is conditional on that."""
    poisson = counts.Poisson(2.5)
    push = poisson.push_probability(2.0)

    assert push == pytest.approx(poisson.pmf(2))
    assert poisson.over_probability(2.0) == pytest.approx(
        poisson.sf(2) / (1.0 - push)
    )


def test_a_whole_number_line_prices_higher_than_the_half_point_above_it() -> None:
    """Over 2.0 is a better bet than over 2.5; treating them alike misprices."""
    poisson = counts.Poisson(2.5)

    assert poisson.over_probability(2.0) > poisson.over_probability(2.5)


def test_the_over_probability_falls_as_the_line_rises() -> None:
    poisson = counts.Poisson(3.0)
    probabilities = [poisson.over_probability(line) for line in (0.5, 1.5, 2.5, 3.5)]

    assert probabilities == sorted(probabilities, reverse=True)


def test_overdispersion_is_measured_not_assumed() -> None:
    clustered = [0] * 60 + [1] * 20 + [5] * 20  # variance far above the mean
    dispersion = counts.measure_dispersion(clustered)

    assert dispersion.overdispersed is True
    assert dispersion.r is not None
    assert "negative binomial" in dispersion.describe()


def test_a_poisson_like_column_stays_poisson() -> None:
    # Sampled deterministically from a Poisson(2) shape.
    poisson_like = [0] * 14 + [1] * 27 + [2] * 27 + [3] * 18 + [4] * 9 + [5] * 5
    dispersion = counts.measure_dispersion(poisson_like)

    assert dispersion.overdispersed is False
    assert dispersion.r is None
    assert "Poisson" in dispersion.describe()


def test_too_few_samples_never_claims_overdispersion() -> None:
    dispersion = counts.measure_dispersion([0, 9, 0, 9])

    assert dispersion.samples == 4
    assert dispersion.overdispersed is False
    assert "too few" in dispersion.describe()


def test_an_empty_column_measures_nothing() -> None:
    dispersion = counts.measure_dispersion([])

    assert dispersion.samples == 0
    assert dispersion.ratio == 1.0


def test_distribution_for_returns_poisson_without_a_dispersion() -> None:
    assert isinstance(counts.distribution_for(2.0, None), counts.Poisson)


def test_distribution_for_returns_negative_binomial_when_overdispersed() -> None:
    dispersion = counts.measure_dispersion([0] * 60 + [1] * 20 + [5] * 20)

    shape = counts.distribution_for(2.0, dispersion)

    assert isinstance(shape, counts.NegativeBinomial)
    assert shape.mean == 2.0


def test_a_near_poisson_dispersion_collapses_back_to_poisson() -> None:
    """A huge r is numerically Poisson and costs precision in the gammas."""
    dispersion = counts.Dispersion(mean=20.0, variance=20.0001, samples=500)

    assert isinstance(counts.distribution_for(20.0, dispersion), counts.Poisson)


def test_pricing_saves_as_poisson_understates_the_high_tail() -> None:
    """This is the whole reason the negative binomial is here."""
    poisson = counts.Poisson(25.0)
    negbin = counts.NegativeBinomial(mean=25.0, r=8.0)

    assert negbin.over_probability(31.5) > poisson.over_probability(31.5)
    assert negbin.over_probability(19.5) < poisson.over_probability(19.5)


def test_a_zero_mean_is_clamped_rather_than_dividing_by_zero() -> None:
    assert counts.Poisson(0.0).pmf(0) == pytest.approx(1.0, abs=1e-6)
    assert counts.Poisson(0.0).over_probability(0.5) == pytest.approx(0.0, abs=1e-6)


def test_the_convenience_helper_agrees_with_the_class() -> None:
    assert counts.poisson_over_probability(2.5, 1.5) == pytest.approx(
        counts.Poisson(2.5).over_probability(1.5)
    )


def test_tail_sum_adds_the_mass_it_is_given() -> None:
    poisson = counts.Poisson(2.0)

    assert counts.tail_sum(poisson, [0, 1, 2]) == pytest.approx(poisson.cdf(2))


def test_the_cdf_is_never_above_one() -> None:
    assert counts.Poisson(1.0).cdf(200) <= 1.0
    assert counts.Poisson(1.0).sf(200) >= 0.0


def test_the_dispersion_threshold_is_above_one_on_purpose() -> None:
    """A sample ratio wobbles above one by chance; swapping shapes on noise
    would make the model depend on which games are in the file."""
    assert counts.DISPERSION_THRESHOLD > 1.0
