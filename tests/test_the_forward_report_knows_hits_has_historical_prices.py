"""The forward report no longer says hits has no historical prices.

`render_forward_report` opened every forward_evidence.md with "This is the
only possible price evidence for the markets no book retains historically —
hits and the regulation three-way", and the module docstring said the same.
That was true until the 9.5-hour card-window purchase asked both regions and
came back with hits from the two books that quote it: 5,178 settled wagers at
-1.3%, 95% interval -4.0% to +1.4% — no demonstrated edge, and real price
evidence. The published report kept telling readers the forward stream was
the only evidence hits would ever have, which is the report contradicting
the backtest it sits next to.

The regulation three-way is still true to the sentence: it is per-event only
and has never been bought historically (it was never requested, so whether a
book retains it is unasked, not known to be "no"), so the forward ledger
remains its only possible price evidence — and the sentence must say "never
bought", not "no book retains", or it repeats the unasked-probe mistake the
hits correction undoes. The fix removes hits from the claim and keeps the
three-way in it; these tests pin both halves, on an empty ledger (the report
a fresh season publishes) and on a ledger with a settled row, and hold the
module docstring and the maintained status doc to the same statement.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.models.value import american_to_implied, profit_on_win


NOW = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
REPO = Path(__file__).resolve().parents[1]

#: Wording that says a market has no historical price evidence, or that the
#: forward stream is the only evidence it has. None may share a sentence
#: with "hits".
NO_PRICES = (
    "no book retains",
    "never been bought",
    "no historical price",
    "only possible price evidence",
    "only price evidence",
    "will ever have",
)


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)
    return [s for s in re.split(r"(?<=[.!?])\s", flat) if s]


def _hits_claims(text: str) -> list[str]:
    return [
        s for s in _sentences(text)
        if re.search(r"\bhits\b", s, re.IGNORECASE)
        and any(p in s.lower() for p in NO_PRICES)
    ]


def _three_way_claims(text: str) -> list[str]:
    return [
        s for s in _sentences(text)
        if "regulation three-way" in s
        and any(p in s.lower() for p in NO_PRICES)
    ]


def _settled_row() -> dict:
    odds, p = 120, 0.62
    return {
        "snapshot_date": "2026-10-08", "commence_time": "2026-10-09T00:10:00Z",
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "market": "hits", "player": "Auston Matthews", "selection": "over",
        "line": 1.5, "american_odds": float(odds), "book": "espnbet",
        "model_probability": p, "edge": p - american_to_implied(odds),
        "verdicts_in_force": "x", "settled_at": "2026-10-10T12:00:00+00:00",
        "outcome": "won", "actual": 3.0,
        "profit_units": profit_on_win(float(odds)),
    }


@pytest.fixture(params=["empty", "one settled hits row"])
def rendered(request) -> str:
    rows = [] if request.param == "empty" else [_settled_row()]
    ledger = pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))
    return fe.render_forward_report(fe.build_forward_report(ledger, now=NOW))


def test_the_report_never_says_hits_lacks_historical_prices(rendered) -> None:
    assert _hits_claims(rendered) == []


def test_the_report_still_names_the_three_way_as_forward_only(rendered) -> None:
    claims = _three_way_claims(rendered)
    assert claims, "the three-way lost its forward-only statement"
    assert all("only" in s for s in claims), claims
    # Non-retention was never asked, so it must not be asserted.
    assert not any("no book retains" in s for s in claims), claims


def test_the_module_docstring_says_the_same() -> None:
    assert _hits_claims(fe.__doc__) == []
    claims = _three_way_claims(fe.__doc__)
    assert claims
    assert not any("no book retains" in s for s in claims), claims


def test_the_status_doc_says_the_same() -> None:
    text = (REPO / "docs" / "project_status_for_claude.md").read_text()
    assert _hits_claims(text) == []
    claims = _three_way_claims(text)
    assert claims
    assert not any("no book retains" in s for s in claims), claims


def test_the_settle_step_comment_says_the_same() -> None:
    """The gameday workflow's settle step explains why the ledger matters;
    its comment carried the same stale claim."""
    raw = (REPO / ".github" / "workflows" / "gameday-refresh.yml").read_text()
    text = "\n".join(
        line.strip().lstrip("#").strip()
        for line in raw.splitlines() if line.strip().startswith("#")
    )
    assert _hits_claims(text) == []
    claims = _three_way_claims(text)
    assert claims
    assert not any("no book retains" in s for s in claims), claims
