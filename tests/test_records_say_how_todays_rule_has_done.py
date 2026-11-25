"""2026-11-25 (Cooper: "We have to improve our totals and leans in our model
and on the website. Find a way"): the Totals and Leans season records keep
only the nights under the rule in force today (`CURRENT_RULE_FROM`), and
the board names the day it began (then: "i dont want to see the old
stuff"). About -32u of the old Totals record at 1u was graded under the
projection-against-the-line call retired on 2026-11-05.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from test_site_never_calls_an_unpriced_game_a_pass import site_module


def _night(totals: tuple[int, int, int], units: float, leans: tuple[int, int, int] = (0, 0, 0), lean_units: float = 0.0) -> dict:
    def rec(t):
        return {"w": t[0], "l": t[1], "p": t[2]}
    return {
        "resultsDate": "", "games": [{"id": 1}],
        "summary": {
            "straightUp": {"w": 1, "l": 0}, "picks": rec((0, 0, 0)), "leans": rec(leans), "totals": rec(totals),
            "money": {
                "straightUp": {"units": 1.0, "staked": 1.0, "stake": 1.0},
                "picks": {"units": 0.0, "staked": 0.0, "stake": 1.0},
                "leans": {"units": lean_units, "staked": 1.0, "stake": 1.0},
                "totals": {"units": units, "staked": 1.0, "stake": 1.0},
            },
        },
    }


NIGHTS = {
    date(2026, 11, 3): _night((0, 2, 0), -2.0, (1, 0, 0), 1.0),
    date(2026, 11, 5): _night((2, 1, 0), 0.9),
    date(2026, 11, 25): _night((1, 0, 1), 1.0, (0, 1, 0), -1.0),
}


def _season(tmp_path: Path, monkeypatch) -> dict:
    module = site_module()
    history = tmp_path / "history"
    history.mkdir()
    for day in NIGHTS:
        (history / f"{day.isoformat()}.json").write_text("{}", encoding="utf-8")

    def settle(day, history_dir, **kw):
        return {"resultsDate": day.isoformat(), **{k: v for k, v in NIGHTS[day].items() if k != "resultsDate"}}

    monkeypatch.setattr(module, "settle", settle)
    monkeypatch.setattr(module, "night_record", lambda results: {"games": 1, "summary": results["summary"], "bets": []})
    return module.season_record(date(2026, 11, 28), history, {"resultsDate": "none"})


def test_the_totals_record_counts_only_nights_under_its_rule(tmp_path: Path, monkeypatch) -> None:
    season = _season(tmp_path, monkeypatch)
    assert season["totals"] == {"w": 3, "l": 1, "p": 1}
    assert season["money"]["totals"]["units"] == 1.9
    assert season["money"]["totals"]["since"] == {"from": "2026-11-05", "nights": 2}


def test_the_leans_record_keeps_every_night(tmp_path: Path, monkeypatch) -> None:
    """Cooper: "can we not re-go through the leans. didnt want that to
    start fresh"."""
    season = _season(tmp_path, monkeypatch)
    assert season["leans"] == {"w": 1, "l": 1, "p": 0}
    assert season["money"]["leans"]["units"] == 0.0
    assert "since" not in season["money"]["leans"]


def test_the_other_records_keep_every_night(tmp_path: Path, monkeypatch) -> None:
    season = _season(tmp_path, monkeypatch)
    assert season["straightUp"] == {"w": 3, "l": 0}
    assert season["money"]["straightUp"]["units"] == 3.0
    assert "since" not in season["money"]["picks"]
    assert "since" not in season["money"]["straightUp"]


def test_the_board_names_the_day_the_rule_began() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("_smooth", Path(__file__).resolve().parents[1] / "web" / "smooth_pages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "since(m.since)" in module.PL
    assert "(current rule)" not in module.PL
