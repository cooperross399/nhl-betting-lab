from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import boxscore_payload
from nhl_betting_lab.data import build_datasets as builder


def _cache(tmp_path: Path, payload: dict) -> Path:
    directory = tmp_path / "nhl" / "boxscore"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{payload['id']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _registry(tmp_path: Path, names: dict[int, str], season: int = 20242025) -> None:
    directory = tmp_path / "nhl" / "registry"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{season}.json").write_text(
        json.dumps(
            {
                "seasonId": season,
                "skaters": [
                    {"playerId": pid, "fullName": name, "positionCode": "C"}
                    for pid, name in names.items()
                ],
                "goalies": [],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("13:11", 791), ("0:00", 0), ("59:38", 3578), ("21:30", 1290)],
)
def test_toi_parses_to_seconds(value: str, expected: int) -> None:
    assert builder.parse_toi(value) == expected


@pytest.mark.parametrize("value", ["", None, "13", "abc:def", "--"])
def test_an_unreadable_toi_is_zero_not_a_guess(value: object) -> None:
    assert builder.parse_toi(value) == 0


def test_saves_parse_to_saves_and_shots_against() -> None:
    assert builder.parse_saves("30/31") == (30, 31)


@pytest.mark.parametrize("value", ["", None, "30", "a/b"])
def test_unreadable_saves_are_zero(value: object) -> None:
    assert builder.parse_saves(value) == (0, 0)


def test_a_final_game_produces_rows_for_both_sides(tmp_path: Path) -> None:
    _cache(tmp_path, boxscore_payload(game_state="OFF"))

    players, teams, result = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )

    assert result.games_used == 1
    assert set(players["venue"]) == {"home", "away"}
    assert set(players["team"]) == {"TOR", "NJD"}
    assert len(teams) == 1


def test_an_unfinished_game_produces_no_rows_at_all(tmp_path: Path) -> None:
    """A second-period boxscore has real numbers; they are not a whole game."""
    _cache(tmp_path, boxscore_payload(game_state="LIVE", period=2))

    players, teams, result = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )

    assert players.empty
    assert teams.empty
    assert result.games_not_final == [2024020001]
    assert result.games_used == 0


def test_a_final_game_missing_its_stats_block_is_reported_not_skipped(
    tmp_path: Path,
) -> None:
    """A dataset that is quietly short is the hardest kind of bug to see."""
    payload = boxscore_payload(game_state="OFF")
    del payload["playerByGameStats"]
    _cache(tmp_path, payload)

    _, _, result = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )

    assert result.games_malformed == [2024020001]
    assert "malformed" in result.summary_line()


def test_a_corrupt_cache_file_is_reported_as_malformed(tmp_path: Path) -> None:
    directory = tmp_path / "nhl" / "boxscore"
    directory.mkdir(parents=True)
    (directory / "2024020001.json").write_text("{not json", encoding="utf-8")

    _, _, result = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )

    assert result.games_malformed == [2024020001]


def test_skater_columns_come_straight_from_the_boxscore(tmp_path: Path) -> None:
    _cache(tmp_path, boxscore_payload(game_state="OFF"))

    players, _, _ = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )
    skater = players[players["role"] == "skater"].iloc[0]

    assert skater["shots_on_goal"] == 4
    assert skater["goals"] == 1
    assert skater["assists"] == 2
    assert skater["points"] == 3
    assert skater["blocked_shots"] == 1
    assert skater["power_play_goals"] == 1
    assert skater["toi_seconds"] == 1290


def test_goalie_saves_are_split_from_the_shots_against_string(
    tmp_path: Path,
) -> None:
    _cache(tmp_path, boxscore_payload(game_state="OFF"))

    players, _, _ = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )
    goalie = players[players["role"] == "goalie"].iloc[0]

    assert goalie["saves"] == 30
    assert goalie["shots_against"] == 31
    assert goalie["goals_against"] == 1


def test_a_goalie_never_carries_skater_counting_stats(tmp_path: Path) -> None:
    """A goalie's `sog` field means shots faced in some feeds; never trust it."""
    _cache(tmp_path, boxscore_payload(game_state="OFF"))

    players, _, _ = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )
    goalie = players[players["role"] == "goalie"].iloc[0]

    assert goalie["shots_on_goal"] == 0
    assert goalie["goals"] == 0
    assert goalie["blocked_shots"] == 0


def test_there_is_no_power_play_points_column(tmp_path: Path) -> None:
    """Naming a goals count "points" would be a lie the model inherits."""
    assert "power_play_points" not in builder.PLAYER_LOG_COLUMNS


def test_full_names_come_from_the_registry(tmp_path: Path) -> None:
    _cache(tmp_path, boxscore_payload(game_state="OFF"))
    _registry(tmp_path, {8478483: "Mitch Marner"})

    players, _, result = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )
    marner = players[players["player_id"] == 8478483].iloc[0]

    assert marner["player"] == "Mitch Marner"
    assert marner["boxscore_name"] == "M. Marner"
    assert result.names_resolved > 0


def test_a_player_missing_from_the_registry_is_counted_not_invented(
    tmp_path: Path,
) -> None:
    _cache(tmp_path, boxscore_payload(game_state="OFF"))

    players, _, result = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )

    assert set(players["player"]) == {""}
    assert result.names_unresolved == len(players)
    assert "names unresolved" in result.summary_line()


def test_a_later_season_registry_wins_on_a_name_change(tmp_path: Path) -> None:
    _registry(tmp_path, {8478483: "Old Name"}, season=20232024)
    _registry(tmp_path, {8478483: "New Name"}, season=20242025)

    names = builder.load_player_registry(raw_dir=tmp_path)

    assert names[8478483] == "New Name"


def test_the_team_row_carries_the_result_and_shot_counts(tmp_path: Path) -> None:
    _cache(tmp_path, boxscore_payload(game_state="OFF"))

    _, teams, _ = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )
    game = teams.iloc[0]

    assert game["home_team"] == "TOR"
    assert game["away_team"] == "NJD"
    assert game["home_goals"] == 4
    assert game["away_goals"] == 2
    assert game["home_shots"] == 33
    assert bool(game["regulation"]) is True


def test_an_overtime_game_is_marked_as_not_regulation(tmp_path: Path) -> None:
    _cache(tmp_path, boxscore_payload(game_state="OFF", period=4))

    _, teams, _ = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )

    assert bool(teams.iloc[0]["regulation"]) is False


def test_a_game_whose_teams_are_the_same_is_refused(tmp_path: Path) -> None:
    payload = boxscore_payload(game_state="OFF", home="TOR", away="TOR")

    assert builder.team_row_from_boxscore(payload) is None


def test_the_build_writes_both_tables(tmp_path: Path) -> None:
    _cache(tmp_path, boxscore_payload(game_state="OFF"))
    processed = tmp_path / "processed"

    builder.build_datasets(raw_dir=tmp_path, processed_dir=processed)

    assert (processed / builder.PLAYER_LOGS_FILENAME).is_file()
    assert (processed / builder.TEAM_GAMES_FILENAME).is_file()


def test_write_false_produces_frames_but_no_files(tmp_path: Path) -> None:
    _cache(tmp_path, boxscore_payload(game_state="OFF"))
    processed = tmp_path / "processed"

    players, _, _ = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=processed, write=False
    )

    assert not players.empty
    assert not processed.exists()


def test_loading_an_absent_table_gives_the_right_empty_shape(tmp_path: Path) -> None:
    players = builder.load_player_logs(tmp_path)
    teams = builder.load_team_games(tmp_path)

    assert players.empty and list(players.columns) == list(builder.PLAYER_LOG_COLUMNS)
    assert teams.empty and list(teams.columns) == list(builder.TEAM_GAME_COLUMNS)


def test_rows_are_sorted_by_date_so_a_walk_forward_fit_can_trust_the_order(
    tmp_path: Path,
) -> None:
    _cache(
        tmp_path,
        boxscore_payload(game_id=2024020009, game_date="2024-11-01", game_state="OFF"),
    )
    _cache(
        tmp_path,
        boxscore_payload(game_id=2024020002, game_date="2024-10-09", game_state="OFF"),
    )

    players, teams, _ = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )

    assert list(teams["date"]) == ["2024-10-09", "2024-11-01"]
    assert players["date"].is_monotonic_increasing


def test_the_build_reads_no_network(tmp_path: Path, monkeypatch) -> None:
    """A rebuild must be reproducible offline."""
    import requests

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("build_datasets must not make a request")

    monkeypatch.setattr(requests, "get", forbidden)
    _cache(tmp_path, boxscore_payload(game_state="OFF"))

    _, _, result = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed"
    )

    assert result.games_used == 1


def test_an_empty_build_never_replaces_a_populated_dataset(tmp_path: Path) -> None:
    """An absent raw cache produces empty frames without an error; writing
    them would replace 750k accumulated rows with headers. The price CSVs
    grew this guard after exactly that accident, and this path had not."""
    _cache(tmp_path, boxscore_payload(game_state="OFF"))
    processed = tmp_path / "processed"
    builder.build_datasets(raw_dir=tmp_path, processed_dir=processed)
    before = (processed / builder.PLAYER_LOGS_FILENAME).read_text()
    teams_before = (processed / builder.TEAM_GAMES_FILENAME).read_text()

    empty_raw = tmp_path / "nowhere"
    with pytest.raises(ValueError, match="Refusing to shrink"):
        builder.build_datasets(raw_dir=empty_raw, processed_dir=processed)

    assert (processed / builder.PLAYER_LOGS_FILENAME).read_text() == before
    assert (processed / builder.TEAM_GAMES_FILENAME).read_text() == teams_before


def test_the_guard_protects_the_team_file_on_its_own(tmp_path: Path) -> None:
    """The first guard checked one of the two files it writes: with the
    player file deleted to force a rebuild, a populated team_games.csv was
    still clobbered by an empty build."""
    _cache(tmp_path, boxscore_payload(game_state="OFF"))
    processed = tmp_path / "processed"
    builder.build_datasets(raw_dir=tmp_path, processed_dir=processed)
    (processed / builder.PLAYER_LOGS_FILENAME).unlink()
    teams_before = (processed / builder.TEAM_GAMES_FILENAME).read_text()

    with pytest.raises(ValueError, match="team games"):
        builder.build_datasets(
            raw_dir=tmp_path / "nowhere", processed_dir=processed
        )

    assert (processed / builder.TEAM_GAMES_FILENAME).read_text() == teams_before


def test_a_tiny_build_cannot_silently_replace_a_full_one(tmp_path: Path) -> None:
    """The guard's own motivating scenario is a wrongly-pointed cache, which
    usually holds a few games rather than zero. One game where thousands
    existed is refused the same as none."""
    for game_id in (2024020001, 2024020002, 2024020003, 2024020004):
        _cache(tmp_path, boxscore_payload(game_id=game_id, game_state="OFF"))
    processed = tmp_path / "processed"
    builder.build_datasets(raw_dir=tmp_path, processed_dir=processed)

    with pytest.raises(ValueError, match="shrink an accumulated dataset"):
        builder.build_datasets(
            raw_dir=tmp_path,
            processed_dir=processed,
            game_ids=[2024020001],
        )


def test_a_deliberate_shrink_is_permitted_with_the_flag(tmp_path: Path) -> None:
    for game_id in (2024020001, 2024020002, 2024020003, 2024020004):
        _cache(tmp_path, boxscore_payload(game_id=game_id, game_state="OFF"))
    processed = tmp_path / "processed"
    builder.build_datasets(raw_dir=tmp_path, processed_dir=processed)

    _, teams, _ = builder.build_datasets(
        raw_dir=tmp_path,
        processed_dir=processed,
        game_ids=[2024020001],
        allow_shrink=True,
    )

    assert len(teams) == 1


def test_a_repeated_empty_build_is_an_idempotent_no_op(tmp_path: Path) -> None:
    """The first version raised falsely here: it treated the header-only file
    its own first run wrote as "already holds data"."""
    processed = tmp_path / "processed"
    builder.build_datasets(raw_dir=tmp_path / "nowhere", processed_dir=processed)

    players, _, _ = builder.build_datasets(
        raw_dir=tmp_path / "nowhere", processed_dir=processed
    )

    assert players.empty


def test_the_cli_surfaces_the_refusal_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    import importlib.util
    import sys as _sys

    from nhl_betting_lab.config import PROJECT_ROOT

    spec = importlib.util.spec_from_file_location(
        "_script_build_datasets_guard", PROJECT_ROOT / "scripts" / "build_datasets.py"
    )
    module = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def refuse(**kwargs):
        raise ValueError("This build produced 0 rows ... Refusing to shrink")

    monkeypatch.setattr(module, "build_datasets", refuse)
    code = module.main([])

    assert code == 1
    err = capsys.readouterr().err
    assert err.startswith("Refused:")
    assert "Traceback" not in err


def test_an_empty_build_into_an_empty_directory_is_allowed(tmp_path: Path) -> None:
    """First run on a fresh checkout: nothing to destroy, nothing refused."""
    players, teams, _ = builder.build_datasets(
        raw_dir=tmp_path / "nowhere", processed_dir=tmp_path / "processed"
    )

    assert players.empty
    assert (tmp_path / "processed" / builder.PLAYER_LOGS_FILENAME).is_file()
