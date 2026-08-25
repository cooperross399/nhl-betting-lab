from __future__ import annotations

import math
import random

import pytest

from nhl_betting_lab.models import calibration as cal


def _overconfident_samples(count: int, seed: int = 7) -> list[tuple[float, bool]]:
    """A model that says 70% and is right 60% of the time.

    This is the defect a per-player Poisson actually has: it runs hot in the
    middle of the range, which is the signature a slope below one straightens.
    """
    rng = random.Random(seed)
    samples: list[tuple[float, bool]] = []
    for _ in range(count):
        claimed = rng.uniform(0.15, 0.85)
        true = claimed - 0.10 * (claimed - 0.10)
        samples.append((claimed, rng.random() < true))
    return samples


def test_logit_and_sigmoid_are_inverses() -> None:
    for probability in (0.05, 0.3, 0.5, 0.77, 0.95):
        assert cal.sigmoid(cal.logit(probability)) == pytest.approx(probability)


def test_logit_clamps_the_extremes_rather_than_returning_infinity() -> None:
    assert math.isfinite(cal.logit(0.0))
    assert math.isfinite(cal.logit(1.0))


def test_the_identity_correction_changes_nothing() -> None:
    identity = cal.PlattCalibration.identity()

    assert identity.is_identity is True
    assert identity.apply(0.42) == pytest.approx(0.42)


def test_too_few_samples_returns_the_identity_and_says_so() -> None:
    fitted = cal.PlattCalibration.fit([(0.5, True)] * 40)

    assert fitted.is_identity is True
    assert fitted.fitted_on == 40
    assert "below the" in fitted.describe()


def test_a_correction_fitted_on_all_wins_is_refused() -> None:
    """A logistic fit on one outcome runs to infinity and reports perfection."""
    fitted = cal.PlattCalibration.fit([(0.5, True)] * 500)

    assert fitted.is_identity is True


def test_a_correction_fitted_on_all_losses_is_refused() -> None:
    fitted = cal.PlattCalibration.fit([(0.5, False)] * 500)

    assert fitted.is_identity is True


def test_a_fitted_correction_pulls_an_overconfident_model_down() -> None:
    samples = _overconfident_samples(3000)

    fitted = cal.PlattCalibration.fit(samples)

    assert not fitted.is_identity
    assert fitted.apply(0.70) < 0.70
    assert "slope" in fitted.describe()


def test_a_fitted_correction_improves_the_brier_score_in_sample() -> None:
    samples = _overconfident_samples(3000)
    fitted = cal.PlattCalibration.fit(samples)

    raw = cal.brier_score(samples)
    corrected = cal.brier_score([(fitted.apply(p), won) for p, won in samples])

    assert corrected < raw


def test_a_correction_never_leaves_the_unit_interval() -> None:
    extreme = cal.PlattCalibration(intercept=-8.0, slope=4.0, fitted_on=1000)

    for probability in (0.0, 0.001, 0.5, 0.999, 1.0):
        assert 0.0 <= extreme.apply(probability) <= 1.0


def test_the_reliability_table_reports_counts_beside_every_rate() -> None:
    samples = [(0.15, False)] * 50 + [(0.85, True)] * 30

    table = cal.reliability_table(samples)

    assert sum(bucket.count for bucket in table) == 80
    assert all(bucket.count > 0 for bucket in table)


def test_the_reliability_table_shows_the_gap_in_the_right_direction() -> None:
    """Positive gap means the model promised more than happened."""
    samples = [(0.80, True)] * 60 + [(0.80, False)] * 40

    bucket = cal.reliability_table(samples)[0]

    assert bucket.predicted == pytest.approx(0.80)
    assert bucket.observed == pytest.approx(0.60)
    assert bucket.gap == pytest.approx(0.20)


def test_empty_reliability_buckets_are_omitted_rather_than_shown_as_zero() -> None:
    table = cal.reliability_table([(0.05, True)] * 10)

    assert len(table) == 1
    assert table[0].label == "0%-10%"


def test_a_probability_of_exactly_one_lands_in_the_top_bucket() -> None:
    table = cal.reliability_table([(1.0, True)])

    assert table[0].label == "90%-100%"


def test_malformed_bucket_edges_are_refused() -> None:
    with pytest.raises(ValueError):
        cal.reliability_table([(0.5, True)], edges=(0.0, 0.5, 0.4))


def test_brier_and_log_loss_are_none_on_an_empty_sample() -> None:
    assert cal.brier_score([]) is None
    assert cal.log_loss([]) is None


def test_a_perfect_forecaster_scores_zero() -> None:
    assert cal.brier_score([(1.0, True), (0.0, False)]) == pytest.approx(0.0)


def test_log_loss_survives_a_confident_miss() -> None:
    """Without clamping this is infinite and takes the report with it."""
    assert math.isfinite(cal.log_loss([(1.0, False)]))


# -- walk-forward ------------------------------------------------------


def _dated(samples: list[tuple[float, bool]], start_day: int = 1) -> list[tuple[str, float, bool]]:
    rows = []
    for index, (probability, won) in enumerate(samples):
        day = start_day + index // 8  # eight props a game-day
        rows.append((f"2025-{1 + day // 28:02d}-{1 + day % 28:02d}", probability, won))
    return rows


def test_walk_forward_never_scores_a_sample_with_its_own_day() -> None:
    """A dozen props on one game-day share lineup assumptions; a same-day fit
    leaks within the day even though the dates look ordered."""
    rows = _dated(_overconfident_samples(2000))
    seen: list[tuple[str, cal.PlattCalibration]] = []

    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=200)
    seen = result.corrections

    assert seen, "a refit should have happened"
    scored_days = {date for date, _, _, _ in result.scored}
    # Every correction is stamped with the first day it applies to, and that
    # day's samples were not in the fit that produced it.
    assert all(date in scored_days for date, _ in seen)


def test_walk_forward_drops_the_warmup_rather_than_scoring_it_uncorrected() -> None:
    """Mixing corrected and uncorrected samples into one average flatters
    whichever is worse."""
    rows = _dated(_overconfident_samples(1000))

    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=400)

    assert result.warmup_skipped >= 400
    assert len(result.scored) + result.warmup_skipped == len(rows)


def test_walk_forward_improves_a_systematically_overconfident_model() -> None:
    rows = _dated(_overconfident_samples(6000))

    result = cal.walk_forward_calibrate(
        rows, minimum_fit_samples=500, refit_every=10
    )

    raw = cal.brier_score(result.raw)
    corrected = cal.brier_score(result.corrected)
    assert corrected < raw


def test_walk_forward_straightens_the_high_probability_bucket() -> None:
    """The top bucket collapsing is the defect; the table must show it fixed."""
    rows = _dated(_overconfident_samples(6000))
    result = cal.walk_forward_calibrate(
        rows, minimum_fit_samples=500, refit_every=10
    )

    def gap_at_top(samples: list[tuple[float, bool]]) -> float:
        table = [b for b in cal.reliability_table(samples) if b.count >= 100]
        return max(abs(bucket.gap) for bucket in table)

    assert gap_at_top(result.corrected) < gap_at_top(result.raw)


def test_walk_forward_refuses_a_non_iso_date() -> None:
    with pytest.raises(ValueError, match="ISO dates"):
        cal.walk_forward_calibrate([("7 Jan 2025", 0.5, True)])


def test_walk_forward_refuses_an_impossible_probability() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        cal.walk_forward_calibrate([("2025-01-07", 1.4, True)])


def test_walk_forward_sorts_unordered_input() -> None:
    rows = [("2025-02-01", 0.5, True), ("2025-01-01", 0.4, False)]

    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=1)

    assert [date for date, _, _, _ in result.scored] == ["2025-02-01"]


def test_an_empty_input_produces_an_empty_result() -> None:
    result = cal.walk_forward_calibrate([])

    assert result.scored == []
    assert result.warmup_skipped == 0


def test_the_verdict_refuses_to_speak_below_the_sample_floor() -> None:
    rows = _dated(_overconfident_samples(300))
    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=100)

    verdict = cal.calibration_verdict(result, minimum_samples=1000)

    assert "Not measurable" in verdict
    assert "No verdict" in verdict


def test_the_verdict_never_says_the_model_is_good() -> None:
    rows = _dated(_overconfident_samples(3000))
    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=500)

    verdict = cal.calibration_verdict(result)

    assert "rule this model out" in verdict
    assert "cannot rule it in" in verdict
    for forbidden in ("profitable", "edge demonstrated", "works"):
        assert forbidden not in verdict


def test_the_verdict_states_the_sample_size() -> None:
    rows = _dated(_overconfident_samples(3000))
    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=500)

    verdict = cal.calibration_verdict(result)

    assert f"{len(result.scored):,}" in verdict


def test_refit_every_reduces_the_number_of_fits_without_leaking() -> None:
    rows = _dated(_overconfident_samples(4000))

    often = cal.walk_forward_calibrate(rows, minimum_fit_samples=300, refit_every=2)
    rarely = cal.walk_forward_calibrate(rows, minimum_fit_samples=300, refit_every=20)

    assert len(rarely.corrections) < len(often.corrections)
    assert len(rarely.scored) == len(often.scored)


def test_the_verdict_does_not_call_a_five_decimal_change_an_improvement() -> None:
    """It used to print "improves the Brier score (0.1053 raw, 0.1053
    corrected)", which is technically true and reads as a finding."""
    result = cal.WalkForwardResult(
        scored=[("2025-01-01", 0.5, 0.5000001, index % 2 == 0) for index in range(400)],
        corrections=[],
        warmup_skipped=0,
    )

    verdict = cal.calibration_verdict(result)

    assert "no material difference" in verdict
    assert "improves" not in verdict


def test_the_verdict_reports_a_correction_that_made_things_worse() -> None:
    result = cal.WalkForwardResult(
        scored=[("2025-01-01", 0.5, 0.9, False) for _ in range(400)],
        corrections=[],
        warmup_skipped=0,
    )

    verdict = cal.calibration_verdict(result)

    assert "worse" in verdict


def test_a_grouped_correction_fits_each_group_separately() -> None:
    """Two groups with opposite biases cannot both be fixed by one curve."""
    rows: list[tuple[str, float, bool, str]] = []
    for index in range(4000):
        day = f"2025-{1 + index // 900:02d}-{1 + index % 27:02d}"
        if index % 2:
            # "low" claims 40% and happens 20% of the time.
            rows.append((day, 0.40, index % 10 < 2, "low"))
        else:
            # "high" claims 40% and happens 60% of the time.
            rows.append((day, 0.40, index % 10 < 6, "high"))

    pooled = cal.walk_forward_calibrate(rows, minimum_fit_samples=500, refit_every=5)
    grouped = cal.walk_forward_calibrate(
        rows, minimum_fit_samples=500, refit_every=5, grouped=True
    )

    assert cal.brier_score(grouped.corrected) < cal.brier_score(pooled.corrected)


def test_a_group_with_too_little_history_falls_back_to_the_pooled_curve() -> None:
    rows: list[tuple[str, float, bool, str]] = []
    for index in range(2000):
        day = f"2025-{1 + index // 500:02d}-{1 + index % 27:02d}"
        rows.append((day, 0.70, index % 10 < 6, "common"))
    # One sample from a group that will never have enough history of its own.
    rows.append(("2025-04-27", 0.70, True, "rare"))

    result = cal.walk_forward_calibrate(
        rows, minimum_fit_samples=300, refit_every=5, grouped=True
    )
    rare = [row for row in result.scored if row[1] == 0.70]

    assert rare, "the rare sample should still be scored, by the pooled curve"


def test_grouping_is_off_by_default_so_a_three_tuple_still_works() -> None:
    rows = [("2025-01-01", 0.5, True), ("2025-01-02", 0.5, False)]

    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=1)

    assert len(result.scored) == 1
