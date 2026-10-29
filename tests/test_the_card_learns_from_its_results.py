"""The card learns from its own settled opinions (`self_learning`)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from nhl_betting_lab.self_learning import (
    Trust,
    adjusted,
    apply_trust,
    fit_trust,
    load_ledger_for_learning,
)

ROOT = Path(__file__).resolve().parents[1]


def _ledger(market: str, *, days: int, won_when_model_leans: bool, day0: str = "2026-10-22"):
    rows = []
    start = pd.Timestamp(day0)
    for i in range(days):
        day = (start + pd.Timedelta(days=i)).date().isoformat()
        for g in range(4):
            # The model says 60% against a fair even-money price.
            lean_won = won_when_model_leans if (i + g) % 5 else not won_when_model_leans
            rows.append(
                dict(
                    snapshot_date=day, home_team=f"H{g}", away_team=f"A{g}", market=market,
                    player="P" if market in {"points", "shots_on_goal"} else "",
                    selection="over", line=0.5, american_odds=100.0, book="X",
                    model_probability=0.60, outcome="won" if lean_won else "lost",
                )
            )
    return pd.DataFrame(rows)


def test_nothing_learned_changes_nothing():
    probabilities = {("points", "p", "H", "A", "over", 0.5, "d"): 0.6}
    out, moved = apply_trust(probabilities, pd.DataFrame(), {}, key_for=lambda *a, **k: None)
    assert out == probabilities and moved == 0
    assert adjusted(0.6, 100.0, Trust()) == 0.6 or abs(adjusted(0.6, 100.0, Trust()) - 0.6) < 1e-9


def test_a_lean_that_keeps_losing_is_trusted_less():
    losing = fit_trust(_ledger("points", days=60, won_when_model_leans=False))["points"]
    winning = fit_trust(_ledger("points", days=60, won_when_model_leans=True))["points"]
    assert losing.w < 0.6 < 1.0 <= winning.w
    assert adjusted(0.6, 100.0, losing) < 0.6


def test_a_thin_market_barely_moves():
    thin = fit_trust(_ledger("points", days=2, won_when_model_leans=False))["points"]
    thick = fit_trust(_ledger("points", days=60, won_when_model_leans=False))["points"]
    assert thick.w < thin.w


def test_a_superseded_model_is_not_learned_from():
    old = _ledger("total_goals", days=10, won_when_model_leans=False, day0="2026-10-01")
    assert "total_goals" not in fit_trust(old)


def test_a_missing_ledger_reads_as_nothing(tmp_path):
    assert load_ledger_for_learning(tmp_path / "absent.csv").empty


def test_the_snapshot_is_frozen_before_the_card_learns():
    source = (ROOT / "scripts" / "run_gameday_card.py").read_text()
    frozen = source.index("written = write_snapshot(")
    learned = source.index("apply_trust(probabilities")
    card = source.index("card = build_card(")
    assert frozen < learned < card
    assert re.search(r"fit_trust\(load_ledger_for_learning\(processed / LEDGER_FILENAME\)\)", source)
