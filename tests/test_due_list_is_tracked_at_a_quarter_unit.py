"""The Due List is tracked as if 0.25u were bet on every entry, and is never a pick.

Cooper's Due List (`games[].drought`) is his own list to pick from. Until
2026-10-09 its record was a count with no units. Cooper then asked for it to be
"tracked season long on the website as if we bet .25u on each one every
night", so every graded entry with a price carries `units` at 0.25u, and the
season record carries `stake`, `units` and `staked`. Nothing is bet. An entry
with no price is graded and carries no units. Its entries are still never
props rows, never in `summary.picks` and never in `record.picks`, which stay
the card's best bets alone.

The season record comes from the lab's own Due List ledger when Publish Site
restored it (`drought_forward.csv`, which also holds the nights rebuilt
before the list was first recorded), and from the frozen boards otherwise.

Through the real `main()`: a staged board whose card holds one best bet and
whose Due List holds three entries, graded the next morning.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import csv

import pytest

from test_site_never_calls_an_unpriced_game_a_pass import BOARD_DAY, SLATE, make_lab, schedule, site_module
from test_the_site_board_carries_the_drought_list import row, write_list
from test_due_list_is_graded_season_long import START, write_logs

NEXT_DAY = BOARD_DAY + timedelta(days=1)

LIST = [
    row("TOR", "MTL", player="Alpha Points", player_id=1, market="points", american_odds=-150.0),
    row("TOR", "MTL", team="MTL", player="Bravo Goals", player_id=2, market="goals", american_odds=140.0),
    row("NYI", "BOS", player="Charlie Assists", player_id=3, market="assists", american_odds=None, book=""),
]
LOGS = [
    (SLATE[0][2], 1, "Alpha Points", "TOR", 1, 1),
    (SLATE[0][2], 2, "Bravo Goals", "MTL", 0, 0),
    (SLATE[1][2], 3, "Charlie Assists", "NYI", 0, 1),
]


def _build(lab: Path, out: Path, monkeypatch, day, *, finals: bool) -> tuple[dict, dict]:
    module = site_module()

    def later(d):
        games = schedule(d, final=finals and d < day)
        for g in games:
            g["startTimeUTC"] = START
        return games

    monkeypatch.setattr(module, "schedule_for", later)
    monkeypatch.setattr(module, "allowlisted_markets", lambda _lab: ["moneyline", "puck_line", "total_goals"])
    assert module.main(["--lab", str(lab), "--out", str(out), "--date", day.isoformat()]) == 0
    board = json.loads((out / "board.json").read_text(encoding="utf-8"))
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    return board, results


def _settled(tmp_path: Path, monkeypatch) -> tuple[dict, dict, dict]:
    """The night's board, then the morning after's board and results."""
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    write_list(lab, LIST)
    write_logs(lab, LOGS)
    out = tmp_path / "out"
    night_board, _ = _build(lab, out, monkeypatch, BOARD_DAY, finals=False)
    board, results = _build(lab, out, monkeypatch, NEXT_DAY, finals=True)
    return night_board, board, results


def _paths_holding(node, wanted: str, path: tuple = ()) -> list[tuple]:
    """Every key path at which `wanted` appears as a value."""
    if isinstance(node, dict):
        return [p for key, value in node.items() for p in _paths_holding(value, wanted, path + (key,))]
    if isinstance(node, list):
        return [p for index, value in enumerate(node) for p in _paths_holding(value, wanted, path + (index,))]
    return [path] if node == wanted else []


def test_every_priced_entry_is_tracked_at_a_quarter_unit(tmp_path: Path, monkeypatch) -> None:
    _, board, results = _settled(tmp_path, monkeypatch)

    rows = {r["player"]: r for r in results["dueList"]["rows"]}
    assert [rows[n]["result"] for n in ("Alpha Points", "Bravo Goals", "Charlie Assists")] == ["win", "loss", "win"]
    # -150 won: 0.25 x 100/150. +140 lost: the 0.25 stake. No price: graded, no units.
    assert rows["Alpha Points"]["units"] == pytest.approx(0.1667, abs=1e-4)
    assert rows["Bravo Goals"]["units"] == -0.25
    assert rows["Charlie Assists"]["units"] is None
    assert board["record"]["dueList"] == {"w": 2, "l": 1, "p": 0, "nights": 1, "stake": 0.25, "units": -0.08, "staked": 0.5}
    season = results["seasonRecord"]["dueList"]
    assert (season["source"], season["units"], season["staked"], season["returnPct"]) == ("boards", -0.08, 0.5, -16.7)


def _write_ledger(lab: Path, rows: list[dict], sources: dict | None = None) -> None:
    processed = lab / "data" / "processed"
    columns = ["date", "home_team", "away_team", "team", "player", "player_id", "market", "line",
               "american_odds", "book", "outcome", "actual", "profit_units"]
    with (processed / "drought_forward.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in columns})
    if sources is not None:
        (processed / "drought_list").mkdir(parents=True, exist_ok=True)
        (processed / "drought_list" / "sources.json").write_text(json.dumps(sources), encoding="utf-8")


def test_the_season_comes_from_the_labs_ledger_with_its_backfilled_nights(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    write_list(lab, LIST)
    write_logs(lab, LOGS)
    day = BOARD_DAY.isoformat()
    earlier = (BOARD_DAY - timedelta(days=3)).isoformat()
    _write_ledger(lab, [
        # A night rebuilt before the list was first recorded: +200 won, -110 lost, one never dressed.
        {"date": earlier, "player": "Old A", "player_id": 11, "market": "goals", "american_odds": 200, "outcome": "won"},
        {"date": earlier, "player": "Old B", "player_id": 12, "market": "points", "american_odds": -110, "outcome": "lost"},
        {"date": earlier, "player": "Old C", "player_id": 13, "market": "assists", "american_odds": 150, "outcome": "void"},
        # The board's night, settled by the lab; Charlie was listed with no price and took the card's +120.
        {"date": day, "player": "Alpha Points", "player_id": 1, "market": "points", "american_odds": -150, "outcome": "won"},
        {"date": day, "player": "Bravo Goals", "player_id": 2, "market": "goals", "american_odds": 140, "outcome": "lost"},
        {"date": day, "player": "Charlie Assists", "player_id": 3, "market": "assists", "american_odds": 120, "outcome": "won"},
        # Graded with no price anywhere: in the record, not in the units.
        {"date": day, "player": "Delta None", "player_id": 4, "market": "goals", "american_odds": "", "outcome": "lost"},
    ], {"backfilled": {earlier: {"rows": 3, "priced": 3, "card_prices": True}},
        "filled": {day: [{"player_id": 3, "market": "assists", "american_odds": 120, "book": "FanDuel"}]}})
    out = tmp_path / "out"
    _build(lab, out, monkeypatch, BOARD_DAY, finals=False)
    board, results = _build(lab, out, monkeypatch, NEXT_DAY, finals=True)

    charlie = next(r for r in results["dueList"]["rows"] if r["player"] == "Charlie Assists")
    assert (charlie["price"], charlie["priceSource"], charlie["units"]) == (120, "card", 0.3)

    season = results["dueList"]["season"]
    # Won: +0.50, +0.1667, +0.30. Lost: -0.25, -0.25. Six priced wagers' worth of stake less the void and Delta.
    assert (season["w"], season["l"], season["p"], season["nights"]) == (3, 3, 0, 2)
    assert (season["wagers"], season["unpriced"], season["void"]) == (5, 1, 1)
    assert season["units"] == pytest.approx(0.47, abs=0.005) and season["staked"] == 1.25
    assert season["backfilledNights"] == [earlier] and season["cardPriced"] == 1 and season["source"] == "ledger"
    assert board["record"]["dueList"] == {"w": 3, "l": 3, "p": 0, "nights": 2, "stake": 0.25,
                                          "units": season["units"], "staked": 1.25}


def test_due_list_entries_are_never_picks_or_props(tmp_path: Path, monkeypatch) -> None:
    night_board, board, results = _settled(tmp_path, monkeypatch)

    # The card's one best bet is the whole record; three graded Due List
    # entries added nothing to it.
    assert results["summary"]["picks"] == {"w": 1, "l": 0, "p": 0}
    assert results["seasonRecord"]["picks"] == {"w": 1, "l": 0, "p": 0}
    assert board["record"]["picks"] == {"w": 1, "l": 0, "p": 0}
    assert results["summary"]["leans"] == {"w": 0, "l": 0, "p": 0}
    listed = {(e["player_id"], e["market"]) for e in LIST}
    for prop_row in (results.get("props") or {}).get("rows") or []:
        assert (prop_row.get("playerId"), prop_row.get("market")) not in listed, prop_row
    # A listed player's name appears under the Due List and nowhere else on
    # either file: not a pick, not a prop, not a tally.
    for entry in LIST:
        on_results = _paths_holding(results, entry["player"])
        assert on_results and all(p[0] == "dueList" for p in on_results), on_results
        on_board = _paths_holding(night_board, entry["player"])
        assert on_board and all(p[0] == "games" and p[2] == "drought" for p in on_board), on_board
