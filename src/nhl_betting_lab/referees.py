"""Referee crews: how many goals each referee's games produce, read into the card.

Cooper, 2026-10-21, asked for referee crew penalty rates to be factored in.
Penalties reach the bets this lab makes as goals: a crew that calls more puts
more power plays, and more goals and points, on the ice. So this measures the
outcome directly: for each referee, the total goals of the regular-season
games he worked against the league's per-game total over the same games'
seasons, shrunk toward even at `SHRINKAGE_GAMES`. A crew is the mean of its
referees (linesmen call no penalties that matter here), clamped to
`FACTOR_RANGE`, and it scales both clubs' expected goals, so the total moves
and the split does not, and the scoring props (goals, assists, points) of
every skater in the game.

Who worked each game comes from the NHL's free right-rail
(`/v1/gamecenter/{id}/right-rail`, `gameInfo.referees`), the same block
`scripts/capture_deployment.py` reads. `scripts/fetch_referees.py` adds past
games to `data/processed/referee_games.csv` a budget at a time, newest
first, and records tonight's crews in
`data/processed/referees_tonight/<league day>.csv`; Gameday Refresh runs it
before the card. A game whose crew is not posted yet, or a referee with no
history, moves nothing. Nothing here is measured against prices, and the
constants are this lab's choice.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd

HISTORY_FILENAME = "referee_games.csv"
TONIGHT_DIRNAME = "referees_tonight"
HISTORY_COLUMNS = ("game_id", "date", "home_team", "away_team", "referees")
TONIGHT_COLUMNS = ("date", "game_id", "home_team", "away_team", "referees", "retrieved_at")

#: Games a referee's record needs before it counts half.
SHRINKAGE_GAMES = 120
#: A crew moves a game's expected goals by at most this much either way.
FACTOR_RANGE = (0.95, 1.05)
#: The prop stats a crew moves.
SCORING_STATS = frozenset({"goals", "assists", "points"})


def _name_of(entry: object) -> str:
    """A referee entry's name. The right-rail nests it as fullName.default."""
    if not isinstance(entry, dict):
        return str(entry)
    full = entry.get("fullName")
    if isinstance(full, dict):
        return str(full.get("default", ""))
    if isinstance(full, str):
        return full
    return str(entry.get("default", ""))


def referees_of(payload: object) -> list[str]:
    """The referees a right-rail names, or ValueError when it has no gameInfo."""
    info = payload.get("gameInfo") if isinstance(payload, dict) else None
    if not isinstance(info, dict):
        raise ValueError("the right-rail answered with no gameInfo block")
    names = []
    for entry in info.get("referees") or []:
        name = _name_of(entry)
        if str(name).strip():
            names.append(str(name).strip())
    return names


def load_history(processed_dir: Path) -> pd.DataFrame:
    path = Path(processed_dir) / HISTORY_FILENAME
    if not path.is_file():
        return pd.DataFrame(columns=list(HISTORY_COLUMNS))
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame(columns=list(HISTORY_COLUMNS))
    if not set(HISTORY_COLUMNS) <= set(frame.columns):
        return pd.DataFrame(columns=list(HISTORY_COLUMNS))
    return frame


def append_rows(path: Path, rows: Iterable[dict], columns: tuple[str, ...]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(columns)).to_csv(
        path, mode="a", header=not path.is_file(), index=False, lineterminator="\n"
    )
    return len(rows)


def referee_factors(history: pd.DataFrame, team_games: pd.DataFrame) -> dict[str, float]:
    """Referee -> shrunk ratio of his games' total goals to the league's."""
    if history.empty or team_games.empty:
        return {}
    games = team_games.copy()
    games["game_id"] = games["game_id"].astype(str)
    games["total"] = pd.to_numeric(games["home_goals"], errors="coerce") + pd.to_numeric(
        games["away_goals"], errors="coerce"
    )
    games = games.dropna(subset=["total"])
    if "season" in games.columns:
        league = games.groupby("season")["total"].transform("mean")
    else:
        league = pd.Series(games["total"].mean(), index=games.index)
    games["ratio"] = games["total"] / league
    ratio_of = dict(zip(games["game_id"], games["ratio"]))
    worked: dict[str, list[float]] = {}
    for row in history.itertuples():
        ratio = ratio_of.get(str(row.game_id))
        if ratio is None:
            continue
        for name in _names(row.referees):
            worked.setdefault(name, []).append(float(ratio))
    out = {}
    for name, ratios in worked.items():
        weight = len(ratios) / (len(ratios) + SHRINKAGE_GAMES)
        out[name] = 1.0 + weight * (sum(ratios) / len(ratios) - 1.0)
    return out


def crew_factor(names: Iterable[str], factors: Mapping[str, float]) -> float:
    """The crew's factor: the mean of its known referees, clamped."""
    known = [factors[name] for name in names if name in factors]
    if not known:
        return 1.0
    low, high = FACTOR_RANGE
    return min(high, max(low, sum(known) / len(known)))


def _names(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    return [str(v) for v in parsed if str(v).strip()] if isinstance(parsed, list) else []


def tonight_factors(processed_dir: Path, day: str, team_games: pd.DataFrame) -> dict[frozenset, float]:
    """{frozenset({home, away}): crew factor} for tonight's games with a crew."""
    path = Path(processed_dir) / TONIGHT_DIRNAME / f"{day}.csv"
    if not path.is_file():
        return {}
    try:
        tonight = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, ValueError, pd.errors.ParserError):
        return {}
    if tonight.empty or not set(TONIGHT_COLUMNS) <= set(tonight.columns):
        return {}
    tonight = tonight.sort_values("retrieved_at").drop_duplicates("game_id", keep="last")
    factors = referee_factors(load_history(processed_dir), team_games)
    out: dict[frozenset, float] = {}
    for row in tonight.itertuples():
        names = _names(row.referees)
        if not names:
            continue
        factor = crew_factor(names, factors)
        if factor != 1.0:
            out[frozenset({str(row.home_team), str(row.away_team)})] = factor
    return out
