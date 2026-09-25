"""Two book spellings of one player were two card selections.

`selection_key` keyed the player on the raw string casefolded, while
`price_props` resolves players through `normalize_player_name`. So
"Alexis Lafreniere" (ReBet) and "Alexis Lafrenière" (every other book) on one
outcome each got the same probability under its own key, `build_candidates`
kept a best price for each, and the card listed one wager twice. The bought
card window carries the split on 234 wager keys across 61 events; on the real
2025-10-16 slate it appeared as two leans on one Lafrenière under. The same
key feeds the forward snapshot and the CLV collapse, so they carried it too.
Found by the failure-shape audit (3/3 refuters).
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.closing_lines import collapse_to_best
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import build_candidates


def _row(player: str, book: str, odds: int) -> dict:
    return {
        "date": "2025-10-16", "commence_time": "2025-10-16T23:00:00Z",
        "provider_event_id": "evt", "home_team": "Toronto Maple Leafs",
        "away_team": "New York Rangers", "market": "points", "player": player,
        "selection": "under", "line": 0.5, "american_odds": odds, "book": book,
        "fetched_at": "2025-10-16T13:00:00Z",
    }


def _key(row: dict) -> tuple:
    return selection_key(SimpleNamespace(**row), market=row["market"],
                         selection=row["selection"], line=row["line"])


def test_one_player_spelled_two_ways_is_one_key() -> None:
    assert _key(_row("Alexis Lafreniere", "ReBet", -113)) == _key(
        _row("Alexis Lafrenière", "FanDuel", -104)
    )
    assert _key(_row("JT Miller", "ReBet", -113)) == _key(
        _row("J.T. Miller", "FanDuel", -104)
    )


def test_a_disambiguated_name_stays_its_own_player() -> None:
    assert _key(_row("Elias Pettersson (2004)", "FanDuel", -104)) != _key(
        _row("Elias Pettersson", "FanDuel", -104)
    )


def test_the_card_lists_one_outcome_once_at_the_best_price() -> None:
    rows = [_row("Alexis Lafreniere", "ReBet", -113),
            _row("Alexis Lafrenière", "FanDuel", 104)]
    probabilities = {_key(r): 0.62 for r in rows}

    selections, passes = build_candidates(pd.DataFrame(rows), probabilities)
    listed = [(c.player, c.book, c.american_odds) for c in selections + passes]

    assert len(listed) == 1, listed
    assert listed[0][1] == "FanDuel"


def test_the_clv_collapse_counts_the_two_spellings_once() -> None:
    frame = pd.DataFrame([_row("Alexis Lafreniere", "ReBet", -113),
                          _row("Alexis Lafrenière", "FanDuel", 104)])

    kept = collapse_to_best(frame)

    assert len(kept) == 1 and kept.iloc[0]["book"] == "FanDuel"
