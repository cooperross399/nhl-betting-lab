"""An unreadable line is keyed as no line, and a capped longshot is a pass.

Two tests in `tests/test_gameday_card.py` could not fail. The failure-shape
audit found both (findings 81 and 82, each confirmed by at least two of three
refuters). Each finding's mutant left the whole suite green: 1,768 passed at
the audit's commit, and 1,860 passed at 25a3e8a, measured again for this fix.

- `test_an_unparseable_line_is_treated_as_no_line` keyed its probability with
  a hand-built 6-tuple, `("shots_on_goal", "auston matthews", "TOR", "BOS",
  "over", None)`. `card_pricing.selection_key` has returned 7 parts since it
  gained the game date in #39, so the key matched nothing. The test's only
  assertion, `card.card_generated is True`, held just as well with an empty
  map. m10 makes the card read an unreadable line as 2.5 instead of None, and
  it passed that test. The literal was the hand-built key that the file's own
  `_key` docstring forbids, and the one fixture that made CLAUDE.md's "the
  fixtures use it too" untrue.
- `test_a_longshot_beyond_the_price_cap_is_passed` asserted only that a +900
  row with a 30-point edge was neither a best bet nor a lean. m11 deletes
  `passes.append(candidate)` from the price-cap branch. Under it the row
  vanished from the card (summary "0 pass(es)", markdown "_No passes._"), and
  the test still passed.

Production is correct today. These tests hold it there, keyed the way
production keys them: by the real pricers where the fixture allows it, and by
`card_pricing.selection_key` otherwise, never by a hand-built tuple. The first
of the two old tests is also rewritten in place. It is now keyed by `_key`, and
it asserts what its name claims: the row is listed once, at no line. The
second is left as it was, because this file asserts the pass it omitted.

Where each branch is reached:

- **An unreadable line.** No production path produces one today.
  `odds_api._line_of` emits a float or None, and the staging CSV reads back as
  float64. One refuter drove 17 bad provider values through the real
  normalize, write-staging and read-staging chain, and none reached the
  card's `except` branch. The branch is defensive, and the tests hold it to
  the pricer. `card_pricing._line` reads an unreadable line as None, and
  `price_team_markets` keys moneyline and the regulation 3-way at that None.
  So the card must key the row the same way, or a priced opinion is lost
  without a word. `price_props` gives a prop with an unreadable line no
  opinion at all. A card that guessed that line would put the row in a quoted
  line's slot, and best-of-price would then publish its price on a line no
  book offered at that price.
- **The price cap.** This branch is reached. Of the 25,947 wagers in
  `data/outputs/player_props_backtest_bets.csv`, 6 were priced above +600 and
  cleared the 6-point prop bar: 3 on points (up to +796) and 3 on goals (up
  to +900). The backtest applies no cap, and `build_card` uses the +600
  default. The forward ledger freezes before `build_card`, so m11 cost no
  stake and no ledger row. What it cost was a priced, modelled judgement
  missing from the published Passes section, indistinguishable from a row the
  model never priced.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab.config import MAX_DEFAULT_PRICE
from nhl_betting_lab.market_eligibility import (
    ELIGIBLE,
    EligibilityReport,
    MarketEligibility,
)
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.reports import gameday_card as card_module
from nhl_betting_lab.reports.card_pricing import (
    price_props,
    price_team_markets,
    selection_key,
)
from test_player_props_model import sample_logs
from test_team_model import balanced_league


NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)
UNREADABLE = "two and a half"


def _row(**overrides: object) -> dict:
    row = {
        "date": "2026-10-08",
        "commence_time": (NOW + timedelta(hours=4))
        .isoformat()
        .replace("+00:00", "Z"),
        "home_team": "TOR",
        "away_team": "BOS",
        "market": "shots_on_goal",
        "player": "Star TOR",
        "selection": "over",
        "line": 2.5,
        "american_odds": 110,
        "book": "DraftKings",
    }
    row.update(overrides)
    return row


def _key(row: dict, *, line: float | None) -> tuple:
    """The production key function, given the line production would parse."""
    return selection_key(
        SimpleNamespace(**row),
        market=row["market"],
        selection=row["selection"],
        line=line,
    )


def _eligible(*markets: str) -> EligibilityReport:
    return EligibilityReport(
        provider_name="the_odds_api",
        games_in_slate=1,
        markets=[
            MarketEligibility(market=market, state=ELIGIBLE, reason="Allowlisted.")
            for market in markets
        ],
    )


def _listed(card: card_module.GamedayCard) -> list[dict]:
    """Every row the card published, in whichever section it landed."""
    return card.best_bets + card.leans + card.passes


# -- finding 81: an unreadable line ------------------------------------


@pytest.mark.parametrize(
    ("market", "selection", "raw_line"),
    [
        ("moneyline", "home", UNREADABLE),
        ("moneyline", "away", "pk"),
        ("regulation_3_way", "draw", ""),
    ],
)
def test_an_unreadable_team_line_is_keyed_as_no_line_as_the_pricer_keys_it(
    market: str, selection: str, raw_line: str
) -> None:
    """The pricer keys this row at no line, and the card must as well.

    Under m10 the card keyed it at 2.5. The priced opinion then matched
    nothing, and the row appeared in no list, exactly like a row the model
    never priced. m10b drops the row, and m10c keeps the raw string. Both
    lose it the same way."""
    row = _row(
        market=market,
        selection=selection,
        player="",
        line=raw_line,
        home_team="STR",
        away_team="WEA",
        american_odds=150,
    )
    with pytest.raises(ValueError):
        float(raw_line)  # so the card's parse takes its `except` branch
    prices = pd.DataFrame([row])
    priced, unresolved = price_team_markets(
        prices, TeamModel().fit(balanced_league())
    )
    assert unresolved == []
    assert list(priced) == [_key(row, line=None)]

    card = card_module.build_card(
        prices, priced, eligibility=_eligible(market), now=NOW
    )

    assert card.card_generated is True
    listed = _listed(card)
    assert len(listed) == 1
    (only,) = listed
    assert (only["market"], only["selection"]) == (market, selection)
    assert only["line"] is None
    assert only["american_odds"] == 150
    assert only["model_probability"] == pytest.approx(priced[_key(row, line=None)])


def test_an_unreadable_prop_line_never_takes_a_quoted_lines_price() -> None:
    """A guessed line puts an unquoted price on a quoted line.

    The player's 2.5 line is quoted at +110. A second book's row for the same
    player and side has an unreadable line at +150. `price_props` prices the
    2.5 line and gives the unreadable row no opinion. Under m10 the card read
    the unreadable line as 2.5, and best-of-price then published the 2.5 line
    at +150 from a book that never offered 2.5 at that price."""
    quoted = _row(line=2.5, american_odds=110, book="DraftKings")
    unreadable = _row(line=UNREADABLE, american_odds=150, book="FanDuel")
    prices = pd.DataFrame([quoted, unreadable])
    priced, unresolved = price_props(prices, PlayerPropsModel().fit(sample_logs()))
    assert unresolved == []
    assert list(priced) == [_key(quoted, line=2.5)]

    card = card_module.build_card(
        prices, priced, eligibility=_eligible("shots_on_goal"), now=NOW
    )

    assert card.card_generated is True
    listed = _listed(card)
    assert len(listed) == 1
    (only,) = listed
    assert only["line"] == 2.5
    assert only["american_odds"] == 110
    assert only["book"] == "DraftKings"


# -- finding 82: the price cap -----------------------------------------


def _card_at(price: int) -> card_module.GamedayCard:
    """A prop at `price` that the model gives 40%. From +600 up that is an
    edge of 25 points or more, far past the 12-point best-bet bar and never
    heavy juice, so only the price cap can keep it off the selections."""
    row = _row(player="Auston Matthews", line=3.5, american_odds=price)
    return card_module.build_card(
        pd.DataFrame([row]),
        {_key(row, line=3.5): 0.40},
        eligibility=_eligible("shots_on_goal"),
        now=NOW,
    )


def test_a_longshot_past_the_cap_is_listed_as_a_pass_with_its_edge() -> None:
    """Under m11 this row appeared in no list and the summary read 0 passes."""
    card = _card_at(900)

    assert card.best_bets == []
    assert card.leans == []
    assert len(card.passes) == 1
    (row,) = card.passes
    assert row["market"] == "shots_on_goal"
    assert row["american_odds"] == 900
    assert row["section"] == card_module.PASSES_SECTION
    assert row["edge"] == pytest.approx(0.40 - 0.10)
    assert row["suggested_units"] == 0.0
    assert "0 best bet(s), 0 lean(s), 1 pass(es)" in card.summary_line()
    rendered = card_module.render_card(card)
    passes = rendered.split(f"## {card_module.PASSES_SECTION}", 1)[1]
    passes = passes.split("\n## ", 1)[0]
    assert "+900" in passes
    assert "_No passes._" not in passes


def test_a_price_at_the_cap_is_still_playable() -> None:
    """The cap is strict: `price > max_price`, not `>=`."""
    card = _card_at(MAX_DEFAULT_PRICE)

    assert card.passes == []
    assert len(card.best_bets) == 1
    assert card.best_bets[0]["american_odds"] == MAX_DEFAULT_PRICE


def test_one_point_past_the_cap_is_a_pass_not_a_selection() -> None:
    """The cap `build_card` applies is the configured default."""
    card = _card_at(MAX_DEFAULT_PRICE + 1)

    assert card.best_bets == []
    assert card.leans == []
    assert [row["american_odds"] for row in card.passes] == [MAX_DEFAULT_PRICE + 1]
