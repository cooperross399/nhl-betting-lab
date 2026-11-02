"""Cooper, 2026-11-01: "Lets always include a 'bet down to' number."

Every best bet and lean the card writes carries the worst American price at
which it still clears the bar its section was decided on, the card prints it
in its own column, and the site's feed carries it through to the tracker.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.config import MAX_DEFAULT_JUICE, MIN_EDGE, MIN_PROP_EDGE
from nhl_betting_lab.models.value import american_to_implied
from nhl_betting_lab.reports import gameday_card as gc


@pytest.mark.parametrize(
    "probability, bar",
    [(0.50, MIN_EDGE), (0.60, gc.BEST_BET_EDGE), (0.30, MIN_PROP_EDGE), (0.20, gc.BEST_BET_PROP_EDGE),
     (0.536, MIN_EDGE), (0.45, 0.035), (0.58, 0.02)],
)
def test_the_number_is_the_worst_whole_price_that_still_clears(probability: float, bar: float) -> None:
    price = gc.bet_down_to(probability, bar)
    assert price is not None
    assert probability - american_to_implied(price) >= bar
    # One whole price worse no longer clears, unless the juice floor stopped it.
    worse = -101 if price == 100 else price - 1
    if price != MAX_DEFAULT_JUICE:
        assert probability - american_to_implied(worse) < bar


def test_it_is_floored_at_the_juice_limit() -> None:
    assert gc.bet_down_to(0.75, MIN_EDGE) == MAX_DEFAULT_JUICE


def test_no_number_when_nothing_can_clear() -> None:
    assert gc.bet_down_to(0.03, MIN_EDGE) is None
    assert gc.bet_down_to(None, MIN_EDGE) is None
    assert gc.bet_down_to(float("nan"), MIN_EDGE) is None


def _card_rows() -> list[gc.Candidate]:
    prices = pd.DataFrame(
        [
            {"date": "2026-11-02", "commence_time": "2026-11-03T00:00:00Z", "home_team": "Boston Bruins",
             "away_team": "Toronto Maple Leafs", "market": "moneyline", "selection": "home", "player": "",
             "line": None, "american_odds": 120, "book": "fanduel"},
            {"date": "2026-11-02", "commence_time": "2026-11-03T00:00:00Z", "home_team": "Boston Bruins",
             "away_team": "Toronto Maple Leafs", "market": "total_goals", "selection": "over", "player": "",
             "line": 6.5, "american_odds": 110, "book": "draftkings"},
        ]
    )
    probabilities = {}
    for row in prices.itertuples():
        key = gc.selection_key(row, market=row.market, selection=row.selection,
                               line=None if pd.isna(row.line) else float(row.line))
        probabilities[key] = 0.60 if row.market == "moneyline" else 0.52
    selections, _passes = gc.build_candidates(prices, probabilities)
    return selections


def test_every_selection_carries_its_number_for_its_own_section() -> None:
    rows = _card_rows()
    assert rows
    for c in rows:
        assert c.bet_down_to is not None
        assert c.bet_down_to <= c.american_odds
        bar = gc.BEST_BET_EDGE if c.section == gc.BEST_BETS_SECTION else MIN_EDGE
        assert c.model_probability - american_to_implied(c.bet_down_to) >= bar
        assert "bet_down_to" in c.as_row()


def test_the_card_prints_a_bet_down_to_column_for_bets_and_leans() -> None:
    rows = [c.as_row() for c in _card_rows()]
    bets = gc._rows_table(rows, staked=True, down_to=True)
    assert "Bet down to" in bets[0]
    assert bets[0].count("|") == bets[1].count("|") == bets[2].count("|")
    passes = gc._rows_table(rows, staked=False)
    assert "Bet down to" not in passes[0]
