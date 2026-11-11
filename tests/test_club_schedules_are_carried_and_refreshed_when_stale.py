"""Club schedules are carried between Gameday Refresh runs, and refreshed when stale.

gameday-state carried the boxscore cache and the registry but not
`data/raw/nhl/club_schedule`, so every Gameday Refresh run asked all 32
clubs for all four seasons `fetch_nhl_data` reads: 128 requests a run, four
runs a day. Locally the opposite held: a cached club schedule was served for
good, so a game postponed after it was cached kept `gameScheduleState` OK and
the card's preseason screen (#239) could not see the postponement.

Since 2026-11-10 the cache is carried and every file carries its fetch
instant:

* a season that had closed when the file was fetched is served for good;
* the season being played is served only while its copy is younger than
  `CLUB_SCHEDULE_MAX_AGE` (six hours), then asked again;
* a file with no readable stamp (every older copy) is asked again once;
* the payload returned is the API's answer, never the stamp;
* gameday-state uploads the folder.

No network: every request goes to a recording stub.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.data import nhl_api

REPO = Path(__file__).resolve().parents[1]
CURRENT = 20262027
CLOSED = 20252026
NOW = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)
GAMES = {"games": [{"id": 2026020001, "gameType": 2, "gameScheduleState": "OK"}]}
POSTPONED = {"games": [{"id": 2026020001, "gameType": 2, "gameScheduleState": "PPD"}]}


def _requester(*answers: Any) -> RecordingRequester:
    queue = list(answers)

    def answer(url: str, **kwargs: Any) -> FakeResponse:
        assert queue, f"asked again: {url}"
        return FakeResponse(queue.pop(0))

    return RecordingRequester({"club-schedule-season": answer})


def _path(raw: Path, season: int) -> Path:
    return raw / "nhl" / "club_schedule" / f"TOR_{season}.json"


def _fetch(raw: Path, season: int, requester: RecordingRequester, now: datetime):
    return nhl_api.fetch_club_season_schedule(
        "TOR", season, requester=requester, raw_dir=raw, now=now
    )


def test_the_file_is_stamped_and_the_payload_is_the_apis_answer(tmp_path: Path) -> None:
    entry = _fetch(tmp_path, CURRENT, _requester(GAMES), NOW)

    assert entry.payload == GAMES
    written = json.loads(_path(tmp_path, CURRENT).read_text(encoding="utf-8"))
    assert written["fetched_at"] == NOW.isoformat()
    assert {k: v for k, v in written.items() if k != "fetched_at"} == GAMES


def test_the_season_being_played_is_served_while_young_and_asked_again_when_stale(
    tmp_path: Path,
) -> None:
    requester = _requester(GAMES, POSTPONED)
    _fetch(tmp_path, CURRENT, requester, NOW)

    young = _fetch(tmp_path, CURRENT, requester, NOW + timedelta(hours=5, minutes=59))
    assert young.from_cache is True
    assert young.payload == GAMES
    assert len(requester.calls) == 1

    stale = _fetch(tmp_path, CURRENT, requester, NOW + nhl_api.CLUB_SCHEDULE_MAX_AGE)
    assert stale.from_cache is False
    assert stale.payload == POSTPONED, "a postponement must reach the cache"
    assert len(requester.calls) == 2
    written = json.loads(_path(tmp_path, CURRENT).read_text(encoding="utf-8"))
    assert written["games"][0]["gameScheduleState"] == "PPD"


def test_the_age_is_six_hours() -> None:
    assert nhl_api.CLUB_SCHEDULE_MAX_AGE == timedelta(hours=6)


def test_a_season_fetched_after_it_closed_is_served_for_good(tmp_path: Path) -> None:
    requester = _requester(GAMES)
    _fetch(tmp_path, CLOSED, requester, NOW)

    a_year_on = _fetch(tmp_path, CLOSED, requester, NOW + timedelta(days=365))

    assert a_year_on.from_cache is True
    assert a_year_on.payload == GAMES
    assert len(requester.calls) == 1


def test_a_season_fetched_while_it_was_played_is_not_settled_later(tmp_path: Path) -> None:
    """A copy of 2025-26 fetched in March 2026 still lists March's states;
    it is asked again, not promoted to settled because the season closed."""
    march = datetime(2026, 3, 1, tzinfo=timezone.utc)
    requester = _requester(GAMES, GAMES)
    _fetch(tmp_path, CLOSED, requester, march)

    entry = _fetch(tmp_path, CLOSED, requester, NOW)

    assert entry.from_cache is False
    assert len(requester.calls) == 2
    # Now stamped after the close, so it is settled from here on.
    assert _fetch(tmp_path, CLOSED, requester, NOW + timedelta(days=30)).from_cache


def test_an_unstamped_file_is_asked_again_once(tmp_path: Path) -> None:
    nhl_api._write_cache(_path(tmp_path, CLOSED), GAMES)
    requester = _requester(GAMES)

    first = _fetch(tmp_path, CLOSED, requester, NOW)
    second = _fetch(tmp_path, CLOSED, requester, NOW + timedelta(hours=1))

    assert (first.from_cache, second.from_cache) == (False, True)
    assert len(requester.calls) == 1


def test_a_stamp_that_cannot_be_read_or_lies_in_the_future_is_not_fresh() -> None:
    for stamp in ("", "yesterday", None, 7):
        assert not nhl_api.club_schedule_is_fresh(
            {**GAMES, "fetched_at": stamp}, CURRENT, now=NOW
        )
    ahead = (NOW + timedelta(hours=1)).isoformat()
    assert not nhl_api.club_schedule_is_fresh({**GAMES, "fetched_at": ahead}, CURRENT, now=NOW)
    assert not nhl_api.club_schedule_is_fresh([], CURRENT, now=NOW)
    naive = (NOW - timedelta(hours=1)).replace(tzinfo=None).isoformat()
    assert nhl_api.club_schedule_is_fresh({**GAMES, "fetched_at": naive}, CURRENT, now=NOW)


def test_a_failed_refresh_leaves_the_stale_copy_on_disk(tmp_path: Path) -> None:
    """The fetch is counted as failed (the run degrades), and the readers of
    the cache directory still have the last copy rather than none."""
    _fetch(tmp_path, CURRENT, _requester(GAMES), NOW)

    def broken(url: str, **kwargs: Any) -> FakeResponse:
        return FakeResponse(None, status_code=404)

    failing = RecordingRequester({"club-schedule-season": broken})
    try:
        _fetch(tmp_path, CURRENT, failing, NOW + timedelta(hours=7))
    except nhl_api.NhlApiError:
        pass
    else:  # pragma: no cover - the stub always fails
        raise AssertionError("a 404 was not a failure")
    assert json.loads(_path(tmp_path, CURRENT).read_text(encoding="utf-8"))["games"] == GAMES["games"]


def test_gameday_state_carries_the_club_schedules() -> None:
    workflow = yaml.safe_load(
        (REPO / ".github" / "workflows" / "gameday-refresh.yml").read_text(encoding="utf-8")
    )
    uploads = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
        and step.get("with", {}).get("name") == "gameday-state"
    ]
    assert len(uploads) == 1
    paths = {line.strip() for line in uploads[0]["with"]["path"].splitlines()}
    assert "data/raw/nhl/club_schedule" in paths
