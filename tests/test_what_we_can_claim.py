from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhl_betting_lab.reports import what_we_can_claim as claims


def _write(directory: Path, name: str, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def test_with_no_measurements_it_says_so_plainly(tmp_path: Path) -> None:
    report = claims.build_claims_report(output_dir=tmp_path)

    assert "nothing has been measured against real prices yet" in report.headline()
    assert report.anything_demonstrated is False


def test_a_calibration_only_market_is_listed_as_not_measured(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "props_calibration.json",
        {"markets": [{"market": "shots_on_goal", "samples": 493384}]},
    )

    report = claims.build_claims_report(output_dir=tmp_path)
    shots = next(c for c in report.claims if c.market == "shots_on_goal")

    assert shots.measured is False
    assert "can never rule it in" in shots.sentence()
    assert "not evidence of an edge" in shots.sentence()


def test_a_calibration_number_is_never_offered_as_a_price_result(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "props_calibration.json",
        {"markets": [{"market": "points", "samples": 370038}]},
    )

    rendered = claims.render_claims(claims.build_claims_report(output_dir=tmp_path))

    assert "Not measured against real prices" in rendered
    assert "not** a market judged to have no value" in rendered


def test_an_interval_that_includes_zero_uses_the_exact_words(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "shots_on_goal": {
                    "bets": 240,
                    "roi": 0.07,
                    "low": -0.05,
                    "high": 0.19,
                    "includes_zero": True,
                    "survives_correction": False,
                }
            },
            "overall": {"bets": 240, "roi": 0.07, "includes_zero": True},
        },
    )

    report = claims.build_claims_report(output_dir=tmp_path)
    shots = next(c for c in report.claims if c.market == "shots_on_goal")

    assert claims.NO_DEMONSTRATED_EDGE.capitalize() in shots.sentence()
    assert "240" in shots.sentence()


def test_a_significant_result_is_still_hedged_about_persistence(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "points": {
                    "bets": 1800,
                    "roi": 0.09,
                    "low": 0.02,
                    "high": 0.16,
                    "includes_zero": False,
                    "survives_correction": True,
                    "looks": 7,
                }
            }
        },
    )

    report = claims.build_claims_report(output_dir=tmp_path)
    points = next(c for c in report.claims if c.market == "points")

    assert "not the same as an edge that will persist" in points.sentence()
    assert "means nothing until it replicates" in points.sentence()
    # Surviving the correction is not enough on its own: a result counts only
    # once it has also held on a window it was not found on.
    assert report.anything_demonstrated is False


def test_every_sentence_carries_its_sample_size(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "goals": {
                    "bets": 412,
                    "roi": -0.03,
                    "low": -0.12,
                    "high": 0.06,
                    "includes_zero": True,
                    "survives_correction": False,
                }
            }
        },
    )

    report = claims.build_claims_report(output_dir=tmp_path)
    goals = next(c for c in report.claims if c.market == "goals")

    assert "412 bets" in goals.sentence()


def test_the_reason_sentence_is_punctuated(tmp_path: Path) -> None:
    """It once read "...bought for it yet It has been calibration-checked"."""
    _write(
        tmp_path,
        "props_calibration.json",
        {"markets": [{"market": "assists", "samples": 1000}]},
    )

    sentence = next(
        c
        for c in claims.build_claims_report(output_dir=tmp_path).claims
        if c.market == "assists"
    ).sentence()

    assert "yet. It has been" in sentence


def test_a_forbidden_phrase_refuses_to_be_written(tmp_path: Path) -> None:
    """A generated summary that reaches for one of these has stopped
    reporting and started selling."""
    report = claims.build_claims_report(output_dir=tmp_path)
    report.notes.append("This is a guaranteed winner.")

    with pytest.raises(ValueError, match="guaranteed"):
        claims.save_claims(report, output_dir=tmp_path)


def test_saving_writes_the_contract_path(tmp_path: Path) -> None:
    report = claims.build_claims_report(output_dir=tmp_path)

    path = claims.save_claims(report, output_dir=tmp_path)

    assert Path(path).name == "what_we_can_claim.md"


def test_the_document_reports_what_the_card_may_actually_use(
    tmp_path: Path,
) -> None:
    report = claims.build_claims_report(
        output_dir=tmp_path,
        policy_status="Nothing allowlisted",
        allowlisted_markets=(),
    )

    rendered = claims.render_claims(report)

    assert "Nothing allowlisted" in rendered
    assert "Allowlisted markets: **none**" in rendered


def test_a_malformed_measurement_file_does_not_crash_the_report(
    tmp_path: Path,
) -> None:
    (tmp_path / "props_calibration.json").write_text("{broken", encoding="utf-8")

    report = claims.build_claims_report(output_dir=tmp_path)

    assert report.claims
    assert claims.render_claims(report)


def test_the_detection_table_is_included_so_sample_size_is_concrete(
    tmp_path: Path,
) -> None:
    rendered = claims.render_claims(claims.build_claims_report(output_dir=tmp_path))

    assert "1,537" in rendered
    assert "props are the only part of the system" in rendered


def test_a_replication_verdict_outranks_the_single_window_number(
    tmp_path: Path,
) -> None:
    """A market that survived on one window and was contradicted on another is
    described by the second fact, not the first."""
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "shots_on_goal": {
                    "bets": 683,
                    "roi": 0.033,
                    "low": -0.041,
                    "high": 0.107,
                    "includes_zero": True,
                    "survives_correction": False,
                }
            }
        },
    )
    _write(
        tmp_path,
        "replication.json",
        {
            "test_label": "2024-25",
            "markets": [{"market": "shots_on_goal", "state": "contradicted"}],
        },
    )

    report = claims.build_claims_report(output_dir=tmp_path)
    shots = next(c for c in report.claims if c.market == "shots_on_goal")

    assert "contradicted" in shots.sentence()
    assert claims.NO_DEMONSTRATED_EDGE in shots.sentence()


def test_a_replicated_result_is_the_only_thing_that_counts_as_demonstrated(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "shots_on_goal": {
                    "bets": 683,
                    "roi": 0.12,
                    "low": 0.04,
                    "high": 0.20,
                    "includes_zero": False,
                    "survives_correction": True,
                    "looks": 7,
                }
            }
        },
    )
    _write(
        tmp_path,
        "replication.json",
        {
            "test_label": "2024-25",
            "markets": [{"market": "shots_on_goal", "state": "replicated"}],
        },
    )

    report = claims.build_claims_report(output_dir=tmp_path)
    shots = next(c for c in report.claims if c.market == "shots_on_goal")

    assert shots.replication.startswith("**Replicated")
    assert report.anything_demonstrated is True
    assert "survived the correction and then replicated" in report.headline()


def test_an_untestable_replication_does_not_change_the_sentence(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "by_market": {
                "points": {
                    "bets": 288,
                    "roi": -0.069,
                    "low": -0.182,
                    "high": 0.043,
                    "includes_zero": True,
                    "survives_correction": False,
                }
            }
        },
    )
    _write(
        tmp_path,
        "replication.json",
        {
            "test_label": "2024-25",
            "markets": [{"market": "points", "state": "untestable"}],
        },
    )

    report = claims.build_claims_report(output_dir=tmp_path)
    points = next(c for c in report.claims if c.market == "points")

    assert "untestable" not in points.sentence()
    assert claims.NO_DEMONSTRATED_EDGE.capitalize() in points.sentence()
