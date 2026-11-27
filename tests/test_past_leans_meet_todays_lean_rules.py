"""Past leans count only where today's card would list them, and the Due List
tracker reads the same ledger as its season line.

2026-11-27, Cooper: "we need the regraded due list/leans/totals/etc all
updated on the website with correct profits". The site spells the lean rules
itself, so they are pinned to the lab's card.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from nhl_betting_lab.reports import gameday_card as card

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "web" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


site = _load("build_site_json")
leans = _load("prop_leans")
LABEL = {"Moneyline": "moneyline", "Total": "total_goals", "Regulation": "regulation_3_way", "Puck line": "puck_line"}


def test_the_sites_team_lean_rules_are_the_cards():
    assert {LABEL[m] for m in site.LEAN_EXCLUDED_MARKETS} == set(card.LEAN_ONLY_EXCLUDED_MARKETS)
    board_floors = {(LABEL[m], side): pct / 100 for (m, side), pct in site.LEAN_MIN_EDGE_PCT.items()}
    card_floors = {k: v for k, v in card.LEAN_MIN_EDGE.items() if k[0] in LABEL.values()}
    assert board_floors == pytest.approx(card_floors)
    assert site.TOTAL_UNDER_LINES == card.TOTAL_UNDER_LINES
    assert site.TOTAL_UNDER_MIN_EDGE_PCT / 100 == pytest.approx(card.TOTAL_UNDER_MIN_EDGE)


def test_the_sites_prop_lean_rules_are_the_cards():
    props = set(leans.PROP_MARKETS)
    assert set(leans.EXCLUDED_SIDES) == {k for k in card.LEAN_EXCLUDED_SIDES if k[0] in props}
    caps = {**card.LEAN_MAX_PRICE, **card.LEAN_ONLY_MAX_PRICE}
    assert leans.MAX_PRICE == {k: v for k, v in caps.items() if k[0] in props}
    # No prop side has an edge floor of its own; the sites would miss one.
    assert not [k for k in card.LEAN_MIN_EDGE if k[0] in props]


@pytest.mark.parametrize("pick, counts", [
    ({"kind": "bet", "market": "Regulation", "side": None, "edgePct": 4.0}, True),
    ({"kind": "lean", "market": "Regulation", "side": None, "edgePct": 9.0}, False),
    ({"kind": "lean", "market": "Moneyline", "side": "home", "edgePct": 5.9}, False),
    ({"kind": "lean", "market": "Moneyline", "side": "away", "edgePct": 6.0}, True),
    ({"kind": "lean", "market": "Total", "side": "over", "edgePct": 4.0, "line": 6.5}, False),
    ({"kind": "lean", "market": "Total", "side": "over", "edgePct": 7.0, "line": 6.5}, True),
    ({"kind": "lean", "market": "Total", "side": "under", "edgePct": 8.0, "line": 6.0}, False),
    ({"kind": "lean", "market": "Total", "side": "under", "edgePct": 5.0, "line": 5.5}, False),
    ({"kind": "lean", "market": "Total", "side": "under", "edgePct": 6.5, "line": 5.5}, True),
    ({"kind": "lean", "market": "Puck line", "side": "away", "edgePct": 3.6, "line": 1.5}, True),
])
def test_a_team_lean_counts_only_under_todays_rules(pick, counts):
    assert site.meets_lean_rules(pick) is counts


@pytest.mark.parametrize("row, counts", [
    ({"market": "points", "side": "under", "price": -150}, False),
    ({"market": "assists", "side": "under", "price": 120}, False),
    ({"market": "points", "side": "over", "price": 200}, True),
    ({"market": "points", "side": "over", "price": 210}, False),
    ({"market": "goals", "side": "over", "price": 160}, False),
    ({"market": "goals", "side": "over", "price": 150}, True),
    ({"market": "goalie_saves", "side": "over", "price": 115}, False),
    ({"market": "shots_on_goal", "side": "under", "price": -140}, True),
])
def test_a_prop_lean_counts_only_under_todays_rules(row, counts):
    assert leans.meets_lean_rules(row) is counts


def test_settle_shows_a_lean_off_the_rules_and_leaves_it_out_of_the_record(tmp_path, monkeypatch):
    import json
    day = "2026-11-20"
    board = {"phase": "regular", "games": [
        {"id": "1", "startUtc": f"{day}T23:00:00Z", "home": {"abbr": "TOR", "projGoals": 3.2},
         "away": {"abbr": "MTL", "projGoals": 2.6},
         "pick": {"kind": "lean", "market": "Regulation", "label": "TOR reg", "price": 120, "side": "home", "edgePct": 8.0}},
        {"id": "2", "startUtc": f"{day}T23:00:00Z", "home": {"abbr": "BOS", "projGoals": 3.0},
         "away": {"abbr": "NYR", "projGoals": 2.8},
         "pick": {"kind": "lean", "market": "Moneyline", "label": "BOS +105", "price": 105, "side": "home", "edgePct": 7.0}},
    ]}
    (tmp_path / f"{day}.json").write_text(json.dumps(board))
    finals = [{"id": 1, "gameState": "OFF", "homeTeam": {"score": 4}, "awayTeam": {"score": 1}},
              {"id": 2, "gameState": "OFF", "homeTeam": {"score": 1}, "awayTeam": {"score": 3}}]
    monkeypatch.setattr(site, "schedule_for", lambda d: finals)
    monkeypatch.setattr(site, "grade_pick", lambda pick, *a: "win" if pick["market"] == "Regulation" else "loss")
    from datetime import date
    out = site.settle(date.fromisoformat(day), tmp_path)
    assert out["summary"]["leans"] == {"w": 0, "l": 1, "p": 0}
    assert out["summary"]["money"]["leans"]["units"] == pytest.approx(-1.0)
    reg = next(g for g in out["games"] if g["id"] == "1")["pick"]
    assert reg["result"] == "win" and reg["onRecord"] is False
    assert site.night_record(out)["leansGrading"] == site.LEANS_GRADING


def test_the_due_trackers_rows_come_from_the_ledger():
    rows = [
        {"date": "2026-11-20", "player": "A", "player_id": "8478402.0", "market": "goals", "line": "0.5",
         "american_odds": "150", "outcome": "won", "last_season": "41", "drought": "4", "team": "EDM", "opponent": "CGY"},
        # The same entry twice is one row.
        {"date": "2026-11-20", "player": "A", "player_id": "8478402", "market": "goals", "line": "0.5",
         "american_odds": "150", "outcome": "won", "last_season": "41", "drought": "4", "team": "EDM", "opponent": "CGY"},
        # Under today's bars a 1+ point entry at +250 does not count.
        {"date": "2026-11-20", "player": "B", "player_id": "1", "market": "points", "line": "0.5",
         "american_odds": "250", "outcome": "lost", "last_season": "80", "drought": "3"},
        # No price, a void, or not graded yet: not a tracked row.
        {"date": "2026-11-21", "player": "C", "player_id": "2", "market": "goals", "american_odds": "",
         "outcome": "lost", "last_season": "30", "drought": "9"},
        {"date": "2026-11-21", "player": "D", "player_id": "3", "market": "goals", "american_odds": "120",
         "outcome": "void", "last_season": "30", "drought": "9"},
        {"date": "2026-11-21", "player": "E", "player_id": "4", "market": "goals", "american_odds": "130",
         "outcome": "lost", "last_season": "30", "drought": "9"},
    ]
    got = site.due_ledger_tracker_rows(rows)
    assert [(r["player"], r["result"]) for r in got] == [("A", "win"), ("E", "loss")]
    assert got[0]["playerId"] == 8478402 and got[0]["band"] == "40+" and got[0]["team"] == "EDM"
    assert got[0]["units"] == pytest.approx(1.5) and got[1]["units"] == pytest.approx(-1.0)
