"""Due List hat tricks are tracked at 0.1u, every other entry at 0.25u.

Cooper, 2026-11-09: "hat tricks should be tracked as .1u bets for the DUE
LIST", then "back-check and apply the .1u all the previous hat trick wagers on
the DUE list also". Nothing is bet. Every tracked figure is restated from each
entry's own price and result, so entries graded before the change read at 0.1u
too: the site's tracker rows, its season and night tallies, the lab ledger's
season line and the weekly scorecard.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab import drought_forward as df
from test_site_never_calls_an_unpriced_game_a_pass import site_module


def test_the_site_tracks_a_hat_trick_at_a_tenth_to_win_on_a_minus_price() -> None:
    site = site_module()
    assert site.due_stake("hat_trick") == 0.1
    assert site.due_stake("goals") == site.DUE_LIST_STAKE == 0.25
    assert site.due_units("win", 900.0, "hat_trick") == pytest.approx(0.9)
    assert site.due_units("loss", 900.0, "hat_trick") == pytest.approx(-0.1)
    assert site.due_units("loss", 900.0, "goals") == pytest.approx(-0.25)
    assert site.due_risk(-200.0, "hat_trick") == pytest.approx(0.2)
    assert site.due_units("win", -200.0, "hat_trick") == pytest.approx(0.1)


def test_a_past_hat_trick_row_is_restated_at_a_tenth() -> None:
    site = site_module()
    kept = {"group": "due", "market": "hat_trick", "price": 800.0, "result": "loss", "staked": 0.25, "units": -0.25}
    again = site.restake(dict(kept))
    assert again["staked"] == pytest.approx(0.1) and again["units"] == pytest.approx(-0.1)
    other = site.restake({**kept, "market": "two_goals"})
    assert other["units"] == pytest.approx(-0.25)
    tally = site.due_list_tallies([kept, {**kept, "market": "points", "price": -120.0, "result": "win"}])
    assert tally["units"] == pytest.approx(-0.1 + 0.25)
    assert tally["staked"] == pytest.approx(0.1 + 0.3)


def test_the_lab_ledger_tracks_hat_tricks_at_a_tenth() -> None:
    assert df.tracked_stake("hat_trick") == 0.1 and df.tracked_stake("goals") == df.TRACKED_STAKE
    ledger = pd.DataFrame({
        "market": ["hat_trick", "goals", "hat_trick"],
        "outcome": ["lost", "won", "won"],
        "american_odds": [900.0, 150.0, 1000.0],
        "profit_units": [-1.0, 1.5, 10.0],
    })
    units, staked = df._tracked(ledger)
    assert units == pytest.approx(-0.1 + 0.375 + 1.0)
    assert staked == pytest.approx(0.1 + 0.25 + 0.1)


def test_the_published_board_and_results_say_hat_tricks_are_a_tenth() -> None:
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("smooth_pages_for_test", root / "web" / "smooth_pages.py")
    smooth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smooth)
    for name, times in (("Board.dc.html", 2), ("Results.dc.html", 1)):
        out = smooth.patch(name, (root / "web" / name).read_text(encoding="utf-8"))
        assert out.count("tracked at 0.25u each, hat tricks 0.1u") == times
        assert "tracked at 0.25u each</span>" not in out
