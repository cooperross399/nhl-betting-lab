"""Big games on the Due List (Cooper, 2026-11-04): 2-goal games, hat tricks, shutouts.

An elite goal scorer is listed for 2+ goals (over 1.5) and a hat trick (over
2.5) after a drought without one; an elite goalie for a shutout after starts
without one. 2+ goals and hat tricks take the best goals over 1.5 / 2.5 a book
posted; a shutout is never priced. Each settles on its own rule.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab import drought_rule as dr
from nhl_betting_lab.drought_forward import settle_shutout
from nhl_betting_lab.reports.gameday_card import GamedayCard, render_drought_section

from test_due_list_tonight_context import TEAM_NAMES as CONTEXT_TEAMS, run, write_goalies

DAY = "2026-11-05"
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
TEAM_NAMES = {"edmonton oilers": "EDM", "calgary flames": "CGY"}
STARTS = {(DAY, "EDM", "CGY"): "2026-11-05T23:00:00Z"}
TWO, HAT, SO = dr.BIG_GAMES["two_goals"], dr.BIG_GAMES["hat_trick"], dr.BIG_GAMES["shutout"]


def skater_games(pid, name, season, start, goals_list, offset=0):
    day = pd.Timestamp(start)
    return [{"game_id": pid * 10_000 + season % 1000 * 10 + offset + i, "season": season, "game_type": 2,
             "date": (day + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), "player_id": pid, "player": name,
             "role": "skater", "team": "EDM", "goals": g, "assists": 0, "points": g, "toi_seconds": 1100}
            for i, g in enumerate(goals_list)]


def goalie_games(pid, name, season, start, ga_list, toi=3600, offset=0):
    day = pd.Timestamp(start)
    return [{"game_id": pid * 10_000 + season % 1000 * 10 + offset + i, "season": season, "game_type": 2,
             "date": (day + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), "player_id": pid, "player": name,
             "role": "goalie", "team": "CGY", "goals": 0, "assists": 0, "points": 0,
             "toi_seconds": toi, "goals_against": ga}
            for i, ga in enumerate(ga_list)]


def make_logs() -> pd.DataFrame:
    rows = []
    # Sniper: 45 goals last season, one hat trick early, then singles; this season dry.
    # His last 2+ game is the hat trick, 44 games before tonight's 2025 tail + this season.
    rows += skater_games(1, "Sniper Guy", 20252026, "2025-10-10", [3] + [1] * 42)
    rows += skater_games(1, "Sniper Guy", 20262027, "2026-10-10", [0] * 20, offset=100)
    # Plinker: 30 goals last season, never a multi-goal game: below the 35 and 40 floors.
    rows += skater_games(2, "Plinker Guy", 20252026, "2025-10-10", [1] * 30)
    rows += skater_games(2, "Plinker Guy", 20262027, "2026-10-10", [0] * 30, offset=100)
    # Wall: 5 shutouts in 50 starts last season, then 16 starts without one, plus a relief
    # appearance (20 minutes) that is not a start and must not count.
    rows += goalie_games(9, "Wall Goalie", 20252026, "2025-10-10", [3] * 45 + [0] * 5)
    rows += goalie_games(9, "Wall Goalie", 20262027, "2026-10-10", [2] * 16, offset=100)
    rows += goalie_games(9, "Wall Goalie", 20262027, "2026-10-30", [0], toi=1200, offset=200)
    # Sieve: 2 shutouts last season: below the floor.
    rows += goalie_games(8, "Sieve Goalie", 20252026, "2025-10-10", [0] * 2 + [4] * 40)
    rows += goalie_games(8, "Sieve Goalie", 20262027, "2026-10-10", [3] * 20, offset=100)
    return pd.DataFrame(rows)


ROSTERS = {1: "EDM", 2: "EDM", 9: "CGY", 8: "CGY"}


def quote(market, line, odds, book, player="Sniper Guy"):
    return {"date": DAY, "commence_time": STARTS[(DAY, "EDM", "CGY")], "home_team": "Edmonton Oilers",
            "away_team": "Calgary Flames", "market": market, "player": player, "selection": "over",
            "line": line, "american_odds": odds, "book": book}


def build(prices=()):
    frame = pd.DataFrame(list(prices), columns=list(quote("goals", 0.5, 1, "b")))
    return dr.build_drought_list(logs=make_logs(), rosters=ROSTERS, starts=STARTS, prices=frame,
                                 team_names=TEAM_NAMES, day=DAY, now=NOW)


def by_market(result):
    return {(r["player"], r["market"]): r for r in result.rows}


def test_elite_scorer_on_a_drought_is_listed_for_two_goals_and_a_hat_trick() -> None:
    rows = by_market(build())
    two, hat = rows[("Sniper Guy", "two_goals")], rows[("Sniper Guy", "hat_trick")]
    assert two["last_season"] == 45 and two["drought"] == 62 and two["line"] == 1.5
    assert hat["drought"] == 62 and hat["line"] == 2.5
    assert two["tier_bar"] == TWO["bar"] and hat["tier_bar"] == HAT["bar"]
    assert two["hit_rate"] == round(1 / 43, 3), "last season's share of games with 2+ goals"
    assert two["cell_record"] == dr.BIG_GAMES_RECORDS[("two_goals", "35+")]
    assert ("Plinker Guy", "two_goals") not in rows and ("Plinker Guy", "hat_trick") not in rows


def test_two_goals_and_hat_tricks_take_the_goals_over_1_5_and_2_5_prices() -> None:
    rows = by_market(build([quote("goals", 1.5, 600, "FanDuel"), quote("goals", 1.5, 650, "BetMGM"),
                            quote("goals", 2.5, 3000, "DraftKings"), quote("goals", 0.5, 110, "FanDuel")]))
    assert (rows[("Sniper Guy", "two_goals")]["american_odds"], rows[("Sniper Guy", "two_goals")]["book"]) == (650, "BetMGM")
    assert (rows[("Sniper Guy", "hat_trick")]["american_odds"], rows[("Sniper Guy", "hat_trick")]["book"]) == (3000, "DraftKings")


def test_an_elite_goalie_on_a_shutout_drought_is_listed_unpriced() -> None:
    rows = by_market(build([quote("goals", 0.5, 400, "FanDuel", player="Wall Goalie")]))
    wall = rows[("Wall Goalie", "shutout")]
    assert wall["last_season"] == 5 and wall["drought"] == 16, "the relief appearance is not a start"
    assert wall["american_odds"] is None and wall["team"] == "CGY" and wall["opponent"] == "EDM"
    assert wall["hit_rate"] == 0.1 and wall["cell_record"] is None
    assert ("Sieve Goalie", "shutout") not in rows


def test_a_shutout_row_is_never_checked_against_the_lines_and_follows_the_listed_starter(tmp_path: Path) -> None:
    row = {"date": "2026-11-02", "home_team": "TOR", "away_team": "MTL", "team": "MTL", "opponent": "TOR",
           "player": "Sam Montembeault", "player_id": 31, "market": "shutout", "selection": "over", "line": 0.5}
    kept, removed = run(tmp_path, [row])
    assert len(kept) == 1 and not removed and kept[0]["status"] is None
    write_goalies(tmp_path, [("Montreal Canadiens", "Sam Montembeault", "Confirmed")])
    kept, removed = run(tmp_path, [row])
    assert kept[0]["status"] == "listed starter (Confirmed)" and kept[0]["opp_goalie"] is None
    write_goalies(tmp_path, [("Montreal Canadiens", "Jakub Dobes", "Confirmed")])
    kept, removed = run(tmp_path, [row])
    assert kept == [] and "Jakub Dobes is MTL's listed starter" in removed[0]
    assert CONTEXT_TEAMS["montreal canadiens"] == "MTL"


def test_a_shutout_settles_on_his_own_start() -> None:
    logs = pd.DataFrame([
        {"player_id": 9, "date": DAY, "toi_seconds": 3600, "goals_against": 0},
        {"player_id": 8, "date": DAY, "toi_seconds": 3600, "goals_against": 2},
        {"player_id": 7, "date": DAY, "toi_seconds": 900, "goals_against": 0},
    ])
    assert settle_shutout(logs, DAY, 9, 100.0)[0] == "won"
    assert settle_shutout(logs, DAY, 8, 100.0)[:2] == ("lost", 2.0)
    assert settle_shutout(logs, DAY, 7, 100.0)[0] == "void", "relief is not a start"
    assert settle_shutout(logs, DAY, 6, 100.0)[0] == "void", "did not play"


def test_the_card_names_each_big_game_and_its_line() -> None:
    result = build([quote("goals", 1.5, 650, "BetMGM")])
    card = GamedayCard(generated_at="2026-11-05T13:00:00+00:00", drought_built=True,
                       drought_headline="headline", drought_rows=result.rows)
    text = "\n".join(render_drought_section(card))
    assert "| 2+ goals | over 1.5 |" in text and "| hat trick | over 2.5 |" in text
    assert "| shutout | no goal against |" in text
    assert dr.BIG_GAMES_HEADLINE in text


def test_the_site_grades_big_games(tmp_path: Path) -> None:
    import importlib.util
    import sys

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("bsj_big_games", root / "web" / "build_site_json.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    pd.DataFrame([
        {"game_id": "1", "player_id": "1", "player": "Sniper Guy", "team": "EDM", "role": "skater", "goals": 2, "assists": 0},
        {"game_id": "1", "player_id": "9", "player": "Wall Goalie", "team": "CGY", "role": "goalie", "goals": 0,
         "assists": 0, "toi_seconds": 3650, "goals_against": 0},
        {"game_id": "1", "player_id": "8", "player": "Sieve Goalie", "team": "CGY", "role": "goalie", "goals": 0,
         "assists": 0, "toi_seconds": 600, "goals_against": 0},
    ]).to_csv(tmp_path / module.PLAYER_LOGS_FILENAME, index=False)
    by_id, _, boxed = module.read_player_counts(tmp_path, {"1"})
    assert boxed == {"1"}
    assert by_id[("1", "1")]["two_goals"] == 2 and by_id[("1", "1")]["hat_trick"] == 2
    assert by_id[("1", "9")]["shutout"] == 1 and by_id[("1", "8")]["shutout"] is None
    assert set(dr.CATEGORIES) == set(module.DUE_LIST_MARKETS)
