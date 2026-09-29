"""The claims document's pooled prop line read the UNCORRECTED interval.

The props backtest measures its overall figure as one look in a family of
its markets plus that figure (`looks = markets + 1`), and its verdict for it
reads the Bonferroni interval. `build_claims_report` copied only
`overall.includes_zero` — the naive 95% interval — and `render_claims`
printed "The interval excludes zero on this sample." whenever that missed
zero. With -2.5% over 10,000 bets at seven looks (naive about -4.4% to
-0.7%, corrected about -5.1% to +0.0%) the headline prop line said the
interval excludes zero while the backtest's own verdict for the same number,
and the per-market line for the same interval in the same document, said
**no demonstrated edge**.

The pooled line now reads the correction the way `MarketClaim.sentence`
does, including the under-thirty-bets branch.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhl_betting_lab.reports.what_we_can_claim import (
    build_claims_report,
    render_claims,
)
from nhl_betting_lab.stats import roi_interval

FAMILY = "6 markets and the overall figure"
HEADING = "## Across every measured prop market"


def _interval(wins: int, bets: int, *, looks: int = 7):
    returns = [0.909] * wins + [-1.0] * (bets - wins)
    return roi_interval(returns, wins=wins, looks=looks, family=FAMILY)


def _entry(iv) -> dict:
    """What `player_props_backtest._interval_payload` writes."""
    return {
        "bets": iv.bets, "profit": iv.profit, "roi": iv.roi, "low": iv.low,
        "high": iv.high, "includes_zero": iv.includes_zero, "looks": iv.looks,
        "family": iv.family, "adjusted_low": iv.adjusted_low,
        "adjusted_high": iv.adjusted_high,
        "survives_correction": iv.survives_correction, "verdict": iv.verdict(),
    }


def _pooled(tmp_path: Path, iv) -> tuple[str, str]:
    entry = _entry(iv)
    payload = {
        "phase": "late", "phase_hours": 4.1, "rows_read": 50_000,
        "bets": iv.bets, "overall": entry, "looks": iv.looks, "family": FAMILY,
        "by_market": {"shots_on_goal": entry},
    }
    (tmp_path / "player_props_backtest.json").write_text(json.dumps(payload))
    text = render_claims(build_claims_report(output_dir=tmp_path))
    section = text.split(HEADING, 1)[1].split("\n## ", 1)[0].strip()
    market = next(
        line for line in text.splitlines() if line.startswith("- `shots_on_goal`")
    )
    return section, market


def _first(predicate):
    for wins in range(4_500, 5_300):
        iv = _interval(wins, 10_000)
        if predicate(iv):
            return iv
    raise AssertionError("no interval of that shape in the search range")


def test_naive_excludes_zero_corrected_does_not_is_no_demonstrated_edge(
    tmp_path: Path,
) -> None:
    iv = _first(lambda iv: not iv.includes_zero and not iv.survives_correction)
    assert iv.roi < 0 and "no demonstrated edge" in iv.verdict()

    section, market = _pooled(tmp_path, iv)

    assert "The interval excludes zero on this sample." not in section, (
        "the pooled line read the naive interval; the backtest's verdict for "
        "the same figure is no demonstrated edge"
    )
    assert "**No demonstrated edge**" in section or "**no demonstrated edge**" in section
    # It names the correction it read, in the family the backtest counted,
    # with the corrected bounds, so the reader can see why.
    assert f"7 figures measured on the same data ({FAMILY})" in section
    assert f"{iv.adjusted_low:+.1%} to {iv.adjusted_high:+.1%}" in section
    # And agrees with the per-market line for the same interval.
    assert "no demonstrated edge" in market.lower()


def test_a_figure_that_survives_correction_says_so_and_no_more(
    tmp_path: Path,
) -> None:
    iv = _first(lambda iv: iv.survives_correction and iv.roi < 0)

    section, _ = _pooled(tmp_path, iv)

    assert "no demonstrated edge" not in section.lower()
    assert "excludes zero even after correcting for the" in section
    assert f"7 figures measured on the same data ({FAMILY})" in section
    # A loss is never announced as an edge.
    assert "an edge" not in section
    assert "a loss" in section


def test_a_naive_interval_spanning_zero_reads_exactly_as_before(
    tmp_path: Path,
) -> None:
    # The committed claims document is in this branch; its wording is pinned
    # by receipts, so it must not move.
    iv = _first(lambda iv: iv.includes_zero)

    section, _ = _pooled(tmp_path, iv)

    assert section.endswith(
        "bets in the `late` window, 4.1 hours before face-off. The interval "
        "includes zero: **no demonstrated edge**."
    ), section


def test_under_thirty_bets_is_far_too_few_whatever_the_interval(
    tmp_path: Path,
) -> None:
    # 22 wins and 3 losses at -110: the naive interval misses zero by a mile.
    iv = _interval(22, 25)
    assert not iv.includes_zero and not iv.survives_correction

    section, _ = _pooled(tmp_path, iv)

    assert "25 bets is far too few to measure anything" in section
    assert "no demonstrated edge" in section.lower()
    assert "excludes zero" not in section
    assert "does not exclude zero" not in section


def test_an_old_payload_without_the_correction_never_claims_exclusion(
    tmp_path: Path,
) -> None:
    # A payload written before the correction fields existed: absent means
    # not shown to survive, never "survives".
    iv = _first(lambda iv: iv.survives_correction and iv.roi < 0)
    entry = {
        key: value
        for key, value in _entry(iv).items()
        if key not in {"survives_correction", "adjusted_low", "adjusted_high"}
    }
    payload = {"phase": "late", "bets": iv.bets, "overall": entry,
               "by_market": {"shots_on_goal": entry}}
    (tmp_path / "player_props_backtest.json").write_text(json.dumps(payload))

    text = render_claims(build_claims_report(output_dir=tmp_path))
    section = text.split(HEADING, 1)[1].split("\n## ", 1)[0]

    assert "The interval excludes zero" not in section
    assert "even after correcting" not in section
    assert "not shown to survive correcting for the" in section
    assert "no demonstrated edge" in section.lower()
