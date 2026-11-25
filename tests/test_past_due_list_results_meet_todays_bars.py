"""Past Due List results count only entries today's bars would list.

2026-11-25, Cooper: "fix the previous results based on those bars". 1+ point
counts at 60+ points, a 2-game drought, priced +120 to +200; 1+ assist at 60+
assists, a 1-game drought, priced +100 or longer. Every other category counts
as before. The site spells the bars itself, so they are pinned to the lab's.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from nhl_betting_lab import drought_forward, drought_rule

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("build_site_json", ROOT / "web" / "build_site_json.py")
site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site)


def test_the_sites_bars_are_the_labs():
    for market, (floor, bar, lo, hi) in site.DUE_CURRENT_BARS.items():
        assert drought_rule.THRESHOLDS[market] == floor
        assert drought_rule.tier_bar(market, floor) == bar
        assert drought_rule.TIERS[market] == ((floor, bar),)
        assert drought_rule.PRICE_WINDOWS[market] == (lo, hi)
    assert set(site.DUE_CURRENT_BARS) == set(drought_rule.PRICE_WINDOWS)


CASES = [
    # market, last season, drought, price, counts
    ("points", 70, 2, 150, True),
    ("points", 70, 2, 120, True),
    ("points", 70, 2, 200, True),
    ("points", 70, 2, 210, False),
    ("points", 70, 2, -120, False),
    ("points", 59, 5, 150, False),
    ("points", 90, 1, 150, False),
    ("points", 70, 3, None, True),
    ("assists", 60, 1, 100, True),
    ("assists", 60, 1, 450, True),
    ("assists", 60, 4, -105, False),
    ("assists", 55, 3, 150, False),
    ("assists", None, 3, 150, True),
    ("goals", 22, 10, -120, True),
    ("hat_trick", 45, 50, 1200, True),
]


def test_both_sides_apply_the_same_rule():
    for market, prior, drought, price, counts in CASES:
        assert site.meets_due_bars(market, prior, drought, price) is counts, (market, prior, drought, price)
        assert drought_rule.meets_current_bars(market, prior, drought, price) is counts, (market, prior, drought, price)


def _ledger_row(market, prior, drought, odds, outcome):
    return {"date": "2026-11-01", "player_id": "8478402", "player": "A", "market": market,
            "last_season": prior, "drought": drought, "american_odds": odds, "outcome": outcome}


def test_the_ledger_season_drops_entries_that_miss_the_bars():
    rows = [_ledger_row("points", 70, 2, 150, "won"), _ledger_row("points", 70, 2, -150, "lost"),
            _ledger_row("assists", 50, 3, 200, "lost"), _ledger_row("goals", 30, 9, 180, "lost")]
    season = site.due_ledger_season(rows, {})
    assert (season["w"], season["l"]) == (1, 1)
    assert season["byMarket"]["points"]["l"] == 0 and season["byMarket"]["assists"]["l"] == 0
    assert season["byMarket"]["goals"]["l"] == 1


def test_the_lab_report_and_scorecard_drop_them_too():
    cols = list(drought_forward.LEDGER_COLUMNS)
    rows = [_ledger_row("points", 70, 2, 150, "won"), _ledger_row("points", 70, 2, -150, "lost"),
            _ledger_row("assists", 60, 1, 120, "lost")]
    for r in rows:
        r["profit_units"] = 1.5 if r["outcome"] == "won" else -1.0
    ledger = pd.DataFrame(rows).reindex(columns=cols)
    kept = drought_forward.current_bars_only(ledger)
    assert len(kept) == 2
    assert list(kept["american_odds"]) == [150, 120]


def test_grading_skips_due_list_entries_that_miss_the_bars():
    board = {"games": [{"id": 1, "home": {"abbr": "TOR"}, "away": {"abbr": "MTL"}, "drought": [
        {"player": "A", "playerId": 1, "team": "TOR", "market": "points", "lastSeason": 80, "drought": 2, "price": -140},
        {"player": "B", "playerId": 2, "team": "TOR", "market": "points", "lastSeason": 80, "drought": 2, "price": 140},
    ]}]}
    graded = site.grade_due_list(board, {}, None)
    assert [r["player"] for r in graded["rows"]] == ["B"]


def test_a_night_kept_before_the_restatement_is_settled_again():
    assert site.night_record({"games": [], "summary": {}})["dueGrading"] == site.DUE_GRADING
