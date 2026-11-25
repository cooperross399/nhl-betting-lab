"""2026-11-25 (Cooper: "also find more winning numbers for the totals/leans"):
moneyline leans and away team-total under leans need a 6% edge, and goals
over leans priced longer than +150 are not listed. Each goes to the passes
with its reason; best bets on them are still staked.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    BEST_BETS_SECTION,
    LEANS_SECTION,
    PASSES_SECTION,
    build_candidates,
    lean_only_reason,
)
from nhl_betting_lab.weekly_review import card_status


def _row(market: str, selection: str, price: float, line=None, player: str = "") -> dict:
    return {
        "date": "2026-11-25", "commence_time": "2026-11-26T00:00:00Z",
        "provider_event_id": "evt", "home_team": "Toronto Maple Leafs",
        "away_team": "New York Rangers", "market": market, "player": player,
        "selection": selection, "line": line, "american_odds": price, "book": "BetMGM",
        "fetched_at": "2026-11-25T13:00:00Z",
    }


def _price(row: dict, probability: float):
    key = selection_key(SimpleNamespace(**row), market=row["market"], selection=row["selection"], line=row["line"])
    return build_candidates(pd.DataFrame([row]), {key: probability})


def test_a_thin_moneyline_lean_goes_to_the_passes() -> None:
    for side in ("home", "away"):
        selections, passes = _price(_row("moneyline", side, 100), 0.545)  # 4.5 points
        assert not selections
        (candidate,) = passes
        assert candidate.section == PASSES_SECTION and candidate.suggested_units == 0.0
        assert "6% edge" in candidate.demotion_reason and "moneyline" in candidate.demotion_reason


def test_a_moneyline_lean_from_six_points_still_leans() -> None:
    selections, _ = _price(_row("moneyline", "home", 100), 0.565)
    assert [c.section for c in selections] == [LEANS_SECTION]


def test_a_thin_away_team_total_under_lean_goes_to_the_passes() -> None:
    selections, passes = _price(_row("team_total", "away_under", 100, 3.5), 0.545)
    assert not selections
    assert "6% edge" in passes[0].demotion_reason


def test_a_long_goals_over_lean_goes_to_the_passes() -> None:
    reason = lean_only_reason("goals", "over", 0.08, 220)
    assert reason and "+150" in reason
    assert lean_only_reason("goals", "over", 0.08, 150) is None
    assert lean_only_reason("goals", "under", 0.08, 220) is None


def test_a_long_goals_over_best_bet_is_not_touched_by_the_lean_cap() -> None:
    # The lean-only cap is read only for rows already in the leans section.
    selections, _ = _price(_row("moneyline", "home", 100), 0.62)
    assert [c.section for c in selections] == [BEST_BETS_SECTION]


def test_the_weekly_review_names_the_new_rules() -> None:
    assert "leans from 6%" in card_status("moneyline", "home")
    assert "leans to +150" in card_status("goals", "over")
