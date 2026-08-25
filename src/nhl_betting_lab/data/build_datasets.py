"""Turn cached NHL boxscores into the two tables everything else reads.

`data/processed/player_game_logs.csv` — one row per player per game, carrying
every column the priced prop markets settle on.

`data/processed/team_games.csv` — one row per game, carrying the result and
the shot counts the team model is fitted on.

Both are built **only from what is already cached**. That is deliberate: a
rebuild must be reproducible offline, and a build that could reach the network
would quietly produce a different dataset depending on when it ran.

Two rules about incomplete games:

* A game that is not final produces **no** rows. A second-period boxscore has
  real numbers in it, and letting them into the logs would train the model on
  fractions of games it believes are whole ones.
* A game that is final but missing a stats block is reported by id, not
  skipped silently. A dataset that is quietly short is the hardest kind of
  bug to see.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.data.nhl_api import (
    _cache_root,
    _read_cache,
    cached_boxscore_ids,
    game_is_final,
)


PLAYER_LOGS_FILENAME = "player_game_logs.csv"
TEAM_GAMES_FILENAME = "team_games.csv"

PLAYER_LOG_COLUMNS = (
    "game_id",
    "season",
    "game_type",
    "date",
    "start_time_utc",
    "player_id",
    "player",
    "boxscore_name",
    "role",
    "position",
    "team",
    "opponent",
    "venue",
    "toi_seconds",
    "shots_on_goal",
    "goals",
    "assists",
    "points",
    "blocked_shots",
    "hits",
    "power_play_goals",
    "saves",
    "shots_against",
    "goals_against",
)

TEAM_GAME_COLUMNS = (
    "game_id",
    "season",
    "game_type",
    "date",
    "start_time_utc",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "home_shots",
    "away_shots",
    "regulation",
)


@dataclass
class BuildResult:
    """What one rebuild saw, so a short dataset announces itself."""

    games_seen: int = 0
    games_used: int = 0
    games_not_final: list[int] = field(default_factory=list)
    games_malformed: list[int] = field(default_factory=list)
    player_rows: int = 0
    names_resolved: int = 0
    names_unresolved: int = 0

    def summary_line(self) -> str:
        parts = [
            f"{self.games_used} of {self.games_seen} cached games used",
            f"{self.player_rows} player-game rows",
        ]
        if self.games_not_final:
            parts.append(f"{len(self.games_not_final)} not final (skipped)")
        if self.games_malformed:
            parts.append(f"{len(self.games_malformed)} malformed (reported)")
        if self.names_unresolved:
            parts.append(f"{self.names_unresolved} names unresolved")
        return "; ".join(parts) + "."


def parse_toi(value: object) -> int:
    """`"13:11"` -> 791 seconds. An unreadable value is 0, never a guess."""
    text = str(value or "").strip()
    if not text or ":" not in text:
        return 0
    minutes, _, seconds = text.partition(":")
    try:
        return int(minutes) * 60 + int(seconds)
    except ValueError:
        return 0


def parse_saves(value: object) -> tuple[int, int]:
    """`"30/31"` -> (saves, shots against). Unreadable -> (0, 0)."""
    text = str(value or "").strip()
    if "/" not in text:
        return 0, 0
    saves, _, shots = text.partition("/")
    try:
        return int(saves), int(shots)
    except ValueError:
        return 0, 0


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def load_player_registry(
    season_ids: Iterable[int] | None = None, *, raw_dir: Path | None = None
) -> dict[int, str]:
    """`playerId` -> full name, merged across every cached season registry."""
    directory = _cache_root(raw_dir) / "registry"
    if not directory.is_dir():
        return {}
    wanted = {int(item) for item in season_ids} if season_ids else None
    names: dict[int, str] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            season = int(path.stem)
        except ValueError:
            continue
        if wanted is not None and season not in wanted:
            continue
        payload = _read_cache(path)
        if not isinstance(payload, Mapping):
            continue
        for role in ("skaters", "goalies"):
            for row in payload.get(role, []) or []:
                if not isinstance(row, Mapping):
                    continue
                player_id = row.get("playerId")
                full_name = str(row.get("fullName", "")).strip()
                if player_id is None or not full_name:
                    continue
                # A later season wins: a player's registered name can change
                # (a legal name change, a spelling correction), and the most
                # recent spelling is the one the odds provider will use.
                names[int(player_id)] = full_name
    return names


def _boxscore_name(player: Mapping[str, Any]) -> str:
    name = player.get("name")
    if isinstance(name, Mapping):
        return str(name.get("default", "")).strip()
    return str(name or "").strip()


def player_rows_from_boxscore(
    payload: Mapping[str, Any], *, registry: Mapping[int, str] | None = None
) -> list[dict[str, Any]]:
    """Every player row for one final boxscore. Raises nothing; returns []."""
    names = registry or {}
    stats = payload.get("playerByGameStats")
    if not isinstance(stats, Mapping):
        return []
    home = payload.get("homeTeam") or {}
    away = payload.get("awayTeam") or {}
    home_team = str(home.get("abbrev", "")).strip().upper()
    away_team = str(away.get("abbrev", "")).strip().upper()
    if not home_team or not away_team:
        return []

    shared = {
        "game_id": _int(payload.get("id")),
        "season": _int(payload.get("season")),
        "game_type": _int(payload.get("gameType")),
        "date": str(payload.get("gameDate", "")).strip(),
        "start_time_utc": str(payload.get("startTimeUTC", "")).strip(),
    }

    rows: list[dict[str, Any]] = []
    for side, team, opponent, venue in (
        ("homeTeam", home_team, away_team, "home"),
        ("awayTeam", away_team, home_team, "away"),
    ):
        block = stats.get(side)
        if not isinstance(block, Mapping):
            continue
        for group in ("forwards", "defense", "goalies"):
            for player in block.get(group, []) or []:
                if not isinstance(player, Mapping):
                    continue
                player_id = _int(player.get("playerId"))
                if not player_id:
                    continue
                is_goalie = group == "goalies"
                saves, shots_against = (
                    parse_saves(player.get("saveShotsAgainst"))
                    if is_goalie
                    else (0, 0)
                )
                rows.append(
                    {
                        **shared,
                        "player_id": player_id,
                        "player": names.get(player_id, ""),
                        "boxscore_name": _boxscore_name(player),
                        "role": "goalie" if is_goalie else "skater",
                        "position": str(player.get("position", "")).strip().upper(),
                        "team": team,
                        "opponent": opponent,
                        "venue": venue,
                        "toi_seconds": parse_toi(player.get("toi")),
                        "shots_on_goal": 0 if is_goalie else _int(player.get("sog")),
                        "goals": 0 if is_goalie else _int(player.get("goals")),
                        "assists": 0 if is_goalie else _int(player.get("assists")),
                        "points": 0 if is_goalie else _int(player.get("points")),
                        "blocked_shots": (
                            0 if is_goalie else _int(player.get("blockedShots"))
                        ),
                        "hits": 0 if is_goalie else _int(player.get("hits")),
                        # The boxscore carries power-play *goals* and nothing
                        # else about power-play usage — no PP time on ice, no
                        # PP assists. There is deliberately no
                        # `power_play_points` column: naming a goals count
                        # "points" would be a lie the model would then inherit.
                        # `player_props.py` builds its deployment proxy from
                        # this column knowing exactly what it is.
                        "power_play_goals": (
                            0 if is_goalie else _int(player.get("powerPlayGoals"))
                        ),
                        "saves": saves,
                        "shots_against": shots_against,
                        "goals_against": _int(player.get("goalsAgainst"))
                        if is_goalie
                        else 0,
                    }
                )
    return rows


def team_row_from_boxscore(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """One game's result row, or None when the payload cannot supply one."""
    home = payload.get("homeTeam")
    away = payload.get("awayTeam")
    if not isinstance(home, Mapping) or not isinstance(away, Mapping):
        return None
    home_team = str(home.get("abbrev", "")).strip().upper()
    away_team = str(away.get("abbrev", "")).strip().upper()
    if not home_team or not away_team or home_team == away_team:
        return None
    period = payload.get("periodDescriptor")
    number = _int(period.get("number")) if isinstance(period, Mapping) else 0
    return {
        "game_id": _int(payload.get("id")),
        "season": _int(payload.get("season")),
        "game_type": _int(payload.get("gameType")),
        "date": str(payload.get("gameDate", "")).strip(),
        "start_time_utc": str(payload.get("startTimeUTC", "")).strip(),
        "home_team": home_team,
        "away_team": away_team,
        "home_goals": _int(home.get("score")),
        "away_goals": _int(away.get("score")),
        "home_shots": _int(home.get("sog")),
        "away_shots": _int(away.get("sog")),
        # Regulation means the game ended in three periods. Overtime and
        # shootouts matter: a puck-line or totals model that treats a shootout
        # winner's empty-net-free extra goal as an ordinary goal is wrong.
        "regulation": number <= 3,
    }


def build_datasets(
    *,
    raw_dir: Path | None = None,
    processed_dir: Path | None = None,
    game_ids: Iterable[int] | None = None,
    write: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, BuildResult]:
    """Rebuild both processed tables from the cache. No network access."""
    ids = (
        [int(item) for item in game_ids]
        if game_ids is not None
        else cached_boxscore_ids(raw_dir)
    )
    registry = load_player_registry(raw_dir=raw_dir)
    result = BuildResult(games_seen=len(ids))
    player_rows: list[dict[str, Any]] = []
    team_rows: list[dict[str, Any]] = []

    for game_id in ids:
        path = _cache_root(raw_dir) / "boxscore" / f"{game_id}.json"
        payload = _read_cache(path)
        if not isinstance(payload, Mapping):
            result.games_malformed.append(game_id)
            continue
        if not game_is_final(payload):
            result.games_not_final.append(game_id)
            continue
        rows = player_rows_from_boxscore(payload, registry=registry)
        team_row = team_row_from_boxscore(payload)
        if not rows or team_row is None:
            result.games_malformed.append(game_id)
            continue
        player_rows.extend(rows)
        team_rows.append(team_row)
        result.games_used += 1

    players = pd.DataFrame(player_rows, columns=list(PLAYER_LOG_COLUMNS))
    teams = pd.DataFrame(team_rows, columns=list(TEAM_GAME_COLUMNS))
    if not players.empty:
        players = players.sort_values(
            ["date", "game_id", "team", "player_id"], ignore_index=True
        )
        result.names_resolved = int((players["player"].astype(str) != "").sum())
        result.names_unresolved = len(players) - result.names_resolved
    if not teams.empty:
        teams = teams.sort_values(["date", "game_id"], ignore_index=True)
    result.player_rows = len(players)

    if write:
        directory = Path(processed_dir) if processed_dir else Path(PROCESSED_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        players.to_csv(
            directory / PLAYER_LOGS_FILENAME, index=False, lineterminator="\n"
        )
        teams.to_csv(
            directory / TEAM_GAMES_FILENAME, index=False, lineterminator="\n"
        )
    return players, teams, result


def load_player_logs(processed_dir: Path | None = None) -> pd.DataFrame:
    """The built player logs, or an empty frame with the right columns."""
    directory = Path(processed_dir) if processed_dir else Path(PROCESSED_DIR)
    path = directory / PLAYER_LOGS_FILENAME
    if not path.is_file():
        return pd.DataFrame(columns=list(PLAYER_LOG_COLUMNS))
    return pd.read_csv(path)


def load_team_games(processed_dir: Path | None = None) -> pd.DataFrame:
    """The built team games, or an empty frame with the right columns."""
    directory = Path(processed_dir) if processed_dir else Path(PROCESSED_DIR)
    path = directory / TEAM_GAMES_FILENAME
    if not path.is_file():
        return pd.DataFrame(columns=list(TEAM_GAME_COLUMNS))
    return pd.read_csv(path)
