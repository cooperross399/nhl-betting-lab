from __future__ import annotations

from pathlib import Path

import pytest

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.providers import historical_props as hist
from nhl_betting_lab.providers.odds_api import OddsApiProvider, ProviderError


ENVIRONMENT = {"NHL_ODDS_API_KEY": "props-secret-must-not-be-written"}


def _snapshot(markets: list[str]) -> dict:
    return {
        "timestamp": "2025-01-05T19:00:00Z",
        "data": {
            "id": "evt1",
            "commence_time": "2025-01-05T23:00:00Z",
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": key,
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Auston Matthews",
                                    "price": -115,
                                    "point": 3.5,
                                }
                            ],
                        }
                        for key in markets
                    ],
                }
            ],
        },
    }


def _provider(responses: dict) -> OddsApiProvider:
    return OddsApiProvider(
        environment=ENVIRONMENT, requester=RecordingRequester(responses)
    )


# -- cost --------------------------------------------------------------


def test_the_historical_rate_is_ten_times_the_live_one() -> None:
    assert hist.HISTORICAL_CREDITS_PER_MARKET_PER_EVENT == 10


def test_the_cost_estimate_is_events_times_markets_times_ten() -> None:
    assert hist.estimate_credits(events=12, markets=6) == 720


def test_the_cost_note_states_the_number_before_it_is_spent() -> None:
    note = hist.cost_note(events=12, markets=6)

    assert "720 credits" in note
    assert "needs a decision, not a default" in note


# -- retention ---------------------------------------------------------


def test_a_probe_reports_which_markets_came_back(tmp_path: Path) -> None:
    provider = _provider(
        {"/historical/": FakeResponse(_snapshot(["player_shots_on_goal"]))}
    )

    probe = hist.probe_retention(
        provider,
        event_id="evt1",
        snapshot="2025-01-05T19:00:00Z",
        markets=["player_shots_on_goal", "player_blocked_shots"],
        raw_dir=tmp_path,
    )

    assert probe.markets_returned == ("player_shots_on_goal",)
    assert probe.markets_missing == ("player_blocked_shots",)


def test_a_probe_states_what_it_cost(tmp_path: Path) -> None:
    provider = _provider(
        {"/historical/": FakeResponse(_snapshot(["player_points"]))}
    )

    probe = hist.probe_retention(
        provider,
        event_id="evt1",
        snapshot="2025-01-05T19:00:00Z",
        markets=["player_points"],
        raw_dir=tmp_path,
    )

    assert probe.credits_spent == 10
    assert "10 credits spent" in probe.summary_line()


def test_a_probe_failure_is_reported_rather_than_raised(tmp_path: Path) -> None:
    provider = _provider({"/historical/": FakeResponse(status_code=422)})

    probe = hist.probe_retention(
        provider,
        event_id="evt1",
        snapshot="2025-01-05T19:00:00Z",
        raw_dir=tmp_path,
    )

    assert probe.error
    assert "Probe failed" in probe.summary_line()


def test_a_cached_probe_costs_nothing(tmp_path: Path) -> None:
    requester = RecordingRequester(
        {"/historical/": FakeResponse(_snapshot(["player_points"]))}
    )
    provider = OddsApiProvider(environment=ENVIRONMENT, requester=requester)

    hist.probe_retention(
        provider,
        event_id="evt1",
        snapshot="2025-01-05T19:00:00Z",
        markets=["player_points"],
        raw_dir=tmp_path,
    )
    second = hist.probe_retention(
        provider,
        event_id="evt1",
        snapshot="2025-01-05T19:00:00Z",
        markets=["player_points"],
        raw_dir=tmp_path,
    )

    assert second.credits_spent == 0
    assert len(requester.calls) == 1


def test_an_unprobed_market_is_reported_as_unknown_not_as_absent() -> None:
    assert "**unknown**" in hist.retention_table([])
    assert "not assumed to be all of them" in hist.retention_table([])


def test_the_retention_table_names_an_unmeasurable_market() -> None:
    probe = hist.RetentionProbe(
        event_id="evt1",
        snapshot="2025-01-05T19:00:00Z",
        markets_requested=("player_points", "player_blocked_shots"),
        markets_returned=("player_points",),
    )

    table = hist.retention_table([probe])

    assert "cannot be measured" in table
    assert "player_blocked_shots" in table


# -- buying ------------------------------------------------------------


def test_a_purchase_returns_normalised_rows(tmp_path: Path) -> None:
    provider = _provider(
        {"/historical/": FakeResponse(_snapshot(["player_shots_on_goal"]))}
    )

    buy = hist.buy_historical_props(
        provider,
        events=[{"event_id": "evt1", "snapshot": "2025-01-05T19:00:00Z"}],
        markets=["player_shots_on_goal"],
        credit_cap=100,
        raw_dir=tmp_path,
    )

    assert buy.rows
    assert buy.rows[0]["player"] == "Auston Matthews"
    assert buy.rows[0]["market"] == "shots_on_goal"
    assert buy.rows[0]["snapshot"] == "2025-01-05T19:00:00Z"


def test_the_credit_cap_stops_the_purchase_before_it_exceeds(tmp_path: Path) -> None:
    provider = _provider(
        {"/historical/": FakeResponse(_snapshot(["player_points"]))}
    )
    events = [
        {"event_id": f"evt{index}", "snapshot": "2025-01-05T19:00:00Z"}
        for index in range(10)
    ]

    buy = hist.buy_historical_props(
        provider,
        events=events,
        markets=["player_points"],
        credit_cap=25,
        raw_dir=tmp_path,
    )

    assert buy.credits_spent <= 25
    assert buy.events_skipped_for_budget > 0


def test_a_cached_event_costs_nothing_so_a_rerun_is_free(tmp_path: Path) -> None:
    requester = RecordingRequester(
        {"/historical/": FakeResponse(_snapshot(["player_points"]))}
    )
    provider = OddsApiProvider(environment=ENVIRONMENT, requester=requester)
    events = [{"event_id": "evt1", "snapshot": "2025-01-05T19:00:00Z"}]

    hist.buy_historical_props(
        provider, events=events, markets=["player_points"], credit_cap=100,
        raw_dir=tmp_path,
    )
    second = hist.buy_historical_props(
        provider, events=events, markets=["player_points"], credit_cap=100,
        raw_dir=tmp_path,
    )

    assert second.credits_spent == 0
    assert second.events_from_cache == 1
    assert second.rows


def test_an_event_with_no_id_or_snapshot_is_reported_not_bought(
    tmp_path: Path,
) -> None:
    provider = _provider(
        {"/historical/": FakeResponse(_snapshot(["player_points"]))}
    )

    buy = hist.buy_historical_props(
        provider,
        events=[{"event_id": "", "snapshot": ""}],
        markets=["player_points"],
        credit_cap=100,
        raw_dir=tmp_path,
    )

    assert buy.rows == []
    assert buy.errors


def test_one_failing_event_does_not_lose_the_rest(tmp_path: Path) -> None:
    calls = {"n": 0}

    def answer(url: str, **kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(status_code=500)
        return FakeResponse(_snapshot(["player_points"]))

    provider = OddsApiProvider(environment=ENVIRONMENT, requester=answer)

    buy = hist.buy_historical_props(
        provider,
        events=[
            {"event_id": "a", "snapshot": "2025-01-05T19:00:00Z"},
            {"event_id": "b", "snapshot": "2025-01-05T19:00:00Z"},
        ],
        markets=["player_points"],
        credit_cap=100,
        raw_dir=tmp_path,
    )

    assert buy.errors
    assert buy.rows


def test_buying_with_no_markets_is_refused(tmp_path: Path) -> None:
    provider = _provider({})

    with pytest.raises(ProviderError, match="at least one market"):
        hist.buy_historical_props(
            provider, events=[], markets=[], credit_cap=10, raw_dir=tmp_path
        )


def test_a_payload_without_the_data_wrapper_is_still_read(tmp_path: Path) -> None:
    """The endpoint's shape has varied; a bare event must still parse."""
    provider = _provider(
        {"/historical/": FakeResponse(_snapshot(["player_points"])["data"])}
    )

    buy = hist.buy_historical_props(
        provider,
        events=[{"event_id": "evt1", "snapshot": "2025-01-05T19:00:00Z"}],
        markets=["player_points"],
        credit_cap=100,
        raw_dir=tmp_path,
    )

    assert buy.rows


def test_the_cache_write_is_atomic(tmp_path: Path) -> None:
    provider = _provider(
        {"/historical/": FakeResponse(_snapshot(["player_points"]))}
    )

    hist.buy_historical_props(
        provider,
        events=[{"event_id": "evt1", "snapshot": "2025-01-05T19:00:00Z"}],
        markets=["player_points"],
        credit_cap=100,
        raw_dir=tmp_path,
    )

    directory = tmp_path / hist.CACHE_DIRNAME
    assert list(directory.glob("*.partial")) == []
    assert list(directory.glob("*.json"))
