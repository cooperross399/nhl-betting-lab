from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.reports import provider_shadow
from nhl_betting_lab.staging_provider_policy import load_policy


NOW = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-10-08",
                "home_team": "TOR",
                "away_team": "BOS",
                "market": market,
                "selection": "over",
                "book": "DraftKings",
                "line": 3.5,
                "american_odds": -110,
            }
            for market in ("moneyline", "shots_on_goal", "points")
        ]
    )


def _summary(tmp_path: Path):
    return provider_shadow.build_shadow_summary(
        _prices(),
        policy=load_policy(),
        provider_name="the_odds_api",
        events_seen=1,
        events_priced=1,
        credits_spent=9,
        quota_remaining="18500",
        staging_files=[tmp_path / "odds_api_prices_staging.csv"],
        now=NOW,
    )


def test_a_shadow_run_against_the_shipped_policy_makes_nothing_eligible(
    tmp_path: Path,
) -> None:
    summary, eligibility, _ = _summary(tmp_path)

    assert summary.eligible_markets == ()
    assert eligibility.eligible_markets == ()
    assert summary.policy_status == "Nothing allowlisted"


def test_the_summary_asserts_what_the_run_did_not_do(tmp_path: Path) -> None:
    summary, _, _ = _summary(tmp_path)

    assert summary.safety == {
        "odds_fabricated": False,
        "bets_placed": False,
        "staging_promoted": False,
        "policy_edited": False,
        "provider_allowlisted": False,
        "credential_written": False,
    }


def test_the_report_says_the_card_cannot_read_staging(tmp_path: Path) -> None:
    summary, eligibility, discovery = _summary(tmp_path)

    rendered = provider_shadow.render_shadow(summary, eligibility, discovery)

    assert "The card cannot read those files" in rendered
    assert "allowlists a provider or a market" in rendered


def test_the_report_states_the_credits_spent(tmp_path: Path) -> None:
    summary, eligibility, discovery = _summary(tmp_path)

    rendered = provider_shadow.render_shadow(summary, eligibility, discovery)

    assert "Credits spent: **9**" in rendered
    assert "18500 remaining" in rendered


def test_every_excluded_market_carries_a_reason(tmp_path: Path) -> None:
    summary, _, _ = _summary(tmp_path)

    assert set(summary.excluded_markets) >= {"moneyline", "shots_on_goal", "points"}
    assert all(summary.exclusion_reasons[market] for market in summary.excluded_markets)


def test_the_report_repeats_that_exclusion_is_not_a_no_value_call(
    tmp_path: Path,
) -> None:
    summary, eligibility, discovery = _summary(tmp_path)

    rendered = provider_shadow.render_shadow(summary, eligibility, discovery)

    assert "not** a pass, an avoid, or a" in rendered
    assert "no price was invented" in rendered


def test_the_next_step_is_a_human_decision_not_an_automatic_one(
    tmp_path: Path,
) -> None:
    summary, eligibility, discovery = _summary(tmp_path)

    rendered = provider_shadow.render_shadow(summary, eligibility, discovery)

    assert "Nothing, automatically" in rendered
    assert "Claude prepares the evidence and stops" in rendered


def test_saving_writes_all_three_reports(tmp_path: Path) -> None:
    summary, eligibility, discovery = _summary(tmp_path)

    paths = provider_shadow.save_shadow_reports(
        summary, eligibility, discovery, output_dir=tmp_path / "out"
    )

    for key in ("json", "markdown", "discovery"):
        assert Path(paths[key]).is_file()


def test_the_json_report_records_the_no_value_flag_per_market(
    tmp_path: Path,
) -> None:
    """So a renderer can ask rather than assume."""
    summary, eligibility, discovery = _summary(tmp_path)
    paths = provider_shadow.save_shadow_reports(
        summary, eligibility, discovery, output_dir=tmp_path / "out"
    )

    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))

    assert payload["markets"]
    assert all(item["is_no_value_call"] is False for item in payload["markets"])


def test_a_credential_that_reaches_a_report_is_redacted(
    tmp_path: Path, monkeypatch
) -> None:
    secret = "shadow-test-secret-never-write"
    monkeypatch.setenv("NHL_ODDS_API_KEY", secret)
    summary, eligibility, discovery = _summary(tmp_path)
    summary.warnings.append(f"a warning mentioning {secret} by mistake")

    paths = provider_shadow.save_shadow_reports(
        summary, eligibility, discovery, output_dir=tmp_path / "out"
    )

    for key in ("json", "markdown"):
        assert secret not in Path(paths[key]).read_text(encoding="utf-8")


def test_an_empty_price_frame_produces_a_report_rather_than_a_crash(
    tmp_path: Path,
) -> None:
    empty = pd.DataFrame(columns=["date", "home_team", "away_team", "market"])

    summary, eligibility, discovery = provider_shadow.build_shadow_summary(
        empty, policy=load_policy(), provider_name="the_odds_api", now=NOW
    )

    assert summary.rows == 0
    assert eligibility.eligible_markets == ()
    assert provider_shadow.render_shadow(summary, eligibility, discovery)
