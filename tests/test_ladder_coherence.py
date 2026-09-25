"""Each test here kills one specific way the scan could be wrong.

The shared fixture temptation is strong for ladders — one table that has a
violation, two books, a duplicate row and a one-sided rung all at once would
satisfy every assertion below. It would also mean no test identified which
defect it caught, which is how four vacuous tests landed in this repository
in a single day. So each case builds the smallest table that isolates it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.ladder_coherence import (
    DETECTION_FLOOR,
    _rungs_from,
    LADDER_KEY,
    LADDER_CLASSES,
    LADDER_CLASS_UNITS,
    Rung,
    find_violations,
    class_for,
    violations_in_ladder,
)


def rows(*specs: tuple) -> pd.DataFrame:
    """A price table. Every identity column is filled unless overridden."""
    built = []
    for spec in specs:
        line, side, odds = spec[:3]
        overrides = spec[3] if len(spec) > 3 else {}
        built.append(
            {
                "provider_event_id": "evt-1",
                "market": "shots_on_goal",
                "player": "A Player",
                "book": "BookOne",
                "snapshot": "2026-10-01T18:00:00Z",
                "line": line,
                "selection": side,
                "american_odds": odds,
                **overrides,
            }
        )
    return pd.DataFrame(built)


# --- the arithmetic -------------------------------------------------------


def test_a_coherent_ladder_yields_nothing() -> None:
    """The easier threshold is priced as the likelier one. Nothing to say."""
    found, scan = find_violations(
        rows(
            (2.5, "over", -110), (2.5, "under", -110),
            (3.5, "over", +200), (3.5, "under", -260),
        )
    )
    assert found.empty
    assert scan.violations == 0
    # The denominator still has to be real, or "no violations" is vacuous.
    assert scan.comparable_pairs == 1


def test_the_edge_is_the_higher_rungs_fair_price_minus_the_lower_rungs_cost() -> None:
    """over 3.5 de-vigs to 0.50; over 2.5 is sold at +200, i.e. 0.3333."""
    found, _ = find_violations(
        rows(
            (2.5, "over", +200),
            (3.5, "over", -110), (3.5, "under", -110),
        )
    )
    assert len(found) == 1
    row = found.iloc[0]
    assert row["p_high_devigged"] == pytest.approx(0.5, abs=1e-9)
    assert row["q_low_implied"] == pytest.approx(1 / 3, abs=1e-9)
    assert row["edge"] == pytest.approx(1 / 6, abs=1e-9)
    assert row["ladder_class"] == "wide"


def test_the_bound_comes_from_the_higher_rung_not_the_lower_one() -> None:
    """Swapping which rung is de-viggable is not a symmetric change.

    The containment argument only runs one way: the HIGHER rung's fair price
    bounds the lower rung's true probability from below. A de-viggable low
    rung and a one-sided high rung proves nothing, and must not be reported
    as though the inequality ran the other way.
    """
    found, scan = find_violations(
        rows(
            (2.5, "over", +200), (2.5, "under", -260),
            (3.5, "over", -110),
        )
    )
    assert found.empty
    assert scan.comparable_pairs == 0


# --- what may never be compared ------------------------------------------


def test_two_books_are_never_compared() -> None:
    """Cross-book is the line-shopping hypothesis, and it is already dead."""
    found, scan = find_violations(
        rows(
            (2.5, "over", +200),
            (3.5, "over", -110, {"book": "BookTwo"}),
            (3.5, "under", -110, {"book": "BookTwo"}),
        )
    )
    assert found.empty
    assert scan.ladders == 2
    assert scan.comparable_pairs == 0


def test_two_moments_are_never_compared() -> None:
    """A book changing its mind between snapshots is not a contradiction."""
    later = {"snapshot": "2026-10-01T22:00:00Z"}
    found, scan = find_violations(
        rows(
            (2.5, "over", +200),
            (3.5, "over", -110, later), (3.5, "under", -110, later),
        )
    )
    assert found.empty
    assert scan.ladders == 2


def test_a_missing_identity_column_raises_rather_than_regrouping() -> None:
    """Dropping 'book' would silently turn every scan into cross-book."""
    frame = rows((2.5, "over", +200)).drop(columns=["book"])
    with pytest.raises(ValueError, match="book"):
        find_violations(frame)


# --- the artifact that produced most historical 'violations' --------------


def test_a_duplicate_row_is_collapsed_and_counted_not_treated_as_a_step() -> None:
    """Two rows at one line are a duplicate, not a zero-width rung.

    In the two-season store these were the single largest source of apparent
    violations, and a scan that treats them as a ladder step reports a
    contradiction where the book said one thing once.
    """
    found, scan = find_violations(
        rows((2.5, "over", +200), (2.5, "over", -110))
    )
    assert scan.duplicate_rows_collapsed == 1
    assert found.empty
    # One distinct line is not a ladder: neither two lines nor two
    # de-viggable rungs. (`ladders_with_two_rungs` now counts de-viggable
    # depth only, which one line can never have, so the line count is what
    # holds this comment.)
    assert scan.ladders_with_two_lines == 0
    assert scan.ladders_with_two_rungs == 0


def test_a_duplicate_is_counted_even_when_its_ladder_is_never_visited() -> None:
    """The fast path skips single-line ladders; the count must not skip too.

    This is the regression for the optimisation: pre-filtering to ladders
    with two or more distinct lines made the duplicate tally silently zero
    for every group it filtered out, and nothing else in this file noticed.
    """
    found, scan = find_violations(
        rows(
            (2.5, "over", +200), (2.5, "over", -110),   # duplicate, one line
            (1.5, "over", -300, {"player": "B Player"}),  # a second, clean
        )
    )
    assert found.empty
    assert scan.ladders_with_two_lines == 0, "neither group is a ladder"
    assert scan.ladders_with_two_rungs == 0, "neither group is a ladder"
    assert scan.duplicate_rows_collapsed == 1


def test_the_two_duplicate_counts_agree() -> None:
    """The whole-table tally must equal the sum of the per-ladder ones."""
    frame = rows(
        (2.5, "over", +200), (2.5, "over", -110),
        (3.5, "over", -110), (3.5, "under", -110), (3.5, "under", +100),
    )
    _, scan = find_violations(frame)
    per_ladder = sum(
        _rungs_from(group)[1]
        for _, group in frame.groupby(list(LADDER_KEY), dropna=False)
    )
    assert scan.duplicate_rows_collapsed == per_ladder == 2


# --- coverage of the comparison itself ------------------------------------


def test_a_ladder_coherent_step_by_step_can_still_contradict_itself() -> None:
    """Adjacent-only comparison misses this; every-pair comparison finds it."""
    ladder = [
        Rung(2.5, over_odds=+200, under_odds=-260),   # fair ~0.3333
        Rung(3.5, over_odds=+150, under_odds=-190),   # fair ~0.3968
        Rung(4.5, over_odds=+120, under_odds=-155),   # fair ~0.4412
    ]
    hits = violations_in_ladder(ladder)
    spans = {(hit["low_line"], hit["high_line"]) for hit in hits}
    assert (2.5, 4.5) in spans, "the end-to-end contradiction must be found"


def test_one_wager_is_reported_once_at_its_largest_edge() -> None:
    """Two higher rungs bounding the same bet is still one bet.

    The 4.5 rung is priced so that it contradicts 2.5 *more* than 3.5 does
    and does not contradict 3.5 at all. Without that second condition the
    table carries two genuine wagers and the test passes for the wrong
    reason — which is what the first draft of it did.
    """
    found, _ = find_violations(
        rows(
            (2.5, "over", +200),                      # sold at 0.3333
            (3.5, "over", -110), (3.5, "under", -110),  # fair 0.5000
            (4.5, "over", -115), (4.5, "under", -105),  # fair 0.5108
        )
    )
    assert len(found) == 1, "one bet per wager, however many rungs bound it"
    row = found.iloc[0]
    assert row["low_line"] == 2.5
    assert row["high_line"] == 4.5, "the binding rung is the strongest one"
    assert row["edge"] == pytest.approx(0.5108 - 1 / 3, abs=1e-3)


# --- the tier table -------------------------------------------------------


@pytest.mark.parametrize(
    "edge,expected",
    [
        (0.0199, None),
        (0.02, "marginal"),
        (0.0399, "marginal"),
        (0.04, "clear"),
        (0.0799, "clear"),
        (0.08, "wide"),
        (1.0, "wide"),
    ],
)
def test_the_band_boundaries_are_inclusive_at_the_threshold(
    edge: float, expected: str | None
) -> None:
    assert class_for(edge) == expected


def test_nothing_below_the_floor_is_flagged() -> None:
    found, scan = find_violations(
        rows(
            (2.5, "over", +101),
            (3.5, "over", -102), (3.5, "under", +100),
        )
    )
    assert scan.comparable_pairs == 1
    assert found.empty, "a sub-floor gap is a vig asymmetry, not a finding"


def test_the_floor_is_read_from_the_band_table_not_repeated() -> None:
    """Two copies of 2% could drift apart; only one of them is authoritative."""
    assert DETECTION_FLOOR == LADDER_CLASSES[-1][1]


def test_every_band_can_be_staked_and_none_outside_the_table_can() -> None:
    assert set(LADDER_CLASS_UNITS) == {name for name, _ in LADDER_CLASSES}
    assert all(units > 0 for units in LADDER_CLASS_UNITS.values())


# --- the report -----------------------------------------------------------


def test_an_empty_scan_says_so_rather_than_reporting_a_clean_market() -> None:
    found, scan = find_violations(
        pd.DataFrame(columns=[*LADDER_KEY, "line", "selection", "american_odds"])
    )
    assert found.empty
    assert "absence" in scan.summary_line()


def test_the_summary_carries_the_denominator() -> None:
    _, scan = find_violations(
        rows(
            (2.5, "over", +200),
            (3.5, "over", -110), (3.5, "under", -110),
        )
    )
    line = scan.summary_line()
    assert "1 violation" in line
    assert "1 comparable rung pair" in line
