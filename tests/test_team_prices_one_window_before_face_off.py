"""The team measurement took the best price per wager across two windows and across face-off.

`stores.label_phases` says in its own docstring what happens without a window:
"the best-price collapse takes the better of a card-time quote and a closing
quote for one wager, which inflates every measured edge by an amount nobody can
see." The props backtest refuses a mixed store for exactly that reason. The team
measurement never called `label_phases` at all.

Measured on the bought team store, 308,944 rows:

* It holds two windows — `late` (inside six hours) and `early` (fifteen hours or
  more) — and 7,410 of 24,726 team wagers are quoted in both. The collapse took
  whichever paid more.
* **34,196 rows were captured at or after face-off**: 21,434 at exactly the
  start, 12,692 inside the first three hours, 70 later. `label_phases` files
  them under `late`, because a negative number of hours is fewer than six.

A flat-stake loss costs one unit whatever the price, so taking the maximum
payout across time only ever inflates the winners. Published, the three team
markets read moneyline +0.0% over 1,366, puck line -1.3% over 1,762, totals
-2.5% over 2,201. In the `late` window, strictly before face-off: -6.6% over
954, -4.2% over 1,117, -4.0% over 1,216. Every interval still spans zero, so no
verdict moved; every point estimate did, and all in the same direction.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.reports.team_markets_measurement import (
    MixedWindowError,
    build_team_measurement,
    select_price_window,
)

FACE_OFF = "2025-01-10T00:00:00Z"


def _quote(hours_before: float, *, odds: int = 150, selection: str = "home") -> dict:
    """One moneyline quote, captured `hours_before` the face-off."""
    snapshot = pd.Timestamp(FACE_OFF) - pd.Timedelta(hours=hours_before)
    return {
        "date": "2025-01-09",
        "commence_time": FACE_OFF,
        "snapshot": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "market": "moneyline",
        "selection": selection,
        "line": None,
        "american_odds": odds,
        "book": "draftkings",
    }


def _store(*quotes: dict) -> pd.DataFrame:
    return pd.DataFrame(list(quotes))


# --------------------------------------------------------------------------
# Face-off.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("hours_before", [0.0, -0.5, -2.9, -622.65])
def test_a_price_captured_at_or_after_face_off_is_never_measured(hours_before):
    """Including exactly at the start: the closing rule this lab uses for CLV is
    'the last price captured strictly before the face-off'.

    -622.65 is the real store's worst row, twenty-six days after its game.
    """
    kept, info = select_price_window(_store(_quote(hours_before)), "all")
    assert kept.empty
    assert info["excluded_after_face_off"] == 1


def test_post_start_rows_are_excluded_even_when_the_mixture_is_asked_for():
    """`all` is the mixture of pre-face-off windows, not an in-play escape hatch."""
    kept, info = select_price_window(
        _store(_quote(2.0), _quote(-1.0), _quote(20.0)), "all"
    )
    assert len(kept) == 2
    assert info["excluded_after_face_off"] == 1


def test_an_in_play_long_price_can_no_longer_become_the_best_price():
    """The mechanism, end to end through the collapse the measurement runs.

    A +900 captured mid-game on a team that was losing used to win the
    best-price collapse against the +150 a card could actually have taken.
    """
    store = _store(_quote(2.0, odds=150), _quote(-1.5, odds=900))
    kept, _ = select_price_window(store, "late")
    assert list(kept["american_odds"]) == [150]


# --------------------------------------------------------------------------
# One window.
# --------------------------------------------------------------------------

def test_auto_refuses_a_store_holding_two_windows():
    """Refuses rather than choosing. The props backtest's first version of this
    guard hardcoded a window, matched nothing, and measured the mixture it was
    written to prevent."""
    with pytest.raises(MixedWindowError, match="more than one window"):
        select_price_window(_store(_quote(2.0), _quote(20.0)), "auto")


def test_auto_counts_only_pre_face_off_windows():
    """A store with one real window plus post-start rows is ONE window.

    If post-start rows counted as a window of their own, auto would refuse the
    ordinary case; if they were folded into `late`, auto would pass the mixture.
    """
    kept, info = select_price_window(_store(_quote(2.0), _quote(-1.0)), "auto")
    assert info["phase"] == "late"
    assert len(kept) == 1


@pytest.mark.parametrize("window,expected_hours", [("late", 2.0), ("early", 20.0)])
def test_a_named_window_keeps_only_that_window(window, expected_hours):
    kept, info = select_price_window(
        _store(_quote(2.0, odds=120), _quote(20.0, odds=180)), window
    )
    assert len(kept) == 1
    assert info["phase"] == window
    assert info["phase_hours"] == pytest.approx(expected_hours)
    assert info["excluded_other_windows"] == 1


def test_a_named_window_that_matches_nothing_measures_nothing():
    """Not everything. The props guard used to fall through here and measure the
    whole mixture under no label."""
    kept, info = select_price_window(_store(_quote(2.0), _quote(20.0)), "card")
    assert kept.empty
    assert info["phase"] == "card"


def test_the_better_of_two_windows_is_not_taken_for_one_wager():
    """The original defect: best price per wager across windows."""
    store = _store(_quote(2.0, odds=140), _quote(20.0, odds=175))
    late, _ = select_price_window(store, "late")
    early, _ = select_price_window(store, "early")
    assert list(late["american_odds"]) == [140]
    assert list(early["american_odds"]) == [175]


# --------------------------------------------------------------------------
# No window information at all.
# --------------------------------------------------------------------------

def test_a_frame_with_no_timestamps_is_measured_as_it_is_and_says_so():
    """The props backtest's rule for the same case, kept identical.

    There is nothing to choose between and no face-off to be after. The bought
    team store always carries both columns; test fixtures often do not.
    """
    frame = _store(_quote(2.0)).drop(columns=["commence_time", "snapshot"])
    kept, info = select_price_window(frame, "auto")
    assert len(kept) == 1
    assert info["no_window_information"] is True


def test_rows_with_unreadable_timestamps_in_a_timed_store_are_excluded():
    """Different from the no-timestamps case: the store HAS window information,
    this row just cannot be placed in it, so it is not guessed into one."""
    bad = _quote(2.0)
    bad["snapshot"] = "not a time"
    kept, info = select_price_window(_store(_quote(2.0), bad), "late")
    assert len(kept) == 1
    assert info["excluded_unknown"] == 1


# --------------------------------------------------------------------------
# Through the report.
# --------------------------------------------------------------------------

def _samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": 1,
                "date": "2025-01-09",
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "model_probability": 0.62,
                "outcome": True,
                "push": False,
            }
        ]
    )


#: Keyed the way `load_team_name_map` keys it: `resolve_team` looks up the
#: NORMALIZED name. This used to read {"Toronto Maple Leafs": "TOR", ...}, which
#: resolves nothing, so the report below measured zero bets without saying so.
#: The unresolved-teams guard is what found it.
TEAM_NAMES = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}


def test_the_report_refuses_a_mixed_store_by_default():
    with pytest.raises(MixedWindowError):
        build_team_measurement(
            _samples(), _store(_quote(2.0), _quote(20.0)),
            team_names=TEAM_NAMES,
        )


def test_the_report_records_the_window_and_what_it_set_aside():
    report = build_team_measurement(
        _samples(), _store(_quote(2.0), _quote(20.0), _quote(-1.0)),
        team_names=TEAM_NAMES,
        phase="late",
    )
    assert report.phase == "late"
    assert report.excluded_after_face_off == 1
    assert report.priced_outcomes == 1
    joined = " ".join(report.notes)
    assert "after face-off were excluded" in joined
    assert "other windows were excluded" in joined
