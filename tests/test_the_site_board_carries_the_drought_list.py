"""`games[].drought` and `droughtNote`: the shape web/SCHEMA.md names, written by the site builder.

The Board's game cards render Cooper's drought list (2026-10-07). The site reads a file and
imports nothing from the card: the card writes `data/outputs/drought_list.json`, Publish
Site restores it with `gameday-reports`, and `web/build_site_json.py` turns it into
`games[].drought`. Every regular-season game carries the array, empty when nobody
qualifies; a missing price stays null; a list built for another day is never shown on this one.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY, CLUBS, SLATE, make_lab, schedule, site_module,
)

SCHEMA_KEYS = {"player", "playerId", "team", "market", "line", "lastSeason", "drought", "price", "book", "heavyJuice"}
ROOT = Path(__file__).resolve().parents[1]


def row(home: str, away: str, **kw) -> dict:
    base = {"date": BOARD_DAY.isoformat(), "home_team": home, "away_team": away, "team": home, "opponent": away,
            "player": "Assist Man", "player_id": 8471111, "market": "assists", "line": 0.5, "last_season": 31,
            "drought": 6, "american_odds": 170.0, "book": "DraftKings", "heavy_juice": False}
    base.update(kw)
    return base


def write_list(lab: Path, rows: list[dict], day: date = BOARD_DAY) -> None:
    (lab / "data" / "outputs" / "drought_list.json").write_text(
        json.dumps({"generated_at": "x", "day": day.isoformat(), "headline": "h", "rows": rows,
                    "unresolved": [], "notes": []}), encoding="utf-8")


def build(lab: Path, out: Path, monkeypatch, *, start: str = "2099-10-08T23:00:00Z") -> dict:
    module = site_module()

    def later(d):
        games = schedule(d)
        for g in games:
            g["startTimeUTC"] = start
        return games

    monkeypatch.setattr(module, "schedule_for", later)
    monkeypatch.setattr(module, "allowlisted_markets", lambda _lab: ["moneyline"])
    assert module.main(["--lab", str(lab), "--out", str(out), "--date", BOARD_DAY.isoformat()]) == 0
    return json.loads((out / "board.json").read_text(encoding="utf-8"))


@pytest.fixture
def lab(tmp_path: Path, monkeypatch) -> Path:
    return make_lab(tmp_path, monkeypatch, staged=False)


def test_every_regular_season_game_carries_the_array_in_the_schemas_shape(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL"), row("TOR", "MTL", player="Second", player_id=2, market="goals",
                                              american_odds=None, book="", heavy_juice=False),
                     row("NYI", "BOS", player="Heavy", player_id=3, american_odds=-190.0, heavy_juice=True)])

    board = build(lab, tmp_path / "out", monkeypatch)
    by = {g["home"]["abbr"]: g["drought"] for g in board["games"]}

    assert all(isinstance(g["drought"], list) for g in board["games"])
    assert [r["player"] for r in by["TOR"]] == ["Assist Man", "Second"], "the card's order is kept"
    assert set(by["TOR"][0]) == SCHEMA_KEYS
    assert by["TOR"][0] == {"player": "Assist Man", "playerId": 8471111, "team": "TOR", "market": "assists", "line": 0.5,
                            "lastSeason": 31, "drought": 6, "price": 170, "book": "DraftKings", "heavyJuice": False}
    assert by["TOR"][1]["price"] is None and by["TOR"][1]["book"] is None, "a missing price stays null"
    assert by["NYI"][0]["price"] == -190 and by["NYI"][0]["heavyJuice"] is True


def test_a_game_nobody_qualifies_in_carries_an_empty_array(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL")])

    board = build(lab, tmp_path / "out", monkeypatch)

    assert {g["home"]["abbr"]: g["drought"] for g in board["games"]}["NYI"] == []


def test_the_note_is_the_rule_and_the_backtest_headline_read_from_its_file(lab, tmp_path, monkeypatch) -> None:
    outputs = lab / "data" / "outputs"
    (outputs / "drought_rule_backtest.json").write_text((ROOT / "data" / "outputs" / "drought_rule_backtest.json").read_text())
    write_list(lab, [row("TOR", "MTL")])

    note = build(lab, tmp_path / "out", monkeypatch)["droughtNote"]

    assert "70+ points, 30+ goals or 30+ assists" in note and "unstaked" in note
    assert "points -15.8% over 69 wagers" in note and "goals -4.3% over 971" in note and "assists -10.4% over 1804" in note
    assert "did not reach this build" not in note


def test_a_list_built_for_another_day_is_never_shown(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL")], day=date(2026, 10, 7))

    board = build(lab, tmp_path / "out", monkeypatch)

    assert all(g["drought"] == [] for g in board["games"])
    assert "did not reach this build" in board["droughtNote"], "an empty array must not read as nobody qualifying"


def test_no_list_at_all_is_an_empty_array_with_a_note_not_a_crash(lab, tmp_path, monkeypatch) -> None:
    board = build(lab, tmp_path / "out", monkeypatch)

    assert all(g["drought"] == [] for g in board["games"]) and "did not reach this build" in board["droughtNote"]


def test_a_game_that_has_started_lists_nobody(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL")])

    board = build(lab, tmp_path / "out", monkeypatch, start="2020-10-08T00:00:00Z")

    assert all(g["drought"] == [] for g in board["games"])


def test_the_builder_imports_nothing_from_the_card() -> None:
    import ast

    imported = set()
    for node in ast.walk(ast.parse((ROOT / "web" / "build_site_json.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)

    assert not {m for m in imported if m.startswith("nhl_betting_lab.reports") or "gameday_card" in m}, imported


def test_the_schema_the_builder_writes_is_the_one_the_page_reads() -> None:
    schema = (ROOT / "web" / "SCHEMA.md").read_text(encoding="utf-8")

    for key in SCHEMA_KEYS | {"droughtNote", "games[].drought"}:
        assert key in schema, key
    assert CLUBS and SLATE
