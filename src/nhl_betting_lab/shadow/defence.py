"""The defensive half of a skater's rating, from who was on the ice.

Cooper, 2026-10-26 (PostHockey's Net Rating has an offensive and a defensive
half; this lab had only the offensive one, `lineups.skater_ratings`). Net
Rating's defence is a skater's on-ice goals and xG against. This builds the
xG half from the shift charts (`shadow.shifts`) and the play-by-play's
shooter-adjusted xG (`xg_sh`):

* **On ice at 5v5 only**, five skaters and a goalie a side, read from the
  shift charts second by second. Special teams are deployment, not defence.
* **Relative to his teammates** (RelTM): his on-ice xG against per second
  minus his team's when he is off the ice, so a good player on a bad team is
  not charged for the team. Negative is better.
* **Three seasons, Marcel-style**, weighted 1 / 0.5 / 0.3 as the offensive
  rating is, and **shrunk toward zero** by `SHRINKAGE_SECONDS` of 5v5 ice
  time, because on-ice defence is noisy: a season of a third-pair defenceman
  is about half signal.
* **In goals a game**: the relative rate times his own 5v5 ice time a game,
  sign flipped, so a positive number is goals he prevents per game he
  dresses. Clamped to +/- `MAX_IMPACT`.

No age curve: the offensive curve is fitted on box-score game score and
there is no defensive history long enough here (the shift charts this lab
reads start with the play-by-play, 2023-24) to fit one. Nothing here is
measured against prices.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from nhl_betting_lab.shadow.shifts import shifts as read_shifts

#: Season weights, newest first: the offensive rating's (`lineups.SEASON_WEIGHTS`).
SEASON_WEIGHTS = (1.0, 0.5, 0.3)

#: Weighted 5v5 seconds of a skater's own record that count as much as the
#: prior of zero (1,000 minutes, about a season of a second-pair defenceman).
SHRINKAGE_SECONDS = 60_000.0

#: The most goals a game one skater's defence can be worth either way.
MAX_IMPACT = 0.20

PERIOD_SECONDS = 1200


def _on_ice_matrix(rows: list[dict[str, Any]], length: int) -> tuple[list[int], np.ndarray]:
    players = sorted({r["player_id"] for r in rows})
    index = {p: k for k, p in enumerate(players)}
    matrix = np.zeros((len(players), length), dtype=bool)
    for r in rows:
        # A shift covers (start, end]: second index i is the interval (i, i+1].
        matrix[index[r["player_id"]], r["start"]:min(r["end"], length)] = True
    return players, matrix


def game_on_ice(
    payload: Mapping[str, Any],
    shots: pd.DataFrame,
    goalies: set[int],
    *,
    column: str = "xg_sh",
) -> pd.DataFrame:
    """One game's skaters: 5v5 seconds on ice, xG against on ice, and the team's.

    `shots` is this game's scored attempts (`game_seconds`, `period`, `team`,
    `unblocked` and `column`); `goalies` the ids of every goalie, so a goalie's
    shift marks his net as manned and never earns him a skater row.
    """
    every = read_shifts(payload)
    if not every:
        return pd.DataFrame()
    teams = sorted({r["team"] for r in every})
    if len(teams) != 2:
        return pd.DataFrame()
    attempts = shots[shots["unblocked"].astype(bool)] if not shots.empty else shots
    out: dict[int, dict[str, Any]] = {}
    team_seconds = 0.0
    team_xga = {t: 0.0 for t in teams}
    for period in sorted({r["period"] for r in every}):
        rows = [r for r in every if r["period"] == period]
        length = max(r["end"] for r in rows)
        skaters = {t: [r for r in rows if r["team"] == t and r["player_id"] not in goalies] for t in teams}
        nets = {t: [r for r in rows if r["team"] == t and r["player_id"] in goalies] for t in teams}
        counts, mats, manned = {}, {}, {}
        for t in teams:
            players, matrix = _on_ice_matrix(skaters[t], length)
            mats[t] = (players, matrix)
            counts[t] = matrix.sum(axis=0) if len(players) else np.zeros(length, dtype=int)
            _, net = _on_ice_matrix(nets[t], length)
            manned[t] = net.any(axis=0) if len(net) else np.zeros(length, dtype=bool)
        five = (counts[teams[0]] == 5) & (counts[teams[1]] == 5) & manned[teams[0]] & manned[teams[1]]
        team_seconds += float(five.sum())
        for t in teams:
            players, matrix = mats[t]
            seconds = (matrix & five).sum(axis=1)
            for k, p in enumerate(players):
                row = out.setdefault(p, {"player_id": p, "team": t, "seconds": 0.0, "on_xga": 0.0})
                row["seconds"] += float(seconds[k])
        if attempts.empty:
            continue
        mine = attempts[attempts["period"] == period]
        for shooter_team, game_seconds, value in mine[["team", "game_seconds", column]].itertuples(index=False):
            i = int(game_seconds) - (period - 1) * PERIOD_SECONDS - 1
            if i < 0:
                i = 0
            if i >= length or not five[i]:
                continue
            xg = float(value) if value == value else 0.0
            if str(shooter_team) not in teams:
                continue
            defending = teams[1] if str(shooter_team) == teams[0] else teams[0]
            team_xga[defending] += xg
            players, matrix = mats[defending]
            for k in np.flatnonzero(matrix[:, i]):
                out[players[k]]["on_xga"] += xg
    frame = pd.DataFrame(out.values())
    if frame.empty:
        return frame
    frame["team_seconds"] = team_seconds
    frame["team_xga"] = frame["team"].map(team_xga)
    frame = frame[frame["seconds"] > 0]
    return frame.reset_index(drop=True)


def on_ice_table(
    charts: Iterable[tuple[int, Mapping[str, Any]]],
    shots: pd.DataFrame,
    *,
    column: str = "xg_sh",
) -> pd.DataFrame:
    """Every charted game's skater rows, with `game_id` and `season`."""
    goalies = {int(g) for g in shots.get("goalie_id", pd.Series(dtype=float)).dropna().unique()}
    by_game = {gid: rows for gid, rows in shots.groupby("game_id")} if not shots.empty else {}
    frames = []
    for game_id, payload in charts:
        rows = game_on_ice(payload, by_game.get(int(game_id), shots.iloc[0:0]), goalies, column=column)
        if rows.empty:
            continue
        rows["game_id"] = int(game_id)
        rows["season"] = int(str(game_id)[:4])
        frames.append(rows)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def skater_defence(on_ice: pd.DataFrame) -> tuple[dict[str, float], dict[str, float]]:
    """({NHL id: goals prevented a game}, {NHL id: weighted 5v5 seconds}).

    Over the last three seasons `on_ice` holds, weighted `SEASON_WEIGHTS`
    newest first: on-ice xG against per second minus the team's off-ice rate,
    shrunk toward zero by `SHRINKAGE_SECONDS`, times his own 5v5 seconds a
    game, sign flipped.
    """
    if on_ice is None or on_ice.empty:
        return {}, {}
    seasons = sorted(on_ice["season"].unique())[-len(SEASON_WEIGHTS):][::-1]
    weight_of = {s: SEASON_WEIGHTS[k] for k, s in enumerate(seasons)}
    frame = on_ice[on_ice["season"].isin(seasons)].copy()
    frame["w"] = frame["season"].map(weight_of)
    frame["off_seconds"] = (frame["team_seconds"] - frame["seconds"]).clip(lower=0.0)
    frame["off_xga"] = (frame["team_xga"] - frame["on_xga"]).clip(lower=0.0)
    for column in ("seconds", "on_xga", "off_seconds", "off_xga"):
        frame[f"w_{column}"] = frame[column] * frame["w"]
    frame["w_games"] = frame["w"]
    sums = frame.groupby("player_id")[
        ["w_seconds", "w_on_xga", "w_off_seconds", "w_off_xga", "w_games"]
    ].sum()
    impacts: dict[str, float] = {}
    evidence: dict[str, float] = {}
    for player, row in sums.iterrows():
        if row["w_seconds"] <= 0 or row["w_off_seconds"] <= 0 or row["w_games"] <= 0:
            continue
        relative = row["w_on_xga"] / row["w_seconds"] - row["w_off_xga"] / row["w_off_seconds"]
        shrunk = relative * row["w_seconds"] / (row["w_seconds"] + SHRINKAGE_SECONDS)
        per_game = row["w_seconds"] / row["w_games"]
        impact = -shrunk * per_game
        impacts[str(int(player))] = round(float(max(-MAX_IMPACT, min(MAX_IMPACT, impact))), 5)
        evidence[str(int(player))] = round(float(row["w_seconds"]), 1)
    return impacts, evidence
