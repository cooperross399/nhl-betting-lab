"""The rule that decides which day a game belongs to.

The provider timestamps a game by when the puck drops, in UTC. The NHL
timestamps it by the day it is played. For a North American evening those are
different days, and roughly three quarters of the schedule is an evening game.

Getting this wrong is not a small error. Joining prices to results on the raw
UTC date discarded 69% of every price bought, and the survivors were
disproportionately afternoon games — weekend matinees, holiday specials,
national-TV windows — which is a systematically different set of fixtures from
a Tuesday night in Winnipeg.
"""

from __future__ import annotations

import pytest

from nhl_betting_lab.season import game_date


@pytest.mark.parametrize(
    ("commence", "expected"),
    [
        # 19:10 Eastern is the next morning in UTC. This is the common case:
        # most of the league plays here.
        ("2026-01-11T00:10:00Z", "2026-01-10"),
        # 22:00 Pacific is 01:00 Eastern the next day, and the NHL still calls
        # it the previous day's game.
        ("2026-01-11T06:00:00Z", "2026-01-11"),
        ("2026-01-11T03:00:00Z", "2026-01-10"),
        # An afternoon game, where UTC and the game date agree.
        ("2026-01-10T17:00:00Z", "2026-01-10"),
        # Offsets, not just Z.
        ("2026-01-10T19:10:00-05:00", "2026-01-10"),
    ],
)
def test_the_game_date_is_the_eastern_date_of_face_off(
    commence: str, expected: str
) -> None:
    assert game_date(commence) == expected


def test_an_evening_game_belongs_to_the_previous_utc_day() -> None:
    """The single case that was wrong, stated on its own."""
    assert game_date("2026-01-11T00:10:00Z") != "2026-01-11"
    assert game_date("2026-01-11T00:10:00Z") == "2026-01-10"


def test_a_bare_date_passes_through() -> None:
    assert game_date("2026-01-10") == "2026-01-10"


def test_a_naive_timestamp_is_not_converted() -> None:
    """No timezone means no conversion is possible, and inventing one would
    move a third of the schedule by a day."""
    assert game_date("2026-01-11T00:10:00") == "2026-01-11"


@pytest.mark.parametrize("value", ["", None, "   "])
def test_an_empty_value_yields_an_empty_date(value: object) -> None:
    assert game_date(value) == ""


def test_an_unparseable_value_falls_back_to_its_leading_characters() -> None:
    """Never silently better than the input."""
    assert game_date("not a timestamp") == "not a time"


def test_daylight_saving_is_handled_by_the_zone_not_by_arithmetic() -> None:
    """A fixed five-hour offset would be an hour wrong for eight months."""
    # 00:30 UTC in July is 20:30 Eastern the previous day (UTC-4).
    assert game_date("2026-07-02T00:30:00Z") == "2026-07-01"
    # 00:30 UTC in January is 19:30 Eastern the previous day (UTC-5).
    assert game_date("2026-01-02T00:30:00Z") == "2026-01-01"
    # 04:30 UTC in July is 00:30 Eastern the same day; a fixed -5 would say
    # 23:30 the previous day and put the game on the wrong date.
    assert game_date("2026-07-02T04:30:00Z") == "2026-07-02"
