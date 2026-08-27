"""The live by-TOI correction: fitted, saved, loaded, applied, and gated."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.models import toi_corrections as tc
from nhl_betting_lab.models.calibration import PlattCalibration


def _grid(count: int = 1200) -> pd.DataFrame:
    rows = []
    for index in range(count):
        low = index % 2 == 0
        rows.append(
            {
                "date": f"2025-01-{1 + index % 28:02d}",
                "market": "shots_on_goal",
                "model_probability": 0.40,
                # Low-TOI overconfident, high-TOI underconfident — the real
                # defect's shape.
                "outcome": (index % 10 < 2) if low else (index % 10 < 6),
                "toi_seconds": 600 if low else 1400,
                "expected_toi_seconds": 600 if low else 1400,
            }
        )
    return pd.DataFrame(rows)


def test_fitting_produces_pooled_and_bucketed_curves() -> None:
    current = tc.fit_current_corrections(_grid(), fitted_at="2026-08-26T00:00:00Z")

    assert "shots_on_goal" in current.pooled
    assert any(m == "shots_on_goal" for m, _ in current.bucketed)


def test_the_correction_pulls_each_bucket_its_own_way() -> None:
    current = tc.fit_current_corrections(_grid(2000), fitted_at="now")

    low = current.apply("shots_on_goal", 600, 0.40)
    high = current.apply("shots_on_goal", 1400, 0.40)

    assert low < 0.40 < high


def test_an_unknown_market_passes_through_uncorrected() -> None:
    current = tc.fit_current_corrections(_grid(), fitted_at="now")

    assert current.apply("hits", 900, 0.37) == pytest.approx(0.37)


def test_a_thin_bucket_falls_back_to_the_pooled_curve() -> None:
    current = tc.CurrentCorrections(
        pooled={"points": PlattCalibration(-0.5, 1.0, fitted_on=5000)},
        bucketed={("points", "under 12 min"): PlattCalibration.identity(fitted_on=3)},
    )

    corrected = current.apply("points", 600, 0.50)

    assert corrected == pytest.approx(
        PlattCalibration(-0.5, 1.0, fitted_on=5000).apply(0.50)
    )


def test_the_curves_round_trip_through_disk(tmp_path: Path) -> None:
    current = tc.fit_current_corrections(_grid(2000), fitted_at="2026-08-26T00:00:00Z")

    tc.save_current_corrections(current, processed_dir=tmp_path)
    loaded = tc.load_current_corrections(processed_dir=tmp_path)

    assert loaded.fitted_at == "2026-08-26T00:00:00Z"
    for probability in (0.2, 0.4, 0.6):
        assert loaded.apply("shots_on_goal", 1400, probability) == pytest.approx(
            current.apply("shots_on_goal", 1400, probability)
        )


def test_a_missing_file_degrades_to_no_correction(tmp_path: Path) -> None:
    """The raw model was the card's behaviour before the experiment; absence
    must degrade to that rather than to a crash or a stale guess."""
    loaded = tc.load_current_corrections(processed_dir=tmp_path)

    assert loaded.apply("shots_on_goal", 1400, 0.42) == pytest.approx(0.42)
    assert "no correction on file" in loaded.describe()


def test_an_unreadable_file_degrades_to_no_correction(tmp_path: Path) -> None:
    (tmp_path / tc.CORRECTIONS_FILENAME).write_text("{broken", encoding="utf-8")

    loaded = tc.load_current_corrections(processed_dir=tmp_path)

    assert loaded.apply("points", 900, 0.30) == pytest.approx(0.30)


def test_the_card_applies_corrections_only_on_the_recorded_verdict(
    tmp_path: Path,
) -> None:
    """The decision is read from disk, not asserted in code, so the card's
    configuration is auditable against the experiment that made it."""
    import sys

    sys.path.insert(0, "tests")
    from test_scripts import load_script

    module = load_script("run_gameday_card.py")

    assert module._read_experiment(tmp_path) == {}

    (tmp_path / "correction_experiment.json").write_text(
        json.dumps({"ships": ["by_toi"]}), encoding="utf-8"
    )
    assert "by_toi" in module._read_experiment(tmp_path)["ships"]

    (tmp_path / "correction_experiment.json").write_text(
        json.dumps({"ships": []}), encoding="utf-8"
    )
    assert module._read_experiment(tmp_path)["ships"] == []
