"""Cooper's Hot List (2026-11-19): who qualifies, the card's section, the site's list, its record and the page.

The rules (`nhl_betting_lab.hot_list.HOT_RULES`): 80+ points last season and 8+ points in
his last 5 games; 60+ assists and 6+ assists in his last 5; 40+ goals and a goal in each of
his last 2+ games. Forms run across the season boundary and count regular-season games he
dressed for. It is an unstaked list like the Due List, tracked on the site at the same
notional sizes as its own group, "hot".
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.hot_list import (
    HEADLINE,
    HOT_RULES,
    build_hot_list,
    hot_qualifiers_entering,
    render_section,
    streak_entering,
)
from test_site_never_calls_an_unpriced_game_a_pass import BOARD_DAY, make_lab, site_module
from test_the_site_board_carries_the_drought_list import _PAGE_DRIVER, build

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-19"


def _games(pid: int, name: str, team: str, season: int, start: date, counts: list[tuple[int, int]]) -> list[dict]:
    """One regular-season skater row per (goals, assists), a day apart."""
    out = []
    for i, (g, a) in enumerate(counts):
        d = start.toordinal() + i
        out.append({"role": "skater", "game_type": 2, "season": season, "date": date.fromordinal(d).isoformat(),
                    "game_id": season * 10 + pid * 1000 + i, "player_id": pid, "player": name, "team": team,
                    "goals": g, "assists": a, "points": g + a})
    return out


def logs() -> pd.DataFrame:
    rows = []
    # Hot Scorer: 90 points last season (45 goals, 45 assists), 9 points in his last 5, goals in his last 3.
    rows += _games(1, "Hot Scorer", "TOR", 20252026, date(2025, 10, 10), [(1, 1)] * 45)
    rows += _games(1, "Hot Scorer", "TOR", 20262027, date(2026, 10, 10), [(0, 0), (0, 2), (1, 1), (1, 2), (1, 1)])
    # Cold Star: 100 points last season, 2 points in his last 5: not hot.
    rows += _games(2, "Cold Star", "MTL", 20252026, date(2025, 10, 10), [(1, 1)] * 50)
    rows += _games(2, "Cold Star", "MTL", 20262027, date(2026, 10, 10), [(0, 0), (0, 1), (0, 0), (1, 0), (0, 0)])
    # Depth Guy: 8 points in his last 5 but 20 points last season: under the floor.
    rows += _games(3, "Depth Guy", "MTL", 20252026, date(2025, 10, 10), [(0, 1)] * 20)
    rows += _games(3, "Depth Guy", "MTL", 20262027, date(2026, 10, 10), [(1, 1), (1, 1), (1, 1), (1, 1), (0, 0)])
    # A game on or after the day is not entered: tonight is not played.
    rows += _games(2, "Cold Star", "MTL", 20262027, date(2026, 11, 19), [(5, 5)])
    return pd.DataFrame(rows)


def test_a_streak_counts_games_in_a_row_ending_at_his_last_game() -> None:
    assert streak_entering([1, 0, 1, 2, 1]) == 3
    assert streak_entering([1, 1, 0]) == 0
    assert streak_entering([]) == 0


def test_who_qualifies_and_for_what() -> None:
    q = hot_qualifiers_entering(logs(), DAY)
    got = {(r.player, r.market): (r.last_season, r.last5, r.streak) for r in q.itertuples()}
    assert got == {("Hot Scorer", "points"): (90, 9, 4), ("Hot Scorer", "goals"): (45, 3, 3)}, got
    assert set(HOT_RULES) == {"points", "assists", "goals"}


def test_the_card_list_prices_the_over_and_keeps_an_unposted_price_missing() -> None:
    prices = pd.DataFrame([
        {"market": "points", "line": 0.5, "selection": "over", "player": "Hot Scorer", "american_odds": -180,
         "book": "DraftKings", "home_team": "Toronto Maple Leafs", "away_team": "Montreal Canadiens", "commence_time": f"{DAY}T23:00:00Z"},
        {"market": "points", "line": 0.5, "selection": "over", "player": "Hot Scorer", "american_odds": -170,
         "book": "FanDuel", "home_team": "Toronto Maple Leafs", "away_team": "Montreal Canadiens", "commence_time": f"{DAY}T23:00:00Z"},
    ])
    result = build_hot_list(logs=logs(), rosters={1: "TOR", 2: "MTL", 3: "MTL"},
                            starts={(DAY, "TOR", "MTL"): f"{DAY}T23:00:00Z"}, prices=prices,
                            team_names={"toronto maple leafs": "TOR", "montreal canadiens": "MTL"}, day=DAY,
                            now=datetime(2026, 11, 19, 15, tzinfo=timezone.utc))
    by = {r["market"]: r for r in result.rows}
    assert [r["market"] for r in result.rows] == ["points", "goals"]
    assert by["points"]["american_odds"] == -170 and by["points"]["book"] == "FanDuel" and by["points"]["heavy_juice"]
    assert by["goals"]["american_odds"] is None and by["goals"]["book"] == "", "never filled in"
    section = "\n".join(render_section(result.rows, result.notes, result.unresolved))
    assert section.startswith("## Hot List") and HEADLINE in section
    assert "| Hot Scorer | TOR | MTL | 1+ point | over 0.5 | 90 | 9 points in his last 5 |" in section
    assert "| not posted |" in section and "A list, not bets" in section
    assert "no demonstrated edge" in HEADLINE


def test_a_started_game_lists_nobody() -> None:
    result = build_hot_list(logs=logs(), rosters={1: "TOR"}, starts={(DAY, "TOR", "MTL"): f"{DAY}T23:00:00Z"},
                            prices=pd.DataFrame(), team_names={}, day=DAY,
                            now=datetime(2026, 11, 20, 1, tzinfo=timezone.utc))
    assert result.rows == [] and result.removed_by_guard == 2


# -- the site --------------------------------------------------------------

def _listed(home="TOR", away="MTL", **kw) -> dict:
    base = {"home_team": home, "away_team": away, "team": home, "player": "Hot Scorer", "player_id": 1,
            "market": "points", "line": 0.5, "last_season": 90, "last5": 9, "streak": 4, "rule": "last5", "bar": 8,
            "american_odds": 250.0, "book": "DraftKings", "heavy_juice": False, "model_probability": 0.31,
            "model_edge": 0.024}
    base.update(kw)
    return base


def test_the_site_copies_the_cards_rows_in_the_schemas_shape() -> None:
    site = site_module()
    listed = {"day": DAY, "rows": [_listed(), _listed(home="NYI", away="BOS", team="BOS"),
                                   _listed(player="No Price", player_id=9, american_odds=None, book="", rule="bogus")]}
    out = site.hot_for_game(listed, "TOR", "MTL", False)
    assert [r["player"] for r in out] == ["Hot Scorer", "No Price"]
    assert out[0] == {"player": "Hot Scorer", "playerId": 1, "team": "TOR", "market": "points", "line": 0.5,
                      "lastSeason": 90, "last5": 9, "streak": 4, "bar": 8, "rule": "last5", "price": 250,
                      "book": "DraftKings", "heavyJuice": False, "stake": 0.15, "modelChance": 0.31, "modelEdge": 0.024}
    assert out[1]["price"] is None and out[1]["book"] is None and out[1]["stake"] is None and out[1]["rule"] is None
    assert site.hot_for_game(listed, "TOR", "MTL", True) == [], "a started game lists nobody"


def test_a_list_for_another_day_is_never_read(tmp_path) -> None:
    site = site_module()
    (tmp_path / "data" / "outputs").mkdir(parents=True)
    (tmp_path / "data" / "outputs" / "hot_list.json").write_text(json.dumps({"day": "2026-11-18", "rows": []}))
    assert site.read_hot_list(tmp_path, date(2026, 11, 19)) is None
    assert site.read_hot_list(tmp_path, date(2026, 11, 18)) == {"day": "2026-11-18", "rows": []}


def test_the_hot_list_is_graded_and_tracked_as_its_own_group(tmp_path) -> None:
    site = site_module()
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame([
        {"game_id": "2026020101", "player_id": 1, "player": "Hot Scorer", "team": "TOR", "role": "skater", "goals": 0, "assists": 1},
        {"game_id": "2026020101", "player_id": 2, "player": "Missed", "team": "TOR", "role": "skater", "goals": 0, "assists": 0},
    ]).to_csv(processed / site.PLAYER_LOGS_FILENAME, index=False)
    entry = site.hot_for_game({"day": DAY, "rows": [
        _listed(), _listed(player="Missed", player_id=2, american_odds=-150.0),
        _listed(player="Scratched", player_id=3, american_odds=-150.0),
    ]}, "TOR", "MTL", False)
    board = {"games": [{"id": "2026020101", "home": {"abbr": "TOR"}, "away": {"abbr": "MTL"}, "hot": entry, "drought": []}]}
    graded = site.grade_due_list(board, {"2026020101": {}}, processed, field="hot")
    by = {r["player"]: r for r in graded["rows"]}
    assert graded["summary"] == {"w": 1, "l": 1, "p": 0}
    assert by["Hot Scorer"]["result"] == "win" and by["Missed"]["result"] == "loss" and by["Scratched"]["result"] == "void"
    due = site.grade_due_list(board, {"2026020101": {}}, processed)
    assert due["rows"] == [], "the Due List grades only its own field"
    rows = site.tracker_rows({"resultsDate": DAY, "hotList": graded})
    assert [(r["group"], r["player"], r["result"], r["units"], r["staked"]) for r in rows] == [
        ("hot", "Hot Scorer", "win", 0.38, 0.15), ("hot", "Missed", "loss", -0.38, 0.375)]
    tracked = site.tracker(rows, nights=1)
    assert {g["key"]: g["bets"] for g in tracked["byGroup"]}["hot"] == 2
    assert site.TRACKER_GROUPS["hot"] == "Hot List"


# -- the page, patched as Publish Site publishes it -------------------------

def test_the_published_board_draws_hot_rows_beside_the_due_list(tmp_path, monkeypatch) -> None:
    sys.path.insert(0, str(ROOT / "web"))
    import smooth_pages

    node = shutil.which("node")
    assert node, "node renders the Board's own component"
    site = tmp_path / "page"
    (site / "lib").mkdir(parents=True)
    for name in ("sports.js", "format.js", "live.js"):
        shutil.copyfile(ROOT / "web" / "lib" / name, site / "lib" / name)
    (site / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (site / "render.mjs").write_text(_PAGE_DRIVER.replace(
        "const pick = (x) => ({ player: x.player, meta: x.meta, record: x.record, facts: x.facts });",
        "const pick = (x) => ({ player: x.player, category: x.category, history: x.history, streak: x.streak, "
        "boxLabel: x.boxLabel, price: x.price, facts: x.facts });").replace(
        'for (const tab of ["tonight", "props"]) {', 'for (const tab of ["tonight", "props", "hot"]) {').replace(
        'tab, propView: "drought"', 'tab: tab === "hot" ? "props" : tab, propView: tab === "hot" ? "hot" : "drought"'),
        encoding="utf-8")
    page = site / "Board.dc.html"
    page.write_text(smooth_pages.patch("Board.dc.html", (ROOT / "web" / "Board.dc.html").read_text(encoding="utf-8")),
                    encoding="utf-8")
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    (lab / "data" / "outputs" / "hot_list.json").write_text(json.dumps({"day": BOARD_DAY.isoformat(), "rows": [
        _listed(),
        _listed(player="Goal Man", player_id=7, market="goals", rule="streak", streak=3, last5=4, american_odds=None, book=""),
    ]}), encoding="utf-8")
    board = build(lab, tmp_path / "out", monkeypatch)
    tor = next(g for g in board["games"] if g["home"]["abbr"] == "TOR")
    assert [r["player"] for r in tor["hot"]] == ["Hot Scorer", "Goal Man"]
    assert all(g["hot"] == [] for g in board["games"] if g["home"]["abbr"] != "TOR")
    data = site / "board.json"
    data.write_text(json.dumps(board), encoding="utf-8")
    result = subprocess.run([node, str(site / "render.mjs"), str(page), str(data)],
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    shown = next(g for g in out["tonight"]["games"] if g["rows"])
    assert shown["label"] == "Due/Hot ×2"
    hot, goal = shown["rows"]
    assert (hot["category"], hot["streak"], hot["boxLabel"], hot["price"]) == ("Hot · 1+ point", "9", "in last 5", "+250")
    assert hot["history"] == "90 points last season · 9 points in his last 5 games"
    assert {f["label"] for f in hot["facts"]} == {"Last 5 games", "Streak", "Tracked at", "Model's chance"}
    assert (goal["category"], goal["streak"], goal["boxLabel"], goal["price"]) == ("Hot · anytime goal", "3", "straight", "—")
    # Props has a Due List tab and a Hot List tab (Cooper, 2026-11-19): the
    # Due List tab lists only the Due List, the Hot List tab only the Hot List.
    assert out["props"]["view"] == [], "the Due List tab lists no Hot List row"
    view = out["hot"]["view"]
    assert [r["category"] for g in view for r in g["rows"]] == ["Hot · 1+ point", "Hot · anytime goal"]
