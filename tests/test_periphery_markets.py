"""The periphery: team totals, prop ladders, anytime scorer, the fetch window.

Wired after the 2026-08-26 probe and the 2026-08-27 decision record
(`docs/periphery_markets_decision.md`). Everything here follows one rule: a
market is wired only when this lab can model it *and* settle it from data it
already caches — and a new market reaches the card only through the same
allowlist door every other market walked.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab import market_eligibility as elig
from nhl_betting_lab.backtest.team_walk_forward import settle_team_total
from nhl_betting_lab.forward_evidence import _settle_team_row
from nhl_betting_lab.markets import ANYTIME_SCORER_LINE
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.odds_api import normalize_event
from nhl_betting_lab.reports.card_pricing import price_team_markets, selection_key

from tests.test_team_model import balanced_league


HOME = "Toronto Maple Leafs"
AWAY = "Boston Bruins"


def _event(markets: list[dict]) -> dict:
    return {
        "id": "evt1",
        "commence_time": "2026-10-09T23:00:00Z",
        "home_team": HOME,
        "away_team": AWAY,
        "bookmakers": [
            {"key": "draftkings", "title": "DraftKings", "markets": markets}
        ],
    }


# -- normalisation -----------------------------------------------------


def test_team_totals_arrive_in_this_labs_vocabulary() -> None:
    """Both teams ride one provider key; the side must land in the
    selection, and the team name must never land in the player column."""
    rows = normalize_event(
        _event(
            [
                {
                    "key": "team_totals",
                    "outcomes": [
                        {"name": "Over", "description": HOME, "price": -115, "point": 3.5},
                        {"name": "Under", "description": HOME, "price": -105, "point": 3.5},
                        {"name": "Over", "description": AWAY, "price": 110, "point": 2.5},
                    ],
                }
            ]
        ),
        fetched_at="2026-10-09T12:00:00+00:00",
    )

    assert [(r["market"], r["selection"], r["line"]) for r in rows] == [
        ("team_total", "home_over", 3.5),
        ("team_total", "home_under", 3.5),
        ("team_total", "away_over", 2.5),
    ]
    assert all(r["player"] == "" for r in rows)


def test_a_team_total_for_an_unrecognised_team_is_dropped() -> None:
    rows = normalize_event(
        _event(
            [
                {
                    "key": "team_totals",
                    "outcomes": [
                        {"name": "Over", "description": "Springfield Isotopes", "price": -110, "point": 3.5}
                    ],
                }
            ]
        ),
        fetched_at="x",
    )

    assert rows == []


def test_the_alternate_team_ladder_lands_on_the_same_market() -> None:
    rows = normalize_event(
        _event(
            [
                {
                    "key": "alternate_team_totals",
                    "outcomes": [
                        {"name": "Over", "description": AWAY, "price": 240, "point": 4.5}
                    ],
                }
            ]
        ),
        fetched_at="x",
    )

    assert [(r["market"], r["selection"], r["line"]) for r in rows] == [
        ("team_total", "away_over", 4.5)
    ]


def test_a_prop_ladder_lands_on_the_same_market_as_its_bulk_line() -> None:
    """`player_shots_on_goal_alternate` is more lines, not a new market —
    two keys measuring the same thing under two names is how numbers drift."""
    rows = normalize_event(
        _event(
            [
                {
                    "key": "player_shots_on_goal_alternate",
                    "outcomes": [
                        {"name": "Over", "description": "Auston Matthews", "price": 260, "point": 5.5}
                    ],
                }
            ]
        ),
        fetched_at="x",
    )

    assert [(r["market"], r["player"], r["selection"], r["line"]) for r in rows] == [
        ("shots_on_goal", "Auston Matthews", "over", 5.5)
    ]


def test_anytime_scorer_is_goals_over_half_whichever_shape_arrives() -> None:
    """The scorer market inverts the prop shape. Both observed layouts must
    land identically, because they mean the same bet."""
    name_shape = normalize_event(
        _event(
            [
                {
                    "key": "player_goal_scorer_anytime",
                    "outcomes": [{"name": "Auston Matthews", "price": 130}],
                }
            ]
        ),
        fetched_at="x",
    )
    yes_shape = normalize_event(
        _event(
            [
                {
                    "key": "player_goal_scorer_anytime",
                    "outcomes": [
                        {"name": "Yes", "description": "Auston Matthews", "price": 130}
                    ],
                }
            ]
        ),
        fetched_at="x",
    )

    for rows in (name_shape, yes_shape):
        assert [(r["market"], r["player"], r["selection"], r["line"]) for r in rows] == [
            ("goals", "Auston Matthews", "yes", ANYTIME_SCORER_LINE)
        ]


# -- the model ---------------------------------------------------------


def test_team_total_probabilities_are_a_coherent_distribution() -> None:
    model = TeamModel().fit(balanced_league())

    on_half = model.team_total_probabilities("STR", "WEA", line=2.5, side="home")
    on_whole = model.team_total_probabilities("STR", "WEA", line=3.0, side="home")

    assert on_half["push"] == 0.0
    assert on_half["over"] + on_half["under"] == pytest.approx(1.0)
    assert on_whole["push"] > 0.0
    assert on_whole["over"] + on_whole["under"] == pytest.approx(1.0)


def test_the_stronger_side_clears_the_same_line_more_often() -> None:
    model = TeamModel().fit(balanced_league())

    strong = model.team_total_probabilities("STR", "WEA", line=2.5, side="home")
    weak = model.team_total_probabilities("STR", "WEA", line=2.5, side="away")

    assert strong["over"] > weak["over"]


def test_an_unknown_side_raises_rather_than_guessing() -> None:
    model = TeamModel().fit(balanced_league())

    with pytest.raises(ValueError, match="side"):
        model.team_total_probabilities("STR", "WEA", line=2.5, side="total")


# -- settlement --------------------------------------------------------


def test_team_total_settlement_honours_the_whole_number_push() -> None:
    assert settle_team_total(4, 3.5) == (True, False)
    assert settle_team_total(3, 3.5) == (False, False)
    assert settle_team_total(3, 3.0) == (False, True)


def test_a_frozen_team_total_row_settles_against_the_final_score() -> None:
    game = (
        pd.DataFrame([{"home_goals": 4, "away_goals": 2, "regulation": True}])
        .itertuples()
        .__next__()
    )

    won_row = pd.DataFrame(
        [{"market": "team_total", "selection": "home_over", "line": 3.5, "american_odds": -110}]
    ).itertuples().__next__()
    lost_row = pd.DataFrame(
        [{"market": "team_total", "selection": "away_over", "line": 2.5, "american_odds": -110}]
    ).itertuples().__next__()
    junk_row = pd.DataFrame(
        [{"market": "team_total", "selection": "over", "line": 2.5, "american_odds": -110}]
    ).itertuples().__next__()

    assert _settle_team_row(won_row, game)[0] == "won"
    assert _settle_team_row(lost_row, game)[0] == "lost"
    assert _settle_team_row(junk_row, game)[0] == "unsettleable"


# -- pricing and the card gate -----------------------------------------


def _team_total_prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-10-09",
                "commence_time": "2026-10-09T23:00:00Z",
                "home_team": "STR",
                "away_team": "WEA",
                "market": "team_total",
                "player": "",
                "selection": selection,
                "line": 2.5,
                "american_odds": -110,
                "book": "DraftKings",
            }
            for selection in ("home_over", "home_under", "nonsense")
        ]
    )


def test_the_card_prices_team_totals_and_ignores_unknown_selections() -> None:
    model = TeamModel().fit(balanced_league())
    prices = _team_total_prices()

    probabilities, unresolved = price_team_markets(prices, model)

    over_key = selection_key(
        prices.iloc[0], market="team_total", selection="home_over", line=2.5
    )
    under_key = selection_key(
        prices.iloc[1], market="team_total", selection="home_under", line=2.5
    )
    junk_key = selection_key(
        prices.iloc[2], market="team_total", selection="nonsense", line=2.5
    )

    assert probabilities[over_key] + probabilities[under_key] == pytest.approx(1.0)
    assert junk_key not in probabilities
    assert unresolved == []


def test_team_total_is_gated_until_a_human_approves_it(tmp_path) -> None:
    """The receipt approves eleven markets by name; a market wired later is
    excluded by the same rule that once excluded all of them."""
    import json
    from pathlib import Path

    from nhl_betting_lab.staging_provider_policy import load_policy

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
                        "approved_at": "2026-08-27T12:00:00-04:00",
                        "reviewer_name": "cooperross399",
                        "evidence_receipt_id": "receipt-1",
                        "required_markets": [
                            "assists", "blocked_shots", "goalie_saves",
                            "goals", "hits", "moneyline", "points",
                            "puck_line", "regulation_3_way", "shots_on_goal",
                            "total_goals",
                        ],
                    }
                },
                "max_provider_run_age_hours": 12,
            }
        ),
        encoding="utf-8",
    )
    policy = load_policy(repository_root=Path(tmp_path))
    prices = _team_total_prices()

    report = elig.assess_markets(
        prices,
        slate_games=elig.slate_games_from(prices),
        policy=policy,
        provider_name="the_odds_api",
        markets=["team_total"],
    )

    assert report.eligible_markets == ()
    assert report.markets[0].state == elig.NOT_ALLOWLISTED
    assert report.markets[0].is_no_value_call is False


# -- the fetch window --------------------------------------------------


class _Response:
    def __init__(self, payload: object) -> None:
        self.status_code = 200
        self.headers = {"x-requests-last": "1", "x-requests-remaining": "1000"}
        self._payload = payload

    def json(self) -> object:
        return self._payload


def test_the_per_event_fetch_spends_only_on_the_days_it_is_for() -> None:
    """32 posted August events once starved the nearest nine under the cap.
    The window keeps the budget on the slate the card is actually about."""
    today_event = {
        "id": "today1",
        "commence_time": "2026-10-09T23:00:00Z",
        "home_team": HOME,
        "away_team": AWAY,
    }
    far_event = {
        "id": "far1",
        "commence_time": "2026-10-12T23:00:00Z",
        "home_team": AWAY,
        "away_team": HOME,
    }
    asked: list[str] = []

    def requester(url: str, **kwargs):  # noqa: ANN001, ANN202
        if url.endswith("/events"):
            return _Response([today_event, far_event])
        asked.append(url)
        return _Response({**today_event, "bookmakers": []})

    provider = odds_api.OddsApiProvider(
        environment={"NHL_ODDS_API_KEY": "k" * 24}, requester=requester
    )

    result = provider.fetch_player_props(
        markets=["player_shots_on_goal"],
        league_days=["2026-10-09"],
        fetched_at="x",
    )

    assert len(asked) == 1
    assert "today1" in asked[0]
    assert any("outside the fetch window" in note for note in result.warnings)
