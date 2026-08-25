"""Shared fixtures.

Every test here runs offline. Nothing in this suite makes a network request,
reads a credential, or writes outside `tmp_path`.
"""

from __future__ import annotations

from typing import Any

import pytest


class FakeResponse:
    """The narrow slice of `requests.Response` this project actually uses."""

    def __init__(
        self,
        payload: Any = None,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self._raises = raises

    def json(self) -> Any:
        if self._raises is not None:
            raise self._raises
        return self._payload


class RecordingRequester:
    """A requester that answers from a script and records what it was asked.

    Keyed by a substring of the URL so a test states the endpoint it means
    rather than reconstructing a full URL with query parameters.
    """

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.default = FakeResponse(status_code=404)

    def __call__(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, dict(kwargs)))
        for fragment, response in self.responses.items():
            if fragment in url:
                if callable(response):
                    return response(url, **kwargs)
                return response
        return self.default

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.calls]


@pytest.fixture
def responses() -> type[FakeResponse]:
    return FakeResponse


@pytest.fixture
def requester() -> RecordingRequester:
    return RecordingRequester()


def boxscore_payload(
    *,
    game_id: int = 2024020001,
    game_state: str = "OFF",
    season: int = 20242025,
    game_type: int = 2,
    game_date: str = "2024-10-08",
    start_time: str = "2024-10-09T23:00:00Z",
    home: str = "TOR",
    away: str = "NJD",
    home_score: int = 4,
    away_score: int = 2,
    period: int = 3,
    skaters: list[dict[str, Any]] | None = None,
    goalies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A boxscore in the shape `api-web.nhle.com` actually returns."""
    default_skaters = [
        {
            "playerId": 8478483,
            "name": {"default": "M. Marner"},
            "position": "R",
            "goals": 1,
            "assists": 2,
            "points": 3,
            "sog": 4,
            "blockedShots": 1,
            "hits": 2,
            "powerPlayGoals": 1,
            "toi": "21:30",
        }
    ]
    default_goalies = [
        {
            "playerId": 8474593,
            "name": {"default": "J. Markstrom"},
            "position": "G",
            "saveShotsAgainst": "30/31",
            "goalsAgainst": 1,
            "toi": "59:38",
        }
    ]
    block = {
        "forwards": skaters if skaters is not None else default_skaters,
        "defense": [],
        "goalies": goalies if goalies is not None else default_goalies,
    }
    return {
        "id": game_id,
        "season": season,
        "gameType": game_type,
        "gameDate": game_date,
        "startTimeUTC": start_time,
        "gameState": game_state,
        "periodDescriptor": {"number": period},
        "homeTeam": {"abbrev": home, "score": home_score, "sog": 33},
        "awayTeam": {"abbrev": away, "score": away_score, "sog": 28},
        "playerByGameStats": {"homeTeam": block, "awayTeam": block},
    }


@pytest.fixture(autouse=True)
def never_actually_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may spend real time waiting.

    The NHL client backs off between retries, which is correct in production
    and pure cost in a suite. A test that wants to assert on the delays passes
    its own recorder; everything else simply never waits.
    """
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
