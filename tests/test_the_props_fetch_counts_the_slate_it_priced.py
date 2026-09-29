"""The per-event fetch's "X of Y events" counts the slate it priced.

`fetch_player_props` set `events_seen` from the whole posted `/events` board
and never updated it after the league-day window or the started-game drop.
Only the preseason screen overwrote it, and only when it dropped an event.
So on a night with two unstarted games the summary line Line Movement prints
every round, and the shadow run prints as "Per-event markets: ...", read
"from 2 of 13 events" (every game posted this week, plus one already under
way): a coverage gap of eleven games that were never on the slate. With one
exhibition screened out the same night read "from 1 of 1". The denominator's
meaning flipped on whether an exhibition was on the board.

`fetch_team_markets` resets the count after the window and after the drop,
and now so does the per-event fetch: Y is always the windowed, unstarted
(and screened) slate the cap was spent on.

The transport is a stub. Nothing reaches the network, and no credit is spent.
"""

from __future__ import annotations

from datetime import datetime, timezone

from nhl_betting_lab.providers import odds_api


#: 17:00 in New York on 2026-10-07.
NOW = datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)
TONIGHT = "2026-10-07"
MARKET = "player_shots_on_goal"


class _Response:
    status_code = 200
    headers: dict = {}

    def __init__(self, payload) -> None:
        self._payload = payload

    def json(self):
        return self._payload


def _event(index: int, start: str) -> dict:
    return {"id": f"e{index}", "commence_time": start,
            "home_team": "Winnipeg Jets", "away_team": "Colorado Avalanche"}


#: One game already under way, two still to play tonight, ten on later days.
STARTED = [_event(0, f"{TONIGHT}T20:00:00Z")]
TONIGHT_GAMES = [_event(i, f"{TONIGHT}T23:00:00Z") for i in (1, 2)]
LATER = [_event(i, f"2026-10-{8 + i:02d}T23:00:00Z") for i in range(3, 13)]
BOARD = STARTED + TONIGHT_GAMES + LATER


def _requester(url, **_kwargs):
    if url.endswith("/events"):
        return _Response(BOARD)
    event_id = url.split("/events/")[1].split("/")[0]
    event = next(e for e in BOARD if e["id"] == event_id)
    return _Response({**event, "bookmakers": [{
        "key": "draftkings", "title": "DraftKings", "markets": [{
            "key": MARKET, "outcomes": [{
                "name": "Over", "description": "Kyle Connor",
                "point": 2.5, "price": -110,
            }],
        }],
    }]})


def _fetch(**kwargs):
    provider = odds_api.OddsApiProvider(
        environment={"NHL_ODDS_API_KEY": "stub-credential-never-sent"},
        requester=_requester,
    )
    return provider.fetch_player_props(
        markets=[MARKET], credit_cap=1000, now=NOW, **kwargs
    )


def test_a_windowed_night_counts_tonight_s_unstarted_games() -> None:
    result = _fetch(league_days=[TONIGHT])
    assert result.events_priced == 2
    assert result.events_seen == 2, result.summary_line()
    assert "from 2 of 2 events" in result.summary_line()


def test_the_count_means_the_same_whether_or_not_the_screen_dropped_one() -> None:
    kept_all = _fetch(league_days=[TONIGHT], keep_event=lambda event: True)
    screened = _fetch(league_days=[TONIGHT], keep_event=lambda e: e["id"] != "e2")
    assert kept_all.events_seen == 2
    assert screened.events_seen == 1


def test_a_started_game_is_not_on_the_slate_without_a_window_either() -> None:
    """No window (the Discovery probe): the whole board, less the game under way."""
    result = _fetch()
    assert result.events_already_started == 1
    assert result.events_seen == len(BOARD) - 1, result.summary_line()


def test_the_window_alone_narrows_the_count() -> None:
    """A clock before every face-off: nothing started, so only the window acts."""
    provider = odds_api.OddsApiProvider(
        environment={"NHL_ODDS_API_KEY": "stub-credential-never-sent"},
        requester=_requester,
    )
    result = provider.fetch_player_props(
        markets=[MARKET], credit_cap=1000, league_days=[TONIGHT],
        now=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
    )
    assert result.events_already_started == 0
    assert result.events_seen == 3, result.summary_line()


def test_the_event_cap_is_the_slate_as_the_bulk_fetch_counts_it() -> None:
    """`--max-events` narrows Y as it does in `fetch_team_markets`.

    Provider Market Discovery runs `--horizon-days 0 --max-events 20`. With no
    window and a clock before every face-off, a cap of 2 on this 13-game
    board read "from 2 of 13 events" beside the bulk fetch's "2 of 2": eleven
    games never in scope, read as a coverage gap.
    """
    provider = odds_api.OddsApiProvider(
        environment={"NHL_ODDS_API_KEY": "stub-credential-never-sent"},
        requester=_requester,
    )
    result = provider.fetch_player_props(
        markets=[MARKET], credit_cap=1000, max_events=2,
        now=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
    )
    assert result.events_already_started == 0
    assert result.events_priced == 2
    assert result.events_seen == 2, result.summary_line()
    assert "from 2 of 2 events" in result.summary_line()


def test_a_cap_above_the_slate_leaves_the_count_alone() -> None:
    """A cap the slate never reaches truncates nothing and counts nothing new."""
    result = _fetch(league_days=[TONIGHT], max_events=20)
    assert result.events_seen == 2, result.summary_line()
