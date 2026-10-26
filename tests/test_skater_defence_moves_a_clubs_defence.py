"""The defensive half of a skater's rating reaches the card through the lineup.

Cooper, 2026-10-26: PostHockey's Net Rating has a defensive half, from who was
on the ice for the chances against. These hold:

* the shift chart is read as shifts, goals and the shootout dropped;
* only 5v5 seconds with both nets manned count, and an attempt is charged to
  the five skaters defending at that second;
* a skater on the ice for fewer chances against than his team without him is
  rated as preventing goals, shrunk toward zero by his ice time;
* tonight's sheet with a better defender than the usual eighteen lowers the
  club's defence factor, never past its floor, and a club with no rated
  skater moves nothing.
"""

from __future__ import annotations

import json

import pandas as pd

from nhl_betting_lab import lineups as lu
from nhl_betting_lab.shadow import defence
from nhl_betting_lab.shadow.shifts import is_charted, shifts

GAME = 2025020001


def _shift(player: int, team: str, start: str, end: str, period: int = 1, kind: int = 517) -> dict:
    return {"gameId": GAME, "playerId": player, "teamAbbrev": team, "period": period,
            "startTime": start, "endTime": end, "typeCode": kind}


def _chart(home_swap: bool = True) -> dict:
    rows = []
    # Goalies 1 (TOR) and 2 (BOS) all period; five skaters a side.
    rows.append(_shift(1, "TOR", "00:00", "20:00"))
    rows.append(_shift(2, "BOS", "00:00", "20:00"))
    for k in range(5):
        rows.append(_shift(200 + k, "BOS", "00:00", "20:00"))
    for k in range(4):
        rows.append(_shift(100 + k, "TOR", "00:00", "20:00"))
    # TOR's fifth skater: 104 for the first ten minutes, 105 for the rest.
    rows.append(_shift(104, "TOR", "00:00", "10:00"))
    rows.append(_shift(105, "TOR", "10:00", "20:00"))
    rows.append({"gameId": GAME, "playerId": 104, "typeCode": 505, "eventDescription": "EVG",
                 "period": 1, "startTime": "05:00", "endTime": "05:00", "teamAbbrev": "TOR"})
    rows.append(_shift(104, "TOR", "00:00", "00:05", period=5))
    return {"data": rows, "total": len(rows)}


def _shots() -> pd.DataFrame:
    # BOS shoots at TOR: 0.5 xG while 104 is on, 0.1 while 105 is on, and a
    # blocked attempt that carries no xG.
    return pd.DataFrame([
        {"game_id": GAME, "period": 1, "game_seconds": 300, "team": "BOS", "unblocked": True, "xg_sh": 0.5, "goalie_id": 1},
        {"game_id": GAME, "period": 1, "game_seconds": 900, "team": "BOS", "unblocked": True, "xg_sh": 0.1, "goalie_id": 1},
        {"game_id": GAME, "period": 1, "game_seconds": 950, "team": "BOS", "unblocked": False, "xg_sh": None, "goalie_id": 1},
        {"game_id": GAME, "period": 1, "game_seconds": 500, "team": "TOR", "unblocked": True, "xg_sh": 0.2, "goalie_id": 2},
    ])


def test_the_chart_is_read_as_shifts_only() -> None:
    chart = _chart()
    assert is_charted(chart) and not is_charted({"data": []})
    read = shifts(chart)
    assert all(r["period"] < 5 for r in read)
    assert len(read) == 13  # two goalies, ten skaters' shifts, one swap; no goal row


def test_an_attempt_is_charged_to_the_five_defending() -> None:
    rows = defence.game_on_ice(_chart(), _shots(), {1, 2}).set_index("player_id")
    assert 1 not in rows.index and 2 not in rows.index  # goalies are not skaters
    assert rows.loc[104, "on_xga"] == 0.5 and rows.loc[105, "on_xga"] == 0.1
    assert rows.loc[100, "on_xga"] == 0.6
    assert rows.loc[104, "seconds"] == 600 and rows.loc[100, "seconds"] == 1200
    assert rows.loc[100, "team_xga"] == 0.6 and rows.loc[200, "on_xga"] == 0.2


def test_the_better_defender_is_rated_as_preventing_goals() -> None:
    on_ice = defence.on_ice_table([(GAME, _chart())], _shots())
    impacts, evidence = defence.skater_defence(on_ice)
    assert impacts["105"] > 0 > impacts["104"]
    assert abs(impacts["105"]) <= defence.MAX_IMPACT
    # Shrunk: ten minutes of evidence is far below the prior's weight.
    raw = (0.5 / 600 - 0.1 / 600) * 600
    assert abs(impacts["105"]) < raw * 0.05
    assert evidence["105"] == 600.0


def _logs() -> pd.DataFrame:
    rows = []
    for g in range(20):
        for k in range(18):
            rows.append({"role": "skater", "date": f"2025-05-{1 + g:02d}", "team": "TOR",
                         "game_id": 1000 + g, "player": f"Skater {k}", "player_id": 500 + k,
                         "position": "D" if k >= 12 else "C"})
    rows.append({"role": "skater", "date": "2025-05-21", "team": "TOR", "game_id": 2000,
                 "player": "Star Defender", "player_id": 900, "position": "D"})
    return pd.DataFrame(rows)


def test_a_better_defender_tonight_lowers_the_clubs_defence(tmp_path) -> None:
    logs = _logs()
    usual = [(f"Skater {k}", "d1" if k >= 12 else "f1") for k in range(18)]
    tonight = usual[:-1] + [("Star Defender", "d3")]
    impacts = {"900": 0.15}
    factors = lu._lineup_defence(logs, {"TOR": {}}, {"TOR": tonight}, "2025-06-01", impacts)
    expected = 1.0 - lu.HOLE_WEIGHT * 0.15 / lu.LEAGUE_GOALS_PER_GAME
    assert abs(factors["TOR"] - expected) < 1e-9
    huge = lu._lineup_defence(logs, {"TOR": {}}, {"TOR": tonight}, "2025-06-01", {"900": 5.0})
    assert huge["TOR"] == lu.MIN_DEFENCE_FACTOR
    same = lu._lineup_defence(logs, {"TOR": {}}, {"TOR": usual}, "2025-06-01", impacts)
    assert same["TOR"] == 1.0
    assert lu._lineup_defence(logs, {"TOR": {}}, {"TOR": tonight}, "2025-06-01", {}) == {}


def test_the_ratings_file_is_read_and_a_missing_one_moves_nothing(tmp_path) -> None:
    assert lu.load_skater_defence(tmp_path) == {}
    (tmp_path / lu.RATINGS_FILE).write_text(json.dumps({"skater_defence": {"900": 0.1}}))
    assert lu.load_skater_defence(tmp_path) == {"900": 0.1}
