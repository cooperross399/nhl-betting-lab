"""Prop leans have their own season line and are never in the best bets' record.

web/SCHEMA.md names `props.seasonLeans {w, l, p, nights}` on results.json and
`record.props {w, l, p, units, nights}` / `record.propLeans {w, l, p, nights}`
on board.json. `season_record` sums each settled night's published props rows
(`props.rows[]`: kind, units, result, profitUnits): a row of kind "bet" into
`props`, with its profit in units; a row of kind "lean" into `propLeans`, with
none; a pass, a void or an ungraded row into neither. A lean is never in
`props`, `props.season`, `summary.picks` or `record.picks`.

These tests attach a props block to each settled night's results in the
shape SCHEMA.md gives, around the real `settle()` (which since 2026-10-09
grades the builder's own block, tests/test_the_site_publishes_the_cards_props.py),
and drive the real `main()` over three nights. A night whose block holds no
row is not a night of props.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from test_site_never_calls_an_unpriced_game_a_pass import site_module
from test_due_list_is_graded_season_long import D0, D1, D2, D3, build_night, make_due_list_lab


def _row(pid: int, kind: str, result, *, units=None, profit=None) -> dict:
    """One props results row, as web/SCHEMA.md shapes it."""
    return {"gameId": "x", "player": f"Player {pid}", "playerId": pid, "team": "TOR", "opp": "MTL",
            "position": "C", "market": "shots_on_goal", "line": 2.5, "side": "over", "price": -110,
            "book": "DraftKings", "kind": kind, "tier": "A" if kind == "bet" else None, "units": units,
            "actual": 3 if result else None, "result": result, "profitUnits": profit}


#: What each night published. A pass, a void lean and an ungraded bet are in
#: no tally; D2 publishes no props at all.
NIGHTS = {
    D0: [_row(1, "bet", "win", units=1, profit=0.87), _row(2, "bet", "loss", units=0.5, profit=-0.5),
         _row(3, "bet", "push", units=0.5, profit=0), _row(4, "lean", "win"), _row(5, "lean", "loss"),
         _row(6, "lean", "win"), _row(7, "pass", "win"), _row(8, "lean", "void"), _row(9, "bet", None, units=1)],
    D1: [_row(10, "bet", "win", units=0.5, profit=0.5), _row(11, "lean", "loss")],
}


def _settle_with_props(module, nights: dict[date, list[dict]]):
    """The real settle(), with that night's props block attached as the pipeline would publish it."""
    real = module.settle

    def settle(day, history_dir, **kw):
        results = real(day, history_dir, **kw)
        if day in nights and results["games"]:
            results["props"] = {"status": "ok", "note": "", "marketNotes": {}, "rows": nights[day],
                                "summary": {"w": 0, "l": 0, "p": 0, "units": 0, "ungraded": 0}}
        return results

    return settle


def _three_nights(tmp_path: Path, monkeypatch) -> tuple[Path, dict, dict, dict, dict]:
    lab = make_due_list_lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    module = site_module()
    monkeypatch.setattr(module, "settle", _settle_with_props(module, NIGHTS))
    build_night(lab, out, monkeypatch, D0, module=module)
    first_board, first_results = build_night(lab, out, monkeypatch, D1, module=module)
    build_night(lab, out, monkeypatch, D2, module=module)
    board, results = build_night(lab, out, monkeypatch, D3, module=module)
    return out, first_board, first_results, board, results


def test_leans_have_their_own_season_line_and_the_bets_keep_theirs(tmp_path: Path, monkeypatch) -> None:
    _, first_board, first_results, _, _ = _three_nights(tmp_path, monkeypatch)

    assert first_results["props"]["seasonLeans"] == {"w": 2, "l": 1, "p": 0, "nights": 1}
    assert first_results["props"]["season"] == {"w": 1, "l": 1, "p": 1, "units": 0.37, "nights": 1}
    assert first_board["record"]["props"] == first_results["props"]["season"]
    assert first_board["record"]["propLeans"] == first_results["props"]["seasonLeans"]
    # Three leans, two of them winners, moved the best bets' record not at all.
    assert first_board["record"]["props"]["w"] == 1
    assert "units" not in first_board["record"]["propLeans"]


def test_the_season_sums_every_night_that_carried_props_and_no_other(tmp_path: Path, monkeypatch) -> None:
    out, _, _, board, results = _three_nights(tmp_path, monkeypatch)

    # D0 and D1 published props; D2 did not. The team record counts all three nights.
    assert board["record"]["season"]["nights"] == 3
    assert board["record"]["props"] == {"w": 2, "l": 1, "p": 1, "units": 0.87, "nights": 2}
    assert board["record"]["propLeans"] == {"w": 2, "l": 2, "p": 0, "nights": 2}
    assert results["seasonRecord"]["props"] == board["record"]["props"]
    assert results["seasonRecord"]["propLeans"] == board["record"]["propLeans"]
    # D2's block holds no row: it carries the season line and adds no night.
    assert results["props"]["rows"] == []
    assert results["props"]["season"] == board["record"]["props"]
    # D0 holds an ungraded bet (its box score not yet in the logs), so the
    # night is settled again each run rather than kept, as the Due List's is.
    assert not (out / "history" / "settled" / f"{D0.isoformat()}.json").exists()
    kept = json.loads((out / "history" / "settled" / f"{D1.isoformat()}.json").read_text(encoding="utf-8"))
    assert kept["props"] == {"bets": {"w": 1, "l": 0, "p": 0, "units": 0.5}, "leans": {"w": 0, "l": 1, "p": 0}, "pending": 0}


def test_leans_are_never_in_the_picks_record(tmp_path: Path, monkeypatch) -> None:
    _, first_board, first_results, board, _ = _three_nights(tmp_path, monkeypatch)

    for payload in (first_board, board):
        assert payload["record"]["picks"] == {"w": 0, "l": 0, "p": 0}, "no card, no team pick: the props never leak into it"
        assert payload["record"]["leans"] == {"w": 0, "l": 0, "p": 0}
    assert first_results["summary"]["picks"] == {"w": 0, "l": 0, "p": 0}
    assert first_results["summary"]["leans"] == {"w": 0, "l": 0, "p": 0}
