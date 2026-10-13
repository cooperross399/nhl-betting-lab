"""The period-market shadow model: parsing, pricing, settlement, walk-forward.

Every fixture is synthetic; nothing here touches the network.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nhl_betting_lab.new_markets import periods

HOME_ID, AWAY_ID = 10, 20


def _payload(gid: int, goals: list[tuple[int, str]], *, home: str = "TOR", away: str = "MTL",
             shootout: bool = False, scores: bool = True, owners: bool = True) -> dict:
    """A play-by-play payload. `goals` is (period, side); period 4 is overtime."""
    ids = {"home": HOME_ID, "away": AWAY_ID}
    plays: list[dict] = []
    score = {"home": 0, "away": 0}
    order = 0
    for period, side in goals:
        score[side] += 1
        details: dict = {}
        if owners:
            details["eventOwnerTeamId"] = ids[side]
        if scores:
            details["homeScore"] = score["home"]
            details["awayScore"] = score["away"]
        order += 1
        plays.append({
            "sortOrder": order,
            "typeDescKey": "goal",
            "periodDescriptor": {"number": period, "periodType": "REG" if period <= 3 else "OT"},
            "details": details,
        })
        order += 1
        plays.append({"sortOrder": order, "typeDescKey": "faceoff",
                      "periodDescriptor": {"number": period, "periodType": "REG" if period <= 3 else "OT"},
                      "details": {}})
    if shootout:
        plays.append({"sortOrder": order + 1, "typeDescKey": "goal",
                      "periodDescriptor": {"number": 5, "periodType": "SO"},
                      "details": {"eventOwnerTeamId": HOME_ID}})
    return {
        "id": gid,
        "gameType": 2,
        "gameState": "OFF",
        "homeTeam": {"id": HOME_ID, "abbrev": home},
        "awayTeam": {"id": AWAY_ID, "abbrev": away},
        "plays": plays,
        **({"gameOutcome": {"lastPeriodType": "SO"}} if shootout else {}),
    }


# -- parsing ---------------------------------------------------------------


def test_goals_land_in_their_period_and_overtime_is_kept_apart() -> None:
    parsed = periods.period_goals(_payload(1, [(1, "home"), (1, "away"), (3, "home"), (3, "home"), (4, "away")]))
    assert parsed is not None
    row = parsed.row()
    assert (row["home_p1"], row["away_p1"]) == (1, 1)
    assert (row["home_p2"], row["away_p2"]) == (0, 0)
    assert (row["home_p3"], row["away_p3"]) == (2, 0)
    assert (row["home_ot"], row["away_ot"]) == (0, 1)
    assert row["shootout"] is False and row["unattributed"] == 0


def test_the_side_is_read_from_the_score_or_the_owner() -> None:
    no_owner = periods.period_goals(_payload(2, [(2, "away"), (2, "home")], owners=False)).row()
    assert (no_owner["home_p2"], no_owner["away_p2"]) == (1, 1)
    no_score = periods.period_goals(_payload(3, [(2, "away"), (1, "home")], scores=False)).row()
    assert (no_score["home_p1"], no_score["away_p2"]) == (1, 1)
    neither = periods.period_goals(_payload(4, [(1, "home")], scores=False, owners=False)).row()
    assert neither["unattributed"] == 1 and neither["home_p1"] == 0


def test_shootout_goals_are_no_period_goal() -> None:
    parsed = periods.period_goals(_payload(5, [(1, "home"), (2, "away")], shootout=True)).row()
    assert parsed["shootout"] is True
    assert parsed["home_p1"] + parsed["home_p2"] + parsed["home_p3"] + parsed["home_ot"] == 1


def test_a_payload_without_teams_is_not_read() -> None:
    assert periods.period_goals({"id": 1, "plays": []}) is None


def test_validation_adds_the_shootout_winner() -> None:
    table = pd.DataFrame([
        periods.period_goals(_payload(1, [(1, "home"), (2, "away")], shootout=True)).row(),
        periods.period_goals(_payload(2, [(3, "home")])).row(),
    ])
    games = pd.DataFrame({"game_id": [1, 2], "home_goals": [2, 1], "away_goals": [1, 0]})
    assert periods.validate_against_boxscores(games, table) == {"games": 2, "match": 1.0}
    wrong = games.assign(away_goals=[1, 3])
    assert periods.validate_against_boxscores(wrong, table)["match"] == 0.5


# -- pricing ----------------------------------------------------------------


def test_every_market_is_consistent_with_one_scoreline_matrix() -> None:
    p = periods.period_probabilities(0.7, 0.5)
    three = p["three_way"]
    assert sum(three.values()) == pytest.approx(1.0)
    assert p["h2h"]["push"] == pytest.approx(three["draw"])
    assert p["h2h"]["home"] == pytest.approx(three["home"] / (1 - three["draw"]))
    assert p["h2h"]["home"] + p["h2h"]["away"] == pytest.approx(1.0)
    assert p["spreads"][-0.5] == pytest.approx(three["home"])
    assert p["spreads"][0.5] == pytest.approx(1 - three["away"])
    assert p["spreads"][-1.5] < p["spreads"][-0.5] < p["spreads"][0.5] < p["spreads"][1.5]
    assert p["totals"][0.5] == pytest.approx(1 - math.exp(-1.2))
    # Independent Poisson: the total is Poisson(1.2).
    assert p["totals"][1.5] == pytest.approx(1 - math.exp(-1.2) * (1 + 1.2))
    assert p["three_way"]["draw"] == pytest.approx(
        sum(math.exp(-1.2) * (0.7 * 0.5) ** k / math.factorial(k) ** 2 for k in range(12))
    )


def test_a_tied_period_voids_the_two_way_and_settles_the_three_way() -> None:
    probs = periods.period_probabilities(0.6, 0.6)
    rows = {(r["market"], r["line"]): r for r in periods.score_period(probs, 2, 1, 1)}
    assert rows[("h2h_p2", "home")]["void"] is True
    assert math.isnan(rows[("h2h_p2", "home")]["log_loss"])
    three = rows[("h2h_3_way_p2", "home/draw/away")]
    assert three["log_loss"] == pytest.approx(-math.log(probs["three_way"]["draw"]))
    expected_brier = (probs["three_way"]["home"] ** 2 + (1 - probs["three_way"]["draw"]) ** 2
                      + probs["three_way"]["away"] ** 2)
    assert three["brier"] == pytest.approx(expected_brier)
    assert rows[("spreads_p2", "home +0.5")]["y"] == 1.0
    assert rows[("spreads_p2", "home -0.5")]["y"] == 0.0
    assert rows[("totals_p2", "over 1.5")]["y"] == 1.0
    assert rows[("totals_p2", "over 2.5")]["y"] == 0.0
    # Every market and line of the period, once.
    assert len(rows) == 1 + 1 + len(periods.SPREAD_LINES) + len(periods.TOTAL_LINES)


def test_a_decided_period_settles_the_two_way() -> None:
    probs = periods.period_probabilities(0.6, 0.4)
    rows = {(r["market"], r["line"]): r for r in periods.score_period(probs, 1, 0, 2)}
    h2h = rows[("h2h_p1", "home")]
    assert h2h["void"] is False and h2h["y"] == 0.0
    assert h2h["log_loss"] == pytest.approx(-math.log(probs["h2h"]["away"]))
    assert rows[("spreads_p1", "home +1.5")]["y"] == 0.0
    assert rows[("spreads_p1", "home +1.5")]["log_loss"] == pytest.approx(
        -math.log(1 - probs["spreads"][1.5]))


def test_period_shares_divide_period_goals_by_final_goals() -> None:
    history = pd.DataFrame({
        "home_p1": [1, 0], "home_p2": [1, 1], "home_p3": [0, 1], "home_goals": [3, 3],
        "away_p1": [0, 0], "away_p2": [1, 0], "away_p3": [1, 2], "away_goals": [2, 2],
    })
    fit = periods.fit_period_shares(history)
    assert fit.shares[("home", 1)] == pytest.approx(1 / 6)
    assert fit.shares[("away", 3)] == pytest.approx(3 / 4)
    assert fit.rates[("home", 2)] == pytest.approx(1.0)
    assert fit.games == 2


# -- walk-forward -------------------------------------------------------------

TEAMS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
STRENGTH = {t: s for t, s in zip(TEAMS, np.linspace(0.55, 1.6, len(TEAMS)))}
SHARE = {1: 0.30, 2: 0.34, 3: 0.36}


def _league(games: int = 560, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synthetic team games and their period goals, strong teams scoring more."""
    rng = np.random.default_rng(seed)
    start = date(2024, 10, 8)
    team_rows, period_rows = [], []
    for n in range(games):
        home, away = rng.choice(TEAMS, size=2, replace=False)
        day = start + timedelta(days=n // 4)
        gid = 2024020000 + n + 1
        goals = {}
        for p in periods.PERIODS:
            goals[("home", p)] = int(rng.poisson(3.1 * SHARE[p] * STRENGTH[home] / STRENGTH[away]))
            goals[("away", p)] = int(rng.poisson(2.9 * SHARE[p] * STRENGTH[away] / STRENGTH[home]))
        h = sum(goals[("home", p)] for p in periods.PERIODS)
        a = sum(goals[("away", p)] for p in periods.PERIODS)
        ot = {"home": 0, "away": 0}
        if h == a:
            ot["home" if rng.random() < 0.5 else "away"] = 1
        team_rows.append({
            "game_id": gid, "season": 20242025, "game_type": 2, "date": day.isoformat(),
            "start_time_utc": "", "home_team": home, "away_team": away,
            "home_goals": h + ot["home"], "away_goals": a + ot["away"],
            "home_shots": 30, "away_shots": 30, "regulation": h != a,
        })
        row = {"game_id": gid, "home_team": home, "away_team": away, "shootout": False, "unattributed": 0,
               "home_ot": ot["home"], "away_ot": ot["away"]}
        for (side, p), value in goals.items():
            row[f"{side}_p{p}"] = value
        period_rows.append(row)
    return pd.DataFrame(team_rows), pd.DataFrame(period_rows)


def test_team_information_beats_the_league_baseline_when_teams_differ() -> None:
    team_games, table = _league()
    scored = periods.walk_forward(team_games, table)
    assert set(scored["model"]) == {"baseline", "goals"}
    first_scored = scored["date"].min()
    # Nothing before 200 games of history is priced.
    assert (team_games["date"] < first_scored).sum() >= periods.MINIMUM_HISTORY_GAMES
    summary = periods.summarise(scored)
    overall = next(r for r in summary if r["scope"] == "overall")
    assert overall["ll_gain_per_1000"] > 0
    assert overall["low"] is not None and overall["low"] > 0
    markets = {r["market"] for r in summary if r["scope"] == "market"}
    assert markets == {periods.market_key(k, p) for k in ("h2h", "h2h_3_way", "spreads", "totals")
                       for p in periods.PERIODS}
    h2h = next(r for r in summary if r["market"] == "h2h_p1" and r["scope"] == "line")
    assert h2h["void"] > 0
    assert h2h["games"] + h2h["void"] == scored[scored["model"] == "goals"]["game_id"].nunique()


def test_a_later_result_never_moves_an_earlier_price() -> None:
    team_games, table = _league()
    before = periods.walk_forward(team_games, table)
    last_day = team_games["date"].max()
    changed_games = team_games.copy()
    changed_table = table.copy()
    late = changed_games["date"] == last_day
    changed_games.loc[late, "home_goals"] += 5
    changed_table.loc[changed_table["game_id"].isin(changed_games.loc[late, "game_id"]), "home_p1"] += 5
    after = periods.walk_forward(changed_games, changed_table)
    keep = before["date"] < last_day
    pd.testing.assert_frame_equal(
        before[keep].reset_index(drop=True)[["p"]], after[after["date"] < last_day].reset_index(drop=True)[["p"]]
    )


def test_the_xg_ratings_are_scored_when_the_shadow_table_is_given() -> None:
    team_games, table = _league()
    metrics = []
    for g in team_games.itertuples():
        for team, opp, is_home, gf, ga in ((g.home_team, g.away_team, True, g.home_goals, g.away_goals),
                                           (g.away_team, g.home_team, False, g.away_goals, g.home_goals)):
            metrics.append({"game_id": g.game_id, "season": 20242025, "team": team, "is_home": is_home,
                            "gf": gf, "ga": ga, "xgf": 3.0 * STRENGTH[team] / STRENGTH[opp],
                            "xga": 3.0 * STRENGTH[opp] / STRENGTH[team], "goalie_ga": ga,
                            "goalie_xga": 3.0 * STRENGTH[opp] / STRENGTH[team]})
    scored = periods.walk_forward(team_games, table, xg_metrics=pd.DataFrame(metrics))
    assert set(scored["model"]) == {"baseline", "goals", "xg"}
    summary = periods.summarise(scored)
    assert any(r["model"] == "xg" and r["scope"] == "overall" for r in summary)


def test_too_little_history_scores_nothing() -> None:
    team_games, table = _league(games=150)
    scored = periods.walk_forward(team_games, table)
    assert scored.empty
    assert periods.summarise(scored) == []


# -- the runner ----------------------------------------------------------------


def _runner():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "run_period_markets.py"
    spec = importlib.util.spec_from_file_location("run_period_markets", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_cache(raw: Path, team_games: pd.DataFrame, table: pd.DataFrame) -> None:
    folder = raw / "nhl" / "play_by_play"
    folder.mkdir(parents=True)
    by_game = table.set_index("game_id")
    for g in team_games.itertuples():
        r = by_game.loc[g.game_id]
        goals = [(p, side) for p in periods.PERIODS for side in ("home", "away")
                 for _ in range(int(r[f"{side}_p{p}"]))]
        goals += [(4, side) for side in ("home", "away") for _ in range(int(r[f"{side}_ot"]))]
        payload = _payload(int(g.game_id), goals, home=g.home_team, away=g.away_team)
        (folder / f"{int(g.game_id)}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_the_runner_measures_offline_and_writes_its_report(tmp_path: Path) -> None:
    team_games, table = _league()
    processed, raw, outputs = tmp_path / "processed", tmp_path / "raw", tmp_path / "outputs"
    processed.mkdir()
    team_games.to_csv(processed / "team_games.csv", index=False)
    _write_cache(raw, team_games, table)
    runner = _runner()
    code = runner.main(["--processed-dir", str(processed), "--raw-dir", str(raw), "--output-dir", str(outputs)])
    assert code == 0
    payload = json.loads((outputs / "period_markets.json").read_text(encoding="utf-8"))
    assert payload["validation"] == {"games": len(team_games), "match": 1.0}
    assert payload["games_read"] == len(team_games)
    assert payload["summary"]
    report = (outputs / "period_markets.md").read_text(encoding="utf-8")
    assert "a tied period is a push" in report
    assert "`h2h_3_way_p3`" in report and "`totals_p2`" in report
    written = pd.read_csv(processed / "period_goals.csv")
    assert len(written) == len(team_games)


def test_the_runner_refuses_a_parse_that_disagrees_with_the_boxscores(tmp_path: Path) -> None:
    team_games, table = _league()
    processed, raw, outputs = tmp_path / "processed", tmp_path / "raw", tmp_path / "outputs"
    processed.mkdir()
    _write_cache(raw, team_games, table)
    team_games.assign(home_goals=team_games["home_goals"] + 1).to_csv(processed / "team_games.csv", index=False)
    runner = _runner()
    code = runner.main(["--processed-dir", str(processed), "--raw-dir", str(raw), "--output-dir", str(outputs)])
    assert code == 2
    assert not (outputs / "period_markets.json").exists()


def test_the_runner_without_play_by_play_measures_nothing(tmp_path: Path) -> None:
    team_games, _ = _league(games=20)
    processed = tmp_path / "processed"
    processed.mkdir()
    team_games.to_csv(processed / "team_games.csv", index=False)
    runner = _runner()
    code = runner.main(["--processed-dir", str(processed), "--raw-dir", str(tmp_path / "raw"),
                        "--output-dir", str(tmp_path / "outputs")])
    assert code == 1
