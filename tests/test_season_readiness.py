"""Checks that keep the lab honest across a whole season, not one run.

Every test here is a defect that survived a review round and was reproduced
before it was fixed. They are grouped by the shape of the failure rather than
by module, because that is how they were found: each one made the lab report
something false without any error anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.season import schedule_cache_is_complete


SECRET = "season-readiness-secret"
ENVIRONMENT = {"NHL_ODDS_API_KEY": SECRET}


def _workflow(name: str) -> str:
    return (PROJECT_ROOT / ".github" / "workflows" / name).read_text(
        encoding="utf-8"
    )


# -- one wager, one selection ------------------------------------------


def test_the_scorer_and_the_goals_rung_are_one_selection_at_the_best_price() -> None:
    """Anytime scorer IS goals over 0.5, and two names for it staked it twice.

    The card publishes the best reachable price per selection. When the same
    wager arrived under two spellings the collapse never fired: both were
    published as independent best bets, the stake doubled, the worse price
    was quoted beside the better, and the forward ledger froze one outcome as
    two rows.
    """
    event = {
        "id": "evt1",
        "commence_time": "2026-10-09T23:00:00Z",
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "player_goals",
                        "outcomes": [
                            {
                                "name": "Over",
                                "description": "Auston Matthews",
                                "price": 420,
                                "point": 0.5,
                            }
                        ],
                    },
                    {
                        "key": "player_goal_scorer_anytime",
                        "outcomes": [
                            {"name": "Auston Matthews", "price": 430}
                        ],
                    },
                ],
            }
        ],
    }

    rows = odds_api.normalize_event(event, fetched_at="2026-10-09T12:00:00Z")
    goals = [row for row in rows if row["market"] == "goals"]
    assert len(goals) == 2, "both spellings should still be staged"

    frame = pd.DataFrame(goals)
    keys = {
        selection_key(
            row,
            market=row.market,
            selection=row.selection,
            line=row.line,
        )
        for row in frame.itertuples()
    }
    assert len(keys) == 1, (
        "one wager must produce one selection key, or the card stakes it "
        f"twice: {keys}"
    )
    assert {str(row["selection"]) for row in goals} == {"over"}


# -- one bad market key must not cost every prop -----------------------


def test_a_refused_market_list_falls_back_to_the_core_markets() -> None:
    """Nineteen keys ride one request, so one dead key would zero the lot.

    The provider answers a market list it does not serve with a 422 for
    *every* event, so a key it stops serving mid-season would take every prop
    on every event with it — a season of empty cards that read exactly like
    books not posting props.
    """
    priced = {
        "id": "evt1",
        "commence_time": "2026-10-09T23:00:00Z",
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "player_shots_on_goal",
                        "outcomes": [
                            {
                                "name": "Over",
                                "description": "Auston Matthews",
                                "price": -115,
                                "point": 3.5,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    dead_key = odds_api.ALTERNATE_PROVIDER_MARKETS[0]

    def odds(url: str, **kwargs):
        asked = str(kwargs.get("params", {}).get("markets", ""))
        if dead_key in asked:
            return FakeResponse(status_code=422, payload={"message": "bad"})
        return FakeResponse(payload=priced, headers={"x-requests-last": "8"})

    # Most specific fragment first: the requester returns the first match,
    # and "/events" is a prefix of the per-event odds URL.
    requester = RecordingRequester(
        {
            "/events/evt1/odds": odds,
            "/events": FakeResponse(payload=[{"id": "evt1"}]),
        }
    )
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    result = provider.fetch_player_props(
        markets=list(odds_api.PER_EVENT_PROVIDER_MARKETS)
        + list(odds_api.ALTERNATE_PROVIDER_MARKETS),
        credit_cap=500,
        fetched_at="2026-10-09T12:00:00Z",
    )

    assert result.rows, "the core markets must survive a refused ladder"
    assert any("422" in warning for warning in result.warnings)
    assert any(dead_key in warning for warning in result.warnings)


# -- a cache with holes cannot judge a slate ---------------------------


def test_a_holed_schedule_cache_reports_itself_incomplete(tmp_path: Path) -> None:
    """A partial cache is the same truth with holes, and the holes look
    exactly like exhibition games to anything that only asks whether a
    fixture is in the set."""
    directory = tmp_path / "nhl" / "club_schedule"
    directory.mkdir(parents=True)
    (directory / "TOR.json").write_text(
        json.dumps(
            {
                "games": [
                    {
                        "gameType": 2,
                        "gameDate": "2026-10-08",
                        "homeTeam": {"abbrev": "TOR"},
                        "awayTeam": {"abbrev": "BOS"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    complete, clubs = schedule_cache_is_complete(tmp_path)

    assert complete is False
    assert clubs == 2


def test_the_card_abstains_from_screening_on_a_holed_cache() -> None:
    """Dropping real games shrinks the slate the eligibility gate measures
    against, so a card built on one eighth of the night reports itself
    complete and green."""
    text = (PROJECT_ROOT / "scripts" / "run_gameday_card.py").read_text(
        encoding="utf-8"
    )

    assert "schedule_cache_is_complete" in text
    screen = text.index("not schedule_complete")
    abstain = text.index("preseason screen is skipped")
    assert screen < abstain


# -- the same event set on both sides of a coverage measurement --------


def test_capping_the_per_event_fetch_caps_the_bulk_fetch_too() -> None:
    """The slate is derived from the staged rows, so a bulk fetch of the
    whole board beside a capped per-event fetch reports the cap as the
    provider's absence."""
    events = [
        {
            "id": f"evt{index}",
            "commence_time": f"2026-10-0{index + 1}T23:00:00Z",
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Toronto Maple Leafs", "price": -140},
                                {"name": "Boston Bruins", "price": 120},
                            ],
                        }
                    ],
                }
            ],
        }
        for index in range(4)
    ]
    requester = RecordingRequester({"/odds": FakeResponse(payload=events)})
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    result = provider.fetch_team_markets(
        fetched_at="2026-10-01T12:00:00Z", max_events=2
    )

    assert result.events_seen == 2
    assert {row["provider_event_id"] for row in result.rows} == {"evt0", "evt1"}


def test_the_probe_asks_the_whole_board_with_a_matched_event_cap() -> None:
    """A starved probe and an unquoted market must never look alike: telling
    them apart is the whole job of the discovery workflow."""
    text = _workflow("provider-market-discovery.yml")

    assert "--horizon-days 0" in text
    assert "--max-events 20" in text
    asked = len(odds_api.PER_EVENT_PROVIDER_MARKETS) + len(
        odds_api.ALTERNATE_PROVIDER_MARKETS
    )
    assert f"'{asked * 20}'" in text, (
        "the credit cap must buy exactly the events the fetch is capped to, "
        f"which is {asked} markets x 20 events"
    )


# -- silence must stay safe to read ------------------------------------


def test_a_dark_night_cannot_hide_a_degraded_run() -> None:
    """The league does not play every night, so an empty slate that exits
    before the degraded check hides faults on half the season's nights."""
    text = _workflow("gameday-refresh.yml")
    report = text.index("- name: Report the outcome")
    tail = text[report:]

    assert tail.index("steps.health.outputs.degraded") < tail.index(
        "steps.prices.outputs.empty_slate"
    ), "the degraded check must come before the empty-slate exit"


def test_the_backup_run_stands_down_when_the_primary_already_delivered() -> None:
    """Two scheduled triggers, and when the first works the second has
    nothing to add but a duplicate bill."""
    text = _workflow("gameday-refresh.yml")

    assert "precheck" in text
    assert "needs.precheck.outputs.already != 'true'" in text
    # A manual run means run it, and a degraded card is exactly what the
    # backup exists to replace.
    assert "github.event_name }}\" != \"schedule\"" in text
    assert '"$DEGRADED" = "false"' in text


def test_the_forward_ledger_survives_a_broken_artifact_chain() -> None:
    """The prices it settled against are gone, so the ledger cannot be
    rebuilt from anything if the chain drops it."""
    text = _workflow("gameday-refresh.yml")

    assert "forward_evidence.csv" in text
    publish = text.index("BLOB_LEDGER")
    restore = text.index("refs/card-feed-tip:forward_evidence.csv")
    assert restore < publish, "the restore reads what an earlier run published"
