"""A capped fetch spent its budget on a game already under way.

`OddsApiProvider.fetch_player_props` sorted the events list by start time and
bought front-to-back under `max_events` and the credit cap, and nothing
dropped a game that had already started (`list_events` asks for no
`commenceTimeFrom` either). A started game sorts first. On the 15:00 UTC
backup run an afternoon game in progress was bought before the evening slate,
the puck-drop guard then quarantined it on the card, and the games that could
still be played were the ones the cap left unpriced. `fetch_team_markets`
truncated its capped board by the same ordering, so it made the same choice.

What these tests hold:

* a game whose start is at or before `now` is dropped before the sort and
  the cap, in both fetches, so the budget buys the games still to be played;
* a game whose start time is missing, unparseable or naive is dropped too:
  ambiguity falls on the not-a-play side, as it does in `puck_drop`;
* both fetches drop the same games, so the slate the staged rows describe is
  one slate (a started game kept in the bulk rows and skipped per event would
  read as every per-event market missing one game);
* the count dropped is stated in the result's warnings, never silent;
* `now` must be an aware instant.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.providers import odds_api


ENVIRONMENT = {"NHL_ODDS_API_KEY": "k" * 24}

#: The 15:00 UTC backup run on a Saturday with an early game.
NOW = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)

#: 11:00 ET matinee, under way at 15:00 UTC; then the evening slate.
UNDER_WAY = ("evt_matinee", "2026-10-10T14:30:00Z")
AT_PUCK_DROP = ("evt_exact", "2026-10-10T15:00:00Z")
EVENING = [
    ("evt_1900", "2026-10-10T23:00:00Z"),
    ("evt_1930", "2026-10-10T23:30:00Z"),
    ("evt_2200", "2026-10-11T02:00:00Z"),
]


def _event(event_id: str, commence: object) -> dict:
    return {
        "id": event_id,
        "commence_time": commence,
        "home_team": f"Home {event_id}",
        "away_team": f"Away {event_id}",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": f"Home {event_id}", "price": -140},
                            {"name": f"Away {event_id}", "price": 120},
                        ],
                    }
                ],
            }
        ],
    }


def _requester(board: list[tuple[str, object]]) -> RecordingRequester:
    listing = [_event(event_id, commence) for event_id, commence in board]
    return RecordingRequester(
        {
            "/events/": lambda url, **_: FakeResponse(
                _event(url.split("/events/")[1].split("/")[0], "2026-10-10T23:00:00Z")
            ),
            "/events": FakeResponse(listing),
            "/odds": FakeResponse(listing),
        }
    )


def _bought(requester: RecordingRequester) -> list[str]:
    return [
        url.split("/events/")[1].split("/")[0]
        for url in requester.urls
        if "/events/" in url
    ]


def _provider(requester: RecordingRequester) -> odds_api.OddsApiProvider:
    return odds_api.OddsApiProvider(environment=ENVIRONMENT, requester=requester)


# -- the per-event fetch ------------------------------------------------


def test_the_capped_per_event_fetch_buys_the_evening_slate_not_the_game_under_way() -> None:
    requester = _requester([UNDER_WAY, *EVENING])

    result = _provider(requester).fetch_player_props(
        markets=["player_points"], max_events=2, credit_cap=100, now=NOW
    )

    assert _bought(requester) == ["evt_1900", "evt_1930"]
    assert result.events_already_started == 1


def test_the_credit_cap_is_spent_on_games_still_to_be_played() -> None:
    requester = _requester([UNDER_WAY, *EVENING])

    provider = _provider(requester)
    two_games = provider.estimate_prop_credits(events=2, markets=["player_points"])

    result = provider.fetch_player_props(
        markets=["player_points"], credit_cap=two_games, now=NOW
    )

    assert _bought(requester) == ["evt_1900", "evt_1930"]
    assert result.credits_spent == two_games


def test_a_game_starting_exactly_now_has_started() -> None:
    requester = _requester([AT_PUCK_DROP, *EVENING])

    _provider(requester).fetch_player_props(
        markets=["player_points"], max_events=1, credit_cap=100, now=NOW
    )

    assert _bought(requester) == ["evt_1900"]


@pytest.mark.parametrize(
    "commence",
    ["", None, "tonight", "2026-10-10T23:00:00"],
    ids=["blank", "missing", "unparseable", "naive"],
)
def test_a_start_time_that_cannot_be_confirmed_is_not_bought(commence: object) -> None:
    requester = _requester([("evt_unknown", commence), *EVENING])

    result = _provider(requester).fetch_player_props(
        markets=["player_points"], credit_cap=100, now=NOW
    )

    assert "evt_unknown" not in _bought(requester)
    assert result.events_already_started == 1


def test_the_dropped_count_is_stated_in_the_warnings() -> None:
    requester = _requester([UNDER_WAY, AT_PUCK_DROP, *EVENING])

    result = _provider(requester).fetch_player_props(
        markets=["player_points"], credit_cap=100, now=NOW
    )

    assert any(
        "2 event(s) had already started" in note for note in result.warnings
    ), result.warnings


def test_nothing_is_dropped_or_warned_about_before_any_game_starts() -> None:
    requester = _requester(EVENING)

    result = _provider(requester).fetch_player_props(
        markets=["player_points"], credit_cap=100, now=NOW
    )

    assert _bought(requester) == ["evt_1900", "evt_1930", "evt_2200"]
    assert result.events_already_started == 0
    assert not any("already started" in note for note in result.warnings)


def test_a_naive_now_is_refused() -> None:
    requester = _requester(EVENING)

    with pytest.raises(ValueError, match="naive"):
        _provider(requester).fetch_player_props(
            markets=["player_points"],
            credit_cap=100,
            now=NOW.replace(tzinfo=None),
        )


# -- the bulk fetch, and one slate across both ---------------------------


def test_the_capped_bulk_fetch_takes_the_same_games_still_to_be_played() -> None:
    requester = _requester([UNDER_WAY, *EVENING])

    result = _provider(requester).fetch_team_markets(max_events=2, now=NOW)

    games = {row["home_team"] for row in result.rows}
    assert games == {"Home evt_1900", "Home evt_1930"}
    assert result.events_seen == 2
    assert result.events_already_started == 1
    assert any("1 event(s) had already started" in n for n in result.warnings)


def test_both_fetches_describe_one_slate_when_a_game_is_under_way() -> None:
    board = [UNDER_WAY, *EVENING]
    bulk = _provider(_requester(board)).fetch_team_markets(now=NOW)
    per_event_requester = _requester(board)
    _provider(per_event_requester).fetch_player_props(
        markets=["player_points"], credit_cap=100, now=NOW
    )

    staged = {row["home_team"].removeprefix("Home ") for row in bulk.rows}
    assert staged == set(_bought(per_event_requester))
    assert "evt_matinee" not in staged


def test_without_a_now_the_fetch_reads_the_provider_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scripts pass no `now`; the default must still drop a started game."""
    monkeypatch.setattr(odds_api, "_provider_clock", lambda: NOW)
    requester = _requester([UNDER_WAY, *EVENING])

    _provider(requester).fetch_player_props(
        markets=["player_points"], max_events=1, credit_cap=100
    )

    assert _bought(requester) == ["evt_1900"]
