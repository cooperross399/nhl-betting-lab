"""A club schedule cached before the league published it was that club's schedule all season.

`fetch_club_season_schedule` served any cached JSON object and cached any
object the API answered, and `scripts/fetch_nhl_data.py` never asks it to
refresh one. The API's answer for a season it has not published yet is an
object with an empty `games` list, so a club asked too early was written as
`{"games": []}` and that file was served on every later run: no game id for
that club all season, no boxscore fetched, and `schedule_cache_is_complete`
(which already counts only a file holding a regular-season game) short by
one club for good, its partial-cache warning telling the operator to run the
one script that would serve the same file again. It is the club-schedule
twin of the player registry #206 fixed: an answer naming no games is today's
answer, not the season's.

What these tests hold:

* an answer listing no regular-season game (`gameType` 2) is returned and
  never written: not an empty list, and not a list of exhibitions only;
* a cached file listing no regular-season game is a cache miss and is asked
  again, and the first answer that lists the season replaces it and is then
  served from cache like any other;
* an empty answer never overwrites a cached schedule, even on a refresh;
* through `fetch_nhl_data`, a cache holding one club's empty file is
  completed by running the script the card's warning names, and a club the
  API still lists no games for is said so, not cached, and asked again next
  run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.season import known_regular_season_games, schedule_cache_is_complete
from test_a_club_schedule_that_is_not_an_object import (
    SEASON,
    _api,
    _cache,
    _fetch,
    _game,
    _round_robin,
)


def _path(raw: Path, club: str = "TOR") -> Path:
    return raw / "nhl" / "club_schedule" / f"{club}_{SEASON}.json"


PUBLISHED = {"games": [_game("2026-10-07", "TOR", "MTL"), _game("2026-10-09", "BOS", "TOR")]}

#: Answers that name no regular-season game: the API's own "not yet", a body
#: with no `games` key, and a schedule that so far lists only exhibitions.
NO_SEASON = pytest.mark.parametrize(
    "answer",
    [
        {"games": []},
        {},
        {"games": [{**_game("2026-09-24", "TOR", "OTT"), "gameType": 1}]},
    ],
    ids=["empty", "no-games-key", "preseason-only"],
)


def _requester(*answers: Any) -> RecordingRequester:
    """The club-schedule endpoint answering with `answers`, one per request;
    a request past the last one fails the test."""
    queue = list(answers)

    def answer(url: str, **kwargs: Any) -> FakeResponse:
        assert queue, f"asked again: {url}"
        return FakeResponse(queue.pop(0))

    return RecordingRequester({"club-schedule-season": answer})


@NO_SEASON
def test_an_answer_listing_no_regular_season_game_is_returned_and_never_written(
    tmp_path: Path, answer: dict[str, Any]
) -> None:
    requester = _requester(answer)

    entry = nhl_api.fetch_club_season_schedule(
        "TOR", int(SEASON), requester=requester, raw_dir=tmp_path
    )

    assert entry.payload == answer
    assert entry.from_cache is False
    assert not _path(tmp_path).exists()
    assert not list((tmp_path / "nhl").rglob("*.partial"))


@NO_SEASON
def test_a_cached_schedule_listing_no_regular_season_game_is_asked_again(
    tmp_path: Path, answer: dict[str, Any]
) -> None:
    """The exact file an early fetch used to leave behind. The next fetch
    must ask the API, keep the published season it answers with, and serve
    that from cache afterwards without asking again."""
    nhl_api._write_cache(_path(tmp_path), answer)
    requester = _requester(PUBLISHED)

    first = nhl_api.fetch_club_season_schedule(
        "TOR", int(SEASON), requester=requester, raw_dir=tmp_path
    )
    second = nhl_api.fetch_club_season_schedule(
        "TOR", int(SEASON), requester=requester, raw_dir=tmp_path
    )

    assert first.from_cache is False
    assert first.payload == PUBLISHED
    assert json.loads(_path(tmp_path).read_text(encoding="utf-8")) == PUBLISHED
    assert second.from_cache is True
    assert second.payload == PUBLISHED
    assert len(requester.calls) == 1, "a published schedule was asked for twice"


@NO_SEASON
def test_an_answer_listing_no_regular_season_game_never_overwrites_a_cached_schedule(
    tmp_path: Path, answer: dict[str, Any]
) -> None:
    """A refresh that catches the API blinking must not erase the season."""
    nhl_api._write_cache(_path(tmp_path), PUBLISHED)

    nhl_api.fetch_club_season_schedule(
        "TOR", int(SEASON), requester=_requester(answer), raw_dir=tmp_path,
        refresh=True,
    )

    assert json.loads(_path(tmp_path).read_text(encoding="utf-8")) == PUBLISHED


# --------------------------------------------------------------------------
# Through the script the card's partial-cache warning tells the operator to run.
# --------------------------------------------------------------------------

def test_fetch_nhl_data_replaces_a_club_schedule_cached_before_it_was_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """31 clubs' published schedules and Toronto's `{"games": []}` from an
    August run. Running the fetch must ask for Toronto again and complete
    the cache; it used to serve the empty file (32 from cache, 31 clubs)."""
    schedule = _round_robin()
    raw = tmp_path / "raw"
    _cache(raw, schedule, {"TOR": {"games": []}})
    assert schedule_cache_is_complete(raw, season=SEASON) == (False, 31)

    code, out, err = _fetch(raw, _api(schedule), monkeypatch, capsys)

    assert code == 0, err
    assert "Live requests, club schedules: 1 ok, 31 from cache, 0 failed." in out
    assert schedule_cache_is_complete(raw, season=SEASON) == (True, 32)
    assert known_regular_season_games(raw) == set(schedule)


def test_fetch_nhl_data_says_a_club_has_no_season_yet_and_asks_again_next_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The league has published 31 clubs and not Toronto. Nothing is cached
    for Toronto, the run says so by name, and the next run, by which time
    the league has published it, completes the cache."""
    schedule = _round_robin()
    raw = tmp_path / "raw"

    code, out, err = _fetch(
        raw, _api(schedule, {"TOR": {"games": []}}), monkeypatch, capsys
    )

    assert code == 0, err
    assert not _path(raw).exists()
    assert "TOR" in out and "no regular-season game" in out
    assert schedule_cache_is_complete(raw, season=SEASON) == (False, 31)

    code, out, err = _fetch(raw, _api(schedule), monkeypatch, capsys)

    assert code == 0, err
    assert "Live requests, club schedules: 1 ok, 31 from cache, 0 failed." in out
    assert schedule_cache_is_complete(raw, season=SEASON) == (True, 32)
