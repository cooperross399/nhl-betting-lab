"""Due List hat tricks are tracked as 0.1u bets; every other category stays at 0.25u.

Cooper, 2026-11-09: "hat tricks should be tracked as .1u bets for the DUE LIST".
Nothing is bet. The site (`web/build_site_json.py`) and the lab's ledger summaries
(`drought_forward`) both count a hat trick at 0.1u: its profit, what it risked,
the season record's units and staked, and the Monday scorecard. The two stakes
are spelled out in both places and must agree.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import drought_forward as df

ROOT = Path(__file__).resolve().parents[1]


def site():
    spec = importlib.util.spec_from_file_location("build_site_json_hat_tricks", ROOT / "web" / "build_site_json.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_site_and_the_lab_agree_on_the_stakes():
    module = site()
    assert module.DUE_LIST_STAKE == df.TRACKED_STAKE == 0.25
    assert module.DUE_LIST_STAKES == df.TRACKED_STAKES == {"hat_trick": 0.1}


def test_a_hat_trick_wins_and_loses_a_tenth_of_a_unit():
    module = site()
    assert module.due_units("win", 400.0, "hat_trick") == pytest.approx(0.4)
    assert module.due_units("loss", 400.0, "hat_trick") == pytest.approx(-0.1)
    assert module.due_risk(400.0, "hat_trick") == pytest.approx(0.1)
    assert module.due_units("push", 400.0, "hat_trick") == 0.0


def test_other_categories_stay_at_a_quarter_unit():
    module = site()
    assert module.due_units("win", 150.0, "goals") == pytest.approx(0.375)
    assert module.due_units("loss", -150.0, "points") == pytest.approx(-0.375)
    assert module.due_risk(-150.0, "points") == pytest.approx(0.375)
    assert module.due_units("win", 150.0) == pytest.approx(0.375)


def test_the_season_record_counts_each_entry_at_its_own_stake():
    module = site()
    rows = [
        {"date": "2026-11-08", "market": "hat_trick", "american_odds": "400", "outcome": "lost", "player_id": "1"},
        {"date": "2026-11-08", "market": "hat_trick", "american_odds": "400", "outcome": "won", "player_id": "2"},
        {"date": "2026-11-08", "market": "goals", "american_odds": "150", "outcome": "lost", "player_id": "3"},
    ]
    season = module.due_ledger_season(rows, {})
    assert season["units"] == pytest.approx(round(-0.1 + 0.4 - 0.25, 2))
    assert season["staked"] == pytest.approx(0.45)
    assert season["stake"] == 0.25 and season["stakeByMarket"] == {"hat_trick": 0.1}


def ledger() -> pd.DataFrame:
    rows = [
        {"date": "2026-11-08", "market": "hat_trick", "american_odds": 400.0, "outcome": "lost", "profit_units": -1.0,
         "home_team": "TOR", "away_team": "MTL"},
        {"date": "2026-11-08", "market": "goals", "american_odds": 150.0, "outcome": "won", "profit_units": 1.5,
         "home_team": "BOS", "away_team": "NYR"},
    ]
    return pd.DataFrame(rows).reindex(columns=list(df.LEDGER_COLUMNS))


def test_the_lab_report_and_scorecard_use_each_entrys_stake():
    report = df.build_report(ledger())
    assert report["tracked"] == {"units": pytest.approx(round(-0.1 + 0.375, 2)), "staked": pytest.approx(0.35), "wagers": 2}
    card = df.build_scorecard(ledger(), "2026-11-10")
    assert card["slices"]["season"]["overall"]["units"] == pytest.approx(round(-0.1 + 0.375, 2))
    assert card["slices"]["season"]["categories"]["hat_trick"]["units"] == pytest.approx(-0.1)
