"""The early-afternoon Line Movement round spends credits only on the games
it can close.

Cooper approved a 15:30 UTC round on 2026-11-10 ("ALL", on a card reading
"Afternoon games get scored on beating the closing line, at roughly 38
credits per afternoon game"). Under today's other rounds the 13:00-14:00
EDT and 12:00-13:00 EST starts have no capture within
`closing_lines.CLOSE_MAX_LEAD`, so their opinions can never meet a close.

The round asks only games facing off within 150 minutes of the capture
(`--max-lead-minutes 150`, `starts_by` in both fetches). The evening slate is
closed by the evening rounds, so buying it at 15:30 would spend 38 credits a
game on prices no close can use. And a night with no afternoon game must
cost nothing: the events list is free, no per-event request is made, and
the bulk team request (6 credits whatever it returns) is not sent.

Every request goes to a stub transport; nothing reaches the network.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult
from nhl_betting_lab.season import regular_season_games_still_to_play
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from test_scripts import load_script


ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}

#: Saturday 2026-11-14, 10:31 EST: the 15:30 round, a minute in.
NOW = datetime(2026, 11, 14, 15, 31, tzinfo=timezone.utc)
DAY = "2026-11-14"
#: A 13:00 EST matinee (closes only on this round) and a 19:00 EST game.
AFTERNOON = {"id": "aft", "commence_time": "2026-11-14T18:00:00Z",
             "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins"}
EVENING = {"id": "eve", "commence_time": "2026-11-15T00:00:00Z",
           "home_team": "Montreal Canadiens", "away_team": "Ottawa Senators"}

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def _odds(item: dict) -> dict:
    return {
        **item,
        "bookmakers": [{
            "key": "draftkings", "title": "DraftKings",
            "markets": [{"key": "player_shots_on_goal", "outcomes": [
                {"name": "Over", "description": "Skater", "price": -115, "point": 2.5},
                {"name": "Under", "description": "Skater", "price": -105, "point": 2.5},
            ]}],
        }],
    }


def _bulk(board: list[dict]) -> list[dict]:
    return [
        {**item, "bookmakers": [{
            "key": "draftkings", "title": "DraftKings",
            "markets": [{"key": "h2h", "outcomes": [
                {"name": item["home_team"], "price": -150},
                {"name": item["away_team"], "price": 130},
            ]}],
        }]}
        for item in board
    ]


def _requester(board: list[dict]) -> RecordingRequester:
    by_id = {item["id"]: item for item in board}

    def per_event(url: str, **_kwargs) -> FakeResponse:
        return FakeResponse(_odds(by_id[url.split("/events/", 1)[1].split("/", 1)[0]]))

    return RecordingRequester({
        "/events/": per_event,
        "/events": FakeResponse(board),
        "/odds": FakeResponse(_bulk(board)),
    })


def _cache_schedule(raw: Path, games: list[tuple[str, str, str]]) -> None:
    """Club schedules listing `games` as (home, away, startTimeUTC)."""
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    for home, away, start in games:
        payload = {"games": [{
            "gameType": 2, "gameDate": DAY, "gameScheduleState": "OK",
            "startTimeUTC": start,
            "homeTeam": {"abbrev": home}, "awayTeam": {"abbrev": away},
        }]}
        (directory / f"{home}_20262027.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def _capture(tmp_path, monkeypatch, board, *, lead: int | None = 150,
             schedule: list[tuple[str, str, str]] | None = None):
    dirs = point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    if schedule is not None:
        _cache_schedule(dirs.raw, schedule)
    requester = _requester(board)
    module = load_script("capture_line_movement.py")
    real = odds_api.OddsApiProvider
    monkeypatch.setattr(
        module.odds_api, "OddsApiProvider",
        lambda: real(environment=ENVIRONMENT, requester=requester, regions="us,us2"),
    )
    monkeypatch.setattr(module, "load_provider_env",
                        lambda: ProviderEnvLoadResult(path=tmp_path / ".env"))
    monkeypatch.setattr(module, "datetime", _Frozen)
    processed = tmp_path / "processed"
    argv = ["--live", "--credit-cap", "600", "--processed-dir", str(processed)]
    argv += ["--max-lead-minutes", "" if lead is None else str(lead)]
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    try:
        code = module.main(argv)
    finally:
        monkeypatch.setattr(sys, "stdout", sys.__stdout__)
    return code, " ".join(out.getvalue().split()), requester, processed


def _per_event(requester) -> list[str]:
    return [url.split("/events/", 1)[1].split("/", 1)[0]
            for url in requester.urls if "/events/" in url]


def _bulk_asked(requester) -> int:
    return sum(1 for url in requester.urls
               if url.endswith("/odds") and "/events/" not in url)


def test_the_round_buys_the_afternoon_game_and_not_the_evening_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, requester, processed = _capture(
        tmp_path, monkeypatch, [AFTERNOON, EVENING]
    )
    assert code == 0, out
    assert _per_event(requester) == ["aft"]
    assert _bulk_asked(requester) == 1
    assert "1 event(s) face off after" in out
    day = (processed / "line_movement" / f"{DAY}.csv").read_text(encoding="utf-8")
    assert "Toronto Maple Leafs" in day
    # The bulk rows are bounded too: the evening game is the evening rounds'.
    assert "Montreal Canadiens" not in day


def test_a_night_with_no_afternoon_game_asks_nothing_that_bills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, requester, processed = _capture(tmp_path, monkeypatch, [EVENING])
    assert code == 0, out
    assert _per_event(requester) == []
    assert _bulk_asked(requester) == 0
    # Only the free events list was read.
    assert all(url.endswith("/events") for url in requester.urls), requester.urls
    assert "bulk team markets were not asked" in out
    assert not (processed / "line_movement" / f"{DAY}.csv").exists()


def test_an_evening_game_the_schedule_lists_does_not_make_the_round_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The board is not missing the evening game; this round never asks it."""
    code, out, requester, _ = _capture(
        tmp_path, monkeypatch, [EVENING],
        schedule=[("MTL", "OTT", "2026-11-15T00:00:00Z")],
    )
    assert code == 0, out
    assert "::error::" not in out
    assert _bulk_asked(requester) == 0


def test_a_board_missing_the_scheduled_matinee_is_a_lost_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, requester, _ = _capture(
        tmp_path, monkeypatch, [EVENING],
        schedule=[("TOR", "BOS", "2026-11-14T18:00:00Z"),
                  ("MTL", "OTT", "2026-11-15T00:00:00Z")],
    )
    assert code == 2, out
    assert "1 regular-season game(s)" in out
    assert _per_event(requester) == []


def test_without_the_flag_a_round_still_asks_the_whole_slate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, requester, _ = _capture(
        tmp_path, monkeypatch, [AFTERNOON, EVENING], lead=None
    )
    assert code == 0, out
    assert _per_event(requester) == ["aft", "eve"]
    assert _bulk_asked(requester) == 1
    assert "face off after" not in out


@pytest.mark.parametrize("lead", ["0", "-5"])
def test_a_lead_that_is_not_positive_is_refused(lead, monkeypatch) -> None:
    module = load_script("capture_line_movement.py")
    with pytest.raises(SystemExit):
        module.main(["--live", "--credit-cap", "600", "--max-lead-minutes", lead])


def test_a_failed_events_list_falls_back_to_the_schedule_for_the_team_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_script("capture_line_movement.py")
    dirs = point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    starts_by = NOW + timedelta(minutes=150)
    assert module.ask_team_markets(None, starts_by=None, league_days=[DAY], now=NOW)
    assert not module.ask_team_markets(
        None, starts_by=starts_by, league_days=[DAY], now=NOW
    )
    _cache_schedule(dirs.raw, [("TOR", "BOS", "2026-11-14T18:00:00Z")])
    assert module.ask_team_markets(
        None, starts_by=starts_by, league_days=[DAY], now=NOW
    )


def test_the_schedule_count_reads_the_lead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirs = point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    _cache_schedule(dirs.raw, [("TOR", "BOS", "2026-11-14T18:00:00Z"),
                               ("MTL", "OTT", "2026-11-15T00:00:00Z")])
    assert regular_season_games_still_to_play([DAY], not_started_by=NOW) == 2
    assert regular_season_games_still_to_play(
        [DAY], not_started_by=NOW, starting_by=NOW + timedelta(minutes=150)
    ) == 1


def test_the_workflow_bounds_only_the_afternoon_round() -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = document.get("on", document.get(True))
    crons = [entry["cron"] for entry in triggers["schedule"]]
    assert "30 4 * 1-4,10-12 *" in crons
    assert triggers["workflow_dispatch"]["inputs"]["max_lead_minutes"]["default"] == ""
    (step,) = [s for s in document["jobs"]["capture"]["steps"]
               if "capture_line_movement.py" in str(s.get("run", ""))]
    # The bound is set for one cron only; every other round passes an empty
    # bound, which is none.
    assert step["run"].count("--max-lead-minutes") == 1
    assert "github.event.schedule == '30 4 * 1-4,10-12 *' && '150'" in step["run"]


def test_an_empty_lead_is_no_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """What every round but 15:30 passes: the whole slate, as before."""
    module = load_script("capture_line_movement.py")
    assert module._lead_minutes("") is None
    assert module._lead_minutes("150") == 150
    # A runner's word splitting may drop the empty value; a bare flag is no
    # bound too.
    parsed = []
    monkeypatch.setattr(module, "load_provider_env", lambda: parsed.append(1))
    assert module.main(["--max-lead-minutes"]) == 0
