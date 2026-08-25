from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.reports import props_calibration as report_module


def _samples(count: int = 900, market: str = "shots_on_goal") -> pd.DataFrame:
    """A model that runs hot on low minutes and cold on high ones — the exact
    defect the real measurement found."""
    rows = []
    for index in range(count):
        day = f"2025-{1 + index // 350:02d}-{1 + index % 27:02d}"
        low_minutes = index % 2 == 0
        probability = 0.40
        # Low-minutes players: claims 40%, happens 20%. High: claims 40%,
        # happens 60%. One monotone curve cannot fix both.
        happened = (index % 10 < 2) if low_minutes else (index % 10 < 6)
        rows.append(
            {
                "date": day,
                "game_id": index,
                "player_id": index % 50,
                "market": market,
                "line": 2.5,
                "model_probability": probability,
                "outcome": happened,
                "actual": 3.0 if happened else 1.0,
                "toi_seconds": 600 if low_minutes else 1400,
            }
        )
    return pd.DataFrame(rows)


def test_no_samples_produces_a_report_that_says_so_plainly() -> None:
    report = report_module.build_calibration_report(pd.DataFrame(columns=["market"]))

    rendered = report_module.render_calibration(report)

    assert "has not been measured" in rendered
    assert "not that it is uncalibrated" in rendered


def test_the_report_never_says_the_model_beats_a_price() -> None:
    report = report_module.build_calibration_report(_samples())

    rendered = report_module.render_calibration(report)

    assert "cannot rule one in" in rendered
    assert "player_props_backtest.md" in rendered


def test_every_reliability_row_carries_its_count() -> None:
    report = report_module.build_calibration_report(_samples())

    for item in report.markets:
        for row in item.raw_table:
            assert row.count > 0


def test_the_ice_time_split_is_reported() -> None:
    report = report_module.build_calibration_report(_samples())

    assert report.markets[0].volume_rows
    assert {row["bucket"] for row in report.markets[0].volume_rows} <= {
        label for label, _, _ in report_module.TOI_BUCKETS
    }


def test_the_conditional_correction_beats_the_pooled_one_on_a_split_defect() -> None:
    """Two buckets needing opposite corrections is what the real data shows."""
    report = report_module.build_calibration_report(
        _samples(1400), minimum_fit_samples=200
    )

    assert report.markets[0].grouped_beats_pooled is True


def test_both_corrections_are_reported_whether_or_not_the_variant_wins() -> None:
    """A variant shown only when it wins is a selection, not a measurement."""
    report = report_module.build_calibration_report(
        _samples(1400), minimum_fit_samples=200
    )

    rendered = report_module.render_calibration(report)

    assert "Brier pooled" in rendered
    assert "Brier by ice time" in rendered
    assert "whether or not the conditional one wins" in rendered


def test_the_report_points_at_the_mechanism_document() -> None:
    report = report_module.build_calibration_report(
        _samples(1400), minimum_fit_samples=200
    )

    rendered = report_module.render_calibration(report)

    assert "why_ice_time_gets_its_own_correction" in rendered


def test_a_thin_bucket_is_flagged_rather_than_read_as_a_finding() -> None:
    rows = _samples(900)
    rows.loc[rows.index[:20], "toi_seconds"] = 1800  # a sparse third bucket

    report = report_module.build_calibration_report(rows, minimum_fit_samples=200)
    rendered = report_module.render_calibration(report)

    assert "⚠" in rendered
    assert "read as noise, not as a finding" in rendered


def test_a_market_below_the_sample_floor_shows_no_reliability_table() -> None:
    rows = _samples(210)

    report = report_module.build_calibration_report(rows, minimum_fit_samples=200)
    rendered = report_module.render_calibration(report)

    assert "too few for a reliability table" in rendered


def test_goalies_are_bucketed_on_their_own_scale() -> None:
    """A 41-minute start was once labelled "under 12 min"."""
    assert report_module._bucket_for(2500, is_goalie=True).startswith("goalie")
    assert report_module._bucket_for(3600, is_goalie=True) == (
        "goalie, full game (50 min+)"
    )
    assert report_module._bucket_for(600, is_goalie=False) == "under 12 min"


def test_a_skater_never_lands_in_a_goalie_bucket() -> None:
    for seconds in (0, 600, 1200, 1800, 3600):
        assert not report_module._bucket_for(seconds, is_goalie=False).startswith(
            "goalie"
        )


def test_saving_writes_both_outputs_at_the_contract_path(tmp_path: Path) -> None:
    report = report_module.build_calibration_report(_samples())

    paths = report_module.save_calibration_report(report, output_dir=tmp_path)

    assert Path(paths["markdown"]).name == "props_calibration.md"
    assert Path(paths["json"]).is_file()


def test_the_json_carries_both_corrections_for_every_market(tmp_path: Path) -> None:
    report = report_module.build_calibration_report(
        _samples(1400), minimum_fit_samples=200
    )

    paths = report_module.save_calibration_report(report, output_dir=tmp_path)
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))

    for item in payload["markets"]:
        assert "corrected_brier" in item
        assert "grouped_brier" in item
        assert "grouped_beats_pooled" in item


def test_the_notes_state_the_goalie_starter_limitation() -> None:
    report = report_module.build_calibration_report(_samples())

    rendered = report_module.render_calibration(report)

    assert "goalie_props_need_a_confirmed_starter" in rendered
    assert "no way to know who starts" in rendered
