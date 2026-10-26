"""tracker.json, the file All results (Tracker.dc.html) reads.

Units and return for every graded best bet are published (Cooper,
2026-10-26). These pin the shape the page and other readers expect: the
fields, the result enum, the units arithmetic to the cent, and every split
adding back to `overall` (by team excepted: a total counts under both clubs).
The drop's own fixture is held to the same rules as the builder's output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_site_never_calls_an_unpriced_game_a_pass import site_module
from test_the_tracker_adds_up import _night

ROOT = Path(__file__).resolve().parents[1]
TOP = {"generatedAt", "nights", "firstDate", "lastDate", "teamPickDefaultUnits", "dueStake", "overall",
       "byGroup", "byMarket", "byPropType", "byTeam", "byPlayer", "byPrice", "byMonth", "rows"}
TALLY = {"w", "l", "p", "bets", "staked", "units", "returnPct"}
ROW = {"date", "group", "market", "price", "result", "staked", "units"}
TEAM_ROW = {"label", "team", "teams"}
PLAYER_ROW = {"propType", "side", "line", "player", "playerId", "team", "opp"}


def _win(stake: float, price: float) -> float:
    return stake * (price / 100 if price > 0 else 100 / abs(price))


def _check(doc: dict, *, splits: bool = True) -> None:
    assert set(doc) >= TOP, sorted(TOP - set(doc))
    assert set(doc["overall"]) >= TALLY
    for row in doc["rows"]:
        assert set(row) >= ROW, row
        assert row["group"] in ("team", "props", "due")
        assert row["result"] in ("win", "loss", "push")
        assert set(row) >= (TEAM_ROW if row["group"] == "team" else PLAYER_ROW), row
        expected = {"win": _win(row["staked"], row["price"]), "loss": -row["staked"], "push": 0.0}[row["result"]]
        assert row["units"] == pytest.approx(expected, abs=0.01), row
        if row.get("stakeAssumed"):
            assert row["staked"] == doc["teamPickDefaultUnits"]
        if row["group"] == "due":
            assert row["staked"] == doc["dueStake"]
    o = doc["overall"]
    assert o["bets"] == len(doc["rows"]) == o["w"] + o["l"] + o["p"]
    assert o["units"] == pytest.approx(sum(r["units"] for r in doc["rows"]), abs=0.02)
    if o["staked"]:
        assert o["returnPct"] == pytest.approx(100 * o["units"] / o["staked"], abs=0.1)
    if not splits:
        return
    for split in ("byGroup", "byMarket", "byPrice", "byMonth"):
        parts = doc[split]
        assert all(set(g) >= TALLY | {"key", "label"} for g in parts), split
        assert sum(g["bets"] for g in parts) == o["bets"], split
        assert sum(g["units"] for g in parts) == pytest.approx(o["units"], abs=0.02 * max(1, len(parts))), split


def test_the_builders_tracker_has_the_published_shape() -> None:
    module = site_module()
    rows = module.tracker_rows(_night("2026-10-20")) + module.tracker_rows(_night("2026-11-02"))
    doc = json.loads(json.dumps(module.tracker(rows, nights=2)))
    _check(doc)
    assert all(round(r["units"], 2) == r["units"] for r in doc["rows"]), "units are published to the cent"


def test_an_empty_tracker_has_the_published_shape() -> None:
    _check(json.loads(json.dumps(site_module().tracker([], nights=0))))


@pytest.mark.parametrize("name", ["tracker.json", "tracker_empty.json"])
def test_the_pages_fixtures_follow_the_same_rules(name: str) -> None:
    """The page recomputes every split from `rows`, so the fixtures' split
    arrays are illustrative; their rows and overall are held to the rules."""
    _check(splits=False, doc=json.loads((ROOT / "web" / "data" / "sample" / name).read_text(encoding="utf-8")))
