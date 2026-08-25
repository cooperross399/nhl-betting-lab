from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import requests

from conftest import FakeResponse, RecordingRequester, boxscore_payload
from nhl_betting_lab.data import nhl_api


def test_a_final_boxscore_is_fetched_once_and_then_read_from_cache(
    tmp_path: Path,
) -> None:
    payload = boxscore_payload(game_state="OFF")
    requester = RecordingRequester({"boxscore": FakeResponse(payload)})

    first = nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)
    second = nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.complete is True
    assert len(requester.calls) == 1


def test_an_unfinished_boxscore_is_refetched_every_time(tmp_path: Path) -> None:
    """A second-period boxscore frozen in the cache would never finish."""
    payload = boxscore_payload(game_state="LIVE", period=2)
    requester = RecordingRequester({"boxscore": FakeResponse(payload)})

    nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)
    second = nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)

    assert second.from_cache is False
    assert second.complete is False
    assert len(requester.calls) == 2


def test_refresh_forces_a_refetch_of_a_final_game(tmp_path: Path) -> None:
    payload = boxscore_payload(game_state="OFF")
    requester = RecordingRequester({"boxscore": FakeResponse(payload)})

    nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)
    nhl_api.fetch_boxscore(
        2024020001, requester=requester, raw_dir=tmp_path, refresh=True
    )

    assert len(requester.calls) == 2


def test_a_truncated_cache_file_is_treated_as_a_miss(tmp_path: Path) -> None:
    """Half a boxscore that a later run trusts is worse than no boxscore."""
    path = tmp_path / "nhl" / "boxscore" / "2024020001.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"id": 2024020', encoding="utf-8")
    requester = RecordingRequester(
        {"boxscore": FakeResponse(boxscore_payload(game_state="OFF"))}
    )

    entry = nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)

    assert entry.from_cache is False
    assert entry.complete is True


def test_the_cache_write_is_atomic(tmp_path: Path) -> None:
    """No `.partial` file may survive a successful write."""
    requester = RecordingRequester(
        {"boxscore": FakeResponse(boxscore_payload(game_state="OFF"))}
    )

    nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)

    directory = tmp_path / "nhl" / "boxscore"
    assert list(directory.glob("*.partial")) == []
    assert (directory / "2024020001.json").is_file()


@pytest.mark.parametrize("state", ["OFF", "FINAL", "off", "final"])
def test_final_states_are_recognised(state: str) -> None:
    assert nhl_api.game_is_final({"gameState": state}) is True


@pytest.mark.parametrize("state", ["LIVE", "PRE", "FUT", "CRIT", ""])
def test_unfinished_states_are_not_final(state: str) -> None:
    assert nhl_api.game_is_final({"gameState": state}) is False


def test_a_non_dict_payload_is_not_final() -> None:
    assert nhl_api.game_is_final(["not", "a", "game"]) is False


def test_an_http_error_raises_rather_than_caching_nothing(tmp_path: Path) -> None:
    requester = RecordingRequester({"boxscore": FakeResponse(status_code=503)})

    with pytest.raises(nhl_api.NhlApiError, match="503"):
        nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)

    assert not (tmp_path / "nhl" / "boxscore").exists()


def test_an_unreachable_api_raises_a_project_error(tmp_path: Path) -> None:
    def explode(url: str, **kwargs: object) -> object:
        raise requests.ConnectionError("no route")

    with pytest.raises(nhl_api.NhlApiError, match="could not be reached"):
        nhl_api.fetch_boxscore(2024020001, requester=explode, raw_dir=tmp_path)


def test_unreadable_json_raises_a_project_error(tmp_path: Path) -> None:
    requester = RecordingRequester(
        {"boxscore": FakeResponse(raises=ValueError("not json"))}
    )

    with pytest.raises(nhl_api.NhlApiError, match="unreadable JSON"):
        nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)


@pytest.mark.parametrize("game_id", [0, -5])
def test_a_nonsense_game_id_is_refused(game_id: int, tmp_path: Path) -> None:
    with pytest.raises(nhl_api.NhlApiError):
        nhl_api.fetch_boxscore(game_id, requester=RecordingRequester(), raw_dir=tmp_path)


def test_the_schedule_endpoint_is_addressed_by_iso_date(tmp_path: Path) -> None:
    requester = RecordingRequester({"schedule": FakeResponse({"gameWeek": []})})

    nhl_api.fetch_schedule_day(
        date(2026, 10, 7), requester=requester, raw_dir=tmp_path
    )

    assert requester.urls[0].endswith("/v1/schedule/2026-10-07")


@pytest.mark.parametrize("value", ["7 October 2026", "2026-13-01x", "", "20261007"])
def test_a_malformed_schedule_date_is_refused(value: str, tmp_path: Path) -> None:
    with pytest.raises(nhl_api.NhlApiError, match="ISO date"):
        nhl_api.fetch_schedule_day(
            value, requester=RecordingRequester(), raw_dir=tmp_path
        )


def test_a_schedule_day_is_cached_but_never_treated_as_settled(
    tmp_path: Path,
) -> None:
    requester = RecordingRequester({"schedule": FakeResponse({"gameWeek": []})})

    first = nhl_api.fetch_schedule_day(
        "2026-10-07", requester=requester, raw_dir=tmp_path
    )
    second = nhl_api.fetch_schedule_day(
        "2026-10-07", requester=requester, raw_dir=tmp_path
    )

    assert first.complete is False
    assert second.from_cache is True
    assert second.complete is False


@pytest.mark.parametrize("team", ["T", "TORO", "../etc", "TO0", "", "T/R"])
def test_a_bad_team_abbreviation_is_refused(team: str, tmp_path: Path) -> None:
    """A path segment that is not three capitals could escape the cache dir."""
    with pytest.raises(nhl_api.NhlApiError, match="three-letter"):
        nhl_api.fetch_club_season_schedule(
            team, 20262027, requester=RecordingRequester(), raw_dir=tmp_path
        )


def test_a_bad_season_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(nhl_api.NhlApiError, match="eight-digit"):
        nhl_api.fetch_club_season_schedule(
            "TOR", 2026, requester=RecordingRequester(), raw_dir=tmp_path
        )


def test_a_lowercase_team_abbreviation_is_normalised_not_refused(
    tmp_path: Path,
) -> None:
    """Case is a typing convenience; only the shape is a safety question."""
    requester = RecordingRequester({"club-schedule-season": FakeResponse({"games": []})})

    nhl_api.fetch_club_season_schedule(
        "tor", 20262027, requester=requester, raw_dir=tmp_path
    )

    assert requester.urls[0].endswith("/TOR/20262027")


def test_the_club_schedule_is_cached_per_team_and_season(tmp_path: Path) -> None:
    requester = RecordingRequester({"club-schedule-season": FakeResponse({"games": []})})

    nhl_api.fetch_club_season_schedule(
        "TOR", 20262027, requester=requester, raw_dir=tmp_path
    )

    assert (tmp_path / "nhl" / "club_schedule" / "TOR_20262027.json").is_file()


def test_the_player_registry_pages_until_the_api_runs_out(tmp_path: Path) -> None:
    pages = {
        "skater/summary": [
            FakeResponse(
                {
                    "data": [
                        {
                            "playerId": 8000000 + index,
                            "skaterFullName": f"Player {index}",
                            "positionCode": "C",
                        }
                        for index in range(100)
                    ]
                }
            ),
            FakeResponse(
                {
                    "data": [
                        {
                            "playerId": 8000100,
                            "skaterFullName": "Last Player",
                            "positionCode": "D",
                        }
                    ]
                }
            ),
        ],
        "goalie/summary": [FakeResponse({"data": []})],
    }

    def answer(url: str, **kwargs: object) -> object:
        for fragment, queue in pages.items():
            if fragment in url:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        return FakeResponse(status_code=404)

    entry = nhl_api.fetch_player_registry(
        20242025, requester=answer, raw_dir=tmp_path
    )

    assert len(entry.payload["skaters"]) == 101
    assert entry.payload["skaters"][-1]["fullName"] == "Last Player"


def test_the_registry_skips_rows_without_a_usable_name(tmp_path: Path) -> None:
    def answer(url: str, **kwargs: object) -> object:
        if "skater/summary" in url:
            return FakeResponse(
                {
                    "data": [
                        {"playerId": 1, "skaterFullName": "Real Name"},
                        {"playerId": 2, "skaterFullName": "   "},
                        {"skaterFullName": "No Id"},
                    ]
                }
            )
        return FakeResponse({"data": []})

    entry = nhl_api.fetch_player_registry(
        20242025, requester=answer, raw_dir=tmp_path
    )

    assert [row["fullName"] for row in entry.payload["skaters"]] == ["Real Name"]


def test_cached_boxscore_ids_reads_the_directory_without_the_network(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "nhl" / "boxscore"
    directory.mkdir(parents=True)
    for name in ("2024020002.json", "2024020001.json", "notanumber.json"):
        (directory / name).write_text("{}", encoding="utf-8")

    assert nhl_api.cached_boxscore_ids(tmp_path) == [2024020001, 2024020002]


def test_cached_boxscore_ids_is_empty_when_nothing_is_cached(tmp_path: Path) -> None:
    assert nhl_api.cached_boxscore_ids(tmp_path) == []


def test_the_client_never_sends_a_credential(tmp_path: Path) -> None:
    """The NHL API is keyless. A key in these requests would be a leak."""
    requester = RecordingRequester(
        {"boxscore": FakeResponse(boxscore_payload(game_state="OFF"))}
    )

    nhl_api.fetch_boxscore(2024020001, requester=requester, raw_dir=tmp_path)

    _, kwargs = requester.calls[0]
    assert "apiKey" not in json.dumps(kwargs)
    assert kwargs.get("params") == {}


# -- rate limiting ------------------------------------------------------


def test_a_rate_limited_request_is_retried(tmp_path: Path) -> None:
    """A cold cache makes about four thousand requests, which is enough to
    earn a 429. Without a retry the fetch simply returns less data and every
    report downstream is quietly thinner."""
    attempts = {"n": 0}

    def flaky(url: str, **kwargs: object) -> object:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return FakeResponse(status_code=429)
        return FakeResponse(boxscore_payload(game_state="OFF"))

    slept: list[float] = []
    nhl_api._get_json(
        "https://example/x", requester=flaky, sleeper=slept.append
    )

    assert attempts["n"] == 3
    assert slept == [2.0, 4.0]


def test_backoff_doubles_rather_than_retrying_immediately() -> None:
    """Being asked to slow down and retrying at once earns a longer ban."""
    slept: list[float] = []

    with pytest.raises(nhl_api.NhlApiError):
        nhl_api._get_json(
            "https://example/x",
            requester=lambda url, **kwargs: FakeResponse(status_code=429),
            sleeper=slept.append,
        )

    assert slept == [2.0, 4.0, 8.0]


def test_a_client_error_is_not_retried() -> None:
    """A 404 will still be a 404 in two seconds."""
    attempts = {"n": 0}

    def missing(url: str, **kwargs: object) -> object:
        attempts["n"] += 1
        return FakeResponse(status_code=404)

    with pytest.raises(nhl_api.NhlApiError, match="404"):
        nhl_api._get_json("https://example/x", requester=missing, sleeper=lambda _: None)

    assert attempts["n"] == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_every_retryable_status_is_retried(status: int) -> None:
    attempts = {"n": 0}

    def flaky(url: str, **kwargs: object) -> object:
        attempts["n"] += 1
        if attempts["n"] < 2:
            return FakeResponse(status_code=status)
        return FakeResponse({"ok": True})

    nhl_api._get_json(
        "https://example/x", requester=flaky, sleeper=lambda _: None
    )

    assert attempts["n"] == 2


def test_a_connection_error_is_retried_then_reported() -> None:
    def explode(url: str, **kwargs: object) -> object:
        raise requests.ConnectionError("no route")

    slept: list[float] = []
    with pytest.raises(nhl_api.NhlApiError, match="could not be reached"):
        nhl_api._get_json(
            "https://example/x", requester=explode, sleeper=slept.append
        )

    assert len(slept) == nhl_api.MAX_ATTEMPTS - 1


def test_unreadable_json_is_not_retried() -> None:
    """A malformed body is not a transient condition."""
    attempts = {"n": 0}

    def bad(url: str, **kwargs: object) -> object:
        attempts["n"] += 1
        return FakeResponse(raises=ValueError("not json"))

    with pytest.raises(nhl_api.NhlApiError, match="unreadable"):
        nhl_api._get_json("https://example/x", requester=bad, sleeper=lambda _: None)

    assert attempts["n"] == 1
