"""The schedule cache counted opponents, so one club's file read as complete.

`schedule_cache_is_complete` gathered every club named in any cached game.
One club's 82-game schedule meets all 31 others, so a cache holding a single
club file returned (True, 32), and one holding last season's 32 files plus
four of this season's returned (True, 33). The card's only defence against a
partial cache — skip the preseason screen and say so — could never fire, and
the screen then dropped every game whose club file had not landed as
"preseason". Gameday Refresh does not carry `club_schedule` between runs, so
every run refetches it and a partial fetch is one outage away. Found by the
failure-shape audit (3/3 refuters); the reproduction dropped 165 of 218
October games.

What these tests hold, on real-shaped club files (every game against a real
opponent, named `{ABBR}_{season}.json` as `fetch_club_season_schedule` writes):

* completeness is the number of clubs whose OWN file for the season is
  cached, parses, and holds a regular-season game;
* it is per season, and defaults to the newest season cached;
* the card run with a partial current season warns and keeps a real game the
  screen would otherwise have dropped as preseason.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from conftest import boxscore_payload
from nhl_betting_lab import config
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.season import schedule_cache_is_complete, season_id


CLUBS = (
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET",
    "EDM", "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT",
    "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK",
    "WPG", "WSH",
)


def _club_file(raw: Path, club: str, season: str, *, game_type: int = 2) -> None:
    """`club`'s season: one home game against every other club."""
    start = int(season[:4])
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    games = [
        {
            "gameType": game_type,
            "gameDate": f"{start}-{10 + i // 28:02d}-{1 + i % 28:02d}",
            "homeTeam": {"abbrev": club},
            "awayTeam": {"abbrev": other},
        }
        for i, other in enumerate(c for c in CLUBS if c != club)
    ]
    (directory / f"{club}_{season}.json").write_text(
        json.dumps({"games": games}), encoding="utf-8"
    )


def test_one_real_club_file_is_one_club(tmp_path: Path) -> None:
    _club_file(tmp_path, "TOR", "20262027")

    assert schedule_cache_is_complete(tmp_path) == (False, 1)


def test_last_seasons_full_cache_does_not_complete_this_one(tmp_path: Path) -> None:
    for club in CLUBS:
        _club_file(tmp_path, club, "20252026")
    for club in ("TOR", "MTL", "BOS", "NYR"):
        _club_file(tmp_path, club, "20262027")

    assert schedule_cache_is_complete(tmp_path, season="20262027") == (False, 4)
    assert schedule_cache_is_complete(tmp_path) == (False, 4), (
        "the default is the newest season cached"
    )
    assert schedule_cache_is_complete(tmp_path, season="20252026") == (True, 32)


def test_every_clubs_own_file_is_complete(tmp_path: Path) -> None:
    for club in CLUBS:
        _club_file(tmp_path, club, "20262027")

    assert schedule_cache_is_complete(tmp_path, season="20262027") == (True, 32)


def test_a_file_that_proves_nothing_is_not_a_club(tmp_path: Path) -> None:
    """Unreadable, unnamed, or preseason-only files do not count: 29 good
    files, plus a broken TOR, a preseason-only UTA, and an unnamed file
    naming WPG, is 29 clubs."""
    for club in CLUBS:
        if club not in ("TOR", "UTA", "WPG"):
            _club_file(tmp_path, club, "20262027")
    directory = tmp_path / "nhl" / "club_schedule"
    (directory / "TOR_20262027.json").write_text("{broken", encoding="utf-8")
    _club_file(tmp_path, "UTA", "20262027", game_type=1)
    (directory / "schedule.json").write_text(
        json.dumps({"games": [{"gameType": 2, "gameDate": "2026-10-08",
                               "homeTeam": {"abbrev": "WPG"},
                               "awayTeam": {"abbrev": "WSH"}}]}),
        encoding="utf-8",
    )

    assert schedule_cache_is_complete(tmp_path, season="20262027") == (False, 29)


@pytest.mark.parametrize(
    ("day", "season"),
    [("2026-10-08", "20262027"), ("2027-04-10", "20262027"),
     ("2026-09-29", "20262027"), ("2026-06-15", "20252026")],
)
def test_the_season_of_a_league_date(day: str, season: str) -> None:
    assert season_id(day) == season


# --------------------------------------------------------------------------
# Through the card.
# --------------------------------------------------------------------------

def _load_card() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_gameday_card.py"
    spec = importlib.util.spec_from_file_location("_script_run_gameday_card", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_card_keeps_a_real_game_when_the_seasons_cache_is_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Toronto's file names every club, so the old check called the cache
    complete, the screen ran, and Boston at Montreal — a real game Toronto
    does not play in — was dropped as preseason."""
    raw = tmp_path / "raw"
    _club_file(raw, "TOR", "20262027")
    box = boxscore_payload(game_id=1, game_state="OFF")
    box["homeTeam"].update(abbrev="MTL", placeName={"default": "Montréal"},
                           commonName={"default": "Canadiens"})
    box["awayTeam"].update(abbrev="BOS", placeName={"default": "Boston"},
                           commonName={"default": "Bruins"})
    (raw / "nhl" / "boxscore").mkdir(parents=True)
    (raw / "nhl" / "boxscore" / "1.json").write_text(json.dumps(box), encoding="utf-8")
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)

    staging = tmp_path / "staging"
    staging.mkdir()
    pd.DataFrame(
        [{"date": "2026-10-15", "commence_time": "2026-10-15T23:00:00Z",
          "provider_event_id": "evt1", "home_team": "Montréal Canadiens",
          "away_team": "Boston Bruins", "market": "moneyline", "player": "",
          "selection": "home", "line": "", "american_odds": -120,
          "book": "DraftKings", "fetched_at": "2026-10-15T14:00:00Z"}],
        columns=list(odds_api.PRICE_COLUMNS),
    ).to_csv(staging / odds_api.STAGING_PRICES_FILENAME, index=False)

    _load_card().main(
        ["--staging-dir", str(staging),
         "--processed-dir", str(tmp_path / "processed"),
         "--output-dir", str(tmp_path / "outputs"),
         "--now", "2026-10-15T15:00:00+00:00"]
    )
    out = capsys.readouterr().out

    assert "holds this season's own schedule for only 1 of 32 clubs" in out
    assert "the regular-season schedule does not know" not in out, (
        "a real game was dropped as preseason on a partial cache"
    )


def test_the_card_warns_when_its_season_has_no_files_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Last season's 32 files say nothing about this one: the card asks about
    the slate's own season, not whichever season happens to be complete."""
    raw = tmp_path / "raw"
    for club in CLUBS:
        _club_file(raw, club, "20252026")
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    staging = tmp_path / "staging"
    staging.mkdir()
    pd.DataFrame(
        [{"date": "2026-10-15", "commence_time": "2026-10-15T23:00:00Z",
          "provider_event_id": "evt1", "home_team": "Montréal Canadiens",
          "away_team": "Boston Bruins", "market": "moneyline", "player": "",
          "selection": "home", "line": "", "american_odds": -120,
          "book": "DraftKings", "fetched_at": "2026-10-15T14:00:00Z"}],
        columns=list(odds_api.PRICE_COLUMNS),
    ).to_csv(staging / odds_api.STAGING_PRICES_FILENAME, index=False)

    _load_card().main(
        ["--staging-dir", str(staging),
         "--processed-dir", str(tmp_path / "processed"),
         "--output-dir", str(tmp_path / "outputs"),
         "--now", "2026-10-15T15:00:00+00:00"]
    )

    assert "holds this season's own schedule for only 0 of 32 clubs" in (
        capsys.readouterr().out
    )
