"""Cooper, 2026-11-04: "Lean points overs more often". A points over is
listed as a lean from a 3% edge, not the usual 6% prop bar. Unstaked
(`points` is stake-excluded), and only the card's listing moves: points
unders and every other prop keep the 6% bar."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.config import MIN_PROP_EDGE
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    LEANS_SECTION,
    PASSES_SECTION,
    build_candidates,
    lean_bar,
)


def _row(market: str, selection: str) -> dict:
    return {
        "date": "2026-11-04", "commence_time": "2026-11-05T00:00:00Z",
        "provider_event_id": "evt", "home_team": "Toronto Maple Leafs",
        "away_team": "New York Rangers", "market": market, "player": "Auston Matthews",
        "selection": selection, "line": 0.5, "american_odds": 100, "book": "BetMGM",
        "fetched_at": "2026-11-04T13:00:00Z",
    }


def _section(market: str, selection: str, edge: float) -> str:
    row = _row(market, selection)
    key = selection_key(SimpleNamespace(**row), market=market, selection=selection, line=0.5)
    selections, passes = build_candidates(pd.DataFrame([row]), {key: 0.5 + edge})
    (candidate,) = selections + passes
    return candidate.section


def test_a_points_over_at_four_percent_is_a_lean() -> None:
    assert _section("points", "over", 0.04) == LEANS_SECTION


def test_a_points_over_under_three_percent_is_a_pass() -> None:
    assert _section("points", "over", 0.02) == PASSES_SECTION


def test_a_points_under_keeps_the_prop_bar() -> None:
    assert _section("points", "under", 0.04) == PASSES_SECTION


def test_other_props_keep_the_prop_bar() -> None:
    assert _section("shots_on_goal", "over", 0.04) == PASSES_SECTION
    assert lean_bar("assists", "over", MIN_PROP_EDGE) == MIN_PROP_EDGE


def test_the_measurement_bar_is_unchanged() -> None:
    assert MIN_PROP_EDGE == 0.06
