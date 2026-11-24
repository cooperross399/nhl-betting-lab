"""2026-11-24, the weekly upgrade: a goalie saves over priced longer than
+110 is neither listed as a lean nor staked as a best bet (`LEAN_MAX_PRICE`).
Shorter saves overs and every saves under are untouched, and nothing here
touches the snapshot: `write_snapshot` runs before `build_card`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    LEAN_MAX_PRICE,
    LEAN_MAX_PRICE_REASONS,
    PASSES_SECTION,
    build_candidates,
    lean_excluded_reason,
)


def _row(selection: str, price: float, line: float = 25.5) -> dict:
    return {
        "date": "2026-11-24", "commence_time": "2026-11-25T00:00:00Z",
        "provider_event_id": "evt", "home_team": "Toronto Maple Leafs",
        "away_team": "New York Rangers", "market": "goalie_saves", "player": "Igor Shesterkin",
        "selection": selection, "line": line, "american_odds": price, "book": "BetMGM",
        "fetched_at": "2026-11-24T13:00:00Z",
    }


def _price(row: dict, probability: float):
    key = selection_key(SimpleNamespace(**row), market=row["market"], selection=row["selection"], line=row["line"])
    return build_candidates(pd.DataFrame([row]), {key: probability})


def test_the_cap_is_plus_110() -> None:
    assert LEAN_MAX_PRICE[("goalie_saves", "over")] == 110.0
    assert set(LEAN_MAX_PRICE_REASONS) == set(LEAN_MAX_PRICE)


def test_a_long_saves_over_is_neither_listed_nor_staked() -> None:
    for probability in (0.45, 0.75):  # a lean, and one clearing every bar
        selections, passes = _price(_row("over", 175), probability)
        assert not selections
        (candidate,) = passes
        assert candidate.section == PASSES_SECTION
        assert candidate.suggested_units == 0.0
        assert "priced longer than +110 are neither listed nor staked" in candidate.demotion_reason


def test_the_reason_reads_the_price() -> None:
    assert lean_excluded_reason("goalie_saves", "over", 111) is not None
    assert lean_excluded_reason("goalie_saves", "over", 110) is None
    assert lean_excluded_reason("goalie_saves", "over", -130) is None
    assert lean_excluded_reason("goalie_saves", "under", 175) is None
    assert lean_excluded_reason("goalie_saves", "over", None) is None


def test_a_short_saves_over_still_leans() -> None:
    selections, _ = _price(_row("over", 100), 0.56)
    assert [c.section for c in selections] != []
