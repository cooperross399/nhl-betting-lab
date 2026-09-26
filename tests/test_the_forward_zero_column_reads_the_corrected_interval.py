"""The forward report's "Includes zero" column read the interval nobody registered.

`docs/when_this_ends.md` registers the 2027-04-25 decision on the CORRECTED
interval — "corrected across the markets measured" — and its table reads
"Corrected interval spans zero ... Stop". `build_forward_report` computed
that interval (`roi_interval(..., looks=len(markets))`) and let only the
verdict sentence mention it: the payload's `low` / `high` /
`includes_zero` and the table's "95% interval" and "Includes zero" columns
were all the plain 95% interval. So a market could sit in the table as
"Includes zero: no" while its corrected interval spanned zero and its own
verdict line said **no demonstrated edge** — the column contradicting the
rule it sits beside. `forward_evidence.md` is published to card-feed every
day of the season.

What these tests hold, on a small ledger shaped as settlement writes it
(two markets, so the family is two looks; 100 even-money bets at 60-40 on
one, whose plain interval is about +0.7% .. +39.3% and whose Bonferroni
interval for two looks is about -2.1% .. +42.1%):

* the payload carries the corrected bounds and `survives_correction` from
  the same `RoiInterval` the verdict reads, and keeps the plain interval
  under its old keys;
* the rendered table labels which interval is which, and its zero column
  says "yes" for that market — the corrected interval spans zero — while
  a market that survives the correction still reads "no";
* with one market measured the correction is no correction, and the two
  intervals agree.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.models.value import american_to_implied, profit_on_win
from nhl_betting_lab.stats import bonferroni_z, roi_interval


NOW = datetime(2027, 1, 20, 15, 0, tzinfo=timezone.utc)
P = 0.62  # +100 implies 50%, so every row clears both edge bars
ODDS = 100.0


def _row(market: str, index: int, won: bool) -> dict:
    """One wager, one book, its own player so no two rows collapse."""
    return {
        "snapshot_date": "2026-12-01", "commence_time": "2026-12-02T00:10:00Z",
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "market": market, "player": f"Player {market} {index}",
        "selection": "over", "line": 0.5, "american_odds": ODDS,
        "book": "DraftKings", "model_probability": P,
        "edge": P - american_to_implied(ODDS), "verdicts_in_force": "x",
        "settled_at": "2026-12-03T12:00:00+00:00",
        "outcome": "won" if won else "lost", "actual": 1.0 if won else 0.0,
        "profit_units": profit_on_win(ODDS) if won else -1.0,
    }


def _market(market: str, wins: int, losses: int) -> list[dict]:
    return ([_row(market, i, True) for i in range(wins)]
            + [_row(market, wins + i, False) for i in range(losses)])


def _ledger(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))


#: Plain interval excludes zero; corrected for two looks it spans zero.
BORDERLINE = ("shots_on_goal", 60, 40)
#: Survives the correction: excludes zero both ways.
STRONG = ("points", 64, 36)


def _table_row(rendered: str, market: str) -> list[str]:
    for line in rendered.splitlines():
        if line.startswith(f"| `{market}` |"):
            return [cell.strip() for cell in line.strip("|").split("|")]
    raise AssertionError(f"no table row for {market}")


def _header(rendered: str) -> list[str]:
    for line in rendered.splitlines():
        if line.startswith("| Market |"):
            return [cell.strip() for cell in line.strip("|").split("|")]
    raise AssertionError("no table header")


def test_the_fixture_is_the_case_that_matters() -> None:
    """Guard the fixture: plain excludes zero, corrected spans it."""
    _, wins, losses = BORDERLINE
    interval = roi_interval([1.0] * wins + [-1.0] * losses, wins=wins, looks=2)
    assert not interval.includes_zero
    assert interval.adjusted_low <= 0.0 <= interval.adjusted_high
    assert not interval.survives_correction
    _, wins, losses = STRONG
    strong = roi_interval([1.0] * wins + [-1.0] * losses, wins=wins, looks=2)
    assert strong.survives_correction


def test_the_payload_carries_the_corrected_interval() -> None:
    payload = fe.build_forward_report(
        _ledger(_market(*BORDERLINE) + _market(*STRONG)), now=NOW
    )
    entry = payload["markets"]["shots_on_goal"]

    # The plain interval keeps its keys, unchanged.
    assert entry["low"] > 0.0 and entry["includes_zero"] is False
    # The corrected one is the Bonferroni interval for the two markets.
    width = entry["adjusted_high"] - entry["adjusted_low"]
    plain = entry["high"] - entry["low"]
    assert width / plain == pytest.approx(bonferroni_z(2) / bonferroni_z(1))
    assert entry["adjusted_low"] < 0.0 < entry["adjusted_high"]
    assert entry["survives_correction"] is False
    assert entry["looks"] == 2

    strong = payload["markets"]["points"]
    assert strong["adjusted_low"] > 0.0
    assert strong["survives_correction"] is True


def test_the_zero_column_reads_the_corrected_interval() -> None:
    payload = fe.build_forward_report(
        _ledger(_market(*BORDERLINE) + _market(*STRONG)), now=NOW
    )
    rendered = fe.render_forward_report(payload)
    header = _header(rendered)
    entry = payload["markets"]["shots_on_goal"]

    zero = header.index("Corrected includes zero")
    plain = header.index("95% interval, uncorrected")
    corrected = header.index("Corrected interval")
    assert "Includes zero" not in header, (
        "an unlabelled zero column is the one that read the plain interval"
    )

    row = _table_row(rendered, "shots_on_goal")
    assert row[zero] == "yes", (
        "the corrected interval spans zero; the registered rule reads it"
    )
    assert row[plain] == f"{entry['low']:+.1%} .. {entry['high']:+.1%}"
    assert row[corrected] == (
        f"{entry['adjusted_low']:+.1%} .. {entry['adjusted_high']:+.1%}"
    )
    # The verdict beside it says the same thing the column now does.
    assert "no demonstrated edge" in entry["verdict"]

    assert _table_row(rendered, "points")[zero] == "no"
    # The page says what the correction counted, beside the table (the
    # verdict lines state it too, so this reads the table's own sentence).
    assert (
        "widened (Bonferroni) for the 2 markets measured on the same data"
        in rendered
    )


def test_one_market_is_no_correction() -> None:
    payload = fe.build_forward_report(_ledger(_market(*BORDERLINE)), now=NOW)
    entry = payload["markets"]["shots_on_goal"]

    assert entry["looks"] == 1
    assert entry["adjusted_low"] == entry["low"]
    assert entry["adjusted_high"] == entry["high"]
    assert entry["survives_correction"] is True

    rendered = fe.render_forward_report(payload)
    zero = _header(rendered).index("Corrected includes zero")
    assert _table_row(rendered, "shots_on_goal")[zero] == "no"
