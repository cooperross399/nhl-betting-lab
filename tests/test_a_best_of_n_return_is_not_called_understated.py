"""A return taken at the best of N books is not an understated one.

Both generated reports carried a standing note that the prop measurement errs
in the conservative direction: `what_we_can_claim.md` said "every measured
prop edge here is understated rather than overstated", and
`player_props_backtest.md` said the one-sided vig "**understates** every edge
below — the measurement is conservative in that one direction".

The vig point is true of the edge used to *select* a bet (it is computed
against the price as sold, vig included). It says nothing about the return
the reports then print, and that return leans the other way: the backtest
collapses every book's quote on a wager to one bet at the BEST price across
the books quoting it (`run_backtest`, "ONE WAGER IS ONE BET"), and its own
comment calls that optimistically biased, because the best price is
disproportionately the stale one about to move. The honest bracket recorded
in `docs/where_the_remaining_error_lives.md` runs from about -1.6% (every
quote at its average price) to -0.34% (perfect shopping). A document that
calls the top of that bracket "understated" tells a reader the truth is
better than the number, when it is likelier worse.

What these tests hold, on the text each generator actually writes: neither
report says the measurement is understated or conservative, and each says
the return is taken at the best of the books quoting and leans optimistic.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nhl_betting_lab.reports import player_props_backtest as bt
from nhl_betting_lab.reports import what_we_can_claim as claims


def _backtest_text() -> str:
    report = bt.run_backtest(
        pd.DataFrame(columns=["market"]), pd.DataFrame(columns=["market"])
    )
    return bt.render_backtest(report)


def _claims_text(tmp_path: Path) -> str:
    return claims.render_claims(claims.build_claims_report(output_dir=tmp_path))


def test_the_claims_document_does_not_call_the_prop_return_understated(
    tmp_path: Path,
) -> None:
    text = _claims_text(tmp_path)

    assert "understated rather than overstated" not in text
    assert "understated" not in text.lower()


def test_the_claims_document_says_the_return_is_best_of_n_and_optimistic(
    tmp_path: Path,
) -> None:
    text = _claims_text(tmp_path)

    assert "best price across the books quoting it" in text
    assert "leans optimistic" in text


def test_the_backtest_does_not_call_its_measurement_conservative() -> None:
    text = _backtest_text()

    assert "understates** every edge below" not in text
    assert "conservative in that one direction" not in text


def test_the_backtest_says_its_return_is_best_of_n_and_optimistic() -> None:
    text = _backtest_text()

    assert "best price across the books quoting it" in text
    assert "leans optimistic" in text
    # The vig fact survives, scoped to what it is true of: the selection
    # threshold, not the printed return.
    assert "selection" in text and "vig" in text


def test_the_backtest_module_docstring_no_longer_calls_it_conservative() -> None:
    doc = bt.__doc__ or ""

    assert "conservative in that" not in doc
    assert "best price" in doc
