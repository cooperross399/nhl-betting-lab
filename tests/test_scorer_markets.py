"""First and last goal scorer: goal order, settlement, model and measurement.

Every payload here is synthetic; nothing reaches the network.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.new_markets import scorers
from nhl_betting_lab.new_markets.scorers import NO_SCORER, ScorerContext

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = PROJECT_ROOT / "src" / "nhl_betting_lab" / "new_markets"

HOME_ID, AWAY_ID = 10, 20


def _goal(period: int, clock: str, scorer: int, team_id: int, *, code: str = "1551",
          period_type: str | None = None, sort: int | None = None) -> dict:
    descriptor = {"number": period}
    if period_type:
        descriptor["periodType"] = period_type
    play = {
        "typeDescKey": "goal",
        "periodDescriptor": descriptor,
        "timeInPeriod": clock,
        "situationCode": code,
        "details": {"scoringPlayerId": scorer, "eventOwnerTeamId": team_id},
    }
    if sort is not None:
        play["sortOrder"] = sort
    return play


def _payload(plays: list[dict], *, game_type: int = 2, state: str = "OFF", game_id: int = 2024020001) -> dict:
    roster = [{"playerId": 100 + i, "teamId": HOME_ID} for i in range(3)]
    roster += [{"playerId": 200 + i, "teamId": AWAY_ID} for i in range(3)]
    return {
        "id": game_id,
        "gameType": game_type,
        "gameState": state,
        "homeTeam": {"id": HOME_ID, "abbrev": "HOM"},
        "awayTeam": {"id": AWAY_ID, "abbrev": "AWY"},
        "rosterSpots": roster,
        "plays": plays,
    }


# -- goal order and settlement --------------------------------------------


def test_goals_are_ordered_by_period_and_clock_not_by_list_position() -> None:
    order = scorers.parse_goal_order(
        _payload(
            [
                _goal(2, "05:00", 101, HOME_ID),
                _goal(1, "12:00", 200, AWAY_ID),
                _goal(3, "19:00", 102, HOME_ID, code="0651"),  # away net empty
            ]
        )
    )
    assert [g.scorer_id for g in order.goals] == [200, 101, 102]
    assert order.first.team == "AWY" and order.last.team == "HOM"
    assert order.last.empty_net and not order.first.empty_net
    assert scorers.settle(order, "first", 200) == "win"
    assert scorers.settle(order, "first", 101) == "loss"
    assert scorers.settle(order, "last", 102) == "win"  # empty-net goals count
    assert scorers.settle(order, "last", NO_SCORER) == "loss"


def test_an_overtime_goal_counts_for_both_markets() -> None:
    order = scorers.parse_goal_order(
        _payload([_goal(4, "02:31", 201, AWAY_ID, code="1331", period_type="OT")])
    )
    assert scorers.settle(order, "first", 201) == "win"
    assert scorers.settle(order, "last", 201) == "win"
    assert scorers.settle(order, "first", NO_SCORER) == "loss"
    assert not order.shootout


def test_shootout_goals_never_count() -> None:
    plays = [
        _goal(1, "03:00", 100, HOME_ID),
        _goal(2, "10:00", 200, AWAY_ID),
        _goal(5, "00:00", 102, HOME_ID, period_type="SO"),
        _goal(5, "00:00", 202, AWAY_ID, period_type="SO"),
    ]
    order = scorers.parse_goal_order(_payload(plays))
    assert order.shootout
    assert [g.scorer_id for g in order.goals] == [100, 200]
    assert scorers.settle(order, "last", 200) == "win"
    assert scorers.settle(order, "last", 102) == "loss"


def test_a_regular_season_period_five_without_a_type_is_the_shootout() -> None:
    order = scorers.parse_goal_order(_payload([_goal(5, "00:00", 102, HOME_ID)]))
    assert order.shootout and order.goals == ()


def test_a_game_with_no_goal_in_play_pays_no_scorer_and_beats_every_player() -> None:
    plays = [_goal(5, "00:00", 102, HOME_ID, period_type="SO")]
    order = scorers.parse_goal_order(_payload(plays))
    for market in scorers.MARKETS:
        assert scorers.settle(order, market, NO_SCORER) == "win"
        assert scorers.settle(order, market, 102) == "loss"
        assert scorers.settle(order, market, 100) == "loss"


def test_a_player_who_did_not_dress_is_void() -> None:
    order = scorers.parse_goal_order(_payload([_goal(1, "01:00", 100, HOME_ID)]))
    assert scorers.settle(order, "first", 999) == "void"
    assert scorers.settle(order, "last", 999) == "void"


def test_simultaneous_clock_readings_follow_the_feeds_sort_order() -> None:
    order = scorers.parse_goal_order(
        _payload([_goal(1, "05:00", 101, HOME_ID, sort=20), _goal(1, "05:00", 201, AWAY_ID, sort=10)])
    )
    assert order.first.scorer_id == 201 and order.last.scorer_id == 101


def test_a_game_that_is_not_final_does_not_settle() -> None:
    order = scorers.parse_goal_order(_payload([_goal(1, "01:00", 100, HOME_ID)], state="LIVE"))
    with pytest.raises(ValueError):
        scorers.settle(order, "first", 100)


def test_the_boxscore_check_allows_for_the_shootout_winner() -> None:
    so = scorers.parse_goal_order(
        _payload([_goal(1, "03:00", 100, HOME_ID), _goal(5, "00:00", 101, HOME_ID, period_type="SO")],
                 game_id=1)
    )
    plain = scorers.parse_goal_order(_payload([_goal(1, "03:00", 100, HOME_ID)], game_id=2))
    games = pd.DataFrame(
        [{"game_id": 1, "home_goals": 2, "away_goals": 1}, {"game_id": 2, "home_goals": 2, "away_goals": 0}]
    )
    # Game 1: shootout, home 1 in play +1 for the shootout win, away needs a goal it lacks.
    check = scorers.validate_against_boxscores(games, {1: so, 2: plain})
    assert check["games"] == 2 and check["match"] == 0.0
    games.loc[0, "away_goals"] = 0
    games.loc[1, "home_goals"] = 1
    assert scorers.validate_against_boxscores(games, {1: so, 2: plain})["match"] == 1.0


# -- the model -------------------------------------------------------------


def test_team_probabilities_are_a_poisson_race_and_sum_to_one() -> None:
    context = ScorerContext(ot_goal_share=0.6, empty_net_last_share=0.2)
    probs = scorers.team_probabilities(3.3, 2.7, context)
    none = math.exp(-6.0) * 0.4
    assert probs["first"]["none"] == pytest.approx(none)
    assert probs["first"]["home"] == pytest.approx((1 - none) * 3.3 / 6.0)
    for market in scorers.MARKETS:
        assert sum(probs[market].values()) == pytest.approx(1.0)
    # The stronger side leads more often, so empty-netters move the last goal its way.
    assert probs["last"]["home"] > probs["first"]["home"]
    playoff = scorers.team_probabilities(3.3, 2.7, context, game_type=scorers.PLAYOFFS)
    assert playoff["first"]["none"] == 0.0


def test_player_probabilities_split_a_side_by_weight() -> None:
    sides = {"home": 0.5, "away": 0.4, "none": 0.1}
    probs = scorers.player_probabilities(
        sides, {1: ("home", 3.0), 2: ("home", 1.0), 3: ("away", 0.0), 4: ("away", 0.0)}
    )
    assert probs[1] == pytest.approx(0.375) and probs[2] == pytest.approx(0.125)
    assert probs[3] == probs[4] == pytest.approx(0.2)  # zero weights split equally
    assert sum(probs.values()) == pytest.approx(1.0)


def test_the_context_is_fitted_from_goal_orders() -> None:
    tied_ot = scorers.parse_goal_order(_payload([_goal(4, "01:00", 100, HOME_ID, period_type="OT")]))
    tied_so = scorers.parse_goal_order(_payload([_goal(5, "00:00", 100, HOME_ID, period_type="SO")]))
    en_last = scorers.parse_goal_order(
        _payload([_goal(1, "01:00", 100, HOME_ID), _goal(3, "19:30", 101, HOME_ID, code="0651")])
    )
    context = scorers.fit_context([tied_ot, tied_so, en_last])
    assert context.ot_goal_share == pytest.approx(0.5)
    assert context.empty_net_last_share == pytest.approx(0.5)
    assert context.regulation_goals_per_game == pytest.approx(2 / 3)
    assert context.games == 3


# -- walk-forward on a synthetic league ------------------------------------

TEAMS = ("AAA", "BBB", "CCC", "DDD")


def _league(days: int = 90, seed: int = 7):
    """Team games, player logs and play-by-play for a four-team league."""
    rng = random.Random(seed)
    team_ids = {team: i + 1 for i, team in enumerate(TEAMS)}
    roster = {
        team: [(team_ids[team] * 100 + k, "C" if k < 6 else "D" if k < 9 else "G") for k in range(10)]
        for team in TEAMS
    }
    team_rows, log_rows, payloads = [], [], {}
    start = date(2024, 10, 1)
    number = 0
    for day in range(days):
        today = start + timedelta(days=day)
        pairs = [("AAA", "BBB"), ("CCC", "DDD")] if day % 2 == 0 else [("BBB", "CCC"), ("DDD", "AAA")]
        for home, away in pairs:
            number += 1
            gid = 2024020000 + number
            plays = []
            score = {home: 0, away: 0}
            for team, other in ((home, away), (away, home)):
                for _ in range(rng.choice([0, 1, 2, 3, 4])):
                    shooters = [p for p, pos in roster[team] if pos != "G"]
                    scorer = shooters[0] if rng.random() < 0.3 else rng.choice(shooters)
                    plays.append(
                        _goal(rng.randint(1, 3), f"{rng.randint(0, 19):02d}:{rng.randint(0, 59):02d}",
                              scorer, team_ids[team])
                    )
                    score[team] += 1
            shootout = score[home] == score[away]
            if shootout:
                plays.append(_goal(5, "00:00", roster[home][0][0], team_ids[home], period_type="SO"))
            payload = {
                "id": gid,
                "gameType": 2,
                "gameState": "OFF",
                "homeTeam": {"id": team_ids[home], "abbrev": home},
                "awayTeam": {"id": team_ids[away], "abbrev": away},
                "rosterSpots": [
                    {"playerId": pid, "teamId": team_ids[t]} for t in (home, away) for pid, _ in roster[t]
                ],
                "plays": plays,
            }
            payloads[gid] = payload
            goals_by = {p: 0 for t in (home, away) for p, _ in roster[t]}
            for play in plays:
                if play["periodDescriptor"].get("periodType") != "SO":
                    goals_by[play["details"]["scoringPlayerId"]] += 1
            team_rows.append(
                {
                    "game_id": gid, "season": 20242025, "game_type": 2, "date": today.isoformat(),
                    "start_time_utc": f"{today.isoformat()}T23:00:00Z", "home_team": home, "away_team": away,
                    "home_goals": score[home] + int(shootout), "away_goals": score[away],
                    "home_shots": 30, "away_shots": 30, "regulation": not shootout,
                }
            )
            for team, other, venue in ((home, away, "home"), (away, home, "away")):
                for pid, pos in roster[team]:
                    goalie = pos == "G"
                    log_rows.append(
                        {
                            "game_id": gid, "season": 20242025, "game_type": 2, "date": today.isoformat(),
                            "start_time_utc": "", "player_id": pid, "player": f"Player {pid}",
                            "boxscore_name": f"P. {pid}", "role": "goalie" if goalie else "skater",
                            "position": pos, "team": team, "opponent": other, "venue": venue,
                            "toi_seconds": 3600 if goalie else 1100 + 30 * (pid % 7),
                            "shots_on_goal": 0 if goalie else 2, "goals": goals_by[pid], "assists": 0,
                            "points": goals_by[pid], "blocked_shots": 0, "hits": 1, "power_play_goals": 0,
                            "saves": 25 if goalie else 0, "shots_against": 28 if goalie else 0,
                            "goals_against": 3 if goalie else 0,
                        }
                    )
    return pd.DataFrame(team_rows), pd.DataFrame(log_rows), payloads


def test_the_walk_forward_scores_only_after_the_minimum_history() -> None:
    team_games, logs, payloads = _league()
    orders = {gid: scorers.parse_goal_order(p) for gid, p in payloads.items()}
    result = scorers.measure(team_games, logs, orders, minimum_history=60)
    assert result.windows > 0
    assert result.skipped["before_minimum_history"] > 0
    first = result.games[result.games["market"] == "first"]
    # Every scored game is dated after the 60th game: nothing scored on its own history.
    cutoff = sorted(team_games["date"])[59]
    assert (first["date"] > cutoff).all()
    # Each game's player probabilities, plus no scorer, sum to one.
    for (gid, market), rows in result.players.groupby(["game_id", "market"]):
        none = result.games[(result.games["game_id"] == gid) & (result.games["market"] == market)]["p_none"].iat[0]
        assert rows["p"].sum() + none == pytest.approx(1.0)
    # Goalies are never candidates.
    assert not result.players["player_id"].astype(int).mod(100).isin([9]).any()
    # The heavy scorer (slot 0, three times the others' share) is weighted up.
    leaders = result.players[result.players["player_id"] % 100 == 0]["p"].mean()
    others = result.players[result.players["player_id"] % 100 != 0]["p"].mean()
    assert leaders > others
    # Asked for, every candidate's opinion is kept for the price backtest:
    # each dressed skater and "no scorer", summing to one, exactly one
    # winner per scored game and market. Not asked for, nothing is kept.
    assert result.selections.empty
    with_rows = scorers.measure(team_games, logs, orders, minimum_history=60, selections=True)
    chosen = with_rows.selections
    assert not chosen.empty
    for (gid, market), rows in chosen.groupby(["game_id", "market"]):
        assert rows["p"].sum() == pytest.approx(1.0)
        assert scorers.NO_SCORER in set(rows["selection"])
    scored = chosen.merge(first[["game_id"]].drop_duplicates(), on="game_id")
    assert (scored[scored["market"] == "first"].groupby("game_id")["won"].sum() == 1).all()
    summary = scorers.summarise(result)
    assert set(summary["markets"]) == {"first", "last"}
    for entry in summary["markets"].values():
        assert set(entry["against"]) == set(scorers.BASELINES)
        assert entry["calibration"]


def _load_script():
    path = PROJECT_ROOT / "scripts" / "run_scorer_markets.py"
    spec = importlib.util.spec_from_file_location("_script_run_scorer_markets", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_script_measures_offline_from_the_cache(tmp_path: Path) -> None:
    team_games, logs, payloads = _league(days=70)
    processed = tmp_path / "processed"
    processed.mkdir()
    team_games.to_csv(processed / "team_games.csv", index=False)
    logs.to_csv(processed / "player_game_logs.csv", index=False)
    raw = tmp_path / "raw"
    for gid, payload in payloads.items():
        path = scorers.play_by_play_path(gid, raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "outputs"
    code = _load_script().main(
        ["--processed-dir", str(processed), "--raw-dir", str(raw), "--output-dir", str(out),
         "--minimum-history", "40"]
    )
    assert code == 0
    report = (out / "scorer_markets.md").read_text(encoding="utf-8")
    assert "First scorer" in report and "Last scorer" in report
    data = json.loads((out / "scorer_markets.json").read_text(encoding="utf-8"))
    assert data["validation"]["match"] == 1.0
    assert data["summary"]["markets"]["first"]["games"] > 0


def test_the_script_with_nothing_on_disk_exits_one(tmp_path: Path) -> None:
    code = _load_script().main(
        ["--processed-dir", str(tmp_path / "p"), "--raw-dir", str(tmp_path / "r"),
         "--output-dir", str(tmp_path / "o")]
    )
    assert code == 1
    assert not (tmp_path / "o").exists()


# -- isolation -------------------------------------------------------------


def _imports(path: Path, prefix: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        else:
            continue
        if any(n == prefix or n.startswith(prefix + ".") for n in names):
            return True
    return False


#: The scripts on the card's and the ledger's path.
CARD_SCRIPTS = (
    "run_gameday_card.py",
    "run_forward_evidence.py",
    "run_provider_shadow.py",
    "run_closing_line_value.py",
)


def test_nothing_on_the_card_path_imports_the_new_markets_package() -> None:
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for root in (PROJECT_ROOT / "src", PROJECT_ROOT / "web")
        if root.is_dir()
        for path in root.rglob("*.py")
        if PACKAGE not in path.parents and _imports(path, "nhl_betting_lab.new_markets")
    ]
    offenders += [
        name for name in CARD_SCRIPTS
        if (PROJECT_ROOT / "scripts" / name).is_file()
        and _imports(PROJECT_ROOT / "scripts" / name, "nhl_betting_lab.new_markets")
    ]
    assert offenders == []


def test_the_scorer_module_imports_no_sibling_and_no_shadow_stat() -> None:
    module = PACKAGE / "scorers.py"
    assert not _imports(module, "nhl_betting_lab.shadow")
    for sibling in PACKAGE.glob("*.py"):
        if sibling.stem not in {"__init__", "scorers"}:
            assert not _imports(module, f"nhl_betting_lab.new_markets.{sibling.stem}")
    tree = ast.parse(module.read_text(encoding="utf-8"))
    relative = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level]
    assert relative == []


def test_the_isolation_check_would_see_an_import(tmp_path: Path) -> None:
    sample = tmp_path / "card.py"
    sample.write_text("from nhl_betting_lab.new_markets.scorers import measure\n", encoding="utf-8")
    assert _imports(sample, "nhl_betting_lab.new_markets")
    assert PACKAGE.is_dir() and (PACKAGE / "__init__.py").is_file()
