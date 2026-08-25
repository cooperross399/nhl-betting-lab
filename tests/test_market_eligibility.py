from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab import market_eligibility as elig
from nhl_betting_lab.staging_provider_policy import load_policy


def _prices(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _row(market: str, *, date: str = "2026-10-08", home: str = "TOR", away: str = "BOS", **extra) -> dict:
    row = {
        "date": date,
        "home_team": home,
        "away_team": away,
        "market": market,
        "selection": "over",
        "book": "DraftKings",
        "american_odds": -110,
    }
    row.update(extra)
    return row


def _policy_allowing(tmp_path: Path, markets: list[str]):
    path = tmp_path / "data" / "manual" / "staging_provider_policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "allowed_provider_names": ["the_odds_api"],
                "allowed_provider_types": ["odds_api"],
                "provider_allowlist_entries": {
                    "the_odds_api": {
                        "allowlist_status": "allowed",
                        "provider_type": "odds_api",
                        "approved_at": "2026-10-01T09:00:00-04:00",
                        "reviewer_name": "cooperross399",
                        "evidence_receipt_id": "receipt-1",
                        "required_markets": markets,
                    }
                },
                "max_provider_run_age_hours": 12,
            }
        ),
        encoding="utf-8",
    )
    return load_policy(repository_root=tmp_path)


def test_with_the_shipped_policy_nothing_is_eligible() -> None:
    """The default state of this repository."""
    prices = _prices([_row("moneyline"), _row("shots_on_goal")])

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=load_policy(),
        provider_name="the_odds_api",
        markets=["moneyline", "shots_on_goal"],
    )

    assert report.eligible_markets == ()
    assert set(report.excluded_markets) == {"moneyline", "shots_on_goal"}
    assert all(item.state == elig.NOT_ALLOWLISTED for item in report.markets)


def test_an_allowlisted_and_complete_market_is_eligible(tmp_path: Path) -> None:
    policy = _policy_allowing(tmp_path, ["moneyline"])
    prices = _prices([_row("moneyline")])

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=policy,
        provider_name="the_odds_api",
        markets=["moneyline"],
    )

    assert report.eligible_markets == ("moneyline",)


def test_a_market_with_no_rows_is_unavailable_not_a_no_value_call(
    tmp_path: Path,
) -> None:
    policy = _policy_allowing(tmp_path, ["moneyline", "blocked_shots"])
    prices = _prices([_row("moneyline")])

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=policy,
        provider_name="the_odds_api",
        markets=["moneyline", "blocked_shots"],
    )
    blocked = next(item for item in report.markets if item.market == "blocked_shots")

    assert blocked.state == elig.UNAVAILABLE
    assert blocked.is_no_value_call is False
    assert "not a price of zero" in blocked.reason
    assert "alternate lines" in blocked.reason


def test_a_half_covered_market_is_incomplete_rather_than_half_used(
    tmp_path: Path,
) -> None:
    """Picking only where prices exist is a selection effect, not an edge."""
    policy = _policy_allowing(tmp_path, ["points"])
    prices = _prices(
        [
            _row("moneyline", home="TOR", away="BOS"),
            _row("moneyline", home="EDM", away="CGY"),
            _row("points", home="TOR", away="BOS"),
        ]
    )

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=policy,
        provider_name="the_odds_api",
        markets=["points"],
    )
    points = report.markets[0]

    assert points.state == elig.INCOMPLETE
    assert points.games_priced == 1
    assert points.games_in_slate == 2
    assert len(points.missing_games) == 1
    assert "selection effect" in points.reason


def test_an_incomplete_market_can_be_allowed_when_the_slate_is_not_required(
    tmp_path: Path,
) -> None:
    policy = _policy_allowing(tmp_path, ["points"])
    prices = _prices(
        [
            _row("moneyline", home="EDM", away="CGY"),
            _row("points", home="TOR", away="BOS"),
        ]
    )

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=policy,
        provider_name="the_odds_api",
        markets=["points"],
        require_full_slate=False,
    )

    assert report.eligible_markets == ("points",)


def test_a_disabled_market_is_excluded_regardless_of_everything_else(
    tmp_path: Path,
) -> None:
    policy = _policy_allowing(tmp_path, ["moneyline"])
    prices = _prices([_row("moneyline")])

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=policy,
        provider_name="the_odds_api",
        markets=["moneyline"],
        disabled=["moneyline"],
    )

    assert report.markets[0].state == elig.DISABLED
    assert report.eligible_markets == ()


def test_an_unknown_market_key_is_disabled_rather_than_crashing() -> None:
    report = elig.assess_markets(
        _prices([_row("corner_kicks")]),
        slate_games=("2026-10-08 BOS@TOR",),
        policy=load_policy(),
        provider_name="the_odds_api",
        markets=["corner_kicks"],
    )

    assert report.markets[0].state == elig.DISABLED
    assert "price or settle" in report.markets[0].reason


def test_no_excluded_market_ever_reports_itself_as_a_no_value_call(
    tmp_path: Path,
) -> None:
    policy = _policy_allowing(tmp_path, [])
    prices = _prices([_row("moneyline"), _row("points")])

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=policy,
        provider_name="the_odds_api",
        markets=["moneyline", "points", "goals"],
    )

    assert all(item.is_no_value_call is False for item in report.markets)
    assert all(not item.usable_for_picks for item in report.markets)


def test_the_summary_says_plainly_when_nothing_is_eligible() -> None:
    prices = _prices([_row("moneyline")])

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=load_policy(),
        provider_name="the_odds_api",
        markets=["moneyline"],
    )

    assert "No market is eligible" in report.summary_line()
    assert "none is a pass or a no-value call" in report.summary_line()


def test_filtering_drops_every_ineligible_row(tmp_path: Path) -> None:
    policy = _policy_allowing(tmp_path, ["moneyline"])
    prices = _prices([_row("moneyline"), _row("points")])
    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=policy,
        provider_name="the_odds_api",
        markets=["moneyline", "points"],
    )

    filtered = elig.filter_to_eligible(prices, report)

    assert set(filtered["market"]) == {"moneyline"}


def test_filtering_an_empty_frame_is_safe() -> None:
    empty = pd.DataFrame(columns=["market", "date", "home_team", "away_team"])
    report = elig.assess_markets(
        empty,
        slate_games=(),
        policy=load_policy(),
        provider_name="the_odds_api",
        markets=["moneyline"],
    )

    assert elig.filter_to_eligible(empty, report).empty


def test_the_exclusion_reasons_map_covers_every_excluded_market() -> None:
    prices = _prices([_row("moneyline"), _row("points")])
    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=load_policy(),
        provider_name="the_odds_api",
        markets=["moneyline", "points"],
    )

    reasons = report.exclusion_reasons()

    assert set(reasons) == {"moneyline", "points"}
    assert all(reason for reason in reasons.values())


def test_eligible_markets_sort_before_excluded_ones(tmp_path: Path) -> None:
    policy = _policy_allowing(tmp_path, ["points"])
    prices = _prices([_row("moneyline"), _row("points")])

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=policy,
        provider_name="the_odds_api",
        markets=["moneyline", "points"],
    )

    assert report.markets[0].market == "points"


def test_slate_games_are_deduplicated() -> None:
    prices = _prices([_row("moneyline"), _row("points"), _row("goals")])

    assert elig.slate_games_from(prices) == ("2026-10-08 BOS@TOR",)


def test_only_eligible_is_a_usable_state() -> None:
    """The list of states that may produce a pick is exactly one long."""
    assert elig.USABLE_STATES == {elig.ELIGIBLE}
