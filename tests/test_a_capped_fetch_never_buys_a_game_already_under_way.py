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
* `now` must be an aware instant;
* a script that runs both fetches passes them one instant, so a game that
  starts between the two calls cannot be staged by one and dropped by the
  other;
* the shipped default clock is the wall clock in UTC (the suite pins it
  everywhere else).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult


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



# -- the edge of the rule -------------------------------------------------

#: A minute after the fetch: still to be played, however close.
ABOUT_TO_START = ("evt_soon", "2026-10-10T15:01:00Z")


def test_a_game_a_minute_away_is_bought_by_both_fetches() -> None:
    board = [UNDER_WAY, ABOUT_TO_START, *EVENING]
    per_event = _requester(board)
    _provider(per_event).fetch_player_props(
        markets=["player_points"], max_events=1, credit_cap=100, now=NOW
    )
    bulk = _provider(_requester(board)).fetch_team_markets(max_events=1, now=NOW)

    assert _bought(per_event) == ["evt_soon"]
    assert {row["home_team"] for row in bulk.rows} == {"Home evt_soon"}


def test_a_window_where_every_game_has_started_says_so() -> None:
    result = _provider(_requester([UNDER_WAY, AT_PUCK_DROP])).fetch_team_markets(
        now=NOW
    )

    assert result.rows == []
    assert any(
        "Every one of the 2 event(s) in the fetch window had already started"
        in note
        for note in result.warnings
    ), result.warnings
    assert not any("no usable team-market" in note for note in result.warnings)


# -- the production clock -------------------------------------------------


def test_the_production_clock_is_the_wall_clock_in_utc(real_provider_clock) -> None:
    """The suite replaces `_provider_clock` everywhere; this checks the one
    that ships, since a clock a day out or a century back drops the wrong
    games in production and nothing else here would notice."""
    before = datetime.now(timezone.utc)
    moment = real_provider_clock()
    after = datetime.now(timezone.utc)

    assert moment.tzinfo is not None
    assert moment.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=5) <= moment <= after + timedelta(seconds=5)


# -- one instant per run ----------------------------------------------------
#
# The scripts call both fetches, and a game that starts between the two calls
# must be dropped by both or by neither. If each fetch read its own clock, the
# bulk fetch would stage it and the per-event fetch would drop it; the slate
# the card measures coverage against is built from the staged rows, so every
# per-event market would read "priced for N-1 of N games" and leave the card.

#: Two seconds before the first face-off on a three-game night.
RUN_AT = datetime(2026, 10, 7, 22, 59, 58, tzinfo=timezone.utc)

GAME_NIGHT = (
    ("ev0", "Winnipeg Jets", "Colorado Avalanche", "2026-10-07T23:00:00Z"),
    ("ev1", "Washington Capitals", "Pittsburgh Penguins", "2026-10-07T23:30:00Z"),
    ("ev2", "Anaheim Ducks", "Edmonton Oilers", "2026-10-08T02:00:00Z"),
)


class _RunClock(datetime):
    """The script's own clock, frozen at the run's instant."""

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return RUN_AT.astimezone(tz) if tz else RUN_AT.replace(tzinfo=None)


def _advancing_provider_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clock that has crossed the first face-off by its second reading."""
    ticks = iter([RUN_AT, RUN_AT + timedelta(seconds=4)])
    last = [RUN_AT]

    def clock() -> datetime:
        last[0] = next(ticks, last[0])
        return last[0]

    monkeypatch.setattr(odds_api, "_provider_clock", clock)


def _game_night_event(event_id: str, markets: list[dict]) -> dict:
    for game_id, home, away, commence in GAME_NIGHT:
        if game_id == event_id:
            return {
                "id": game_id, "commence_time": commence, "home_team": home,
                "away_team": away,
                "bookmakers": [
                    {"key": "draftkings", "title": "DraftKings", "markets": markets}
                ],
            }
    raise AssertionError(event_id)


def _game_night_transport(url: str, **_kwargs: object) -> FakeResponse:
    if "/events/" in url and url.endswith("/odds"):
        event_id = url.split("/events/")[1].split("/")[0]
        return FakeResponse(_game_night_event(event_id, [
            {"key": "player_shots_on_goal", "outcomes": [
                {"name": "Over", "description": f"Skater {event_id}",
                 "price": -115, "point": 2.5},
                {"name": "Under", "description": f"Skater {event_id}",
                 "price": -105, "point": 2.5}]}]))
    if url.endswith("/events"):
        return FakeResponse([
            {"id": game_id, "commence_time": commence}
            for game_id, _home, _away, commence in GAME_NIGHT
        ])
    if url.endswith("/odds"):
        return FakeResponse([
            _game_night_event(game_id, [{"key": "h2h", "outcomes": [
                {"name": home, "price": -140}, {"name": away, "price": 120}]}])
            for game_id, home, away, _commence in GAME_NIGHT
        ])
    raise AssertionError(f"unexpected request: {url}")


def _load_script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_g6_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _wire(module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = odds_api.OddsApiProvider
    monkeypatch.setattr(
        module.odds_api, "OddsApiProvider",
        lambda: real(
            environment=ENVIRONMENT, requester=_game_night_transport, regions="us"
        ),
    )
    monkeypatch.setattr(
        module, "load_provider_env",
        lambda: ProviderEnvLoadResult(path=tmp_path / ".env"),
    )
    monkeypatch.setattr(module, "datetime", _RunClock)
    _advancing_provider_clock(monkeypatch)


def _games(frame: pd.DataFrame, market: str) -> set[str]:
    return set(frame.loc[frame["market"] == market, "provider_event_id"].astype(str))


def test_the_shadow_run_stages_one_slate_across_both_fetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script("run_provider_shadow.py")
    _wire(module, tmp_path, monkeypatch)

    code = module.main([
        "--live", "--props", "--overwrite-staging", "--horizon-days", "1",
        "--credit-cap", "320",
        "--staging-dir", str(tmp_path / "staging"),
        "--output-dir", str(tmp_path / "outputs"),
    ])
    capsys.readouterr()

    assert code == 0
    team = pd.read_csv(tmp_path / "staging" / odds_api.STAGING_PRICES_FILENAME)
    props = pd.read_csv(tmp_path / "staging" / odds_api.STAGING_PROPS_FILENAME)
    assert _games(team, "moneyline") == {"ev0", "ev1", "ev2"}
    assert _games(props, "shots_on_goal") == _games(team, "moneyline")


def test_the_closing_capture_takes_one_slate_across_both_fetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script("capture_closing_lines.py")
    _wire(module, tmp_path, monkeypatch)
    captured: list[pd.DataFrame] = []

    def keep(frame: pd.DataFrame, **_kwargs: object) -> pd.DataFrame:
        captured.append(frame.copy())
        return frame

    monkeypatch.setattr(module, "best_prices", keep)
    monkeypatch.setattr(module, "append_captures", lambda frame, **_: len(frame))

    code = module.main([
        "--live", "--credit-cap", "400", "--processed-dir", str(tmp_path),
    ])
    capsys.readouterr()

    assert code == 0
    (frame,) = captured
    assert _games(frame, "moneyline") == {"ev0", "ev1", "ev2"}
    assert _games(frame, "shots_on_goal") == _games(frame, "moneyline")
