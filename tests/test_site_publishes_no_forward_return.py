"""The public site may publish accuracy. It may not publish the return.

`docs/when_this_ends.md` registers one measurement, decided on 2027-04-25:
the forward ledger's pooled return. A pre-registered test whose running
total is on a public page every morning is a test someone is watching, and
the registration's own instruction for a strong mid-season result is that
"the correct action is **nothing**". Publishing the number daily makes that
instruction impossible to follow.

So `web/build_site_json.py::load_record` reports how far the experiment has
got — rows, markets, span of dates — and never how it is going. These tests
hold that line, because it is one comment away from quietly moving.

Straight-up, puck-line and totals win/loss records are a different thing.
They are forecast accuracy, not the registered wager return, and the site
publishes them live.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "web" / "build_site_json.py"

#: Keys that would each be a published return. `bets` is not here: a count
#: of wagers is a size, not a result.
THE_RETURN = ("roi", "low", "high", "clv", "profit_units", "includes_zero")


def _module():
    spec = importlib.util.spec_from_file_location("bsj", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Shaped exactly as `forward_evidence.build_forward_report` writes it — per
#: market, with roi/low/high, and no pooled figure anywhere. The site's first
#: version read `overall.roi`, which does not exist, so it would have shown a
#: zeroed record all season while looking like it was reporting one.
MID_SEASON = {
    "generated_at": "2026-12-14T12:00:00+00:00",
    "rows": 4120,
    "unsettleable": 7,
    "void": 31,
    "markets": {
        "shots_on_goal": {
            "opinions": 2600, "first_date": "2026-09-29",
            "last_date": "2026-12-13", "bets": 900, "roi": 0.061,
            "low": -0.004, "high": 0.126, "includes_zero": True,
            "verdict": "no demonstrated edge",
        },
        "points": {
            "opinions": 1520, "first_date": "2026-09-30",
            "last_date": "2026-12-13", "bets": 410, "roi": -0.022,
            "low": -0.09, "high": 0.046, "includes_zero": True,
            "verdict": "no demonstrated edge",
        },
    },
}


def _record(payload: object, tmp_path: Path) -> dict:
    target = tmp_path / "forward_evidence.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return _module().load_record(target)


def test_a_mid_season_ledger_publishes_no_return(tmp_path: Path) -> None:
    """The one that matters. A +6.1% market must not reach the page."""
    published = json.dumps(_record(MID_SEASON, tmp_path))
    for key in THE_RETURN:
        assert key not in published, (
            f"{key!r} reached the published record. The forward return is "
            "decided on 2027-04-25 and is not published before then."
        )
    assert "0.061" not in published and "6.1" not in published


def test_the_size_of_the_ledger_is_published(tmp_path: Path) -> None:
    """Sealing the return must not turn into saying nothing at all.

    A page that shows a blank where the evidence goes invites the reader to
    assume there is none. There is; it is simply not being scored yet.
    """
    forward = _record(MID_SEASON, tmp_path)["forward"]
    assert forward["sealed"] is True
    assert forward["rows"] == 4120
    assert forward["markets"] == 2
    assert forward["firstDate"] == "2026-09-29"
    assert forward["lastDate"] == "2026-12-13"
    assert forward["decisionDate"] == "2027-04-25"


def test_the_decision_date_matches_the_registration() -> None:
    """Two copies of the date could drift; the doc is the authority."""
    doc = (PROJECT_ROOT / "docs" / "when_this_ends.md").read_text(
        encoding="utf-8"
    )
    assert _module().FORWARD_DECISION_DATE in doc


@pytest.mark.parametrize(
    "payload",
    [
        {"generated_at": "x", "markets": {}, "rows": 0, "unsettleable": 0},
        {},
        [],
        "not json at all",
    ],
    ids=["empty-report", "no-keys", "wrong-type", "garbage"],
)
def test_a_malformed_report_still_seals(payload: object, tmp_path: Path) -> None:
    """Every failure path resolves to sealed, never to an accidental number."""
    target = tmp_path / "forward_evidence.json"
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
        record = _module().load_record(target)
    else:
        record = _record(payload, tmp_path)
    assert record["forward"]["sealed"] is True
    assert record["forward"]["rows"] == 0


def test_a_missing_report_seals_too(tmp_path: Path) -> None:
    record = _module().load_record(tmp_path / "nope.json")
    assert record["forward"]["sealed"] is True


def test_accuracy_records_are_still_published(tmp_path: Path) -> None:
    """The seal is on the wager return, not on whether the model is any good."""
    record = _record(MID_SEASON, tmp_path)
    assert set(record) >= {"straightUp", "puckLine", "totals"}
    assert record["puckLine"] == {"w": 0, "l": 0, "p": 0}


#: The one page whose forward return is sealed. Scoped deliberately.
#:
#: The seal protects NHL's **pre-registered** measurement: its pooled
#: forward return is the test decided on 2027-04-25
#: (docs/when_this_ends.md), and putting a running total on a public page
#: turns that test into a scoreboard.
#:
#: The sibling boards are a different case and must not be caught by this.
#: The EPL page shows its card's own settled record — that market is
#: allowlisted, it publishes selections, and hiding how they have done
#: would be the dishonest choice. The CBB page shows the historical
#: measurement per tier, intervals and all, including the two demonstrated
#: deficits. Neither is a pre-registered forward test, and an earlier
#: version of this test globbed every `*.dc.html` and would have forced
#: both of them blank.
SEALED_PAGE = "NHL Projections.dc.html"


def test_no_page_renders_a_forward_return() -> None:
    """The renderer is the other half; sealing the data is not enough.

    The unsealed branch has now arrived in three separate design drops, so
    this is the guard that keeps catching it.
    """
    page = PROJECT_ROOT / "web" / SEALED_PAGE
    assert page.is_file(), (
        f"{SEALED_PAGE} is missing. A renamed page would make this test "
        "pass by checking nothing, so the name is asserted rather than "
        "globbed."
    )
    text = page.read_text(encoding="utf-8")
    for field in ("roiPct", "ciLow", "ciHigh", "clvPct"):
        assert field not in text, (
            f"{SEALED_PAGE} renders {field}, which load_record does not "
            "supply and must not start supplying."
        )


def test_the_schedule_fetch_sends_a_user_agent() -> None:
    """api-web.nhle.com answers the default urllib agent with 403.

    The first deployment of this site failed on exactly that, with a
    traceback that reads like a network outage. Any agent string gets a 200,
    so this is a one-line fix that is impossible to rediscover from the
    error — which is why it is pinned rather than left to a comment.
    """
    module = _module()
    captured: dict = {}

    class _Resp:
        def read(self) -> bytes:
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    def _urlopen(request: object, timeout: float = 0) -> object:
        captured["agent"] = request.get_header("User-agent")
        return _Resp()

    original = module.urllib.request.urlopen
    original_load = module.json.load
    module.urllib.request.urlopen = _urlopen
    module.json.load = lambda handle: {}
    try:
        module.fetch_json("https://api-web.nhle.com/v1/schedule/2026-09-29")
    finally:
        module.urllib.request.urlopen = original
        module.json.load = original_load

    assert captured.get("agent"), (
        "the request went out with no User-Agent, which api-web.nhle.com "
        "refuses with a 403"
    )
    assert "python-urllib" not in str(captured["agent"]).lower()
