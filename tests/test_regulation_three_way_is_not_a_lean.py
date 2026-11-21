"""2026-11-21 (Cooper: "reevaluate totals, leans, the due list, and the hot
list so we can begin to try and turn that profit into a positive soon"):
regulation three-way is never listed as a lean. It goes to the passes with
its reason, as any excluded side does; other team markets still lean.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    LEAN_ONLY_EXCLUDED_MARKETS,
    LEANS_SECTION,
    PASSES_SECTION,
    build_candidates,
)


def _row(market: str, selection: str, price: float, line=None) -> dict:
    return {
        "date": "2026-11-21", "commence_time": "2026-11-22T00:00:00Z",
        "provider_event_id": "evt", "home_team": "Toronto Maple Leafs",
        "away_team": "New York Rangers", "market": market, "player": "",
        "selection": selection, "line": line, "american_odds": price, "book": "BetMGM",
        "fetched_at": "2026-11-21T13:00:00Z",
    }


def _price(row: dict, probability: float):
    key = selection_key(SimpleNamespace(**row), market=row["market"], selection=row["selection"], line=row["line"])
    return build_candidates(pd.DataFrame([row]), {key: probability})


def test_a_regulation_three_way_lean_goes_to_the_passes() -> None:
    selections, passes = _price(_row("regulation_3_way", "draw", 250), 0.33)  # about 4.4 points: a lean
    assert not selections
    (candidate,) = passes
    assert candidate.section == PASSES_SECTION
    assert candidate.suggested_units == 0.0
    assert candidate.demotion_reason == LEAN_ONLY_EXCLUDED_MARKETS["regulation_3_way"]


def test_a_total_over_still_leans() -> None:
    selections, _ = _price(_row("total_goals", "over", 100, 6.5), 0.55)
    assert [c.section for c in selections] == [LEANS_SECTION]
