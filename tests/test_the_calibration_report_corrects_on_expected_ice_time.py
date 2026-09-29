"""The calibration report's ice-time correction is indexed on what a card knows.

"Conditioned on what, known when?" (`CLAUDE.md`). A card is priced before the
game, so the only ice time it can know is the EXPECTED one. Actual ice time is
partly an outcome — overtime, a blowout, an injury, a pulled goalie — and a
correction indexed on it "won" +162.8u that it lost once indexed on expected
ice time (`docs/why_the_toi_correction_does_not_ship.md`).

`correction_timeline`, `fit_current_corrections` and `expand_to_lines` were
changed to refuse actual ice time. `measure_market` was not: it bucketed the
per-ice-time walk-forward correction on `toi_seconds` even when
`expected_toi_seconds` was right there, and the committed
`props_calibration.md` read "the ice-time-conditional correction beats the
pooled curve" for every market — a hindsight comparison presented as a
finding. These pin the fix:

* the grouped correction is fitted, scored and tabled on expected ice time;
* samples without that column get no grouped correction at all, rather than
  a silent fall back to the actual;
* the actual-ice-time table survives only as a diagnostic, labelled as
  hindsight, with no verdict attached.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.reports import props_calibration as report_module

MINIMUM = 300
#: The outcome rate per ice time, in minutes: a model that claims 13% for
#: everyone, and a truth that depends on workload.
RATE_BY_MINUTES = {8: 0.05, 14: 0.11, 18: 0.17, 23: 0.21}


def _samples(*, driven_by: str, with_expected: bool = True) -> pd.DataFrame:
    """Assists samples whose outcome depends on one ice time and not the other.

    `driven_by="actual"`: every player is expected to play 17 minutes, and
    what happened depends only on the minutes they actually played — the
    hindsight the defect exploited. `driven_by="expected"`: every player
    actually played 17 minutes, and the outcome depends on the minutes they
    were expected to play — information a card really has.
    """
    rng = random.Random(20260929)
    rows: list[dict[str, object]] = []
    day0 = pd.Timestamp("2024-10-01")
    game_id = 0
    for day in range(60):
        for game in range(4):
            game_id += 1
            for player in range(20):
                minutes = rng.choice(sorted(RATE_BY_MINUTES))
                varied, fixed = minutes * 60, 17 * 60
                actual, expected = (
                    (varied, fixed) if driven_by == "actual" else (fixed, varied)
                )
                row: dict[str, object] = {
                    "date": (day0 + pd.Timedelta(days=day)).date().isoformat(),
                    "game_id": game_id,
                    "player_id": game * 100 + player,
                    "market": "assists",
                    "line": 0.5,
                    "model_probability": 0.13,
                    "outcome": rng.random() < RATE_BY_MINUTES[minutes],
                    "toi_seconds": actual,
                }
                if with_expected:
                    row["expected_toi_seconds"] = float(expected)
                rows.append(row)
    return pd.DataFrame(rows)


def _assists(frame: pd.DataFrame) -> report_module.MarketCalibration:
    report = report_module.build_calibration_report(
        frame, minimum_fit_samples=MINIMUM
    )
    (item,) = report.markets
    return item


def test_hindsight_ice_time_cannot_make_the_grouped_correction_win() -> None:
    """Everyone expected 17 minutes: one bucket, so no gain over pooled."""
    item = _assists(_samples(driven_by="actual"))

    assert [row["bucket"] for row in item.grouped_volume_rows] == ["16-20 min"]
    assert item.grouped_brier == pytest.approx(item.corrected_brier, abs=1e-12)
    assert item.grouped_beats_pooled is False


def test_expected_ice_time_is_what_the_grouped_correction_is_fitted_on() -> None:
    """The converse: a real, card-knowable split is found and can win."""
    item = _assists(_samples(driven_by="expected"))

    assert {row["bucket"] for row in item.grouped_volume_rows} == {
        "under 12 min", "12-16 min", "16-20 min", "20 min and up",
    }
    assert item.grouped_beats_pooled is True


def test_the_actual_ice_time_table_is_kept_as_a_diagnostic() -> None:
    """Where the defect lives is still worth seeing — on the actual."""
    item = _assists(_samples(driven_by="actual"))

    assert {row["bucket"] for row in item.volume_rows} == {
        "under 12 min", "12-16 min", "16-20 min", "20 min and up",
    }


def test_samples_without_expected_ice_time_get_no_grouped_correction() -> None:
    """No fall back to the actual: the variant is not measured at all."""
    item = _assists(_samples(driven_by="actual", with_expected=False))

    assert item.grouped_brier is None
    assert item.grouped_volume_rows == []
    assert item.grouped_beats_pooled is False
    # The pooled measurement and its diagnostic table are untouched.
    assert item.corrected_brier is not None
    assert item.volume_rows

    rendered = report_module.render_calibration(
        report_module.build_calibration_report(
            _samples(driven_by="actual", with_expected=False),
            minimum_fit_samples=MINIMUM,
        )
    )
    assert "beats the pooled curve" not in rendered
    assert "not measured" in rendered
    assert "expected_toi_seconds" in rendered


def test_the_rendered_report_labels_the_actual_table_hindsight_with_no_verdict() -> None:
    report = report_module.build_calibration_report(
        _samples(driven_by="actual"), minimum_fit_samples=MINIMUM
    )
    rendered = report_module.render_calibration(report)

    diagnostic = rendered.split("### By ice time", 1)[1].split("###", 1)[0]
    assert "actual ice time (hindsight)" in diagnostic
    assert "beats" not in diagnostic
    grouped = rendered.split("### Corrected per expected ice-time bucket", 1)[1]
    grouped = grouped.split("##", 1)[0]
    assert "does **not** beat the pooled curve" in grouped
    assert "| Expected ice time |" in grouped
    assert "correction beats the pooled curve" not in rendered


def test_the_json_names_the_ice_time_the_correction_was_indexed_on(
    tmp_path: Path,
) -> None:
    for with_expected, index in (
        (True, "expected_toi_seconds"),
        (False, None),
    ):
        report = report_module.build_calibration_report(
            _samples(driven_by="actual", with_expected=with_expected),
            minimum_fit_samples=MINIMUM,
        )
        report_module.save_calibration_report(report, output_dir=tmp_path)
        payload = json.loads(
            (tmp_path / report_module.CALIBRATION_JSON_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        (market,) = payload["markets"]
        assert market["grouped_index"] == index
