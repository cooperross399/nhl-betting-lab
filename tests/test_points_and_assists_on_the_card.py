"""2026-11-09, Cooper's decision ("Yes do all 4"): fix points and assists on
the live card.

- an assists under is neither listed as a lean nor staked as a best bet
  (`LEAN_EXCLUDED_SIDES`), as a points under already was not;
- a points over priced longer than +200 is not listed (`LEAN_MAX_PRICE`);
- neither touches the snapshot: `write_snapshot` runs before `build_card`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    BEST_BETS_SECTION,
    LEAN_MAX_PRICE,
    LEANS_SECTION,
    PASSES_SECTION,
    build_candidates,
    lean_excluded_reason,
)


def _row(market: str, selection: str, price: float, line: float = 0.5) -> dict:
    return {
        "date": "2026-11-09", "commence_time": "2026-11-10T00:00:00Z",
        "provider_event_id": "evt", "home_team": "Toronto Maple Leafs",
        "away_team": "New York Rangers", "market": market, "player": "Auston Matthews",
        "selection": selection, "line": line, "american_odds": price, "book": "BetMGM",
        "fetched_at": "2026-11-09T13:00:00Z",
    }


def _price(row: dict, probability: float):
    key = selection_key(SimpleNamespace(**row), market=row["market"], selection=row["selection"], line=row["line"])
    return build_candidates(pd.DataFrame([row]), {key: probability})


def test_an_assists_under_is_neither_listed_nor_staked() -> None:
    for probability in (0.75, 0.95):  # a lean, and a best bet clearing every bar
        selections, passes = _price(_row("assists", "under", -150), probability)
        assert not selections
        (candidate,) = passes
        assert candidate.section == PASSES_SECTION
        assert candidate.suggested_units == 0.0
        assert "assists unders are neither listed nor staked" in candidate.demotion_reason


def test_an_assists_over_still_leans_and_stakes() -> None:
    selections, _ = _price(_row("assists", "over", 150), 0.47)
    assert [c.section for c in selections] == [LEANS_SECTION]
    selections, _ = _price(_row("assists", "over", 100), 0.70)
    assert [c.section for c in selections] == [BEST_BETS_SECTION]


def test_a_long_points_over_is_not_listed() -> None:
    cap = LEAN_MAX_PRICE[("points", "over")]
    assert cap == 200.0
    selections, passes = _price(_row("points", "over", 250), 0.35)
    assert not selections
    assert "priced longer than +200" in passes[0].demotion_reason
    # At the cap and shorter it still leans from the 3% bar.
    selections, _ = _price(_row("points", "over", 200), 0.37)
    assert [c.section for c in selections] == [LEANS_SECTION]


def test_the_reason_reads_the_price() -> None:
    assert lean_excluded_reason("points", "over", 201) is not None
    assert lean_excluded_reason("points", "over", 200) is None
    assert lean_excluded_reason("points", "over", None) is None
    assert lean_excluded_reason("points", "over", "n/a") is None
    assert lean_excluded_reason("goals", "over", 900) is None
