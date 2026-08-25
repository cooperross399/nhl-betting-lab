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


def test_the_upper_bound_is_pessimistic_on_purpose() -> None:
    """The provider documents 10x for the bulk historical endpoint and is
    ambiguous about the per-event one. Assuming the expensive reading means
    the cap can only ever be over-respected."""
    assert hist.HISTORICAL_CREDITS_UPPER_BOUND_PER_MARKET == 10


def test_the_estimate_is_the_upper_bound_not_a_prediction() -> None:
    assert hist.estimate_credits(events=12, markets=6) == 720


def test_the_cost_note_states_a_range_rather_than_a_number() -> None:
    note = hist.cost_note(events=12, markets=6)

    assert "between **72**" in note
    assert "720 credits" in note
    assert "ambiguous" in note
    assert "x-requests-last" in note


def test_the_cost_note_says_the_cap_cannot_be_breached() -> None:
    assert "cannot be breached" in hist.cost_note(events=1, markets=1)


def test_the_measured_cost_is_read_from_the_response_header(
    tmp_path: Path,
) -> None:
    """Not estimated. The whole point of the rewrite."""
    provider = _provider(
        {
            "/historical/": FakeResponse(
                _snapshot(["player_points"]),
                headers={"x-requests-last": "1", "x-requests-remaining": "4999"},
            )
        }
    )

    probe = hist.probe_retention(
        provider,
        event_id="evt1",
        snapshot="2025-01-05T19:00:00Z",
        markets=["player_points"],
        raw_dir=tmp_path,
    )

    assert probe.credits_spent == 1
    assert probe.credits_estimated == 10
    assert probe.credits_remaining == "4999"


def test_a_missing_cost_header_falls_back_to_the_pessimistic_estimate(
    tmp_path: Path,
) -> None:
    """An unreadable response must never make a run look cheaper than it was."""
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


def test_the_probe_reports_the_real_per_market_rate(tmp_path: Path) -> None:
    provider = _provider(
        {
            "/historical/": FakeResponse(
                _snapshot(["player_points", "player_shots_on_goal"]),
                headers={"x-requests-last": "2"},
            )
        }
    )

    probe = hist.probe_retention(
        provider,
        event_id="evt1",
        snapshot="2025-01-05T19:00:00Z",
        markets=["player_points", "player_shots_on_goal"],
        raw_dir=tmp_path,
    )

    assert probe.measured_cost_per_market == pytest.approx(1.0)
    assert "1 credit(s) per market returned" in probe.summary_line()
    assert "against an assumed upper bound of 10" in probe.summary_line()


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
        {
            "/historical/": FakeResponse(
                _snapshot(["player_points"]),
                headers={"x-requests-last": "1", "x-requests-remaining": "4999"},
            )
        }
    )

    probe = hist.probe_retention(
        provider,
        event_id="evt1",
        snapshot="2025-01-05T19:00:00Z",
        markets=["player_points"],
        raw_dir=tmp_path,
    )

    assert "1 credit(s) actually spent" in probe.summary_line()
    assert "4999 remaining" in probe.summary_line()


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


# -- listing a past window ---------------------------------------------


def _events_listing(events: list[dict]) -> dict:
    return {
        "timestamp": "2025-01-05T12:00:00Z",
        "previous_timestamp": "2025-01-05T11:55:00Z",
        "next_timestamp": "2025-01-05T12:05:00Z",
        "data": events,
    }


def test_a_past_window_is_listed_from_the_historical_endpoint(
    tmp_path: Path,
) -> None:
    """The live events endpoint only knows about upcoming games. Pointing it
    at a past window returns nothing, which looks exactly like 'the provider
    has no data' and is not."""
    requester = RecordingRequester(
        {
            "/historical/sports/icehockey_nhl/events": FakeResponse(
                _events_listing(
                    [
                        {
                            "id": "evt1",
                            "commence_time": "2025-01-05T23:00:00Z",
                            "home_team": "Toronto Maple Leafs",
                            "away_team": "Boston Bruins",
                        }
                    ]
                ),
                headers={"x-requests-last": "1", "x-requests-remaining": "4999"},
            )
        }
    )
    provider = OddsApiProvider(environment=ENVIRONMENT, requester=requester)

    events, cost, remaining = hist.list_historical_events(
        provider, snapshot="2025-01-05T12:00:00Z", raw_dir=tmp_path
    )

    assert [event["id"] for event in events] == ["evt1"]
    assert cost == 1
    assert remaining == "4999"
    assert "/v4/historical/sports/icehockey_nhl/events" in requester.urls[0]


def test_the_listing_sends_the_snapshot_date(tmp_path: Path) -> None:
    requester = RecordingRequester(
        {"/historical/": FakeResponse(_events_listing([]))}
    )
    provider = OddsApiProvider(environment=ENVIRONMENT, requester=requester)

    hist.list_historical_events(
        provider, snapshot="2025-01-05T12:00:00Z", raw_dir=tmp_path
    )

    _, kwargs = requester.calls[0]
    assert kwargs["params"]["date"] == "2025-01-05T12:00:00Z"


def test_a_cached_listing_costs_nothing(tmp_path: Path) -> None:
    requester = RecordingRequester(
        {"/historical/": FakeResponse(_events_listing([{"id": "evt1"}]))}
    )
    provider = OddsApiProvider(environment=ENVIRONMENT, requester=requester)

    hist.list_historical_events(
        provider, snapshot="2025-01-05T12:00:00Z", raw_dir=tmp_path
    )
    _, cost, _ = hist.list_historical_events(
        provider, snapshot="2025-01-05T12:00:00Z", raw_dir=tmp_path
    )

    assert cost == 0
    assert len(requester.calls) == 1


def test_an_empty_listing_is_not_an_error(tmp_path: Path) -> None:
    """Documented as free when it finds nothing, and the offseason is real."""
    provider = _provider({"/historical/": FakeResponse(_events_listing([]))})

    events, _, _ = hist.list_historical_events(
        provider, snapshot="2026-07-04T12:00:00Z", raw_dir=tmp_path
    )

    assert events == []


# -- the cap ------------------------------------------------------------


def test_the_cap_is_enforced_against_the_upper_bound_not_the_real_cost(
    tmp_path: Path,
) -> None:
    """A cap checked against the cheap reading could be breached if the
    expensive reading turns out to be the true one."""
    provider = _provider(
        {
            "/historical/": FakeResponse(
                _snapshot(["player_points"]), headers={"x-requests-last": "1"}
            )
        }
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

    # Worst case is 10 a request, so the cap allows two and stops.
    assert buy.events_bought == 2
    assert buy.events_skipped_for_budget == 8
    # But the measured spend is what gets reported.
    assert buy.credits_spent == 2


def test_a_failed_request_still_counts_against_the_cap(tmp_path: Path) -> None:
    """Assuming a failure was free is how a run of failures walks past its cap."""
    provider = _provider({"/historical/": FakeResponse(status_code=500)})
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

    assert len(buy.errors) == 2
    assert buy.events_skipped_for_budget == 8


def test_the_buy_reports_the_measured_rate_per_event(tmp_path: Path) -> None:
    provider = _provider(
        {
            "/historical/": FakeResponse(
                _snapshot(["player_points", "player_shots_on_goal"]),
                headers={"x-requests-last": "2", "x-requests-remaining": "4998"},
            )
        }
    )

    buy = hist.buy_historical_props(
        provider,
        events=[{"event_id": "evt1", "snapshot": "2025-01-05T19:00:00Z"}],
        markets=["player_points", "player_shots_on_goal"],
        credit_cap=100,
        raw_dir=tmp_path,
    )

    assert buy.credits_per_event == pytest.approx(2.0)
    assert "2 credit(s) actually spent" in buy.summary_line()
    assert "4998 remaining" in buy.summary_line()


def test_the_measured_rate_is_recorded_in_the_module() -> None:
    """Probed 2026-08-25: six markets requested, five returned, 50 credits.
    The pessimistic reading of the documentation was the right one."""
    text = " ".join(hist.__doc__.split())

    assert "ten credits per market returned" in text
    assert "x-requests-last` said 50" in text


def test_the_upper_bound_still_matches_what_was_measured() -> None:
    """If these ever diverge, the cap stops being conservative."""
    assert hist.HISTORICAL_CREDITS_UPPER_BOUND_PER_MARKET == 10
    assert hist.estimate_credits(events=1, markets=5) == 50
