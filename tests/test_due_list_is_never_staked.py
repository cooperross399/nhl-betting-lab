"""The Due List is never staked: no units anywhere under it, and never a pick.

Cooper's Due List (`games[].drought`) is his own list to pick from. The site
grades it (web/build_site_json.py::grade_due_list) and keeps its record
(`record.dueList`, `dueList.season`), and that record is a count: no `units`,
no `profitUnits`, in any row or tally, on board.json or results.json. Its
entries are never props rows, never in `summary.picks` and never in
`record.picks`, which stay the card's best bets alone.

Through the real `main()`: a staged board whose card holds one best bet and
whose Due List holds three entries, graded the next morning.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from test_site_never_calls_an_unpriced_game_a_pass import BOARD_DAY, SLATE, make_lab, schedule, site_module
from test_the_site_board_carries_the_drought_list import row, write_list
from test_due_list_is_graded_season_long import START, write_logs

NEXT_DAY = BOARD_DAY + timedelta(days=1)

#: A key that would make the Due List a wager. `unit` catches every spelling
#: the props block uses (`units`, `profitUnits`, `unitDollars`).
STAKE_WORDS = ("units", "profitUnits")

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


def _keys(node, found: set, path: tuple = ()) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            _keys(value, found, path + (key,))
    elif isinstance(node, list):
        for value in node:
            _keys(value, found, path)


def _paths_holding(node, wanted: str, path: tuple = ()) -> list[tuple]:
    """Every key path at which `wanted` appears as a value."""
    if isinstance(node, dict):
        return [p for key, value in node.items() for p in _paths_holding(value, wanted, path + (key,))]
    if isinstance(node, list):
        return [p for index, value in enumerate(node) for p in _paths_holding(value, wanted, path + (index,))]
    return [path] if node == wanted else []


def test_no_units_anywhere_under_the_due_list(tmp_path: Path, monkeypatch) -> None:
    _, board, results = _settled(tmp_path, monkeypatch)

    graded = [r for r in results["dueList"]["rows"] if r["result"] in ("win", "loss")]
    assert len(graded) == 3, results["dueList"]["rows"]
    assert board["record"]["dueList"] == {"w": 2, "l": 1, "p": 0, "nights": 1}
    for name, node in (("results.dueList", results["dueList"]), ("board.record.dueList", board["record"]["dueList"]),
                       ("results.seasonRecord.dueList", results["seasonRecord"]["dueList"])):
        keys: set = set()
        _keys(node, keys)
        staked = {k for k in keys if k in STAKE_WORDS or "unit" in k.lower()}
        assert not staked, f"{name} carries {sorted(staked)}: the Due List is never staked"


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
