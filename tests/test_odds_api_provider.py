from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.providers import odds_api


SECRET = "props-secret-must-not-be-written"
ENVIRONMENT = {"NHL_ODDS_API_KEY": SECRET}


def _event(
    *,
    event_id: str = "evt1",
    home: str = "Toronto Maple Leafs",
    away: str = "Boston Bruins",
    commence: str = "2026-10-09T23:00:00Z",
    markets: list[dict] | None = None,
    book: str = "DraftKings",
) -> dict:
    return {
        "id": event_id,
        "commence_time": commence,
        "home_team": home,
        "away_team": away,
        "bookmakers": [
            {"key": book.lower(), "title": book, "markets": markets or []}
        ],
    }


def _h2h(home: str = "Toronto Maple Leafs", away: str = "Boston Bruins") -> dict:
    return {
        "key": "h2h",
        "outcomes": [
            {"name": home, "price": -140},
            {"name": away, "price": 120},
        ],
    }


def _shots(player: str = "Auston Matthews", line: float = 3.5) -> dict:
    return {
        "key": "player_shots_on_goal",
        "outcomes": [
            {"name": "Over", "description": player, "price": -115, "point": line},
            {"name": "Under", "description": player, "price": -105, "point": line},
        ],
    }


# -- configuration -----------------------------------------------------


def test_the_default_sport_key_is_the_nhl_one() -> None:
    provider = odds_api.OddsApiProvider(environment=ENVIRONMENT)

    assert provider.sport_key == "icehockey_nhl"


@pytest.mark.parametrize(
    "base",
    [
        "http://api.the-odds-api.com",
        "https://evil.example.com",
        "https://api.the-odds-api.com/v4",
        "https://user:pass@api.the-odds-api.com",
    ],
)
def test_the_credential_is_never_pointed_at_another_host(base: str) -> None:
    with pytest.raises(odds_api.ProviderError, match="approved The Odds API"):
        odds_api.OddsApiProvider(
            environment={**ENVIRONMENT, "NHL_ODDS_API_BASE_URL": base}
        )


@pytest.mark.parametrize("sport", ["icehockey nhl", "../v4", "NHL"])
def test_an_unsafe_sport_key_is_refused(sport: str) -> None:
    with pytest.raises(odds_api.ProviderError, match="unsafe characters"):
        odds_api.OddsApiProvider(environment=ENVIRONMENT, sport_key=sport)


def test_an_unsafe_bookmaker_list_is_refused() -> None:
    with pytest.raises(odds_api.ProviderError, match="lowercase keys"):
        odds_api.OddsApiProvider(environment=ENVIRONMENT, bookmakers="DK;drop")


def test_a_non_positive_timeout_is_refused() -> None:
    with pytest.raises(odds_api.ProviderError, match="timeout"):
        odds_api.OddsApiProvider(environment=ENVIRONMENT, timeout_seconds=0)


def test_the_public_configuration_reports_presence_never_the_value() -> None:
    provider = odds_api.OddsApiProvider(environment=ENVIRONMENT)

    config = provider.public_configuration()

    assert config["credential_present"] is True
    assert SECRET not in json.dumps(config)


def test_a_missing_credential_blocks_a_live_fetch_before_any_request() -> None:
    requester = RecordingRequester()
    provider = odds_api.OddsApiProvider(environment={}, requester=requester)

    with pytest.raises(odds_api.MissingCredentialError, match="NHL_ODDS_API_KEY"):
        provider.list_events()

    assert requester.calls == []


def test_the_error_never_suggests_passing_the_key_as_an_argument() -> None:
    provider = odds_api.OddsApiProvider(environment={})

    with pytest.raises(odds_api.MissingCredentialError) as exc:
        provider.list_events()

    assert "never commit it" in str(exc.value)


# -- prices ------------------------------------------------------------


@pytest.mark.parametrize("price", [0, 50, -99, "", None, "abc", True])
def test_an_unusable_price_is_dropped_rather_than_guessed(price: object) -> None:
    assert odds_api.american_price(price) is None


def test_a_valid_price_survives() -> None:
    assert odds_api.american_price("-115") == -115.0


def test_moneyline_outcomes_map_to_home_and_away() -> None:
    rows = odds_api.normalize_event(
        _event(markets=[_h2h()]), fetched_at="2026-10-08T12:00:00+00:00"
    )

    assert {row["selection"] for row in rows} == {"home", "away"}
    assert {row["market"] for row in rows} == {"moneyline"}


def test_a_moneyline_outcome_that_is_neither_team_is_dropped() -> None:
    """NHL moneylines have no draw; an unknown label is not guessed at."""
    market = {"key": "h2h", "outcomes": [{"name": "Draw", "price": 400}]}

    rows = odds_api.normalize_event(_event(markets=[market]), fetched_at="now")

    assert rows == []


def test_prop_rows_carry_the_player_and_the_line() -> None:
    rows = odds_api.normalize_event(
        _event(markets=[_shots()]), fetched_at="2026-10-08T12:00:00+00:00"
    )

    assert all(row["player"] == "Auston Matthews" for row in rows)
    assert all(row["line"] == 3.5 for row in rows)
    assert {row["selection"] for row in rows} == {"over", "under"}


def test_a_prop_outcome_with_no_player_is_unusable_and_dropped() -> None:
    """It cannot be settled and cannot be matched to a model opinion."""
    market = {
        "key": "player_points",
        "outcomes": [{"name": "Over", "price": -110, "point": 0.5}],
    }

    assert odds_api.normalize_event(_event(markets=[market]), fetched_at="now") == []


def test_a_market_this_lab_does_not_price_is_skipped_not_an_error() -> None:
    market = {"key": "team_totals", "outcomes": [{"name": "Over", "price": -110}]}

    rows = odds_api.normalize_event(
        _event(markets=[market, _h2h()]), fetched_at="now"
    )

    assert {row["market"] for row in rows} == {"moneyline"}


def test_alternate_ladders_land_in_the_same_project_market() -> None:
    market = {
        "key": "alternate_totals",
        "outcomes": [
            {"name": "Over", "price": 150, "point": 6.5},
            {"name": "Under", "price": -180, "point": 6.5},
        ],
    }

    rows = odds_api.normalize_event(_event(markets=[market]), fetched_at="now")

    assert {row["market"] for row in rows} == {"total_goals"}
    assert {row["line"] for row in rows} == {6.5}


def test_every_book_is_kept_not_just_the_best_price() -> None:
    """Keeping only the best makes "best" mean "best at fetch time" forever."""
    event = _event(markets=[_h2h()])
    event["bookmakers"].append(
        {"key": "fanduel", "title": "FanDuel", "markets": [_h2h()]}
    )

    rows = odds_api.normalize_event(event, fetched_at="now")

    assert {row["book"] for row in rows} == {"DraftKings", "FanDuel"}


def test_an_event_with_no_teams_produces_nothing() -> None:
    assert odds_api.normalize_event({"id": "x"}, fetched_at="now") == []


def test_the_commence_time_travels_with_every_row() -> None:
    """The puck-drop guard reads it; a row without one gets quarantined."""
    rows = odds_api.normalize_event(_event(markets=[_h2h()]), fetched_at="now")

    assert all(row["commence_time"] == "2026-10-09T23:00:00Z" for row in rows)
    assert all(row["date"] == "2026-10-09" for row in rows)


# -- fetching ----------------------------------------------------------


def test_a_team_market_fetch_stages_rows_and_counts_credits() -> None:
    requester = RecordingRequester(
        {
            "/odds": FakeResponse(
                [_event(markets=[_h2h()])],
                headers={"x-requests-remaining": "19000"},
            )
        }
    )
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    result = provider.fetch_team_markets(fetched_at="now")

    assert len(result.rows) == 2
    assert result.credits_spent == len(odds_api.BULK_PROVIDER_MARKETS)
    assert result.quota_remaining == "19000"


def test_the_bulk_fetch_asks_only_for_markets_that_endpoint_serves() -> None:
    """Asking for an alternate ladder here makes the provider refuse the
    entire request with a 422 that names nothing."""
    requester = RecordingRequester({"/odds": FakeResponse([])})
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    provider.fetch_team_markets(fetched_at="now")

    _, kwargs = requester.calls[0]
    requested = kwargs["params"]["markets"].split(",")
    assert requested == list(odds_api.BULK_PROVIDER_MARKETS)
    assert not any(item.startswith("alternate_") for item in requested)


def test_the_alternate_ladders_are_still_fetched_somewhere() -> None:
    """Dropping them would repeat the EPL `total_2_5` mistake: the complete
    line lives in the alternate ladder and the bulk endpoint never shows it."""
    assert odds_api.ALTERNATE_PROVIDER_MARKETS
    assert all(
        market.startswith("alternate_")
        for market in odds_api.ALTERNATE_PROVIDER_MARKETS
    )


def test_an_http_error_writes_no_staging_file() -> None:
    requester = RecordingRequester({"/odds": FakeResponse(status_code=429)})
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    with pytest.raises(odds_api.ProviderError, match="429"):
        provider.fetch_team_markets()


def test_an_unreachable_provider_message_carries_no_credential() -> None:
    def explode(url: str, **kwargs: object) -> object:
        raise requests.ConnectionError(f"failed for apiKey={SECRET}")

    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=explode
    )

    with pytest.raises(odds_api.ProviderError) as exc:
        provider.fetch_team_markets()

    assert SECRET not in str(exc.value)


def test_a_slate_with_no_usable_prices_warns_rather_than_inventing() -> None:
    requester = RecordingRequester({"/odds": FakeResponse([_event(markets=[])])})
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    result = provider.fetch_team_markets()

    assert result.rows == []
    assert any("Nothing was guessed" in item for item in result.warnings)


# -- props and cost ----------------------------------------------------


def test_the_props_cost_is_one_credit_per_market_per_event() -> None:
    provider = odds_api.OddsApiProvider(environment=ENVIRONMENT)

    assert provider.estimate_prop_credits(events=12) == 12 * len(
        odds_api.PROP_PROVIDER_MARKETS
    )
    assert provider.estimate_prop_credits(events=3, markets=["player_points"]) == 3


def _props_requester(events: int) -> RecordingRequester:
    listing = [{"id": f"evt{index}"} for index in range(events)]
    return RecordingRequester(
        {
            "/events/": FakeResponse(_event(markets=[_shots()])),
            "/events": FakeResponse(listing),
        }
    )


def test_a_props_fetch_stops_at_the_credit_cap() -> None:
    """A probe that quietly became a full-slate fetch is the accident here."""
    requester = _props_requester(10)
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    result = provider.fetch_player_props(
        markets=["player_shots_on_goal", "player_points"], credit_cap=6
    )

    assert result.credits_spent <= 6
    assert any("cap would have been exceeded" in item for item in result.warnings)


def test_the_cap_warning_says_the_markets_are_absent_not_empty() -> None:
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=_props_requester(5)
    )

    result = provider.fetch_player_props(markets=["player_points"], credit_cap=2)

    assert any("absent, not empty" in item for item in result.warnings)


def test_max_events_limits_the_fetch_independently_of_the_cap() -> None:
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=_props_requester(10)
    )

    result = provider.fetch_player_props(
        markets=["player_points"], max_events=2, credit_cap=100
    )

    assert result.credits_spent == 2


def test_one_failing_event_does_not_lose_the_rest() -> None:
    calls = {"n": 0}

    def answer(url: str, **kwargs: object) -> object:
        if url.endswith("/events"):
            return FakeResponse([{"id": "a"}, {"id": "b"}])
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(status_code=500)
        return FakeResponse(_event(markets=[_shots()]))

    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=answer
    )

    result = provider.fetch_player_props(markets=["player_points"], credit_cap=50)

    assert result.errors and "500" in result.errors[0]
    assert result.events_priced == 1


def test_a_props_fetch_with_no_markets_is_refused() -> None:
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=_props_requester(1)
    )

    with pytest.raises(odds_api.ProviderError, match="at least one market"):
        provider.fetch_player_props(markets=[])


# -- staging -----------------------------------------------------------


def test_staging_refuses_to_overwrite_evidence_by_accident(tmp_path: Path) -> None:
    rows = odds_api.normalize_event(_event(markets=[_h2h()]), fetched_at="now")
    odds_api.write_staging(rows, filename="x.csv", staging_dir=tmp_path)

    with pytest.raises(odds_api.ProviderError, match="already exists"):
        odds_api.write_staging(rows, filename="x.csv", staging_dir=tmp_path)


def test_staging_overwrites_when_asked_explicitly(tmp_path: Path) -> None:
    rows = odds_api.normalize_event(_event(markets=[_h2h()]), fetched_at="now")
    odds_api.write_staging(rows, filename="x.csv", staging_dir=tmp_path)

    path = odds_api.write_staging(
        rows, filename="x.csv", staging_dir=tmp_path, overwrite=True
    )

    assert path.is_file()


def test_an_empty_staging_file_still_has_the_full_column_set(tmp_path: Path) -> None:
    import pandas as pd

    path = odds_api.write_staging([], filename="empty.csv", staging_dir=tmp_path)

    assert list(pd.read_csv(path).columns) == list(odds_api.PRICE_COLUMNS)


def test_provenance_records_the_run_without_the_credential(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NHL_ODDS_API_KEY", SECRET)
    provider = odds_api.OddsApiProvider(environment=ENVIRONMENT)
    result = odds_api.FetchResult(
        fetched_at="2026-10-08T12:00:00+00:00", credits_spent=9
    )

    path = odds_api.write_provenance(
        result,
        configuration=provider.public_configuration(),
        staging_files=[tmp_path / "x.csv"],
        staging_dir=tmp_path,
    )
    text = path.read_text(encoding="utf-8")

    assert SECRET not in text
    assert json.loads(text)["shadow_only"] is True
    assert json.loads(text)["credits_spent"] == 9


def test_provenance_says_staging_allowlists_nothing(tmp_path: Path) -> None:
    path = odds_api.write_provenance(
        odds_api.FetchResult(fetched_at="now"),
        configuration={},
        staging_files=[],
        staging_dir=tmp_path,
    )

    assert "reviewed human approval" in path.read_text(encoding="utf-8")


def test_the_frame_has_a_stable_column_order() -> None:
    rows = odds_api.normalize_event(_event(markets=[_h2h()]), fetched_at="now")

    assert list(odds_api.to_frame(rows).columns) == list(odds_api.PRICE_COLUMNS)


# -- the off-season -----------------------------------------------------


def test_no_odds_at_all_is_reported_as_an_empty_slate() -> None:
    """Refusing even a plain moneyline means the provider is serving no NHL
    odds, which is the ordinary state between seasons."""
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT,
        requester=RecordingRequester({"/odds": FakeResponse(status_code=422)}),
    )

    with pytest.raises(odds_api.EmptySlateError, match="not a fault"):
        provider.fetch_team_markets()


def test_a_bad_market_key_is_a_request_problem_not_an_off_season() -> None:
    """Reading "your markets parameter is wrong" as "the season has not
    started" would hide a real bug for months."""
    calls = {"n": 0}

    def answer(url: str, **kwargs: object) -> object:
        if "/odds" not in url:
            return FakeResponse(status_code=404)
        calls["n"] += 1
        # The full market list is refused; a plain moneyline is served.
        if kwargs["params"]["markets"] == "h2h":
            return FakeResponse([])
        return FakeResponse(status_code=422)

    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=answer
    )

    with pytest.raises(odds_api.ProviderError) as exc:
        provider.fetch_team_markets()

    assert not isinstance(exc.value, odds_api.EmptySlateError)
    assert "not a market it serves" in str(exc.value)
    assert calls["n"] == 2


def test_a_listed_schedule_does_not_prevent_an_empty_slate_verdict() -> None:
    """Through September the October schedule is listed while no book has
    priced anything, so "events exist" is true in exactly the case being
    tested for."""
    def answer(url: str, **kwargs: object) -> object:
        if "/events" in url:
            return FakeResponse([{"id": "evt1", "commence_time": "2026-10-08T23:00:00Z"}])
        return FakeResponse(status_code=422)

    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=answer
    )

    with pytest.raises(odds_api.EmptySlateError):
        provider.fetch_team_markets()


def test_an_empty_slate_error_is_still_a_provider_error() -> None:
    """So a caller that does not care about the distinction still catches it."""
    assert issubclass(odds_api.EmptySlateError, odds_api.ProviderError)


def test_other_statuses_are_never_read_as_an_empty_slate() -> None:
    requester = RecordingRequester(
        {"/odds": FakeResponse(status_code=500), "/events": FakeResponse([])}
    )
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    with pytest.raises(odds_api.ProviderError) as exc:
        provider.fetch_team_markets()

    assert not isinstance(exc.value, odds_api.EmptySlateError)


def test_the_empty_slate_check_does_not_depend_on_the_events_endpoint() -> None:
    """It was the first thing tried and it answered the wrong question."""
    calls: list[str] = []

    def answer(url: str, **kwargs: object) -> object:
        calls.append(url)
        return FakeResponse(status_code=422)

    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=answer
    )

    with pytest.raises(odds_api.EmptySlateError):
        provider.fetch_team_markets()

    assert not any("/events" in url for url in calls)
