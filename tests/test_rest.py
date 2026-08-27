"""The shared "played yesterday" rule, and that the card actually uses it.

The back-to-back adjustment shipped because it won the price backtest with
rest included. The gap these tests close: the card briefly priced team markets
without computing rest at all — shipping an unmeasured policy under a measured
one's name — and nothing failed, because every fixture passed no flags and
every default was False.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.rest import last_played_dates, played_previous_day


def _games(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": day, "home_team": home, "away_team": away,
             "home_goals": 3, "away_goals": 2, "regulation": True,
             "game_id": index}
            for index, (day, home, away) in enumerate(rows)
        ]
    )


def test_each_team_keeps_its_most_recent_date() -> None:
    latest = last_played_dates(
        _games([("2026-01-08", "TOR", "BOS"), ("2026-01-10", "TOR", "MTL")])
    )

    assert latest["TOR"] == "2026-01-10"
    assert latest["BOS"] == "2026-01-08"
    assert latest["MTL"] == "2026-01-10"


def test_a_team_that_played_yesterday_is_back_to_back() -> None:
    latest = {"TOR": "2026-01-10"}

    assert played_previous_day(latest, "TOR", "2026-01-11") is True
    assert played_previous_day(latest, "TOR", "2026-01-12") is False
    assert played_previous_day(latest, "TOR", "2026-01-10") is False


def test_an_unknown_team_prices_as_rested() -> None:
    """The conservative direction: the adjustment only moves a price when the
    schedule affirmatively says a side is tired."""
    assert played_previous_day({}, "SEA", "2026-01-11") is False


def test_an_unusable_date_prices_as_rested() -> None:
    assert played_previous_day({"TOR": "sometime"}, "TOR", "2026-01-11") is False
    assert played_previous_day({"TOR": "2026-01-10"}, "TOR", "whenever") is False


def test_an_empty_history_yields_no_dates() -> None:
    assert last_played_dates(pd.DataFrame(columns=["date"])) == {}


def test_the_sampler_and_the_card_share_one_definition() -> None:
    """Two copies of "played yesterday" is the join-vocabulary bug's shape."""
    import inspect

    from nhl_betting_lab.backtest import team_walk_forward
    from nhl_betting_lab.reports import card_pricing

    for module in (team_walk_forward, card_pricing):
        source = inspect.getsource(module)
        assert "played_previous_day" in source
        # Neither module re-implements the day arithmetic.
        assert ".days == 1" not in source


def test_the_card_moves_a_tired_road_teams_price(tmp_path) -> None:
    """End to end: the same slate, with and without history, prices
    differently for the side the schedule says is tired."""
    import sys
    sys.path.insert(0, "tests")
    from test_team_model import balanced_league

    from nhl_betting_lab.models.team_model import TeamModel
    from nhl_betting_lab.reports.card_pricing import price_team_markets

    model = TeamModel().fit(balanced_league())
    # The synthetic league has no back-to-backs, so the factors are forced
    # apart to make the routing observable — the point of this test is that
    # the flag reaches the model, not how large the fitted effect is. The
    # magnitude is the rest experiment's business.
    model.b2b_factors = {
        "home_for": 0.95,
        "home_against": 1.05,
        "away_for": 0.90,
        "away_against": 1.10,
    }
    prices = pd.DataFrame(
        [
            {
                "date": "2025-02-02",
                "commence_time": "2025-02-03T00:10:00Z",
                "home_team": "STR",
                "away_team": "WEA",
                "market": "moneyline",
                "player": "",
                "selection": "home",
                "line": None,
                "american_odds": -140,
            }
        ]
    )
    history = pd.DataFrame(
        [
            {"date": "2025-02-01", "home_team": "WEA", "away_team": "AVA",
             "home_goals": 2, "away_goals": 3, "regulation": True, "game_id": 1}
        ]
    )

    rested, _ = price_team_markets(prices, model)
    tired, _ = price_team_markets(prices, model, history=history)

    # The away side played yesterday, so the home side's chance rises.
    assert next(iter(tired.values())) > next(iter(rested.values()))


def test_without_history_every_side_prices_as_rested() -> None:
    from test_team_model import balanced_league

    from nhl_betting_lab.models.team_model import TeamModel
    from nhl_betting_lab.reports.card_pricing import price_team_markets

    model = TeamModel().fit(balanced_league())
    prices = pd.DataFrame(
        [
            {
                "date": "2025-02-02",
                "commence_time": "2025-02-03T00:10:00Z",
                "home_team": "STR",
                "away_team": "WEA",
                "market": "moneyline",
                "player": "",
                "selection": "home",
                "line": None,
                "american_odds": -140,
            }
        ]
    )

    with_none, _ = price_team_markets(prices, model)
    baseline = model.moneyline_probabilities("STR", "WEA")["home"]

    assert next(iter(with_none.values())) == pytest.approx(baseline)


def test_the_card_runner_passes_the_history() -> None:
    """The wiring itself, asserted against the file that carries it."""
    from nhl_betting_lab.config import PROJECT_ROOT

    text = (PROJECT_ROOT / "scripts" / "run_gameday_card.py").read_text(
        encoding="utf-8"
    )

    assert "history=games" in text
