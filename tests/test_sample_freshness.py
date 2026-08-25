"""Reusing cached samples is a speed optimisation, never a correctness one."""

from __future__ import annotations

import pandas as pd

from nhl_betting_lab.backtest import samples_are_current
from nhl_betting_lab.markets import prop_market_keys, team_market_keys


def _samples(markets: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"market": markets, "model_probability": [0.5] * len(markets)})


def test_samples_naming_current_markets_are_reusable() -> None:
    current, reason = samples_are_current(
        _samples(["shots_on_goal", "points"]), known_markets=prop_market_keys()
    )

    assert current is True
    assert reason == ""


def test_samples_that_predate_a_rename_are_refused() -> None:
    """`total_5_5` was renamed to `total_goals`. A cached file keeps the old
    key, the report groups by it, and the output describes a market that does
    not exist."""
    current, reason = samples_are_current(
        _samples(["moneyline", "total_5_5"]), known_markets=team_market_keys()
    )

    assert current is False
    assert "total_5_5" in reason
    assert "predate a rename" in reason


def test_empty_samples_are_not_reusable() -> None:
    current, reason = samples_are_current(
        pd.DataFrame(columns=["market"]), known_markets=prop_market_keys()
    )

    assert current is False
    assert "empty" in reason


def test_samples_without_a_market_column_are_not_reusable() -> None:
    current, _ = samples_are_current(
        pd.DataFrame({"x": [1]}), known_markets=prop_market_keys()
    )

    assert current is False


def test_a_prop_sample_file_is_not_reusable_for_team_markets() -> None:
    """Pointing one measurement at the other's cache must not quietly work."""
    current, _ = samples_are_current(
        _samples(["shots_on_goal"]), known_markets=team_market_keys()
    )

    assert current is False
