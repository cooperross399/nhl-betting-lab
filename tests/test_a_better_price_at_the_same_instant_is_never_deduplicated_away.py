"""Inside one window the later moment wins, and at one moment the better price does.

`dedupe_prices` keys on the quote plus its window, and kept whichever row
came LAST in the frame. That was safe only while one identity at one instant
could carry one price, and it cannot: `ALTERNATE_PROVIDER_KEYS` folds every
alternate ladder and the anytime scorer onto the featured market, line and
selection, so one book at one instant can quote the same identity twice at
two prices. Anytime scorer at +250 and goals over 0.5 at +210, at one book in
one response, collapsed onto whichever the payload listed last — here +210 —
and discarded a better price that was takeable at that instant. The
whole-row rebuild had kept both and `best_price_per_wager` took the +250.

And "last in the frame" was never "latest in time": an append of an earlier
fetch, or a cache read out of order, handed the collision to the older
moment.

The rule now, for every row sharing a quote identity and a window:

* the LATEST snapshot wins, whatever the order the rows arrive in, and
  whether its price is better or worse — the better of two moments is a
  price nobody held at one instant;
* among rows at that same snapshot, the BETTER price wins, because both were
  on the board at once.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.stores import dedupe_prices

COMMENCE = "2025-11-01T23:00:00Z"
FIRST = "2025-11-01T13:30:00Z"  # 9.5h out: `card`
SECOND = "2025-11-01T13:35:00Z"  # 9.4h out: `card`

GOAL = {
    "provider_event_id": "e1",
    "commence_time": COMMENCE,
    "market": "goals",
    "player": "Test Player",
    "selection": "over",
    "line": 0.5,
    "book": "DraftKings",
}


def _row(snapshot: str, odds: float, **extra) -> dict:
    return {**GOAL, "snapshot": snapshot, "american_odds": odds, **extra}


@pytest.mark.parametrize("order", ["anytime_first", "featured_first"])
def test_anytime_and_goals_over_half_at_one_instant_keep_the_better_price(
    order: str,
) -> None:
    anytime = _row(FIRST, 250.0, source="player_goal_scorer_anytime")
    featured = _row(FIRST, 210.0, source="player_goals")
    rows = [anytime, featured] if order == "anytime_first" else [featured, anytime]

    out = dedupe_prices(pd.DataFrame(rows))

    assert len(out) == 1
    assert out["american_odds"].tolist() == [250.0], (
        "both prices were on the board at once; dropping the better one "
        "discards a price that was takeable"
    )


def test_negative_prices_rank_by_payout_not_by_magnitude() -> None:
    out = dedupe_prices(pd.DataFrame([_row(FIRST, -105.0), _row(FIRST, -120.0)]))
    assert out["american_odds"].tolist() == [-105.0]

    out = dedupe_prices(pd.DataFrame([_row(FIRST, 120.0), _row(FIRST, -150.0)]))
    assert out["american_odds"].tolist() == [120.0]


@pytest.mark.parametrize("order", ["chronological", "reversed"])
def test_the_later_moment_wins_even_when_its_price_is_worse(order: str) -> None:
    earlier = _row(FIRST, -110.0)
    later = _row(SECOND, -115.0)
    rows = [earlier, later] if order == "chronological" else [later, earlier]

    out = dedupe_prices(pd.DataFrame(rows))

    assert len(out) == 1
    assert out["american_odds"].tolist() == [-115.0], (
        "the better of two moments is a price nobody held at one instant"
    )
    assert out["snapshot"].tolist() == [SECOND]


def test_the_later_moments_best_simultaneous_price_beats_a_better_earlier_one() -> None:
    frame = pd.DataFrame(
        [
            _row(SECOND, -105.0),
            _row(FIRST, 100.0),
            _row(SECOND, -120.0),
        ]
    )

    out = dedupe_prices(frame)

    assert out["american_odds"].tolist() == [-105.0]
    assert out["snapshot"].tolist() == [SECOND]


def test_two_spellings_of_one_instant_are_one_instant() -> None:
    frame = pd.DataFrame(
        [
            _row("2025-11-01T13:30:00+00:00", 250.0),
            _row(FIRST, 210.0),
        ]
    )

    out = dedupe_prices(frame)

    assert out["american_odds"].tolist() == [250.0]


def test_different_windows_are_still_never_collapsed() -> None:
    late = _row("2025-11-01T19:00:00Z", -130.0)
    card = _row(FIRST, 150.0)

    out = dedupe_prices(pd.DataFrame([late, card]))

    assert sorted(out["american_odds"]) == [-130.0, 150.0]


def test_rows_that_cannot_be_dated_are_not_treated_as_simultaneous() -> None:
    """Undated rows sort as one unknown moment; the last given is kept.

    Treating two undated rows as simultaneous would let the better of two
    unknown moments through, which is the defect this rule exists to stop.
    """
    frame = pd.DataFrame([_row("not a time", 250.0), _row("", 210.0)])

    out = dedupe_prices(frame)

    assert out["american_odds"].tolist() == [210.0]


def test_an_unpriced_row_never_beats_a_priced_one_at_the_same_instant() -> None:
    frame = pd.DataFrame([_row(FIRST, 210.0), _row(FIRST, float("nan"))])

    out = dedupe_prices(frame)

    assert out["american_odds"].tolist() == [210.0]


def test_a_frame_without_prices_is_refused() -> None:
    frame = pd.DataFrame([_row(FIRST, 250.0)]).drop(columns=["american_odds"])

    with pytest.raises(ValueError) as caught:
        dedupe_prices(frame)

    assert "american_odds" in str(caught.value)
