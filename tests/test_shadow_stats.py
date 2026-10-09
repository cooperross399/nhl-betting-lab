"""The shadow model's play-by-play reading and its end-to-end measurement.

The real feed cannot be fetched in the test environment, so these build
play-by-play payloads in the API's own shape and hold the parse to the rules
the module states: strength from the shooter's side, the net shot at taken
from the side home defends, blocks kept out of xG, the shootout excluded.
The end-to-end run then checks the boxscore validation reads 100% on a feed
that agrees with its boxscores.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from nhl_betting_lab.data.build_datasets import PLAYER_LOG_COLUMNS, TEAM_GAME_COLUMNS
from nhl_betting_lab.shadow.play_by_play import (
    game_events,
    parse_situation,
    shot_geometry,
    strength_for,
)
from nhl_betting_lab.shadow.xg import XgModel, add_expected_goals, season_of

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_shadow_stats.py"


def _script():
    spec = importlib.util.spec_from_file_location("run_shadow_stats", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


HOME_ID, AWAY_ID = 1, 2


def _play(kind, period, clock, situation="1551", side="left", **details):
    return {
        "typeDescKey": kind,
        "periodDescriptor": {"number": period, "periodType": "SO" if period == 5 else ("OT" if period == 4 else "REG")},
        "timeInPeriod": f"{clock // 60:02d}:{clock % 60:02d}",
        "situationCode": situation,
        "homeTeamDefendingSide": side,
        "details": details,
    }


def _payload(game_id, plays, home="HOM", away="AWY", players=((11, HOME_ID), (21, AWAY_ID))):
    return {
        "id": game_id,
        "gameType": 2,
        "gameState": "OFF",
        "homeTeam": {"id": HOME_ID, "abbrev": home},
        "awayTeam": {"id": AWAY_ID, "abbrev": away},
        "rosterSpots": [{"playerId": p, "teamId": t} for p, t in players],
        "plays": plays,
    }


def test_situation_and_strength_are_read_from_the_shooters_side() -> None:
    situation = parse_situation("1451")  # away 4 skaters, home 5: home power play
    assert situation == (1, 4, 5, 1)
    assert strength_for(situation, home=True) == "PP"
    assert strength_for(situation, home=False) == "SH"
    assert strength_for(parse_situation("1560"), home=True) == "EA"
    assert strength_for(parse_situation("1441"), home=True) == "EV"
    assert parse_situation("15") is None


def test_the_net_shot_at_comes_from_the_side_home_defends() -> None:
    # Home defends left, so home shoots at x = +89.
    distance, angle = shot_geometry(79.0, 0.0, shooter_home=True, home_defending="left", zone="O")
    assert distance == pytest.approx(10.0) and angle == pytest.approx(0.0)
    distance, _ = shot_geometry(79.0, 0.0, shooter_home=False, home_defending="left", zone="D")
    assert distance == pytest.approx(168.0)
    distance, angle = shot_geometry(-79.0, 10.0, shooter_home=False, home_defending="left", zone="O")
    assert distance == pytest.approx(math.hypot(10, 10)) and angle == pytest.approx(45.0)


def test_a_block_counts_for_corsi_only_and_the_shootout_is_excluded() -> None:
    plays = [
        _play("faceoff", 1, 0),
        _play("shot-on-goal", 1, 10, shootingPlayerId=11, xCoord=70, yCoord=5, shotType="wrist", goalieInNetId=99),
        _play("blocked-shot", 1, 12, shootingPlayerId=11, blockingPlayerId=21, eventOwnerTeamId=AWAY_ID, xCoord=60, yCoord=0),
        _play("goal", 1, 13, scoringPlayerId=11, xCoord=85, yCoord=2, shotType="tip-in", goalieInNetId=99),
        _play("missed-shot", 1, 20, situation="1451", shootingPlayerId=21, xCoord=-70, yCoord=0),
        _play("penalty", 1, 30, committedByPlayerId=21, duration=2),
        _play("period-end", 1, 1200),
        _play("goal", 5, 0, scoringPlayerId=21, xCoord=-80, yCoord=0, shotType="wrist"),
    ]
    events = game_events(_payload(2024020001, plays))
    kinds = [(s["team"], s["event"]) for s in events.shots]
    assert kinds == [("HOM", "shot"), ("HOM", "block"), ("HOM", "goal"), ("AWY", "miss")]
    goal = events.shots[2]
    assert goal["rebound"] is True  # three seconds after the last unblocked attempt
    assert events.shots[3]["strength"] == "SH"
    assert events.penalties == {"AWY": 1}
    assert events.seconds[("HOM", "5v5")] == pytest.approx(1190.0)
    assert events.seconds[("HOM", "PP")] == pytest.approx(10.0)


def test_an_unattributable_block_is_dropped_not_guessed() -> None:
    plays = [_play("blocked-shot", 1, 5, shootingPlayerId=None, eventOwnerTeamId=AWAY_ID, xCoord=0, yCoord=0)]
    events = game_events(_payload(2024020002, plays))
    assert events.shots == [] and events.unattributed == 1


def test_xg_learns_that_closer_shots_score_more_and_is_fitted_on_earlier_seasons() -> None:
    rng = np.random.default_rng(1)
    n = 6000
    distance = rng.uniform(5, 60, n)
    p = 1 / (1 + np.exp(-(1.0 - 0.12 * distance)))
    shots = pd.DataFrame(
        {
            "game_id": np.where(np.arange(n) < n // 2, 2023020001, 2024020001),
            "distance": distance,
            "angle": rng.uniform(0, 60, n),
            "rebound": False,
            "empty_net": False,
            "shot_type": "wrist",
            "strength": "5v5",
            "unblocked": True,
            "goal": rng.uniform(size=n) < p,
        }
    )
    model = XgModel.fit(shots)
    near, far = model.predict(shots.iloc[[int(distance.argmin()), int(distance.argmax())]])
    assert near > 3 * far
    _, record = add_expected_goals(shots)
    assert [r.in_sample for r in record] == [True, False]
    assert record[1].fitted_on == (20232024,)
    assert season_of(2025020001) == 20252026


def _synthetic_season(rng, start_year, games_per_team_pair, teams):
    """Payloads, team-game rows and player-log rows that agree with each other."""
    payloads, team_rows, log_rows = [], [], []
    number = 1
    day = pd.Timestamp(f"{start_year}-10-10")
    strength = {t: rng.normal(0, 0.3) for t in teams}
    for _ in range(games_per_team_pair):
        for i, home in enumerate(teams):
            for away in teams[i + 1:]:
                gid = int(f"{start_year}02{number:04d}")
                number += 1
                day += pd.Timedelta(hours=8)
                home_id, away_id = teams.index(home) + 1, teams.index(away) + 1
                shooters = {home: 1000 + home_id * 10, away: 1000 + away_id * 10}
                plays = [_play("faceoff", 1, 0)]
                clock = 0
                tally = {home: [0, 0], away: [0, 0]}  # shots on goal, goals
                for team in [home, away] * 15:
                    clock += 20
                    rate = 0.09 * math.exp(strength[team])
                    dist = rng.uniform(8, 50)
                    scored = rng.uniform() < rate * (40 / (dist + 10))
                    x = 89 - dist if team == home else -(89 - dist)
                    kind = "goal" if scored else "shot-on-goal"
                    key = "scoringPlayerId" if scored else "shootingPlayerId"
                    plays.append(_play(kind, 1, clock, **{key: shooters[team], "xCoord": x, "yCoord": 0, "shotType": "wrist", "goalieInNetId": 9}))
                    tally[team][0] += 1
                    tally[team][1] += int(scored)
                plays.append(_play("period-end", 1, 1200))
                payload = _payload(
                    gid, plays, home=home, away=away,
                    players=((shooters[home], home_id), (shooters[away], away_id)),
                )
                payload["homeTeam"]["id"], payload["awayTeam"]["id"] = home_id, away_id
                payloads.append(payload)
                hg, ag = tally[home][1], tally[away][1]
                regulation = hg != ag
                if not regulation:
                    hg += 1  # a shootout goal the play-by-play never shows
                team_rows.append(
                    {"game_id": gid, "season": season_of(gid), "game_type": 2, "date": str(day.date()),
                     "start_time_utc": "", "home_team": home, "away_team": away,
                     "home_goals": hg, "away_goals": ag, "home_shots": tally[home][0],
                     "away_shots": tally[away][0], "regulation": regulation}
                )
                for team, opp, venue in ((home, away, "home"), (away, home, "away")):
                    log_rows.append(
                        {"game_id": gid, "season": season_of(gid), "game_type": 2, "date": str(day.date()),
                         "start_time_utc": "", "player_id": shooters[team], "player": f"Player {team}",
                         "boxscore_name": "", "role": "skater", "position": "C", "team": team,
                         "opponent": opp, "venue": venue, "toi_seconds": 1200,
                         "shots_on_goal": tally[team][0], "goals": tally[team][1], "assists": 0,
                         "points": tally[team][1], "blocked_shots": 0, "hits": 0,
                         "power_play_goals": 0, "saves": 0, "shots_against": 0, "goals_against": 0}
                    )
    return payloads, team_rows, log_rows


def test_the_whole_run_measures_and_validates(tmp_path) -> None:
    rng = np.random.default_rng(7)
    teams = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
    payloads, team_rows, log_rows = [], [], []
    for year in (2023, 2024):
        p, t, logs = _synthetic_season(rng, year, 9, teams)
        payloads += p
        team_rows += t
        log_rows += logs
    raw = tmp_path / "raw"
    cache = raw / "nhl" / "play_by_play"
    cache.mkdir(parents=True)
    for payload in payloads:
        (cache / f"{payload['id']}.json").write_text(json.dumps(payload))
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame(team_rows, columns=list(TEAM_GAME_COLUMNS)).to_csv(processed / "team_games.csv", index=False)
    pd.DataFrame(log_rows, columns=list(PLAYER_LOG_COLUMNS)).to_csv(processed / "player_game_logs.csv", index=False)
    outputs = tmp_path / "outputs"

    code = _script().main(
        ["--processed-dir", str(processed), "--raw-dir", str(raw), "--output-dir", str(outputs)]
    )

    assert code == 0
    result = json.loads((outputs / "shadow_stats.json").read_text())
    assert result["validation"]["shots_match"] == 1.0
    assert result["validation"]["goals_match"] == 1.0
    assert result["team_games_scored"] > 0
    assert {e["variant"] for e in result["team"]} >= {"corsi", "xg", "xg_luck"}
    assert {e["variant"] for e in result["starter"]} == {"xg_starter_actual", "xg_starter_projected"}
    assert result["starter_projection"]["sides"] > 0
    assert result["props"]["shots_on_goal"][0]["rows"] > 0
    report = (outputs / "shadow_stats.md").read_text()
    assert "never on it" in report and "price backtest" in report
    assert (processed / "shadow_team_games.csv").is_file()


def test_a_feed_that_disagrees_with_the_boxscores_fails_the_run(tmp_path) -> None:
    rng = np.random.default_rng(3)
    teams = ["AAA", "BBB", "CCC", "DDD"]
    payloads, team_rows, log_rows = _synthetic_season(rng, 2023, 2, teams)
    for row in team_rows:
        row["home_shots"] += 1
    raw = tmp_path / "raw"
    cache = raw / "nhl" / "play_by_play"
    cache.mkdir(parents=True)
    for payload in payloads:
        (cache / f"{payload['id']}.json").write_text(json.dumps(payload))
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame(team_rows, columns=list(TEAM_GAME_COLUMNS)).to_csv(processed / "team_games.csv", index=False)
    pd.DataFrame(log_rows, columns=list(PLAYER_LOG_COLUMNS)).to_csv(processed / "player_game_logs.csv", index=False)
    code = _script().main(
        ["--processed-dir", str(processed), "--raw-dir", str(raw), "--output-dir", str(tmp_path / "out")]
    )
    assert code == 2


def test_tables_only_writes_the_site_ratings_and_no_report(tmp_path) -> None:
    rng = np.random.default_rng(11)
    teams = ["AAA", "BBB", "CCC", "DDD"]
    payloads, team_rows, log_rows = _synthetic_season(rng, 2024, 3, teams)
    raw = tmp_path / "raw"
    cache = raw / "nhl" / "play_by_play"
    cache.mkdir(parents=True)
    for payload in payloads:
        (cache / f"{payload['id']}.json").write_text(json.dumps(payload))
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame(team_rows, columns=list(TEAM_GAME_COLUMNS)).to_csv(processed / "team_games.csv", index=False)
    pd.DataFrame(log_rows, columns=list(PLAYER_LOG_COLUMNS)).to_csv(processed / "player_game_logs.csv", index=False)
    outputs = tmp_path / "outputs"
    script = _script()

    code = script.main(
        ["--processed-dir", str(processed), "--raw-dir", str(raw), "--output-dir", str(outputs), "--tables-only"]
    )

    assert code == 0
    ratings = json.loads((processed / script.RATINGS_FILE).read_text())
    assert set(ratings["teams"]) == set(teams)
    assert ratings["last_game_date"] == max(r["date"] for r in team_rows)
    assert not (outputs / "shadow_stats.md").exists()


def test_tables_only_writes_nothing_from_a_feed_that_disagrees(tmp_path) -> None:
    rng = np.random.default_rng(5)
    payloads, team_rows, log_rows = _synthetic_season(rng, 2024, 2, ["AAA", "BBB", "CCC", "DDD"])
    for row in team_rows:
        row["home_shots"] += 1
    raw = tmp_path / "raw"
    cache = raw / "nhl" / "play_by_play"
    cache.mkdir(parents=True)
    for payload in payloads:
        (cache / f"{payload['id']}.json").write_text(json.dumps(payload))
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame(team_rows, columns=list(TEAM_GAME_COLUMNS)).to_csv(processed / "team_games.csv", index=False)
    pd.DataFrame(log_rows, columns=list(PLAYER_LOG_COLUMNS)).to_csv(processed / "player_game_logs.csv", index=False)
    script = _script()
    code = script.main(
        ["--processed-dir", str(processed), "--raw-dir", str(raw), "--output-dir", str(tmp_path / "o"), "--tables-only"]
    )
    assert code == 2
    assert not (processed / script.RATINGS_FILE).exists()
    assert not (processed / "shadow_team_games.csv").exists()
