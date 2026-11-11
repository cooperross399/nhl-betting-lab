"""The Due List shows each row's tracked size, tags a band that lost in
testing, and keeps a live record by group.

Cooper, 2026-11-10, chose "All three" on: show the bet size on each Due List
row, tag the two groups that lost in testing, and track each group's live
record. None of it changes who is listed: a lost-in-testing row stays on the
list, and the size is the notional one the site's season record counts.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhl_betting_lab import drought_rule as dr
from nhl_betting_lab.reports.gameday_card import GamedayCard, render_drought_section
from test_site_never_calls_an_unpriced_game_a_pass import site_module

ROOT = Path(__file__).resolve().parents[1]
LOSING = {"wagers": 659, "roi": -0.19, "ci_low": -0.32, "ci_high": -0.043}
SPANNING = {"wagers": 646, "roi": 0.059, "ci_low": -0.06, "ci_high": 0.202}


def test_only_a_band_whose_interval_sits_below_zero_is_flagged() -> None:
    assert dr.lost_in_testing({"cell_record": LOSING})
    assert not dr.lost_in_testing({"cell_record": SPANNING})
    assert not dr.lost_in_testing({"cell_record": None})
    assert not dr.lost_in_testing({})


def test_the_committed_backtest_flags_the_two_losing_bands() -> None:
    records = dr.cell_records(ROOT / "data" / "outputs")
    flagged = {key for key, rec in records.items() if dr.lost_in_testing({"cell_record": rec})}
    assert flagged == {("goals", "20-24"), ("assists", "40-59")}


def _listed(**kw) -> dict:
    base = {"player": "Some Skater", "player_id": 8470001, "team": "TOR", "opponent": "MTL",
            "home_team": "TOR", "away_team": "MTL", "commence_time": "2026-11-11T00:00:00Z",
            "market": "goals", "line": 0.5, "last_season": 22, "drought": 11, "tier_bar": 10,
            "surprise_bar": None, "hit_rate": 0.2, "rarity": 0.08, "one_in": 12, "rule": "tier",
            "band": "20-24", "cell_record": LOSING, "american_odds": 320, "book": "fanduel",
            "heavy_juice": False}
    base.update(kw)
    return base


def test_the_card_shows_the_tracked_size_and_the_flag() -> None:
    card = GamedayCard(generated_at="2026-11-10T14:40:00+00:00", drought_built=True, drought_headline="h",
                       drought_rows=[_listed(), _listed(player="Even Money", player_id=8470002, band="25-39",
                                                        cell_record=SPANNING, american_odds=-120)])
    text = "\n".join(render_drought_section(card))
    assert "| Best price | Book | Tracked at | Flag |" in text
    assert "| +320 | fanduel | 0.15u | lost in testing (band interval below zero) |" in text
    assert "| -120 | fanduel | 0.25u |  |" in text


def test_the_site_row_carries_its_stake_and_the_flag() -> None:
    site = site_module()
    listed = {"rows": [_listed(), _listed(player="No Price", player_id=8470003, american_odds=None,
                                          cell_record=SPANNING)]}
    rows = site.drought_for_game(listed, "TOR", "MTL", started=False)
    assert rows[0]["stake"] == 0.15 and rows[0]["lostInTesting"] is True
    assert rows[1]["stake"] is None and rows[1]["lostInTesting"] is False


def test_the_tracker_keeps_a_record_by_group(tmp_path) -> None:
    site = site_module()
    results = {"resultsDate": "2026-11-09", "games": [], "dueList": {"rows": [
        {"market": "goals", "band": "20-24", "player": "A", "playerId": 1, "price": 300, "result": "loss"},
        {"market": "goals", "band": "20-24", "player": "B", "playerId": 2, "price": 150, "result": "win"},
        {"market": "assists", "band": "60+", "player": "C", "playerId": 3, "price": -130, "result": "win"},
    ]}}
    rows = site.tracker_rows(results)
    out = site.tracker(rows, nights=1)
    groups = {g["key"]: g for g in out["byDueGroup"]}
    assert set(groups) == {"goals:20-24", "assists:60+"}
    goals = groups["goals:20-24"]
    assert (goals["w"], goals["l"], goals["bets"]) == (1, 1, 2)
    assert goals["units"] == round(0.25 * 1.5 - 0.15, 2)
    assert goals["label"].endswith("20-24 last season")
    assert sum(g["bets"] for g in out["byDueGroup"]) == 3


def test_a_kept_night_without_bands_takes_them_from_its_frozen_board(tmp_path) -> None:
    site = site_module()
    frozen = tmp_path / "2026-11-05.json"
    frozen.write_text(json.dumps({"games": [{"drought": [
        {"playerId": 1, "market": "goals", "band": "25-39"},
        {"player": "Name Only", "market": "points", "band": "100+"},
    ]}]}), encoding="utf-8")
    bets = [{"group": "due", "market": "goals", "playerId": 1}, {"group": "due", "market": "points", "player": "Name Only"},
            {"group": "team", "market": "moneyline"}, {"group": "due", "market": "goals", "playerId": 9}]
    out = site.with_due_bands(bets, frozen)
    assert [r.get("band") for r in out] == ["25-39", "100+", None, None]


def test_the_board_draws_the_size_and_the_tag() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("smooth_pages_for_test", ROOT / "web" / "smooth_pages.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    page = module.patch("Board.dc.html", (ROOT / "web" / "Board.dc.html").read_text(encoding="utf-8"))
    assert 'label: "Tracked at"' in page and "⚠ lost in testing" in page and 'value: "Lost in testing"' in page


def test_the_record_page_has_the_due_list_group_table() -> None:
    page = (ROOT / "web" / "Record.dc.html").read_text(encoding="utf-8")
    assert 'mkTable("by-due-group"' in page
