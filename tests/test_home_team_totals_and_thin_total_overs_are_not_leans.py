"""2026-11-25 (Cooper: "We have to improve our totals and leans in our model
and on the website. Find a way"): a home team total is never listed as a
lean, and a game-total over is listed only from a 6% edge, the bar the under
already had. Both go to the passes with their reason; a best bet on either is
still staked, and the away team total and a 6%+ total over still lean.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    BEST_BETS_SECTION,
    LEAN_MIN_EDGE,
    LEAN_ONLY_EXCLUDED_SIDES,
    LEANS_SECTION,
    PASSES_SECTION,
    build_candidates,
    lean_bar,
    lean_only_reason,
)


def _row(market: str, selection: str, price: float, line=None) -> dict:
    return {
        "date": "2026-11-25", "commence_time": "2026-11-26T00:00:00Z",
        "provider_event_id": "evt", "home_team": "Toronto Maple Leafs",
        "away_team": "New York Rangers", "market": market, "player": "",
        "selection": selection, "line": line, "american_odds": price, "book": "BetMGM",
        "fetched_at": "2026-11-25T13:00:00Z",
    }


def _price(row: dict, probability: float):
    key = selection_key(SimpleNamespace(**row), market=row["market"], selection=row["selection"], line=row["line"])
    return build_candidates(pd.DataFrame([row]), {key: probability})


def test_a_home_team_total_lean_goes_to_the_passes() -> None:
    for selection in ("home_over", "home_under"):
        selections, passes = _price(_row("team_total", selection, 100, 3.5), 0.55)
        assert not selections
        (candidate,) = passes
        assert candidate.section == PASSES_SECTION
        assert candidate.suggested_units == 0.0
        assert candidate.demotion_reason == LEAN_ONLY_EXCLUDED_SIDES[("team_total", selection)]


def test_an_away_team_total_still_leans() -> None:
    selections, _ = _price(_row("team_total", "away_over", 100, 3.5), 0.55)
    assert [c.section for c in selections] == [LEANS_SECTION]


def test_a_home_team_total_best_bet_is_still_staked() -> None:
    selections, _ = _price(_row("team_total", "home_over", 100, 3.5), 0.62)  # 12 points
    assert [c.section for c in selections] == [BEST_BETS_SECTION]
    assert selections[0].suggested_units > 0


def test_a_thin_total_over_goes_to_the_passes() -> None:
    selections, passes = _price(_row("total_goals", "over", 100, 6.5), 0.55)  # 5 points
    assert not selections
    (candidate,) = passes
    assert candidate.demotion_reason == lean_only_reason("total_goals", "over", 0.05)
    assert "6% edge" in candidate.demotion_reason


def test_a_total_over_from_six_points_leans() -> None:
    selections, _ = _price(_row("total_goals", "over", 100, 6.5), 0.565)
    assert [c.section for c in selections] == [LEANS_SECTION]
    assert lean_bar("total_goals", "over", 0.035) == LEAN_MIN_EDGE[("total_goals", "over")]


def test_other_sides_keep_their_bar() -> None:
    assert lean_bar("puck_line", "home", 0.035) == 0.035
    assert lean_only_reason("total_goals", "over", 0.07) is None
    assert lean_only_reason("team_total", "away_over", 0.04) is None
