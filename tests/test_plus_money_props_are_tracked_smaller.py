"""Plus-money props are tracked at a smaller stake, by price, past ones included.

Cooper, 2026-11-10: "goal scorers/props +200 to +500 are going to be .15u
wagers and go back and edit any previous wagers also. Anything +501 to +1500
is .1u and +1500 or greater is .05u", then ".25u for the others like usual".
It replaces the Due List hat-trick 0.1u of 2026-11-09. Nothing is bet. Every
tracked prop (Due List entries, prop best bets, prop leans) is restated from
its own price and result, so rows graded before the change read at the new
stakes: the site's tracker rows, its season and night tallies, the prop leans
record, the lab ledger's season line and the weekly scorecard. Team picks stay
at 0.25u.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import drought_forward as df
from test_site_never_calls_an_unpriced_game_a_pass import site_module

ROOT = Path(__file__).resolve().parents[1]
# The 2026-11-10 ladder times four, on a 1u base since 2026-11-21 (Cooper: "use
# the due list ladder style pricing but with 1u as the main instead of .25u").
CASES = ((-300, 1.0), (-110, 1.0), (150, 1.0), (199, 1.0), (200, 0.6), (500, 0.6),
         (501, 0.4), (1500, 0.4), (1501, 0.2), (4000, 0.2))


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_brackets_are_the_same_on_the_site_the_leans_and_the_lab() -> None:
    site = site_module()
    leans = _module("prop_leans_for_test", ROOT / "web" / "prop_leans.py")
    for price, stake in CASES:
        assert site.prop_stake(float(price)) == stake, price
        assert df.tracked_stake("goals", float(price)) == stake, price
        assert leans.stake(float(price)) == stake, price
    assert site.prop_stake(None) == 1.0 and df.tracked_stake("goals", None) == 1.0


def test_a_minus_price_still_wins_a_quarter_and_a_long_one_risks_less() -> None:
    site = site_module()
    assert site.due_units("win", -200.0, "points") == pytest.approx(1.0)
    assert site.due_risk(-200.0, "points") == pytest.approx(2.0)
    assert site.due_units("win", 300.0, "goals") == pytest.approx(1.8)
    assert site.due_units("loss", 300.0, "goals") == pytest.approx(-0.6)
    assert site.due_units("loss", 900.0, "hat_trick") == pytest.approx(-0.4)
    assert site.due_units("win", 2000.0, "hat_trick") == pytest.approx(4.0)
    assert site.due_risk(2000.0, "hat_trick") == pytest.approx(0.2)


def test_past_tracker_rows_are_restated_and_team_picks_are_not() -> None:
    site = site_module()
    for group in ("due", "props", "leans"):
        kept = {"group": group, "market": "goals", "price": 350.0, "result": "loss", "staked": 0.25, "units": -0.25}
        again = site.restake(dict(kept))
        assert again["staked"] == pytest.approx(0.6) and again["units"] == pytest.approx(-0.6), group
    team = site.restake({"group": "team", "market": "moneyline", "price": 250.0, "result": "loss"})
    assert team["units"] == pytest.approx(-1.0)
    tally = site.due_list_tallies([
        {"group": "due", "market": "goals", "price": 600.0, "result": "loss"},
        {"group": "due", "market": "points", "price": -120.0, "result": "win"},
    ])
    assert tally["units"] == pytest.approx(-0.4 + 1.0)
    assert tally["staked"] == pytest.approx(0.4 + 1.2)


def test_prop_leans_are_restated_by_price() -> None:
    leans = _module("prop_leans_for_test2", ROOT / "web" / "prop_leans.py")
    assert leans.risk(-150.0) == pytest.approx(1.5)
    assert leans._units("win", 400.0) == pytest.approx(2.4)
    assert leans._units("loss", 1200.0) == pytest.approx(-0.4)


def test_the_lab_ledger_restates_by_price() -> None:
    ledger = pd.DataFrame({
        "market": ["hat_trick", "goals", "goals", "points"],
        "outcome": ["lost", "won", "won", "lost"],
        "american_odds": [2000.0, 150.0, 400.0, -130.0],
        "profit_units": [-1.0, 1.5, 4.0, -1.0],
    })
    units, staked = df._tracked(ledger)
    assert units == pytest.approx(-0.2 + 1.5 + 2.4 - 1.0)
    assert staked == pytest.approx(0.2 + 1.0 + 0.6 + 1.0)


def test_the_published_board_and_results_name_the_smaller_stakes() -> None:
    smooth = _module("smooth_pages_for_test", ROOT / "web" / "smooth_pages.py")
    for name, times in (("Board.dc.html", 2), ("Results.dc.html", 1)):
        out = smooth.patch(name, (ROOT / "web" / name).read_text(encoding="utf-8"))
        assert out.count("Not model bets · 1u each, less at +200 and longer") == times
        assert "hat tricks 0.1u" not in out
