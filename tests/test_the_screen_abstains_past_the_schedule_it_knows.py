"""The preseason screen's abstain was guarded by a grep that could not fail.

The card screens staged prices against the cached regular-season schedule and
excludes a game the schedule does not know. It judges only dates it knows: a
game dated after the last day the cache holds is kept (`return True  #
abstain: the cache cannot judge this date`), because excluding it would
throw away a real slate the first time the cache lagged the calendar — the
card would freeze no opinion for the night and publish no selection, and the
first opinion of a day is the only one that settles.

The only test of that direction, `test_the_card_screen_abstains_beyond_the_
dates_it_knows`, greps the script for four strings. All four survive when the
abstain returns False instead (the word "abstain" is still in its comment),
and they survive the branch being deleted outright. No test ran the card with
staged prices and a schedule cache.

Found by the failure-shape audit (finding 68; 3 of 3 refuters confirmed).
Flipping the abstain left the whole suite green (1768 passed at the time of
the audit). Driven with real bought opening-night prices (2025-10-07: 3
games, 414 team and 3,384 prop rows) and a cache ending on 2025-04-17, the
flipped card excluded all 3,798 rows, priced 0 games and froze no opinion,
where the real one froze 3,322 and carded 3 best bets and 18 leans.

Since then (#125) the card checks the slate's OWN season for completeness
first, so a cache holding only last season now takes the partial-cache
warning and skips the screen before the abstain is consulted. The abstain is
reached when the slate's season is complete in the cache and tonight is still
past the last date its files hold; with a real season's files, that is any
night after the regular season's last one. These tests drive the real
`main()` on exactly that cache: every club's own file for the season, a
schedule that ends on 2026-10-31, and moneyline prices the real team model
can price, so the frozen snapshot shows which games reached pricing.

* On a date past the schedule, every game is kept and frozen, and nothing is
  reported as excluded.
* On dates inside it, its last night included, a fixture the schedule holds
  is kept and a pairing it does not hold is excluded and counted — the
  screen still screens.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from conftest import boxscore_payload
from nhl_betting_lab import config
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.data.build_datasets import TEAM_GAMES_FILENAME
from nhl_betting_lab.forward_evidence import snapshots_dir
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from nhl_betting_lab.season import (
    known_regular_season_games,
    schedule_cache_is_complete,
)


CLUBS = (
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET",
    "EDM", "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT",
    "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK",
    "WPG", "WSH",
)

#: The four clubs the staged prices name, as the provider and the NHL spell
#: them.
NAMES = {
    "TOR": ("Toronto", "Maple Leafs"),
    "MTL": ("Montréal", "Canadiens"),
    "BOS": ("Boston", "Bruins"),
    "NYR": ("New York", "Rangers"),
}

SEASON = "20262027"
FIRST_DAY = date(2026, 10, 1)


def _full_name(abbrev: str) -> str:
    place, common = NAMES[abbrev]
    return f"{place} {common}"


def _rounds() -> list[list[tuple[str, str]]]:
    """A single round robin by the circle method: 31 nights, every club
    playing exactly once a night, each pairing exactly once."""
    teams = list(CLUBS)
    rounds = []
    for night in range(len(teams) - 1):
        pairs = []
        for index in range(len(teams) // 2):
            first, second = teams[index], teams[-1 - index]
            pairs.append(
                (first, second) if (night + index) % 2 == 0 else (second, first)
            )
        rounds.append(pairs)
        teams = [teams[0], teams[-1], *teams[1:-1]]
    return rounds


def _schedule_cache(raw: Path) -> list[tuple[str, str, str]]:
    """Every club's own `{ABBR}_{season}.json`, as `fetch_club_season_schedule`
    writes it: each club's games, home and away. Returns (date, home, away)."""
    fixtures = [
        ((FIRST_DAY + timedelta(days=night)).isoformat(), home, away)
        for night, pairs in enumerate(_rounds())
        for home, away in pairs
    ]
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    for club in CLUBS:
        games = [
            {
                "gameType": 2,
                "gameDate": day,
                "homeTeam": {"abbrev": home},
                "awayTeam": {"abbrev": away},
            }
            for day, home, away in fixtures
            if club in (home, away)
        ]
        (directory / f"{club}_{SEASON}.json").write_text(
            json.dumps({"games": games}), encoding="utf-8"
        )
    return fixtures


def _boxscores(raw: Path) -> None:
    """One cached boxscore per pairing the prices name, so the card's team map
    resolves the provider's full names from the cache."""
    directory = raw / "nhl" / "boxscore"
    directory.mkdir(parents=True, exist_ok=True)
    for game_id, (home, away) in enumerate((("TOR", "MTL"), ("BOS", "NYR")), 1):
        payload = boxscore_payload(game_id=game_id, game_state="OFF")
        for side, abbrev in (("homeTeam", home), ("awayTeam", away)):
            place, common = NAMES[abbrev]
            payload[side].update(
                abbrev=abbrev,
                placeName={"default": place},
                commonName={"default": common},
            )
        (directory / f"{game_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def _team_games(processed: Path) -> None:
    """Last season's results for the four clubs, so the team model prices a
    moneyline for each of them. Scores vary game to game."""
    pairs = [("TOR", "MTL"), ("BOS", "NYR"), ("MTL", "BOS"), ("NYR", "TOR")]
    rows = []
    for index in range(48):
        home, away = pairs[index % 4]
        if index % 8 >= 4:
            home, away = away, home
        rows.append(
            {
                "game_id": 2025020000 + index,
                "date": (date(2025, 10, 8) + timedelta(days=2 * index)).isoformat(),
                "home_team": home,
                "away_team": away,
                "home_goals": 1 + (index * 7) % 5,
                "away_goals": 1 + (index * 3) % 4,
                "regulation": index % 6 != 0,
            }
        )
    processed.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(processed / TEAM_GAMES_FILENAME, index=False)


def _stage(staging: Path, games: list[tuple[str, str, str]]) -> None:
    """Both moneyline sides for each (date, HOME, AWAY), in the provider's
    staged shape and spelling."""
    rows = []
    for day, home, away in games:
        for selection, odds in (("home", -130), ("away", 110)):
            rows.append(
                {
                    "date": day,
                    "commence_time": f"{day}T23:00:00Z",
                    "provider_event_id": f"evt-{day}-{home}-{away}",
                    "home_team": _full_name(home),
                    "away_team": _full_name(away),
                    "market": "moneyline",
                    "player": "",
                    "selection": selection,
                    "line": "",
                    "american_odds": odds,
                    "book": "DraftKings",
                    "fetched_at": f"{day}T14:00:00Z",
                }
            )
    staging.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(odds_api.PRICE_COLUMNS)).to_csv(
        staging / odds_api.STAGING_PRICES_FILENAME, index=False
    )


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """A complete season's schedule cache that ends on 2026-10-31, the
    boxscores the team map needs, and last season's results. Every default
    directory the card could fall back to points here, the recorded verdicts
    included: a scratch --output-dir fell back to the tracked ones (#151)."""
    point_default_data_dirs_at(monkeypatch, tmp_path / "checkout_defaults")
    raw = tmp_path / "raw"
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    fixtures = _schedule_cache(raw)
    _boxscores(raw)
    _team_games(tmp_path / "processed")

    # The fixture is the state the tests claim: complete for its own season,
    # and knowing nothing after its last night.
    assert schedule_cache_is_complete(season=SEASON) == (True, 32)
    known = known_regular_season_games()
    assert known == set(fixtures)
    assert max(day for day, _, _ in known) == "2026-10-31"
    return {"root": tmp_path, "fixtures": fixtures}


def _run_card(root: Path, day: str) -> None:
    code = _load_card().main(
        [
            "--staging-dir", str(root / "staging"),
            "--processed-dir", str(root / "processed"),
            "--output-dir", str(root / "outputs"),
            "--archive-dir", str(root / "outputs" / "archive"),
            "--now", f"{day}T15:00:00+00:00",
        ]
    )
    assert code == 0


def _load_card() -> ModuleType:
    """Import the script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / "run_gameday_card.py"
    spec = importlib.util.spec_from_file_location("_script_run_gameday_card", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _frozen_games(root: Path, day: str) -> set[tuple[str, str]]:
    """(home, away) of every game whose opinion the card froze for `day`."""
    path = snapshots_dir(root / "outputs" / "archive") / f"{day}.csv"
    if not path.is_file():
        return set()
    frame = pd.read_csv(path)
    return set(zip(frame["home_team"], frame["away_team"]))


def _card(root: Path) -> dict:
    return json.loads(
        (root / "outputs" / "gameday_card.json").read_text(encoding="utf-8")
    )


def test_a_slate_past_the_schedule_is_priced_and_frozen_not_excluded(
    world: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    """The finding's failure: tonight is after the last night the cache
    holds, so the screen cannot judge it. Every game must reach pricing.

    This holds the rule as the card states it. With a real season's files
    the same branch is what a playoff night takes, and results ingest only
    regular-season games, so should playoff nights ever be excluded, this is
    the test that has to change, deliberately."""
    root = world["root"]
    tonight = "2026-12-15"
    _stage(root / "staging", [(tonight, "TOR", "MTL"), (tonight, "BOS", "NYR")])

    _run_card(root, tonight)
    out = capsys.readouterr().out

    assert "WARNING" not in out, "the screen must run, not be skipped"
    assert "excluded before pricing" not in out, (
        "a real slate past the cached schedule was excluded as preseason"
    )
    assert _frozen_games(root, tonight) == {
        ("Toronto Maple Leafs", "Montréal Canadiens"),
        ("Boston Bruins", "New York Rangers"),
    }
    assert _card(root)["slate_games"] == 2


def test_inside_the_schedule_an_unknown_game_is_still_excluded_and_counted(
    world: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    """The other direction, so an abstain that swallowed the whole screen
    fails too: on nights the cache holds — its last night included — its own
    fixture is kept and a pairing it does not list is excluded, counted, and
    never frozen."""
    root = world["root"]
    fixtures = world["fixtures"]
    (tonight, home, away), = [
        game for game in fixtures if {game[1], game[2]} == {"TOR", "MTL"}
    ]
    last_night = max(day for day, _, _ in fixtures)
    exhibitions = [(tonight, "BOS", "NYR"), (last_night, "NYR", "MTL")]
    for day, first, second in exhibitions:
        assert (day, first, second) not in fixtures
        assert (day, second, first) not in fixtures
    _stage(root / "staging", [(tonight, home, away), *exhibitions])

    _run_card(root, tonight)
    out = capsys.readouterr().out

    assert (
        "4 price row(s) are for games the regular-season schedule does not know"
        in out
    )
    assert _frozen_games(root, tonight) == {(_full_name(home), _full_name(away))}
    # The eligibility slate is every game the schedule holds for the night,
    # priced or not (finding 50): the one priced fixture and the night's other
    # scheduled games, and neither exhibition. This read 1, the priced game
    # alone, while the slate was built from the prices it judged.
    scheduled_tonight = [game for game in fixtures if game[0] == tonight]
    assert len(scheduled_tonight) > 1
    assert _card(root)["slate_games"] == len(scheduled_tonight)
