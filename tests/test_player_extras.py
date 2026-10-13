"""The shadow power-play points, faceoffs and shot-attempt models.

The NHL feed cannot be reached here, so these build play-by-play payloads in
the API's own shape and hold the parse to the rules the module states, then
check the walk-forward model never reads a game on or after the one it
prices, and run the measurement script end to end on a cache on disk.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nhl_betting_lab.data.build_datasets import PLAYER_LOG_COLUMNS, TEAM_GAME_COLUMNS
from nhl_betting_lab.new_markets import player_extras as px

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_player_extras.py"
PACKAGE = PROJECT_ROOT / "src" / "nhl_betting_lab" / "new_markets"
MODULE = "nhl_betting_lab.new_markets.player_extras"

HOME_ID, AWAY_ID = 1, 2
# Home: centre 11, wing 12, defence 13, goalie 19. Away: centre 21, wing 22, goalie 29.
ROSTER = (
    (11, HOME_ID, "C"),
    (12, HOME_ID, "L"),
    (13, HOME_ID, "D"),
    (19, HOME_ID, "G"),
    (21, AWAY_ID, "C"),
    (22, AWAY_ID, "R"),
    (29, AWAY_ID, "G"),
)


def _play(kind, period=1, clock=60, situation="1551", **details):
    kind_of_period = "SO" if period == 5 else ("OT" if period == 4 else "REG")
    return {
        "typeDescKey": kind,
        "periodDescriptor": {"number": period, "periodType": kind_of_period},
        "timeInPeriod": f"{clock // 60:02d}:{clock % 60:02d}",
        "situationCode": situation,
        "details": details,
    }


def _payload(game_id, plays, date="2025-10-10", roster=ROSTER):
    return {
        "id": game_id,
        "season": 20252026,
        "gameType": 2,
        "gameDate": date,
        "gameState": "OFF",
        "homeTeam": {"id": HOME_ID, "abbrev": "HOM"},
        "awayTeam": {"id": AWAY_ID, "abbrev": "AWY"},
        "rosterSpots": [{"playerId": p, "teamId": t, "positionCode": c} for p, t, c in roster],
        "plays": plays,
    }


def _sample_game(game_id=2025020001, date="2025-10-10"):
    plays = [
        _play("faceoff", winningPlayerId=11, losingPlayerId=21),
        _play("faceoff", winningPlayerId=21, losingPlayerId=11),
        _play("faceoff", winningPlayerId=11, losingPlayerId=22),
        # Home power play 5-on-4 (away 4 skaters): a power-play goal and two
        # power-play assists.
        _play("goal", situation="1451", scoringPlayerId=12, assist1PlayerId=11, assist2PlayerId=13, eventOwnerTeamId=HOME_ID),
        # Even strength: a goal, no power-play points.
        _play("goal", situation="1551", scoringPlayerId=11, assist1PlayerId=12, eventOwnerTeamId=HOME_ID),
        # Home goalie pulled for a delayed penalty, 6-on-5: not a power play.
        _play("goal", situation="1560", scoringPlayerId=13, eventOwnerTeamId=HOME_ID),
        # Home 5-on-4 with the away goalie pulled (shown 5-on-5): a power play.
        _play("goal", situation="0551", scoringPlayerId=11, eventOwnerTeamId=HOME_ID),
        # Away scores shorthanded (home on the power play): not an away PP goal.
        _play("goal", situation="1451", scoringPlayerId=21, assist1PlayerId=22, eventOwnerTeamId=AWAY_ID),
        _play("shot-on-goal", shootingPlayerId=12),
        _play("shot-on-goal", shootingPlayerId=12),
        _play("missed-shot", shootingPlayerId=12),
        _play("blocked-shot", shootingPlayerId=12, blockingPlayerId=22),
        _play("blocked-shot", shootingPlayerId=22, blockingPlayerId=13),
        # A goalie credited with an assist is not a skater row.
        _play("goal", situation="1451", scoringPlayerId=12, assist1PlayerId=19, eventOwnerTeamId=HOME_ID),
        # Shootout attempts count for nothing.
        _play("goal", period=5, situation="1010", scoringPlayerId=22, eventOwnerTeamId=AWAY_ID),
        _play("shot-on-goal", period=5, situation="1010", shootingPlayerId=12),
        _play("faceoff", period=5, winningPlayerId=21, losingPlayerId=11),
    ]
    return _payload(game_id, plays, date=date)


def test_the_power_play_rule_takes_the_extra_attacker_off_each_side() -> None:
    assert px.is_power_play(px.parse_situation("1451"), home=True)
    assert not px.is_power_play(px.parse_situation("1451"), home=False)
    assert not px.is_power_play(px.parse_situation("1560"), home=True)  # own net empty, 6-on-5
    assert px.is_power_play(px.parse_situation("0551"), home=True)  # 5-on-4 vs pulled goalie
    assert px.is_power_play(px.parse_situation("1460"), home=True)  # 6-on-4, own goalie pulled
    assert not px.is_power_play(px.parse_situation("1331"), home=True)  # 3-on-3 overtime
    assert px.is_power_play(px.parse_situation("1341"), home=True)  # 4-on-3 overtime
    assert px.parse_situation("15") is None


def test_one_game_counts_every_market_by_its_stated_rule() -> None:
    game = px.player_game_counts(_sample_game())
    rows = {r["player_id"]: r for r in game.rows}
    assert set(rows) == {11, 12, 13, 21, 22}  # goalies are not rows
    centre, wing, defence = rows[11], rows[12], rows[13]
    # Power-play points: wing PP goal x2 (one with a goalie's assist), centre
    # one PP assist and one PP goal against the pulled goalie, defence one PP
    # assist and an un-power-play goal at 6-on-5.
    assert (wing["ppg"], wing["ppa"], wing["ppp"]) == (2, 0, 2)
    assert (centre["ppg"], centre["ppa"], centre["ppp"]) == (1, 1, 2)
    assert (defence["ppg"], defence["ppa"], defence["ppp"]) == (0, 1, 1)
    assert rows[21]["ppp"] == 0 and rows[22]["ppp"] == 0
    # Faceoffs, shootout excluded.
    assert (centre["faceoffs_won"], centre["faceoffs_taken"]) == (2, 3)
    assert (rows[21]["faceoffs_won"], rows[21]["faceoffs_taken"]) == (1, 2)
    assert (rows[22]["faceoffs_won"], rows[22]["faceoffs_taken"]) == (0, 1)
    # Attempts: wing 2 goals + 2 shots + 1 miss + 1 blocked.
    assert (wing["goals"], wing["shots_on_goal"]) == (2, 4)
    assert (wing["shot_attempts"], wing["unblocked_attempts"]) == (6, 5)
    assert (rows[22]["shot_attempts"], rows[22]["unblocked_attempts"]) == (1, 0)
    assert (centre["shot_attempts"], centre["unblocked_attempts"]) == (2, 2)
    assert centre["team"] == "HOM" and centre["opponent"] == "AWY"
    assert game.goals_without_strength == 0 and game.unknown_players == 0


def test_a_goal_with_no_situation_is_counted_but_not_called_a_power_play() -> None:
    game = px.player_game_counts(_payload(5, [_play("goal", situation="", scoringPlayerId=12)]))
    wing = {r["player_id"]: r for r in game.rows}[12]
    assert wing["goals"] == 1 and wing["ppp"] == 0
    assert game.goals_without_strength == 1


def test_a_payload_without_teams_yields_nothing() -> None:
    payload = _sample_game()
    payload["homeTeam"] = {}
    assert px.player_game_counts(payload).rows == []


def _logs_for(counts: pd.DataFrame, *, toi=900, tamper=None) -> pd.DataFrame:
    rows = []
    for r in counts.itertuples():
        rows.append(
            {
                "game_id": r.game_id,
                "season": 20252026,
                "game_type": 2,
                "date": r.date,
                "start_time_utc": "",
                "player_id": r.player_id,
                "player": f"P{r.player_id}",
                "boxscore_name": "",
                "role": "skater",
                "position": r.position,
                "team": r.team,
                "opponent": r.opponent,
                "venue": "home" if r.team == "HOM" else "away",
                "toi_seconds": toi,
                "shots_on_goal": r.shots_on_goal,
                "goals": r.goals,
                "assists": 0,
                "points": 0,
                "blocked_shots": 0,
                "hits": 0,
                "power_play_goals": r.ppg,
                "saves": 0,
                "shots_against": 0,
                "goals_against": 0,
            }
        )
    logs = pd.DataFrame(rows, columns=list(PLAYER_LOG_COLUMNS))
    if tamper is not None:
        tamper(logs)
    return logs


def test_the_join_and_the_boxscore_check() -> None:
    counts, summary = px.build_counts([_sample_game()])
    assert summary["games"] == 1 and len(counts) == 5
    logs = _logs_for(counts)
    table, join = px.attach_ice_time(counts, logs)
    assert join["matched_rows"] == 5 and join["counted_without_boxscore"] == 0
    checks = px.validate(table)
    assert checks["goals_match"] == checks["shots_on_goal_match"] == checks["power_play_goals_match"] == 1.0

    def tamper(frame: pd.DataFrame) -> None:
        frame.loc[frame["player_id"] == 12, "power_play_goals"] = 0

    table, _ = px.attach_ice_time(counts, _logs_for(counts, tamper=tamper))
    assert px.validate(table)["power_play_goals_match"] == pytest.approx(0.8)


def _synthetic_table(players=40, dates=80, seed=7) -> pd.DataFrame:
    """Players with fixed true rates; one game per date per pair of players."""
    rng = np.random.default_rng(seed)
    positions = ["C", "L", "D", "R"]
    truth = {
        p: {
            "toi": 900 + 60 * (p % 7),
            "ppp": 0.15 + 0.05 * (p % 5),
            "taken": (16.0 if positions[p % 4] == "C" else 1.0),
            "win": 0.42 + 0.02 * (p % 6),
            "att": 2.0 + 0.4 * (p % 9),
        }
        for p in range(1, players + 1)
    }
    start = pd.Timestamp("2025-10-01")
    rows = []
    for d in range(dates):
        date = (start + pd.Timedelta(days=d)).strftime("%Y-%m-%d")
        for p, t in truth.items():
            game_id = 2025020000 + d * 100 + (p - 1) // 2
            taken = rng.poisson(t["taken"])
            won = rng.binomial(taken, t["win"])
            att = rng.negative_binomial(4, 4 / (4 + t["att"]))
            blocked = rng.binomial(att, 0.25)
            ppp = rng.poisson(t["ppp"])
            rows.append(
                {
                    "player_id": p,
                    "game_id": game_id,
                    "season": 20252026,
                    "game_type": 2,
                    "date": date,
                    "team": "T%d" % ((p - 1) // 2),
                    "opponent": "O",
                    "position": positions[p % 4],
                    "goals": 0,
                    "shots_on_goal": 0,
                    "ppg": 0,
                    "ppa": ppp,
                    "ppp": ppp,
                    "faceoffs_won": won,
                    "faceoffs_taken": taken,
                    "shot_attempts": att,
                    "unblocked_attempts": att - blocked,
                    "toi_seconds": t["toi"],
                }
            )
    return pd.DataFrame(rows)


def test_the_walk_forward_never_reads_the_game_it_prices_or_later() -> None:
    table = _synthetic_table(players=12, dates=30)
    before = px.walk_forward(table)
    cut = "2025-10-20"
    changed = table.copy()
    later = changed["date"] >= cut
    for column in ("ppp", "faceoffs_won", "faceoffs_taken", "shot_attempts", "unblocked_attempts", "toi_seconds"):
        changed.loc[later, column] = changed.loc[later, column] * 3 + 5
    after = px.walk_forward(changed)
    keep = before["date"] <= cut
    columns = [c for c in before.columns if c.startswith(("mu_", "naive_", "inv_r_"))] + ["priced", "faceoff_taker"]
    pd.testing.assert_frame_equal(
        before.loc[keep, columns].reset_index(drop=True),
        after.loc[after["date"] <= cut, columns].reset_index(drop=True),
    )
    # Nobody is priced before MIN_GAMES earlier games.
    assert not before.loc[before["prior_games"] < px.MIN_GAMES, "priced"].any()
    assert before.loc[before["prior_games"] >= px.MIN_GAMES, "priced"].all()


def test_the_model_recovers_rates_and_fits_dispersion() -> None:
    table = _synthetic_table()
    predictions = px.walk_forward(table)
    last = predictions[predictions["date"] == predictions["date"].max()].set_index("player_id")
    # A centre taking 16 a game wins about 16 x his win rate.
    centre = last.loc[4]  # position C, win 0.42 + 0.08
    assert centre["mu_faceoffs_won"] == pytest.approx(16 * 0.50, rel=0.15)
    assert bool(centre["faceoff_taker"]) and not bool(last.loc[2]["faceoff_taker"])
    # Attempts are generated overdispersed (r = 4); the walk-forward fit sees it.
    assert (last["inv_r_shot_attempts"] > 0.05).all()
    # Power-play points are Poisson by construction; 1/r stays small.
    assert last["inv_r_power_play_points"].max() < 0.1


def test_over_probabilities_are_poisson_or_wider() -> None:
    mu = np.array([2.0, 2.0])
    poisson_only = px.over_probability(mu, np.array([0.0, 0.0]), 4.5)
    assert poisson_only[0] == pytest.approx(1 - sum(math.exp(-2) * 2**k / math.factorial(k) for k in range(5)))
    wider = px.over_probability(mu, np.array([0.0, 0.5]), 4.5)
    assert wider[1] > wider[0]
    assert px.over_probability(np.array([1.0]), np.array([0.0]), 0.5)[0] == pytest.approx(1 - math.exp(-1))
    with pytest.raises(ValueError):
        px.over_probability(mu, np.zeros(2), 2.0)


def test_the_measurement_reports_every_market_and_line() -> None:
    predictions = px.walk_forward(_synthetic_table())
    payload = px.measure(predictions)
    assert payload["looks"] == sum(len(m.lines) for m in px.MARKETS)
    assert set(payload["markets"]) == {m.name for m in px.MARKETS}
    faceoffs = payload["markets"]["faceoffs_won"]
    attempts = payload["markets"]["shot_attempts"]
    # Faceoffs are measured only on takers (the centres here).
    assert faceoffs["player_games"] < attempts["player_games"]
    for market in px.MARKETS:
        entry = payload["markets"][market.name]
        assert [line["line"] for line in entry["lines"]] == list(market.lines)
        for line in entry["lines"]:
            gain = line["log_loss_gain"]
            assert gain["low"] <= gain["mean"] <= gain["high"]
            assert gain["adjusted_low"] <= gain["low"]
            assert 0 <= line["observed_low"] <= line["observed"] <= line["observed_high"] <= 1
            assert sum(b["samples"] for b in line["calibration"]) == line["samples"]
    # On players with fixed rates the shrunk career rate forecasts better
    # than a ten-game mean on the market where both have most to learn.
    assert attempts["lines"][2]["log_loss_gain"]["mean"] > 0


def test_player_shots_is_documented_as_an_assumption() -> None:
    keys = {m.name: m.provider_key for m in px.MARKETS}
    assert keys["shot_attempts"] == keys["unblocked_attempts"] == "player_shots"
    assert "ASSUMED" in (px.__doc__ or "")


# -- the script, end to end ----------------------------------------------------


def _script():
    spec = importlib.util.spec_from_file_location("run_player_extras", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_world(tmp_path: Path, *, games=14, tamper=None) -> tuple[Path, Path, Path]:
    processed, raw, outputs = tmp_path / "processed", tmp_path / "raw", tmp_path / "outputs"
    processed.mkdir()
    cache = raw / "nhl" / "play_by_play"
    cache.mkdir(parents=True)
    team_rows, payloads = [], []
    for n in range(games):
        game_id = 2025020001 + n
        date = (pd.Timestamp("2025-10-01") + pd.Timedelta(days=n)).strftime("%Y-%m-%d")
        payload = _sample_game(game_id, date)
        payloads.append(payload)
        (cache / f"{game_id}.json").write_text(json.dumps(payload), encoding="utf-8")
        team_rows.append(
            {"game_id": game_id, "season": 20252026, "game_type": 2, "date": date, "start_time_utc": "",
             "home_team": "HOM", "away_team": "AWY", "home_goals": 5, "away_goals": 1,
             "home_shots": 30, "away_shots": 20, "regulation": True}
        )
    pd.DataFrame(team_rows, columns=list(TEAM_GAME_COLUMNS)).to_csv(processed / "team_games.csv", index=False)
    counts, _ = px.build_counts(payloads)
    _logs_for(counts, tamper=tamper).to_csv(processed / "player_game_logs.csv", index=False)
    return processed, raw, outputs


def _run(processed: Path, raw: Path, outputs: Path) -> int:
    return _script().main(
        ["--processed-dir", str(processed), "--raw-dir", str(raw), "--output-dir", str(outputs)]
    )


def test_the_script_measures_offline_from_the_cache(tmp_path: Path) -> None:
    processed, raw, outputs = _write_world(tmp_path)
    assert _run(processed, raw, outputs) == 0
    payload = json.loads((outputs / "player_extras.json").read_text(encoding="utf-8"))
    assert payload["games_read"] == 14 and payload["problems"] == []
    assert payload["validation"]["power_play_goals_match"] == 1.0
    assert set(payload["measurement"]["markets"]) == {m.name for m in px.MARKETS}
    report = (outputs / "player_extras.md").read_text(encoding="utf-8")
    assert "ASSUMED" in report and "never in" in report
    assert (processed / "player_extras_counts.csv").is_file()


def test_the_script_refuses_a_parse_the_boxscore_contradicts(tmp_path: Path) -> None:
    def tamper(frame: pd.DataFrame) -> None:
        frame["power_play_goals"] = 0

    processed, raw, outputs = _write_world(tmp_path, tamper=tamper)
    assert _run(processed, raw, outputs) == 2
    assert not (processed / "player_extras_counts.csv").exists()
    assert "Not measured" in (outputs / "player_extras.md").read_text(encoding="utf-8")


def test_the_script_says_so_when_there_is_nothing_to_read(tmp_path: Path) -> None:
    processed, raw, outputs = _write_world(tmp_path, games=2)
    for path in (raw / "nhl" / "play_by_play").iterdir():
        path.unlink()
    assert _run(processed, raw, outputs) == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _run(empty, raw, outputs) == 1


# -- nothing on the card's path may import this ---------------------------------


def _imports(path: Path, target: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        else:
            continue
        if any(n == target or n.startswith(target + ".") for n in names):
            return True
    return False


def _python_files():
    for root in (PROJECT_ROOT / "src", PROJECT_ROOT / "scripts", PROJECT_ROOT / "web"):
        if root.is_dir():
            yield from root.rglob("*.py")


#: 2026-10-13: the price backtest of the new markets reads this model's
#: walk-forward opinions, and nothing else may. Both are shadow code that the
#: card cannot import (`test_the_shadow_model_cannot_reach_the_card.py`).
PRICE_BACKTEST = {
    PACKAGE / "backtest.py",
    PROJECT_ROOT / "scripts" / "run_new_market_backtest.py",
}


def test_nothing_outside_its_runner_imports_this_model() -> None:
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in _python_files()
        if path != SCRIPT and path not in PRICE_BACKTEST and _imports(path, MODULE)
    ]
    assert offenders == []


def test_no_library_module_outside_the_package_imports_it() -> None:
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in (PROJECT_ROOT / "src").rglob("*.py")
        if PACKAGE not in path.parents and _imports(path, "nhl_betting_lab.new_markets")
    ]
    assert offenders == []


def test_this_model_imports_neither_its_siblings_nor_the_shadow_package() -> None:
    path = PACKAGE / "player_extras.py"
    assert not _imports(path, "nhl_betting_lab.shadow")
    for sibling in PACKAGE.glob("*.py"):
        if sibling.stem not in {"__init__", "player_extras"}:
            assert not _imports(path, f"nhl_betting_lab.new_markets.{sibling.stem}")


def test_the_import_check_would_see_an_import(tmp_path: Path) -> None:
    sample = tmp_path / "card.py"
    sample.write_text("from nhl_betting_lab.new_markets.player_extras import MARKETS\n", encoding="utf-8")
    assert _imports(sample, MODULE)
    sample.write_text("from nhl_betting_lab.new_markets import player_extras\n", encoding="utf-8")
    assert _imports(sample, MODULE)


def test_faceoffs_taken_follow_the_last_ten_games_not_the_career() -> None:
    # A winger who took no draws for 30 games, then 16 a game for the last
    # ten, is forecast at his new role (Shadow Stats run 38460470412: the
    # career rate under-forecast takers and lost to the trailing mean).
    table = _synthetic_table(players=8, dates=40)
    mover = 2
    dates = sorted(table["date"].unique())
    early = (table["player_id"] == mover) & (table["date"] < dates[-11])
    late = (table["player_id"] == mover) & (table["date"] >= dates[-11])
    table.loc[early, ["faceoffs_taken", "faceoffs_won"]] = 0
    table.loc[late, "faceoffs_taken"] = 16
    table.loc[late, "faceoffs_won"] = 8
    predictions = px.walk_forward(table)
    row = predictions[(predictions["player_id"] == mover) & (predictions["date"] == dates[-1])].iloc[0]
    assert row["mu_faceoffs_taken"] == pytest.approx(16, rel=0.15)
