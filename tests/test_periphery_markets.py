"""The periphery: team totals, prop ladders, anytime scorer, the fetch window.

Wired after the 2026-08-26 probe and the 2026-08-27 decision record
(`docs/periphery_markets_decision.md`). Everything here follows one rule: a
market is wired only when this lab can model it *and* settle it from data it
already caches — and a new market reaches the card only through the same
allowlist door every other market walked.
"""

from __future__ import annotations

import pathlib

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
            ("goals", "Auston Matthews", "over", ANYTIME_SCORER_LINE)
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


# -- what the review found, pinned so it cannot come back --------------


def test_one_window_covers_both_fetches_or_props_read_as_incomplete() -> None:
    """The gate measures coverage against the slate the staged prices
    describe. Windowing the per-event fetch while the bulk fetch stages the
    whole posted board makes every prop "priced for 9 of 32 games" —
    INCOMPLETE, excluded from the card, and indistinguishable from books
    not posting props at all. Found by review before it ever ran."""
    text = (
        pathlib.Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_provider_shadow.py"
    ).read_text(encoding="utf-8")

    # One window, built once, passed to both fetches.
    assert text.count("args.horizon_days > 0") == 1
    # The invariant, not the formatting: whatever the call looks like, the
    # bulk fetch must receive the same window AND the same event cap the
    # per-event fetch uses. Two fetches over two different event sets make
    # the eligibility gate measure coverage against games nobody priced.
    call = text.split("provider.fetch_team_markets(", 1)[1].split(")", 1)[0]
    assert "league_days=league_days" in call
    assert "max_events=args.max_events" in call
    assert "league_days=league_days," in text


def test_the_bulk_fetch_reports_an_off_day_as_an_empty_slate() -> None:
    """A board full of future games with nothing today is an ordinary
    off-night, not a fault and not a card."""
    board = [
        {
            "id": "far",
            "commence_time": "2026-10-12T23:00:00Z",
            "home_team": HOME,
            "away_team": AWAY,
            "bookmakers": [],
        }
    ]

    def requester(url: str, **kwargs):  # noqa: ANN001, ANN202
        return _Response(board)

    provider = odds_api.OddsApiProvider(
        environment={"NHL_ODDS_API_KEY": "k" * 24}, requester=requester
    )

    with pytest.raises(odds_api.EmptySlateError, match="none is scheduled"):
        provider.fetch_team_markets(
            fetched_at="x", league_days=["2026-10-09"]
        )


def test_the_windowed_bulk_fetch_counts_only_what_it_fetched() -> None:
    """`events_seen` feeds the credit estimate and the coverage ratio. Left
    at the board size it describes games the run never fetched."""
    board = [
        {
            "id": "today",
            "commence_time": "2026-10-09T23:00:00Z",
            "home_team": HOME,
            "away_team": AWAY,
            "bookmakers": [
                {
                    "key": "dk",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": HOME, "price": -140},
                                {"name": AWAY, "price": 120},
                            ],
                        }
                    ],
                }
            ],
        },
        {
            "id": "far",
            "commence_time": "2026-10-12T23:00:00Z",
            "home_team": AWAY,
            "away_team": HOME,
            "bookmakers": [],
        },
    ]

    provider = odds_api.OddsApiProvider(
        environment={"NHL_ODDS_API_KEY": "k" * 24},
        requester=lambda url, **kwargs: _Response(board),
    )

    result = provider.fetch_team_markets(
        fetched_at="x", league_days=["2026-10-09"]
    )

    assert result.events_seen == 1
    assert result.events_priced == 1
    assert {row["provider_event_id"] for row in result.rows} == {"today"}
    assert any("outside the fetch window" in note for note in result.warnings)


def test_the_probe_workflow_asks_about_the_whole_board() -> None:
    """The discovery workflow IS the probe. Windowed to today it would
    report every per-event market at zero coverage on any off-day — a live
    market written off for the wrong reason, which is the exact mistake the
    workflow exists to prevent."""
    text = (
        pathlib.Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "provider-market-discovery.yml"
    ).read_text(encoding="utf-8")

    assert "--horizon-days 0" in text


def test_every_credit_cap_is_scaled_to_the_number_of_markets_asked() -> None:
    """The cap bills every asked market whether a book quotes it or not, so
    a cap set when ten markets were asked buys half the events once
    nineteen are. A starved fetch and an unquoted market look identical."""
    asked = len(odds_api.PER_EVENT_PROVIDER_MARKETS) + len(
        odds_api.ALTERNATE_PROVIDER_MARKETS
    )
    root = pathlib.Path(__file__).resolve().parents[1]
    gameday = (root / ".github/workflows/gameday-refresh.yml").read_text(
        encoding="utf-8"
    )
    discovery = (
        root / ".github/workflows/provider-market-discovery.yml"
    ).read_text(encoding="utf-8")

    # Each default cap must buy a real slate's worth of events, not three.
    assert 320 // asked >= 16, "the gameday cap no longer covers a full slate"
    assert "'320'" in gameday
    assert 380 // asked >= 20, "the probe cap no longer covers a real probe"
    assert "'380'" in discovery


def test_a_missing_line_is_unsettleable_rather_than_an_under_that_won() -> None:
    """NaN is what a missing CSV field becomes, and every comparison against
    it is False — so an absent line quietly settles `under` as a win and
    `over` as a loss. Refuse instead."""
    game = (
        pd.DataFrame([{"home_goals": 4, "away_goals": 2, "regulation": True}])
        .itertuples()
        .__next__()
    )
    for market, selection in (
        ("total_goals", "under"),
        ("team_total", "home_under"),
        ("puck_line", "home"),
    ):
        row = (
            pd.DataFrame(
                [
                    {
                        "market": market,
                        "selection": selection,
                        "line": float("nan"),
                        "american_odds": -110,
                    }
                ]
            )
            .itertuples()
            .__next__()
        )

        assert _settle_team_row(row, game)[0] == "unsettleable", market


def test_a_scratch_run_cannot_freeze_into_the_real_evidence_archive(
    tmp_path,
) -> None:
    """Found by running the card end to end against synthetic prices: with
    `--output-dir` pointed at a scratch directory, the snapshot still froze
    into the real archive — dated to opening night. Because the first
    opinion of a day stands and is never repriced, the real opening-night
    card could then never have frozen its own, and test rows would have
    become the season's first forward evidence."""
    from nhl_betting_lab.config import DATA_DIR

    from tests.test_scripts import load_script

    module = load_script("run_gameday_card.py")
    real_archive = DATA_DIR / "archive" / "priced_snapshots"
    before = set(real_archive.glob("*")) if real_archive.is_dir() else set()

    code = module.main(
        [
            "--staging-dir", str(tmp_path / "staging"),
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "outputs"),
            "--now", "2026-10-08T18:00:00+00:00",
        ]
    )

    after = set(real_archive.glob("*")) if real_archive.is_dir() else set()
    assert code == 0
    assert after == before, "a scratch run wrote into the real archive"
