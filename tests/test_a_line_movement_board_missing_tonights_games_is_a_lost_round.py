"""A Line Movement board missing tonight's scheduled games is a lost round.

Sweep 4 (#257) taught the shadow run that an /events board listing only
later days' games, on a day the cached club schedule lists regular-season
games still to face off, is a provider or region glitch and not an off-day
(exit 2). `capture_line_movement.py` reads the same board and never asked:
it printed "No rows returned; nothing written.", exited 0, Capture prices
went green, and that round's movement and closing price were gone, because
no source keeps an archive (sweep 5,
line-movement-capture-offday-board-green).

Both scripts now count through one helper,
`season.regular_season_games_still_to_play`. A day with nothing scheduled,
or with every scheduled game already under way at the capture instant,
stays a quiet green night.

Every request goes to a stub transport; nothing reaches the network and no
credit is spent. The harness is the exhibition screen's
(`test_line_movement_never_spends_its_cap_on_exhibitions`): a clock at
10:00 in New York on 2026-09-29, and a club schedule listing BOS-FLA
(23:00Z) and LAK-SJS (02:00Z the next UTC day) tonight.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import test_line_movement_never_spends_its_cap_on_exhibitions as lm
from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.season import regular_season_games_still_to_play

#: A board that has moved past tonight: one game, three weeks away.
LATER_ONLY = [lm._event("later", "2026-10-20T23:00:00Z", "BOS", "FLA")]


def _per_event_requests(requester) -> list[str]:
    return [url for url in requester.urls if "/events/" in url]


def test_a_board_with_only_later_games_on_a_game_day_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, requester = lm._capture(tmp_path, monkeypatch, board=LATER_ONLY)

    assert code == 2, out
    assert "::error::" in out
    assert "2 regular-season game(s)" in out
    assert "2026-09-29" in out
    # The red exit buys nothing: no per-event request was made.
    assert _per_event_requests(requester) == []


def test_a_board_of_only_exhibitions_on_a_game_day_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen drops every exhibition, and nothing of tonight's
    regular-season slate is left to ask: the board is missing it."""
    board = [item for item in lm._board() if item["id"].startswith("exh")]
    code, out, requester = lm._capture(tmp_path, monkeypatch, board=board)

    assert code == 2, out
    assert "2 regular-season game(s)" in out
    assert _per_event_requests(requester) == []


def test_tonights_games_on_the_board_with_no_book_quoting_stay_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The board is not missing tonight's games: they were asked about and
    no book quoted them. That is an absence, as it always was, not a lost
    round, so the schedule is not consulted."""
    board = [item for item in lm._board() if item["id"].startswith("reg")]

    def unquoted(board_items):
        by_id = {item["id"]: item for item in board_items}

        def per_event(url: str, **_kwargs):
            event_id = url.split("/events/", 1)[1].split("/", 1)[0]
            return FakeResponse({**by_id[event_id], "bookmakers": []})

        return RecordingRequester(
            {"/events/": per_event, "/events": FakeResponse(board_items)}
        )

    monkeypatch.setattr(lm, "_requester", unquoted)
    code, out, requester = lm._capture(tmp_path, monkeypatch, board=board)

    assert code == 0, out
    assert "::error::" not in out
    assert "No rows returned; nothing written." in out
    assert sorted(_per_event_requests_ids(requester)) == lm.REGULAR_IDS


def _per_event_requests_ids(requester) -> list[str]:
    return [
        url.split("/events/", 1)[1].split("/", 1)[0]
        for url in _per_event_requests(requester)
    ]


def test_after_every_scheduled_game_has_started_it_is_a_quiet_night(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """22:30 in New York, still league day 2026-09-29: both games are under
    way, and a board that has moved on from them is not missing them."""
    monkeypatch.setattr(
        lm, "NOW", datetime(2026, 9, 30, 2, 30, tzinfo=timezone.utc)
    )
    code, out, _ = lm._capture(tmp_path, monkeypatch, board=LATER_ONLY)

    assert code == 0, out
    assert "::error::" not in out
    assert "No rows returned; nothing written." in out


def test_with_no_schedule_cached_the_board_is_believed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, _ = lm._capture(
        tmp_path, monkeypatch, clubs=None, board=LATER_ONLY
    )

    assert code == 0, out
    assert "::error::" not in out


def test_a_normal_board_still_captures_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, requester = lm._capture(tmp_path, monkeypatch)

    assert code == 0, out
    assert "::error::" not in out
    assert lm._bought(requester) == lm.REGULAR_IDS


def _club_file(raw: Path, abbrev: str, games: list[dict]) -> None:
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{abbrev}_20262027.json").write_text(
        json.dumps({"games": games}), encoding="utf-8"
    )


def _game(home: str, away: str, start: str, *, game_type: int = 2,
          state: str = "OK") -> dict:
    return {
        "gameType": game_type,
        "gameDate": "2026-09-29",
        "gameScheduleState": state,
        "startTimeUTC": start,
        "homeTeam": {"abbrev": home},
        "awayTeam": {"abbrev": away},
    }


def test_the_helper_counts_only_games_still_to_play(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _club_file(raw, "BOS", [
        _game("BOS", "FLA", "2026-09-29T23:00:00Z"),
        _game("MTL", "BOS", "2026-09-29T22:00:00Z", game_type=1),
    ])
    _club_file(raw, "LAK", [
        _game("LAK", "SJS", "2026-09-30T02:00:00Z"),
        _game("LAK", "ANA", "2026-09-30T02:30:00Z", state="PPD"),
        _game("LAK", "VGK", ""),
    ])
    tonight = ["2026-09-29"]

    def count(**kwargs) -> int:
        return regular_season_games_still_to_play(tonight, raw_dir=raw, **kwargs)

    # The exhibition and the called-off game are not counted; the game with
    # no readable face-off is, as a game still to play.
    assert count() == 3
    assert count(not_started_by=datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc)) == 3
    # A face-off exactly at the instant has started.
    assert count(not_started_by=datetime(2026, 9, 29, 23, 0, tzinfo=timezone.utc)) == 2
    assert count(not_started_by=datetime(2026, 9, 30, 3, 0, tzinfo=timezone.utc)) == 1
    assert regular_season_games_still_to_play(["2026-09-28"], raw_dir=raw) == 0
    assert regular_season_games_still_to_play(
        tonight, raw_dir=tmp_path / "nothing-cached"
    ) == 0


def test_the_fetch_and_the_schedule_check_read_one_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The started-game filter inside the fetch runs on the capture instant,
    the same one the schedule check reads, so a game facing off between two
    readings of the clock is never dropped by one and counted by the other."""
    seen: list[object] = []
    real = lm.odds_api.OddsApiProvider.fetch_player_props

    def spy(self, **kwargs):
        seen.append(kwargs.get("now"))
        return real(self, **kwargs)

    monkeypatch.setattr(lm.odds_api.OddsApiProvider, "fetch_player_props", spy)
    code, out, _ = lm._capture(tmp_path, monkeypatch, board=LATER_ONLY)

    assert code == 2, out
    assert seen == [lm.NOW]
