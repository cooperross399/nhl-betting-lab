"""The card read its team map, schedules and rosters from data/raw, whatever it was given.

`run_gameday_card.py` takes `--processed-dir`, but it built its team-name map
with `build_team_name_map()` from the DEFAULT raw cache, twice (once for the
preseason screen, once for pricing). It read the club schedules and the
rosters from the default raw cache too, and it had no `--raw-dir` to point
any of that elsewhere. It never read the `team_names.csv` in the
`--processed-dir` it was handed, although every other reader of the map
does: settlement, the props backtest, the team measurement and the
experiments. And it saved whatever it built into that `--processed-dir`, so a
default cache holding fewer teams overwrote a fuller map there.

Found by the failure-shape audit, and confirmed by two of three refuters.
Reproduced on copies of the real tables, run from a clone whose data/raw is
empty. `--processed-dir` held the real `team_names.csv`: 101 spellings, 64 of
them from the cache, 33 franchises. The card:
- built a 6-spelling, alias-only map;
- blocked with "No team-name map could be built, because no boxscores are
  cached";
- left all 12 team names on a real six-game slate (2025-03-02) unresolved;
- skipped the preseason screen ("no regular-season schedule is cached");
- found no rosters.
The same run with the raw reads pointed at the real cache priced the slate
(2 best bets, 3 leans, 7 passes) and read 1,265 roster players.

What these tests hold, through the card's real `main()`, with every default
directory it reads emptied:

* with no boxscores cached, the `team_names.csv` in `--processed-dir`
  prices the slate, and the card leaves that file exactly as it found it;
* `--raw-dir` is the cache every raw read goes to: the team map (then saved
  into `--processed-dir`), the club schedules the preseason screen screens
  against, the completeness count that decides whether it may screen, and
  the rosters;
* the preseason screen resolves teams with the same map the pricers use;
* a cache that knows fewer teams than the saved map never shrinks it, and a
  spelling the cache maps differently replaces the saved one;
* with neither, the card still blocks, saves nothing, and names both
  directories it looked in.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from conftest import boxscore_payload
from nhl_betting_lab import config, verdicts
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.data.build_datasets import (
    PLAYER_LOG_COLUMNS,
    PLAYER_LOGS_FILENAME,
    TEAM_GAME_COLUMNS,
    TEAM_GAMES_FILENAME,
)
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn


#: What the NHL API calls each club, as `placeName` and `commonName`.
TEAMS = {
    "TOR": ("Toronto", "Maple Leafs"),
    "BOS": ("Boston", "Bruins"),
    "MTL": ("Montréal", "Canadiens"),
    "OTT": ("Ottawa", "Senators"),
}

#: What the provider sends.
PROVIDER = {
    "TOR": "Toronto Maple Leafs",
    "BOS": "Boston Bruins",
    "MTL": "Montréal Canadiens",
    "OTT": "Ottawa Senators",
}

#: Every club, so a club-schedule cache can be complete.
CLUBS = (
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET",
    "EDM", "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT",
    "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK",
    "WPG", "WSH",
)

SEASON = "20262027"
NOW = "2026-10-15T15:00:00+00:00"
#: The regular-season game on the slate, and one a week later that fixes
#: how far the cached schedule reaches.
TONIGHT = ("2026-10-15", "2026-10-15T23:00:00Z", "TOR", "BOS")
LATER = ("2026-10-20", "2026-10-20T23:00:00Z", "MTL", "OTT")
#: An exhibition game inside the schedule's range that the schedule does not
#: hold: the screen must drop it.
EXHIBITION = ("2026-10-16", "2026-10-16T23:00:00Z", "MTL", "OTT")


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def default_raw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every default directory the card reads, emptied, so the real cache
    cannot rescue a test or make one pass by checkout. `season` reads
    `config.RAW_DIR` at call time; `nhl_api` and `team_names` bound theirs at
    import."""
    raw = tmp_path / "default_raw"
    raw.mkdir()
    processed = tmp_path / "default_processed"
    processed.mkdir()
    recorded = tmp_path / "default_outputs"
    recorded.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", processed)
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", recorded)
    return raw


def _boxscore(raw: Path, game_id: int, home: str, away: str) -> None:
    payload = boxscore_payload(game_id=game_id, game_state="OFF")
    for side, abbrev in (("homeTeam", home), ("awayTeam", away)):
        place, common = TEAMS[abbrev]
        payload[side].update(
            abbrev=abbrev,
            placeName={"default": place},
            commonName={"default": common},
        )
    directory = raw / "nhl" / "boxscore"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{game_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def _saved_map(tmp_path: Path, processed: Path, clubs: tuple[str, ...]) -> Path:
    """`team_names.csv` exactly as the card writes it: built by the real
    builder from boxscores naming `clubs`, then saved."""
    source = tmp_path / "raw_the_map_came_from"
    for index in range(0, len(clubs), 2):
        _boxscore(source, 900 + index, clubs[index], clubs[index + 1])
    return tn.save_team_name_map(tn.build_team_name_map(source), processed_dir=processed)


def _schedules(raw: Path) -> None:
    """A complete club-schedule cache for the season: every club's own file,
    each holding the season's two known games."""
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    games = [
        {"gameType": 2, "gameDate": day,
         "homeTeam": {"abbrev": home}, "awayTeam": {"abbrev": away}}
        for day, _, home, away in (TONIGHT, LATER)
    ]
    for club in CLUBS:
        (directory / f"{club}_{SEASON}.json").write_text(
            json.dumps({"games": games}), encoding="utf-8"
        )


def _roster(raw: Path) -> None:
    """Toronto's roster for the season: its two skaters."""
    directory = raw / "nhl" / "roster"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"TOR_{SEASON}.json").write_text(
        json.dumps({"forwards": [{"id": 1}], "defensemen": [{"id": 2}], "goalies": []}),
        encoding="utf-8",
    )


def _tables(processed: Path) -> None:
    """Sixty played games per pairing and a skater log for each, enough for
    both models to fit."""
    processed.mkdir(parents=True, exist_ok=True)
    games: list[dict] = []
    logs: list[dict] = []
    for index in range(120):
        day = f"2025-{1 + (index // 2) // 28:02d}-{1 + (index // 2) % 28:02d}"
        pair = ("TOR", "BOS") if index % 2 == 0 else ("MTL", "OTT")
        home, away = pair if (index // 2) % 2 == 0 else pair[::-1]
        games.append({
            "game_id": index, "season": 20242025, "game_type": 2, "date": day,
            "start_time_utc": f"{day}T23:00:00Z", "home_team": home,
            "away_team": away, "home_goals": 4 if home in ("TOR", "MTL") else 2,
            "away_goals": 2 if home in ("TOR", "MTL") else 3,
            "home_shots": 30, "away_shots": 28, "regulation": index % 5 != 0,
        })
        for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
            for offset, position, shots in ((0, "C", 5), (1, "D", 1)):
                player_id = 1 + offset + 100 * list(TEAMS).index(team)
                logs.append({
                    "game_id": index, "season": 20242025, "game_type": 2,
                    "date": day, "start_time_utc": f"{day}T23:00:00Z",
                    "player_id": player_id, "player": f"Skater {player_id}",
                    "boxscore_name": f"S. {player_id}", "role": "skater",
                    "position": position, "team": team, "opponent": opponent,
                    "venue": venue, "toi_seconds": 1200, "shots_on_goal": shots,
                    "goals": 1 if shots > 1 else 0, "assists": 1, "points": 2,
                    "blocked_shots": 1, "hits": 1, "power_play_goals": 0,
                    "saves": 0, "shots_against": 0, "goals_against": 0,
                })
    pd.DataFrame(games, columns=list(TEAM_GAME_COLUMNS)).to_csv(
        processed / TEAM_GAMES_FILENAME, index=False
    )
    pd.DataFrame(logs, columns=list(PLAYER_LOG_COLUMNS)).to_csv(
        processed / PLAYER_LOGS_FILENAME, index=False
    )


def _slate(staging: Path, *games: tuple[str, str, str, str]) -> None:
    staging.mkdir(parents=True, exist_ok=True)
    rows = [
        {"date": day, "commence_time": commence,
         "provider_event_id": f"evt-{home}-{away}-{day}",
         "home_team": PROVIDER[home], "away_team": PROVIDER[away],
         "market": "moneyline", "player": "", "selection": selection,
         "line": "", "american_odds": -110, "book": "DraftKings",
         "fetched_at": f"{day}T11:00:00Z"}
        for day, commence, home, away in games
        for selection in ("home", "away")
    ]
    pd.DataFrame(rows, columns=list(odds_api.PRICE_COLUMNS)).to_csv(
        staging / odds_api.STAGING_PRICES_FILENAME, index=False
    )


def _run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
) -> tuple[str, dict, pd.DataFrame]:
    """The card's real main(); its stdout, its JSON and the frozen snapshot."""
    outputs = tmp_path / "outputs"
    load_script("run_gameday_card.py").main(
        [
            "--staging-dir", str(tmp_path / "staging"),
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(outputs),
            "--now", NOW,
            *extra,
        ]
    )
    out = capsys.readouterr().out
    card = json.loads((outputs / "gameday_card.json").read_text(encoding="utf-8"))
    frozen = sorted(outputs.rglob("priced_snapshots/*.csv"))
    snapshot = pd.read_csv(frozen[0]) if frozen else pd.DataFrame(
        columns=["home_team", "away_team", "model_probability"]
    )
    return out, card, snapshot


def _team_map_blockers(card: dict) -> list[str]:
    return [item for item in card["blockers"] if "team-name map" in item]


def test_a_worktree_card_prices_with_the_map_in_its_processed_dir(
    tmp_path: Path, default_raw: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No boxscores cached anywhere the card can see, and the full map in the
    `--processed-dir` it was given: the map every other reader reads."""
    processed = tmp_path / "processed"
    _tables(processed)
    saved = _saved_map(tmp_path, processed, ("TOR", "BOS", "MTL", "OTT"))
    before = (saved.read_bytes(), os.stat(saved).st_mtime_ns)
    _slate(tmp_path / "staging", TONIGHT)

    out, card, snapshot = _run(tmp_path, capsys)

    assert _team_map_blockers(card) == [], card["blockers"]
    assert card["unresolved_names"] == []
    assert sorted(snapshot["home_team"]) == [PROVIDER["TOR"]] * 2, (
        "Toronto hosting Boston was not priced, so nothing was frozen"
    )
    assert snapshot["model_probability"].notna().all()
    assert (saved.read_bytes(), os.stat(saved).st_mtime_ns) == before, (
        "the card rewrote a map the cache supplied nothing to"
    )


def test_every_raw_read_goes_to_the_raw_dir(
    tmp_path: Path, default_raw: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The team map, the schedule the screen screens against, the count that
    lets it screen, and the rosters all come from `--raw-dir`, while the
    default cache holds nothing at all."""
    raw = tmp_path / "raw"
    _boxscore(raw, 1, "TOR", "BOS")
    _boxscore(raw, 2, "MTL", "OTT")
    _schedules(raw)
    _roster(raw)
    processed = tmp_path / "processed"
    _tables(processed)
    _slate(tmp_path / "staging", TONIGHT, EXHIBITION)

    out, card, snapshot = _run(tmp_path, capsys, "--raw-dir", str(raw))

    assert _team_map_blockers(card) == [], card["blockers"]
    assert tn.resolve_team(
        PROVIDER["TOR"], tn.load_team_name_map(processed_dir=processed)
    ) == "TOR", "the map built from --raw-dir was not saved into --processed-dir"
    assert "no regular-season schedule is cached" not in out
    assert "preseason screen is skipped" not in out
    assert "2 price row(s) are for games the regular-season schedule does not know" in out
    assert sorted(snapshot["home_team"]) == [PROVIDER["TOR"]] * 2, (
        "the screen kept the exhibition game or dropped the real one"
    )
    assert "Rosters: 2 players across 1 clubs" in out


def test_the_screen_resolves_teams_with_the_map_the_pricers_use(
    tmp_path: Path, default_raw: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A cache holding the schedules and no boxscores, and the map in
    `--processed-dir`: a screen building its own map from the cache resolves
    no team, and drops tonight's real game as preseason."""
    raw = tmp_path / "raw"
    _schedules(raw)
    processed = tmp_path / "processed"
    _tables(processed)
    _saved_map(tmp_path, processed, ("TOR", "BOS", "MTL", "OTT"))
    _slate(tmp_path / "staging", TONIGHT)

    out, card, snapshot = _run(tmp_path, capsys, "--raw-dir", str(raw))

    assert "the regular-season schedule does not know" not in out
    assert sorted(snapshot["home_team"]) == [PROVIDER["TOR"]] * 2


def test_a_cache_that_knows_fewer_teams_never_shrinks_the_saved_map(
    tmp_path: Path, default_raw: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default cache holds one Toronto-Boston boxscore; the map in
    `--processed-dir` knows four clubs. Montréal hosting Ottawa still prices,
    and the file still holds all four."""
    _boxscore(default_raw, 1, "TOR", "BOS")
    processed = tmp_path / "processed"
    _tables(processed)
    saved = _saved_map(tmp_path, processed, ("TOR", "BOS", "MTL", "OTT"))
    before = saved.read_bytes()
    _slate(tmp_path / "staging", ("2026-10-15", "2026-10-15T23:00:00Z", "MTL", "OTT"))

    out, card, snapshot = _run(tmp_path, capsys)

    assert card["unresolved_names"] == []
    assert sorted(snapshot["home_team"]) == [PROVIDER["MTL"]] * 2
    assert saved.read_bytes() == before, "the saved map lost spellings"


def test_a_spelling_the_cache_maps_differently_replaces_the_saved_one(
    tmp_path: Path, default_raw: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The cache is the source of truth and the file its copy: a stale
    entry in the file must not outrank the boxscores, or a rename could never
    flow in."""
    _boxscore(default_raw, 1, "TOR", "BOS")
    processed = tmp_path / "processed"
    _tables(processed)
    saved = _saved_map(tmp_path, processed, ("TOR", "BOS", "MTL", "OTT"))
    saved.write_text(
        saved.read_text(encoding="utf-8").replace("boston bruins,BOS", "boston bruins,BOB"),
        encoding="utf-8",
    )
    _slate(tmp_path / "staging", TONIGHT)

    _run(tmp_path, capsys)

    assert tn.load_team_name_map(processed_dir=processed)["boston bruins"] == "BOS"
    # Everything the cache did not see is still there.
    assert tn.resolve_team(
        PROVIDER["OTT"], tn.load_team_name_map(processed_dir=processed)
    ) == "OTT"


@pytest.mark.parametrize("saved_file", ["absent", "aliases only"])
def test_with_neither_the_card_blocks_and_names_where_it_looked(
    tmp_path: Path,
    default_raw: Path,
    capsys: pytest.CaptureFixture[str],
    saved_file: str,
) -> None:
    processed = tmp_path / "processed"
    _tables(processed)
    path = processed / tn.TEAM_NAMES_FILENAME
    if saved_file == "aliases only":
        tn.save_team_name_map(tn.build_team_name_map(), processed_dir=processed)
    before = path.read_bytes() if path.exists() else None
    _slate(tmp_path / "staging", TONIGHT)

    out, card, snapshot = _run(tmp_path, capsys)

    blockers = _team_map_blockers(card)
    assert len(blockers) == 1, card["blockers"]
    assert str(default_raw / "nhl" / "boxscore") in blockers[0]
    assert str(processed) in blockers[0]
    assert (path.read_bytes() if path.exists() else None) == before
    assert snapshot.empty
