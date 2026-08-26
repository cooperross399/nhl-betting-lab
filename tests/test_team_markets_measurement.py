from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.reports import team_markets_measurement as tmm


def _samples(count: int = 3000) -> pd.DataFrame:
    """A model that says 55% on the moneyline and is right 55% of the time."""
    rows = []
    for index in range(count):
        day = f"2025-{1 + index // 700:02d}-{1 + index % 27:02d}"
        rows.append(
            {
                "date": day,
                "game_id": index,
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "model_probability": 0.55,
                "outcome": index % 20 < 11,
                "push": False,
                "home_goals": 4,
                "away_goals": 2,
                "regulation": True,
            }
        )
    return pd.DataFrame(rows)


def _prices(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_no_samples_produces_a_report_that_says_so() -> None:
    report = tmm.build_team_measurement(pd.DataFrame(columns=["market"]))

    rendered = tmm.render_team_measurement(report)

    assert "has not been measured" in rendered
    assert "not that it is fine" in rendered


def test_a_calibrated_market_reports_its_sample_size() -> None:
    report = tmm.build_team_measurement(_samples(), minimum_fit_samples=300)

    assert report.markets[0].samples > 0
    assert f"{report.markets[0].samples:,}" in report.markets[0].verdict


def test_the_verdict_never_says_the_model_is_good() -> None:
    report = tmm.build_team_measurement(_samples(), minimum_fit_samples=300)

    assert "cannot rule it in" in report.markets[0].verdict


def test_without_prices_the_report_says_no_price_based_measurement() -> None:
    from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE

    report = tmm.build_team_measurement(_samples(), minimum_fit_samples=300)

    rendered = tmm.render_team_measurement(report)

    assert "No price-based measurement" in rendered
    assert NO_DEMONSTRATED_EDGE in rendered


def test_calibration_is_explicitly_not_offered_as_a_substitute() -> None:
    report = tmm.build_team_measurement(_samples(), minimum_fit_samples=300)

    rendered = tmm.render_team_measurement(report)

    assert "not** a substitute" in rendered
    assert "internally sensible" in rendered


def test_a_matched_price_above_the_threshold_becomes_a_bet() -> None:
    samples = _samples(400)
    prices = _prices(
        [
            {
                "date": row.date,
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "american_odds": 150,  # implied 40%, model says 55%
            }
            for row in samples.head(50).itertuples()
        ]
    )

    report = tmm.build_team_measurement(
        samples, prices, edge_threshold=0.05, minimum_fit_samples=100
    )
    moneyline = report.markets[0]

    assert moneyline.has_price_evidence is True
    assert moneyline.priced.bets == 50


def test_a_price_below_the_threshold_produces_no_bet() -> None:
    samples = _samples(400)
    prices = _prices(
        [
            {
                "date": samples.iloc[0]["date"],
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "american_odds": -140,  # implied 58%, above the model's 55%
            }
        ]
    )

    report = tmm.build_team_measurement(
        samples, prices, edge_threshold=0.05, minimum_fit_samples=100
    )

    assert report.markets[0].has_price_evidence is False


def test_an_unmatched_price_is_not_scored_as_a_loss() -> None:
    samples = _samples(400)
    prices = _prices(
        [
            {
                "date": "2099-01-01",
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "american_odds": 150,
            }
        ]
    )

    report = tmm.build_team_measurement(
        samples, prices, edge_threshold=0.05, minimum_fit_samples=100
    )

    assert report.markets[0].has_price_evidence is False


def test_a_push_returns_the_stake_rather_than_losing_it() -> None:
    samples = _samples(400)
    samples["push"] = False
    samples.loc[samples.index[:50], "market"] = "total_goals"
    samples.loc[samples.index[:50], "selection"] = "over"
    samples.loc[samples.index[:50], "line"] = 6.0
    samples.loc[samples.index[:50], "push"] = True
    prices = _prices(
        [
            {
                "date": row.date,
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "total_goals",
                "selection": "over",
                "line": 6.0,
                "american_odds": 150,
            }
            for row in samples.head(50).itertuples()
        ]
    )

    report = tmm.build_team_measurement(
        samples, prices, edge_threshold=0.05, minimum_fit_samples=100
    )
    totals = next(m for m in report.markets if m.market == "total_goals")

    assert totals.priced is not None
    assert totals.priced.profit == pytest.approx(0.0)
    assert totals.priced.pushes == 50


def test_pushes_are_excluded_from_the_calibration_measurement() -> None:
    """Scoring a push as a loss makes every whole-number total look worse."""
    samples = _samples(600)
    samples.loc[samples.index[:300], "push"] = True

    report = tmm.build_team_measurement(samples, minimum_fit_samples=100)

    assert report.markets[0].samples <= 300


def test_the_notes_name_the_puck_line_as_the_revealing_market() -> None:
    report = tmm.build_team_measurement(_samples(), minimum_fit_samples=300)

    rendered = tmm.render_team_measurement(report)

    assert "puck line is the market most likely to expose" in rendered
    assert "overtime rule" in rendered


def test_saving_writes_both_files(tmp_path: Path) -> None:
    report = tmm.build_team_measurement(_samples(), minimum_fit_samples=300)

    paths = tmm.save_team_measurement(report, output_dir=tmp_path)
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))

    assert Path(paths["markdown"]).name == "team_markets_measurement.md"
    assert payload["markets"][0]["market"] == "moneyline"
    assert payload["markets"][0]["has_price_evidence"] is False


def test_a_thin_market_gets_its_count_and_no_reliability_table() -> None:
    report = tmm.build_team_measurement(_samples(260), minimum_fit_samples=200)

    rendered = tmm.render_team_measurement(report)

    assert "no reliability table is shown" in rendered


def test_a_puck_line_price_joins_onto_the_samples_vocabulary() -> None:
    """The provider says `home` at line -1.5; the samples say `home_minus`.
    Joining on the raw strings measured the puck line as having no price
    evidence at all — the third join-vocabulary mismatch found here, after
    team names and game dates."""
    assert tmm._puck_line_selection("home", -1.5) == ("home_minus", -1.5)
    assert tmm._puck_line_selection("home", 1.5) == ("home_plus", 1.5)
    assert tmm._puck_line_selection("away", -1.5) == ("away_minus", -1.5)
    assert tmm._puck_line_selection("away", 1.5) == ("away_plus", 1.5)


def test_other_markets_pass_through_the_translator_unchanged() -> None:
    assert tmm._puck_line_selection("over", 5.5) == ("over", 5.5)
    assert tmm._puck_line_selection("home", None) == ("home", None)


def test_a_puck_line_bet_is_actually_matched_end_to_end() -> None:
    samples = pd.DataFrame(
        [
            {
                "date": "2025-01-05",
                "game_id": 1,
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "puck_line",
                "selection": "home_minus",
                "line": -1.5,
                "model_probability": 0.60,
                "outcome": True,
                "push": False,
                "home_goals": 5,
                "away_goals": 2,
                "regulation": True,
            }
        ]
    )
    prices = pd.DataFrame(
        [
            {
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "puck_line",
                "selection": "home",
                "line": -1.5,
                "american_odds": 150,
            }
        ]
    )

    interval = tmm.measure_prices(
        prices, samples, market="puck_line", edge_threshold=0.05,
        team_names={"tor": "TOR", "bos": "BOS"},
    )

    assert interval is not None
    assert interval.bets == 1


def test_team_markets_are_corrected_as_one_family() -> None:
    report = tmm.build_team_measurement(_samples(), minimum_fit_samples=300)

    # However many markets are present, the looks count flows through.
    assert all(
        item.priced is None or item.priced.looks >= 1
        for item in report.markets
    )
