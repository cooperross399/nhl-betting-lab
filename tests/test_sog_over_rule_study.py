"""The shots-over rule study measures what its fixed rule says.

`docs/sog_over_rule_decision_rule.md` fixed three candidates and the tests
they must pass before any result was read; these pin the script to it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _study():
    spec = importlib.util.spec_from_file_location(
        "run_sog_over_rule_study", ROOT / "scripts" / "run_sog_over_rule_study.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _overs(rows):
    frame = pd.DataFrame(rows, columns=["edge", "price", "profit", "won", "day"])
    frame["game"] = [("H", "A", day + str(i)) for i, day in enumerate(frame["day"])]
    frame["selection"] = "over"
    return frame


def test_the_candidates_are_the_three_the_rule_fixed():
    study = _study()
    assert list(study.CANDIDATES) == ["bar", "cap", "exclude"]
    removes = {name: rule for name, (_, rule) in study.CANDIDATES.items()}
    assert removes["bar"](0.11, 150.0) and not removes["bar"](0.12, 150.0)
    assert removes["cap"](0.20, 201.0) and not removes["cap"](0.20, 200.0)
    assert removes["exclude"](0.50, -150.0)
    assert study.LEDGER_FROM == "2026-10-22"
    assert study.LOOKS == 3
    rule = (ROOT / study.RULE).read_text(encoding="utf-8")
    for phrase in ("12%", "+200", "2026-10-22", "1 - 0.05/3", "fewest"):
        assert phrase in rule


def test_improvement_is_what_the_removed_overs_lost():
    study = _study()
    overs = _overs([
        (0.07, 250.0, -1.0, False, "2024-11-01"),
        (0.20, 120.0, 1.2, True, "2025-11-01"),
        (0.08, 110.0, -1.0, False, "2025-12-01"),
    ])
    result = study.measure(overs, study.history_seasons(overs))
    assert result["candidates"]["bar"]["improvement"] == 2.0
    assert result["candidates"]["cap"]["improvement"] == 1.0
    assert abs(result["candidates"]["exclude"]["improvement"] - 0.8) < 1e-9
    seasons = result["candidates"]["bar"]["splits"]
    assert seasons["2024-25"]["improvement"] == 1.0
    assert seasons["2025-26"]["improvement"] == 1.0


def test_nothing_passes_without_a_demonstrated_ledger_improvement():
    study = _study()
    losing = _overs([(0.07, 150.0, -1.0, False, f"2026-10-{22 + i % 8}") for i in range(40)])
    history = _overs([(0.07, 150.0, -1.0, False, d) for d in ["2024-11-01", "2025-11-01"] * 20])
    hist = study.measure(history, study.history_seasons(history))
    led = study.measure(losing, study.ledger_halves(losing))
    decisions, chosen = study.verdict(hist, led)
    # Every candidate but the cap removes all 40 losers; the bar and the
    # exclusion pass, and the one removing fewer ledger overs ships (a tie
    # goes to the first named).
    assert decisions["bar"]["passes"] and decisions["exclude"]["passes"]
    assert not decisions["cap"]["passes"]
    assert chosen == "bar"

    mixed = _overs([(0.07, 150.0, (1.5 if i % 2 else -1.0), i % 2 == 1, f"2026-10-{22 + i % 8}")
                    for i in range(40)])
    led = study.measure(mixed, study.ledger_halves(mixed))
    _, chosen = study.verdict(hist, led)
    assert chosen is None
