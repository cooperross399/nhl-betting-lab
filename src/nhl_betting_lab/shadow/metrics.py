"""Per-game modern stats for teams, skaters and goalies.

Every figure is one team, player or goalie in one game. Rates (per 60, %),
PDO and goals saved above expected are computed from these sums by whoever
reads them, over whatever window they choose, so no table here can leak a
later game into an earlier one.

Shootout attempts are already excluded by `play_by_play.game_events`.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from nhl_betting_lab.shadow.play_by_play import GameEvents, is_high_danger
from nhl_betting_lab.shadow.xg import season_of

TEAM_COLUMNS: tuple[str, ...] = (
    "game_id", "season", "team", "opponent", "is_home",
    "toi_5v5", "toi_pp", "toi_sh",
    "cf", "ca", "ff", "fa", "sf", "sa", "gf", "ga", "xgf", "xga", "hdff", "hdfa",
    "cf_5v5", "ca_5v5", "ff_5v5", "fa_5v5", "sf_5v5", "sa_5v5",
    "gf_5v5", "ga_5v5", "xgf_5v5", "xga_5v5",
    "cf_pp", "xgf_pp", "gf_pp", "ca_sh", "xga_sh", "ga_sh",
    "en_gf", "en_ga",
    "goalie_fa", "goalie_xga", "goalie_ga",
    "pen_taken", "pen_drawn",
)

PLAYER_COLUMNS: tuple[str, ...] = (
    "game_id", "season", "player_id", "team",
    "icf", "iff", "isf", "ixg", "igoals", "ihdff", "icf_pp", "ixg_pp",
)

GOALIE_COLUMNS: tuple[str, ...] = (
    "game_id", "season", "goalie_id", "team", "fa", "sa", "ga", "xga", "hd_fa", "hd_ga",
)


def _sum(rows: pd.DataFrame, column: str) -> float:
    return float(rows[column].sum()) if not rows.empty else 0.0


def team_game_rows(events: GameEvents, shots: pd.DataFrame) -> list[dict]:
    """Two rows, one per side, from the game's xG-scored shots."""
    out: list[dict] = []
    if not events.home or not events.away:
        return out
    if shots.empty:
        shots = pd.DataFrame(
            columns=["team", "unblocked", "on_goal", "goal", "xg", "strength",
                     "empty_net", "hd"]
        )
    for team, opponent, is_home in (
        (events.home, events.away, True),
        (events.away, events.home, False),
    ):
        own = shots[shots["team"] == team]
        opp = shots[shots["team"] == opponent]
        row: dict = {
            "game_id": events.game_id,
            "team": team,
            "opponent": opponent,
            "is_home": is_home,
            "toi_5v5": events.seconds.get((team, "5v5"), 0.0),
            "toi_pp": events.seconds.get((team, "PP"), 0.0),
            "toi_sh": events.seconds.get((team, "SH"), 0.0),
            "pen_taken": events.penalties.get(team, 0),
            "pen_drawn": events.penalties.get(opponent, 0),
        }
        for suffix, mine, theirs in (
            ("", own, opp),
            ("_5v5", own[own["strength"] == "5v5"], opp[opp["strength"] == "5v5"]),
        ):
            row[f"cf{suffix}"] = len(mine)
            row[f"ca{suffix}"] = len(theirs)
            row[f"ff{suffix}"] = int(mine["unblocked"].sum())
            row[f"fa{suffix}"] = int(theirs["unblocked"].sum())
            row[f"sf{suffix}"] = int(mine["on_goal"].sum())
            row[f"sa{suffix}"] = int(theirs["on_goal"].sum())
            row[f"gf{suffix}"] = int(mine["goal"].sum())
            row[f"ga{suffix}"] = int(theirs["goal"].sum())
            row[f"xgf{suffix}"] = _sum(mine, "xg")
            row[f"xga{suffix}"] = _sum(theirs, "xg")
        row["hdff"] = int((own["unblocked"] & own["hd"]).sum())
        row["hdfa"] = int((opp["unblocked"] & opp["hd"]).sum())
        pp = own[own["strength"] == "PP"]
        row["cf_pp"] = len(pp)
        row["xgf_pp"] = _sum(pp, "xg")
        row["gf_pp"] = int(pp["goal"].sum())
        sh = opp[opp["strength"] == "PP"]
        row["ca_sh"] = len(sh)
        row["xga_sh"] = _sum(sh, "xg")
        row["ga_sh"] = int(sh["goal"].sum())
        row["en_gf"] = int((own["goal"] & own["empty_net"]).sum())
        row["en_ga"] = int((opp["goal"] & opp["empty_net"]).sum())
        faced = opp[opp["unblocked"] & ~opp["empty_net"].astype(bool)]
        row["goalie_fa"] = len(faced)
        row["goalie_xga"] = _sum(faced, "xg")
        row["goalie_ga"] = int(faced["goal"].sum())
        out.append(row)
    return out


def player_game_rows(shots: pd.DataFrame) -> list[dict]:
    if shots.empty:
        return []
    named = shots[shots["shooter_id"].notna()]
    rows: list[dict] = []
    for (player, team), mine in named.groupby(["shooter_id", "team"]):
        pp = mine[mine["strength"] == "PP"]
        rows.append(
            {
                "game_id": int(mine["game_id"].iat[0]),
                "player_id": int(player),
                "team": team,
                "icf": len(mine),
                "iff": int(mine["unblocked"].sum()),
                "isf": int(mine["on_goal"].sum()),
                "ixg": float(mine["xg"].sum()),
                "igoals": int(mine["goal"].sum()),
                "ihdff": int((mine["unblocked"] & mine["hd"]).sum()),
                "icf_pp": len(pp),
                "ixg_pp": float(pp["xg"].sum()),
            }
        )
    return rows


def goalie_game_rows(shots: pd.DataFrame) -> list[dict]:
    if shots.empty:
        return []
    faced = shots[
        shots["unblocked"].astype(bool)
        & ~shots["empty_net"].astype(bool)
        & shots["goalie_id"].notna()
    ]
    rows: list[dict] = []
    for (goalie, team), against in faced.groupby(["goalie_id", "opponent"]):
        hd = against[against["hd"]]
        rows.append(
            {
                "game_id": int(against["game_id"].iat[0]),
                "goalie_id": int(goalie),
                "team": team,
                "fa": len(against),
                "sa": int(against["on_goal"].sum()),
                "ga": int(against["goal"].sum()),
                "xga": float(against["xg"].sum()),
                "hd_fa": len(hd),
                "hd_ga": int(hd["goal"].sum()),
            }
        )
    return rows


def mark_high_danger(shots: pd.DataFrame) -> pd.DataFrame:
    frame = shots.copy()
    frame["hd"] = [
        is_high_danger(d, a) for d, a in zip(frame["distance"], frame["angle"])
    ] if not frame.empty else []
    frame["hd"] = frame["hd"].astype(bool)
    return frame


def build_tables(
    games: Iterable[GameEvents], scored_shots: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Team, player and goalie per-game tables from xG-scored shots."""
    shots = mark_high_danger(scored_shots)
    by_game = {gid: rows for gid, rows in shots.groupby("game_id")} if not shots.empty else {}
    team_rows: list[dict] = []
    player_rows: list[dict] = []
    goalie_rows: list[dict] = []
    for events in games:
        game_shots = by_game.get(events.game_id, shots.iloc[0:0])
        team_rows += team_game_rows(events, game_shots)
        player_rows += player_game_rows(game_shots)
        goalie_rows += goalie_game_rows(game_shots)
    tables = []
    for rows, columns in (
        (team_rows, TEAM_COLUMNS),
        (player_rows, PLAYER_COLUMNS),
        (goalie_rows, GOALIE_COLUMNS),
    ):
        frame = pd.DataFrame(rows)
        if frame.empty:
            frame = pd.DataFrame(columns=list(columns))
        else:
            frame["season"] = frame["game_id"].map(season_of)
            frame = frame[list(columns)]
        tables.append(frame)
    return tables[0], tables[1], tables[2]
