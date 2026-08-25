from __future__ import annotations

import pytest

from nhl_betting_lab import stats


def test_an_empty_series_measures_nothing() -> None:
    interval = stats.roi_interval([])

    assert interval.bets == 0
    assert "nothing to measure" in interval.verdict()


def test_a_break_even_series_has_zero_roi() -> None:
    interval = stats.roi_interval([1.0, -1.0] * 50)

    assert interval.roi == pytest.approx(0.0)
    assert interval.includes_zero is True


def test_an_interval_that_includes_zero_says_the_exact_words() -> None:
    """Not 'promising', not 'trending positive', not 'small but positive'."""
    interval = stats.roi_interval([0.91] * 30 + [-1.0] * 25)

    assert interval.includes_zero is True
    assert stats.NO_DEMONSTRATED_EDGE in interval.verdict()
    for forbidden in ("promising", "trending", "small but positive"):
        assert forbidden not in interval.verdict()


def test_a_tiny_sample_is_called_out_regardless_of_its_point_estimate() -> None:
    interval = stats.roi_interval([5.0] * 10)

    assert "far too few" in interval.verdict()
    assert stats.NO_DEMONSTRATED_EDGE in interval.verdict()


def test_a_strongly_positive_large_sample_excludes_zero() -> None:
    interval = stats.roi_interval([0.91] * 700 + [-1.0] * 300)

    assert interval.includes_zero is False
    assert "excludes zero" in interval.verdict()


def test_even_a_significant_result_is_hedged_about_persistence() -> None:
    interval = stats.roi_interval([0.91] * 700 + [-1.0] * 300)

    assert "not the same as an edge that will persist" in interval.verdict()


def test_pushes_are_counted_and_do_not_count_as_wins() -> None:
    interval = stats.roi_interval(
        [0.91, -1.0, 0.0], wins=1, pushes=1
    )

    assert interval.pushes == 1
    assert interval.win_rate == pytest.approx(0.5)


def test_a_single_bet_has_an_unbounded_interval() -> None:
    """One observation cannot bound anything, and saying so beats a fake number."""
    interval = stats.roi_interval([0.91])

    assert interval.low == float("-inf")
    assert interval.high == float("inf")


def test_the_detection_numbers_match_the_documented_ones() -> None:
    """These are quoted in the docs; they must not drift silently."""
    assert stats.bets_needed_to_detect(0.05) == 1537
    assert stats.bets_needed_to_detect(0.10) == 385
    assert stats.bets_needed_to_detect(0.15) == 171


def test_a_zero_edge_needs_no_bets_because_it_cannot_be_detected() -> None:
    assert stats.bets_needed_to_detect(0.0) == 0


def test_the_detection_table_renders_every_row() -> None:
    table = stats.detection_table((0.05, 0.10))

    assert "1,537" in table
    assert "385" in table


def test_the_roi_table_row_always_carries_the_sample_size() -> None:
    interval = stats.roi_interval([0.91] * 30 + [-1.0] * 25)

    row = interval.as_row("shots_on_goal")

    assert "| 55 |" in row
    assert "no" in row  # does not survive correction


def test_the_wilson_interval_is_sane_at_small_n() -> None:
    low, high = stats.wilson_interval(1, 3)

    assert 0.0 <= low < high <= 1.0
    assert low < 1 / 3 < high


def test_the_wilson_interval_never_leaves_the_unit_interval() -> None:
    assert stats.wilson_interval(0, 5) == (0.0, pytest.approx(0.5, abs=0.1))
    low, high = stats.wilson_interval(5, 5)

    assert high == 1.0
    assert low > 0.4


def test_the_wilson_interval_of_no_trials_is_the_whole_range() -> None:
    assert stats.wilson_interval(0, 0) == (0.0, 1.0)


def test_the_multiple_comparison_warning_states_the_chance() -> None:
    """With twenty-five looks, one 95% result is what chance looks like."""
    warning = stats.looks_significant_but_is_a_multiple_comparison(1, 25)

    assert "72%" in warning
    assert "fitted to this sample" in warning


def test_the_multiple_comparison_warning_is_silent_on_a_single_look() -> None:
    assert stats.looks_significant_but_is_a_multiple_comparison(1, 1) == ""
    assert stats.looks_significant_but_is_a_multiple_comparison(0, 25) == ""


# -- correcting for the number of tests ---------------------------------


def test_one_look_needs_no_correction() -> None:
    interval = stats.roi_interval([0.91] * 30 + [-1.0] * 25, looks=1)

    assert interval.adjusted_low == interval.low
    assert interval.adjusted_high == interval.high


def test_more_looks_widen_the_interval() -> None:
    """Testing seven markets and reporting the one that cleared 95% is a
    search, not a finding."""
    returns = [0.91] * 160 + [-1.0] * 103

    naive = stats.roi_interval(returns, looks=1)
    corrected = stats.roi_interval(returns, looks=7)

    assert corrected.adjusted_low < naive.low
    assert corrected.adjusted_high > naive.high


def test_a_marginal_result_stops_surviving_once_the_search_is_counted() -> None:
    returns = [0.91] * 55 + [-1.0] * 45

    interval = stats.roi_interval(returns, looks=7)

    assert interval.includes_zero is False or interval.survives_correction is False


def test_a_strong_result_survives_the_correction() -> None:
    returns = [0.91] * 200 + [-1.0] * 100

    interval = stats.roi_interval(returns, looks=7)

    assert interval.survives_correction is True
    assert "also survives correcting" in interval.verdict()


def test_a_result_that_does_not_survive_says_no_demonstrated_edge() -> None:
    returns = [0.91] * 58 + [-1.0] * 45

    interval = stats.roi_interval(returns, looks=7)
    verdict = interval.verdict()

    if not interval.survives_correction and not interval.includes_zero:
        assert stats.NO_DEMONSTRATED_EDGE in verdict
        assert "family of tests actually run" in verdict


def test_a_tiny_sample_never_survives_correction() -> None:
    interval = stats.roi_interval([5.0] * 10, looks=7)

    assert interval.survives_correction is False


@pytest.mark.parametrize(("looks", "expected"), [(1, 1.96), (7, 2.69), (20, 3.02)])
def test_the_critical_value_grows_with_the_number_of_looks(
    looks: int, expected: float
) -> None:
    assert stats.bonferroni_z(looks) == pytest.approx(expected, abs=0.01)


def test_the_table_row_reports_both_intervals() -> None:
    interval = stats.roi_interval([0.91] * 160 + [-1.0] * 103, looks=7)

    row = interval.as_row("shots_on_goal")

    assert row.count("..") == 2


def test_a_single_test_says_so_rather_than_showing_a_fake_correction() -> None:
    interval = stats.roi_interval([0.91] * 30 + [-1.0] * 25, looks=1)

    assert "n/a (one test)" in interval.as_row("shots_on_goal")
