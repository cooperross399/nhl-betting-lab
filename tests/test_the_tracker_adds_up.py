"""The results tracker (Tracker.html, 2026-10-26).

Cooper asked for one page of every result, broken down by team, player, prop
type and market. These hold:

* only a graded best bet, or a priced Due List entry, is a row: no lean, void,
  unpriced entry or ungraded row;
* each row's units are its stake times the published price's profit;
* every split of the whole (group, market, price, month) adds back to it;
* a team pick with no recorded stake counts at the default and says so;
* a night kept before the tracker existed is settled again once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_site_never_calls_an_unpriced_game_a_pass import site_module


def _night(day: str) -> dict:
    return {
        "resultsDate": day,
        "games": [
            {"home": {"abbr": "TOR"}, "away": {"abbr": "MTL"},
             "pick": {"kind": "bet", "market": "Moneyline", "label": "TOR ML", "price": -150, "units": 0.5, "result": "win"}},
            {"home": {"abbr": "BOS"}, "away": {"abbr": "NYR"},
             "pick": {"kind": "bet", "market": "Total", "label": "Over 6.5", "price": 110, "result": "loss"}},
            {"home": {"abbr": "EDM"}, "away": {"abbr": "CGY"},
             "pick": {"kind": "lean", "market": "Moneyline", "label": "EDM ML", "price": -120, "result": "win"}},
            {"home": {"abbr": "SEA"}, "away": {"abbr": "VAN"}, "pick": None},
        ],
        "props": {"status": "ok", "rows": [
            {"kind": "bet", "market": "shots_on_goal", "side": "over", "line": 2.5, "player": "Auston Matthews",
             "playerId": 8479318, "team": "TOR", "opp": "MTL", "price": 120, "units": 0.25, "result": "win"},
            {"kind": "bet", "market": "hits", "side": "under", "line": 1.5, "player": "Nick Suzuki",
             "playerId": 8480018, "team": "MTL", "opp": "TOR", "price": -110, "units": 0.5, "result": "push"},
            {"kind": "bet", "market": "hits", "side": "under", "line": 1.5, "player": "Void Guy",
             "playerId": 1, "team": "MTL", "opp": "TOR", "price": -110, "units": 0.5, "result": "void"},
            {"kind": "lean", "market": "goals", "side": "over", "line": 0.5, "player": "A Lean",
             "playerId": 2, "team": "TOR", "opp": "MTL", "price": 200, "units": None, "result": "win"},
            {"kind": "bet", "market": "goals", "side": "over", "line": 0.5, "player": "Waiting",
             "playerId": 3, "team": "TOR", "opp": "MTL", "price": 200, "units": 0.25, "result": None},
        ]},
        "dueList": {"rows": [
            {"market": "goals", "player": "Auston Matthews", "playerId": 8479318, "team": "TOR", "opp": "MTL",
             "price": 150, "result": "loss", "units": -0.25},
            {"market": "points", "player": "No Price", "playerId": 4, "team": "TOR", "opp": "MTL",
             "price": None, "result": "win", "units": None},
        ]},
    }


def test_only_graded_staked_rows_are_tracked_at_their_price() -> None:
    module = site_module()
    rows = module.tracker_rows(_night("2026-10-20"))
    assert [(r["group"], r.get("label") or r.get("player")) for r in rows] == [
        ("team", "TOR ML"), ("team", "Over 6.5"), ("props", "Auston Matthews"), ("props", "Nick Suzuki"),
        ("due", "Auston Matthews")]
    ml, total, sog, hits, due = rows
    assert ml["units"] == pytest.approx(0.5 * 100 / 150, abs=1e-4) and ml["team"] == "TOR" and ml["opp"] == "MTL"
    assert "stakeAssumed" not in ml
    assert total["staked"] == module.TEAM_PICK_DEFAULT_UNITS and total["stakeAssumed"] and total["team"] is None
    assert total["units"] == -module.TEAM_PICK_DEFAULT_UNITS
    assert sog["units"] == pytest.approx(0.25 * 1.2) and hits["units"] == 0.0
    assert due["staked"] == module.DUE_LIST_STAKE and due["units"] == -0.25


def test_every_split_adds_back_to_the_whole() -> None:
    module = site_module()
    rows = module.tracker_rows(_night("2026-10-20")) + module.tracker_rows(_night("2026-11-02"))
    t = module.tracker(rows, nights=2)
    o = t["overall"]
    assert o["bets"] == 10 and (o["w"], o["l"], o["p"]) == (4, 4, 2)
    for split in ("byGroup", "byMarket", "byPrice", "byMonth"):
        groups = t[split]
        assert sum(g["bets"] for g in groups) == o["bets"], split
        assert sum(g["w"] for g in groups) == o["w"] and sum(g["l"] for g in groups) == o["l"], split
        assert sum(g["units"] for g in groups) == pytest.approx(o["units"], abs=0.02), split
    assert [g["key"] for g in t["byMonth"]] == ["2026-10", "2026-11"]
    teams = {g["key"]: g for g in t["byTeam"]}
    assert teams["TOR"]["bets"] == 6  # the ML pick, Matthews' prop and Due List entry, twice
    assert teams["BOS"]["bets"] == teams["NYR"]["bets"] == 2  # a total counts under both clubs
    players = {g["key"]: g for g in t["byPlayer"]}
    assert players["8479318"]["bets"] == 4 and players["8479318"]["label"] == "Auston Matthews (TOR)"
    assert {g["label"] for g in t["byPropType"]} == {"Shots on goal over", "Hits under"}
    assert t["rows"][0]["date"] == "2026-11-02" and t["firstDate"] == "2026-10-20"


def test_a_night_kept_before_the_tracker_is_settled_again(tmp_path: Path) -> None:
    module = site_module()
    frozen = tmp_path / "2026-10-20.json"
    frozen.write_text("{}", encoding="utf-8")
    assert module._kept_before_the_list_was_graded({"games": 3, "summary": {}}, frozen)
    night = module.night_record(_night("2026-10-20"))
    assert len(night["bets"]) == 5
    assert not module._kept_before_the_list_was_graded({**night, "dueList": {**night["dueList"], "units": 0.0}}, frozen)


def test_the_tracker_is_written_and_empty_before_anything_settles(tmp_path: Path) -> None:
    module = site_module()
    t = module.tracker([], nights=0)
    assert t["overall"]["bets"] == 0 and t["rows"] == [] and t["firstDate"] is None
