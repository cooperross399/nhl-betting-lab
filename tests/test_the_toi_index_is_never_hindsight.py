"""The by-TOI correction may be indexed on expected ice time, never actual.

Actual ice time is partly an outcome (overtime, blowouts, injuries, a pulled
goalie). Indexed on it, the correction "won" +162.8u, and it lost once indexed
on what a card can know (docs/why_the_toi_correction_does_not_ship.md). Two
code paths still fell back to the hindsight index. Neither fired on the real
samples (all 749,115 carry a non-zero expected figure), and both would have
fired in silence:

* `build_timeline` indexed the fit on `toi_seconds` whenever the samples
  lacked `expected_toi_seconds`. A samples file from before that column
  existed would re-run the hindsight experiment and could ship it.
* `run_backtest` applied the correction on `expected or actual`, so any
  sample whose expected ice time was 0 was corrected on its actual ice time,
  on an index the fit never used.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.backtest.correction_timeline import build_timeline
from nhl_betting_lab.reports import player_props_backtest as bt


def _grid(**extra) -> pd.DataFrame:
    rows = [
        {"date": f"2025-01-{day:02d}", "market": "shots_on_goal",
         "model_probability": 0.55, "outcome": day % 2 == 0,
         "toi_seconds": 1500, **extra}
        for day in range(1, 29)
    ]
    return pd.DataFrame(rows)


def test_the_fit_refuses_samples_without_expected_ice_time():
    with pytest.raises(ValueError, match="expected_toi_seconds"):
        build_timeline(_grid())


def test_the_fit_accepts_samples_that_carry_it():
    build_timeline(_grid(expected_toi_seconds=1100.0))


def _samples(**extra) -> pd.DataFrame:
    return pd.DataFrame([{
        "date": "2025-01-05", "game_id": 1, "player_id": 1,
        "market": "shots_on_goal", "player": "Auston Matthews",
        "mean": 4.6, "dispersion_r": float("nan"), "actual": 5.0,
        "toi_seconds": 1500, **extra,
    }])


PRICES = pd.DataFrame([{
    "date": "2025-01-05", "commence_time": "2025-01-06T00:10:00Z",
    "market": "shots_on_goal", "player": "Auston Matthews",
    "selection": "over", "line": 3.5, "american_odds": 110, "book": "DraftKings",
}])


def _indexes_seen(samples: pd.DataFrame) -> list[float]:
    seen: list[float] = []

    def correct(market, day, toi, p):
        seen.append(toi)
        return p

    bt.run_backtest(PRICES, samples, edge_threshold=0.0, correct=correct, phase="")
    return seen


@pytest.mark.parametrize("expected", [0.0, float("nan")])
def test_an_unknown_expected_ice_time_is_never_replaced_by_the_actual(expected):
    seen = _indexes_seen(_samples(expected_toi_seconds=expected))
    assert seen, "the correction was never applied, so this proves nothing"
    assert 1500 not in seen, "actual ice time reached the correction"
    assert seen == [0.0]


def test_a_known_expected_ice_time_is_what_the_correction_sees():
    assert _indexes_seen(_samples(expected_toi_seconds=1100.0)) == [1100.0]


def test_a_correction_without_the_expected_column_is_refused():
    with pytest.raises(ValueError, match="expected_toi_seconds"):
        _indexes_seen(_samples())


def test_a_backtest_with_no_correction_needs_no_ice_time_at_all():
    """The committed backtests run without one and must not change."""
    report = bt.run_backtest(PRICES, _samples(), edge_threshold=0.0, phase="")
    assert len(report.bets) == 1


def test_expanding_the_samples_never_invents_expected_ice_time():
    """`expand_to_lines` filled the missing column with ACTUAL ice time, which
    satisfied the fit's check for the column with hindsight."""
    from nhl_betting_lab.reports.props_calibration import expand_to_lines

    grid = expand_to_lines(_samples())
    assert not grid.empty
    assert "expected_toi_seconds" not in grid.columns
    with pytest.raises(ValueError, match="expected_toi_seconds"):
        build_timeline(grid)

    carried = expand_to_lines(_samples(expected_toi_seconds=1100.0))
    assert set(carried["expected_toi_seconds"]) == {1100.0}


def test_the_live_curves_are_never_bucketed_on_actual_ice_time():
    from nhl_betting_lab.models.toi_corrections import fit_current_corrections

    without = fit_current_corrections(_grid(), fitted_at="t", minimum_fit_samples=5)
    assert without.pooled, "the pooled curves need no ice time and still fit"
    assert without.bucketed == {}, "bucketed on actual ice time"

    carrying = fit_current_corrections(
        _grid(expected_toi_seconds=1100.0), fitted_at="t", minimum_fit_samples=5
    )
    assert carrying.bucketed


def test_a_cached_sample_file_without_expected_ice_time_is_not_reused():
    import importlib.util
    import sys
    from nhl_betting_lab.backtest import samples_are_current
    from nhl_betting_lab.config import PROJECT_ROOT

    path = PROJECT_ROOT / "scripts" / "run_props_calibration.py"
    spec = importlib.util.spec_from_file_location("_script_run_props_calibration", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    cached = _samples(dispersion_r=float("nan"))
    markets = ("shots_on_goal",)  # the one market this cache holds
    stale, why = samples_are_current(
        cached, known_markets=markets,
        required_columns=module.REUSABLE_SAMPLE_COLUMNS,
    )
    assert stale is False
    assert "expected_toi_seconds" in why
    fresh, reason = samples_are_current(
        cached.assign(expected_toi_seconds=1100.0), known_markets=markets,
        required_columns=module.REUSABLE_SAMPLE_COLUMNS,
    )
    assert fresh is True, reason
