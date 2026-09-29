"""The ladder scan's count cannot depend on the order the provider listed rows.

The price normaliser folds a market's alternate ladder, and the anytime
scorer, onto the featured market's line and side, so at one book and one
capture a rung's over can carry two takeable prices. `_rungs_from` called the
second row a duplicate, counted it, and kept the FIRST. So which price bounded
the edge (`q_low`), and which over was de-vigged against the under, was the
provider's listing order.

Points 1.5 over +100 / under -110, 0.5 under -150, and the 0.5 over quoted at
-110 and at +120: with the -110 row first the scan found 0 violations, with the
+120 row first it found 1 ("marginal", edge +3.4 points). Same capture.

`stores.dedupe_prices` resolves the same collision to the better-paying price
(#244), and the detector now does too, per line and side. Nothing about the
registered test moves: no threshold, band, floor or unit. Found by sweep 5
(ladder-duplicate-rung-keeps-first-row, 2 of 2 verifiers).
"""

from __future__ import annotations

import itertools

import pandas as pd

from nhl_betting_lab.ladder_coherence import (
    _rungs_from,
    find_violations,
)

BASE = dict(
    provider_event_id="g", market="player_points", player="X Y", book="dk",
    snapshot="2026-10-11T20:00:00Z",
)
CORE = [
    dict(BASE, line=1.5, selection="over", american_odds=100),
    dict(BASE, line=1.5, selection="under", american_odds=-110),
    dict(BASE, line=0.5, selection="under", american_odds=-150),
]
FEATURED = dict(BASE, line=0.5, selection="over", american_odds=-110)
ALTERNATE = dict(BASE, line=0.5, selection="over", american_odds=120)


def test_either_order_of_a_duplicate_over_gives_the_same_violations() -> None:
    first, first_scan = find_violations(pd.DataFrame(CORE + [FEATURED, ALTERNATE]))
    second, second_scan = find_violations(pd.DataFrame(CORE + [ALTERNATE, FEATURED]))
    assert first_scan.violations == second_scan.violations == 1
    assert first_scan.duplicate_rows_collapsed == 1
    assert second_scan.duplicate_rows_collapsed == 1
    assert list(first["low_over_odds"]) == list(second["low_over_odds"]) == [120.0]


def test_the_better_paying_price_is_kept_on_each_side() -> None:
    """Per line and side: the over at +120 over -110, the under at -105 over -150."""
    for order in itertools.permutations(
        [FEATURED, ALTERNATE, dict(BASE, line=0.5, selection="under", american_odds=-105)]
    ):
        rungs, collapsed = _rungs_from(pd.DataFrame(CORE + list(order)))
        low = next(rung for rung in rungs if rung.line == 0.5)
        assert low.over_odds == 120, order
        assert low.under_odds == -105, order
        assert collapsed == 2


def test_a_negative_price_is_not_ranked_by_magnitude() -> None:
    """-105 pays more than -200, though -200 is the larger number in size."""
    for order in ([-200, -105], [-105, -200]):
        frame = pd.DataFrame(
            [dict(BASE, line=0.5, selection="over", american_odds=odds) for odds in order]
        )
        rungs, _ = _rungs_from(frame)
        assert rungs[0].over_odds == -105


def test_an_unreadable_price_never_displaces_a_real_one() -> None:
    for order in (["n/a", 150], [150, "n/a"], [float("nan"), 150], [150, float("nan")]):
        frame = pd.DataFrame(
            [dict(BASE, line=0.5, selection="over", american_odds=odds) for odds in order]
        )
        rungs, _ = _rungs_from(frame)
        assert rungs[0].over_odds == 150, order

