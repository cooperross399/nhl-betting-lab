"""A price board without today's games read as an off-day on a game day.

`fetch_team_markets` raises a plain `EmptySlateError` when the provider
answers HTTP 200 with upcoming games and none of them falls on the fetch
window's league day(s). That is right on an ordinary off-day: the league
plays most nights, not every night. But `run_provider_shadow.py` asked the
cached NHL schedule only about the other empty-slate verdict (a 422 to the
market list and to a plain moneyline, `NoOddsServedError`). Every other
`EmptySlateError` went straight to exit 3, which Gameday Refresh records as
`empty_slate=true`; the health step wrote `degraded=false`, no card was
posted, no snapshot was frozen, card-feed published a clean status and the
15:00 backup stood down. All green.

So on a day the schedule the run had just cached listed three regular-season
games, a board carrying only tomorrow's game (a provider or region glitch,
or books pulling today's lines) cost the day's card and its opinions in the
forward ledger, exactly the failure the 422 fix closed by another door
(sweep 4, offday-board-on-scheduled-game-day-reads-as-empty-slate).

What these tests hold:

* on a day the cached schedule lists regular-season games still to face off,
  a board without them is a failed fetch (exit 2, degraded, the backup
  runs), and the script says how many the schedule lists;
* a true off-day (nothing scheduled, or exhibitions only) is still exit 3;
* a game that has already faced off does not count: a late dispatch after
  the day's games are over sees a board of tomorrow's games, and that is
  not a fault;
* with no schedule cached, or a cache with holes that lists nothing today,
  the verdict stays exit 3 as before, and the script says the schedule
  could not vouch for it.

The backup that exit 2 lets run spends its own budgeted fetch (about 326
credits at the 320 per-event cap plus the bulk markets). That is the
designed response to any failed fetch, not a new spend.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import FakeResponse
from test_a_failed_moneyline_check_is_not_the_off_season import (
    TODAY,
    _price_and_health,
    _shadow,
    _tonight,
)

TOMORROW = "2026-10-08"


class Board:
    """The bulk `/odds` request answers HTTP 200 with `events`. Anything else
    is refused as unexpected: no per-event request is made from a board that
    has nothing in the window."""

    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.calls: list[str] = []

    def __call__(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(url)
        if url.endswith("/odds") and "/events/" not in url:
            return FakeResponse(self.events)
        raise AssertionError(f"unexpected request: {url}")


def _tomorrows_board() -> Board:
    return Board([{
        "id": "evt-tomorrow",
        "sport_key": "icehockey_nhl",
        "commence_time": f"{TOMORROW}T23:00:00Z",
        "home_team": "Boston Bruins",
        "away_team": "Buffalo Sabres",
        "bookmakers": [],
    }])


def test_a_board_without_todays_scheduled_games_is_a_failed_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, err = _shadow(tmp_path, monkeypatch, _tomorrows_board(), _tonight())

    assert code == 2, (out, err)
    assert "No slate" not in out
    assert "3 regular-season game(s)" in err and TODAY in err, err


def test_through_the_workflow_it_is_a_degraded_run_the_backup_repeats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, _, _ = _shadow(tmp_path, monkeypatch, _tomorrows_board(), _tonight())

    outcome, prices, health = _price_and_health(tmp_path, code)

    assert health["degraded"] == "true", (code, outcome, prices)
    assert outcome == "failure"
    assert prices.get("empty_slate", "") != "true"


@pytest.mark.parametrize(
    "schedule",
    [_tonight(day=TOMORROW), _tonight(game_type=1)],
    ids=["nothing-scheduled-today", "exhibitions-only-today"],
)
def test_a_true_off_day_is_still_an_empty_slate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schedule
) -> None:
    code, out, err = _shadow(tmp_path, monkeypatch, _tomorrows_board(), schedule)

    assert code == 3, err
    assert "No slate" in out


def test_games_that_have_faced_off_do_not_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At 23:30 ET every game tonight faced off at 19:00 ET (23:00Z) and is
    over; the board has moved on to tomorrow. A late dispatch is not a
    fault."""
    import test_a_failed_moneyline_check_is_not_the_off_season as base

    late = datetime(2026, 10, 8, 3, 30, tzinfo=timezone.utc)  # 23:30 ET on the 7th
    monkeypatch.setattr(base, "NOW", late)
    code, out, err = _shadow(tmp_path, monkeypatch, _tomorrows_board(), _tonight())

    assert code == 3, err
    assert "No slate" in out


def test_with_no_schedule_cached_the_verdict_stands_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, err = _shadow(tmp_path, monkeypatch, _tomorrows_board(), [])

    assert code == 3, err
    assert "No slate" in out
    assert "schedule" in out and "cannot confirm" in out, out
