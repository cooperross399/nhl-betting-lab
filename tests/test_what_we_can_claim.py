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


def test_team_markets_measured_in_their_own_report_are_covered(
    tmp_path: Path,
) -> None:
    """The claims document covers everything or it is not the claims document."""
    _write(
        tmp_path,
        "team_markets_measurement.json",
        {
            "markets": [
                {
                    "market": "moneyline",
                    "bets": 1536,
                    "roi": -0.033,
                    "low": -0.088,
                    "high": 0.022,
                    "includes_zero": True,
                    "survives_correction": False,
                    "looks": 4,
                }
            ]
        },
    )

    report = claims.build_claims_report(output_dir=tmp_path)
    moneyline = next(c for c in report.claims if c.market == "moneyline")

    assert moneyline.measured is True
    assert "1,536 bets" in moneyline.sentence()
    assert "-8.8%" in moneyline.sentence()


def test_the_regulation_three_way_is_named_unmeasurable_with_its_reason(
    tmp_path: Path,
) -> None:
    report = claims.build_claims_report(output_dir=tmp_path)
    three_way = next(
        c for c in report.claims if c.market == "regulation_3_way"
    )

    assert three_way.measured is False
    assert "per-event only" in three_way.sentence()
    assert "accumulates forward" in three_way.sentence()


def test_a_loss_that_survives_the_correction_is_not_called_an_edge(
    tmp_path: Path,
) -> None:
    """This sentence was written for a positive result.

    Nothing reached it with a negative one until `points` lost its
    replication verdict, when the regenerated document described -4.5% over
    5,984 bets as "not the same as an edge that will persist".
    """
    _write(
        tmp_path,
        "player_props_backtest.json",
        {"by_market": {"points": {
            "bets": 5984, "roi": -0.045, "low": -0.070, "high": -0.019,
            "includes_zero": False, "survives_correction": True, "looks": 7,
        }}},
    )
    points = next(
        c for c in claims.build_claims_report(output_dir=tmp_path).claims
        if c.market == "points"
    )

    assert "not the same as a loss that will persist" in points.sentence()
    assert "an edge that will persist" not in points.sentence()


def test_a_prop_market_priced_only_in_another_window_is_measured_from_it(
    tmp_path: Path,
) -> None:
    """`hits` was listed as "no historical prices have been bought for it yet".

    5,021 wagers of it were bought and measured, in the `card` window: the
    two books that quote hits are in a region the `late` purchase never
    asked. The line says which window, because every other prop line does
    not come from that one.
    """
    _write(
        tmp_path,
        "player_props_backtest.json",
        {"phase": "late", "phase_hours": 4.1, "by_market": {}},
    )
    _write(
        tmp_path,
        "player_props_backtest_card.json",
        {"phase": "card", "phase_hours": 9.6, "by_market": {"hits": {
            "bets": 5021, "roi": -0.012, "low": -0.039, "high": 0.015,
            "includes_zero": True, "survives_correction": False, "looks": 7,
        }}},
    )
    hits = next(
        c for c in claims.build_claims_report(output_dir=tmp_path).claims
        if c.market == "hits"
    )

    assert hits.measured is True
    assert "5,021 bets" in hits.sentence()
    assert (
        "measured only in the `card` window, 9.6 hours before face-off."
        in hits.sentence()
    )
    assert "no historical prices" not in hits.sentence()


def test_a_market_the_contract_window_measured_is_never_replaced(
    tmp_path: Path,
) -> None:
    """Taking whichever window looks better per market is a look-back max."""
    _write(
        tmp_path,
        "player_props_backtest.json",
        {"phase": "late", "by_market": {"shots_on_goal": {
            "bets": 9043, "roi": 0.014, "low": -0.008, "high": 0.035,
            "includes_zero": True, "survives_correction": False, "looks": 6,
        }}},
    )
    _write(
        tmp_path,
        "player_props_backtest_card.json",
        {"phase": "card", "by_market": {"shots_on_goal": {
            "bets": 9500, "roi": 0.080, "low": 0.050, "high": 0.110,
            "includes_zero": False, "survives_correction": True, "looks": 7,
        }}},
    )
    shots = next(
        c for c in claims.build_claims_report(output_dir=tmp_path).claims
        if c.market == "shots_on_goal"
    )

    assert "9,043 bets" in shots.sentence()
    assert "+1.4%" in shots.sentence()
    assert "window" not in shots.sentence()


def test_the_document_names_the_windows_its_figures_come_from(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "player_props_backtest.json",
        {
            "phase": "late",
            "phase_hours": 4.07,
            "overall": {"bets": 25009, "roi": -0.002, "includes_zero": True},
            "by_market": {"points": {
                "bets": 5984, "roi": -0.045, "low": -0.070, "high": -0.019,
                "includes_zero": False, "survives_correction": True, "looks": 7,
            }},
        },
    )
    _write(
        tmp_path,
        "team_markets_measurement.json",
        {"phase": "late", "phase_hours": 1.5, "markets": [{
            "market": "moneyline", "bets": 954, "roi": -0.066, "low": -0.136,
            "high": 0.004, "includes_zero": True,
        }]},
    )
    rendered = claims.render_claims(claims.build_claims_report(output_dir=tmp_path))

    assert (
        "Unless a line names another window, prop figures come from the "
        "`late` window, 4.1 hours before face-off, and team figures come from "
        "the `late` window, 1.5 hours before face-off." in rendered
    )
    assert "25,009 bets in the `late` window, 4.1 hours before face-off." in rendered


def test_a_zero_bet_entry_in_the_contract_window_does_not_block_the_other(
    tmp_path: Path,
) -> None:
    """Listed with nothing measured is the same as not measured.

    Otherwise a market that happens to appear with zero bets would be
    reported as never bought, which is the sentence this replaced.
    """
    _write(
        tmp_path,
        "player_props_backtest.json",
        {"phase": "late", "by_market": {"hits": {"bets": 0}}},
    )
    _write(
        tmp_path,
        "player_props_backtest_card.json",
        {"phase": "card", "by_market": {"hits": {
            "bets": 5021, "roi": -0.012, "low": -0.039, "high": 0.015,
            "includes_zero": True, "survives_correction": False, "looks": 7,
        }}},
    )
    hits = next(
        c for c in claims.build_claims_report(output_dir=tmp_path).claims
        if c.market == "hits"
    )

    assert hits.measured is True
    assert hits.bets == 5021
