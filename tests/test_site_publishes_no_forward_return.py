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
They are forecast accuracy, not the registered wager return, and nothing
here seals them. Nothing tallies them yet either, so the record carries
None rather than a 0–0 nobody counted
(tests/test_site_invents_no_season_record.py).
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
    """The seal is on the wager return, not on whether the model is any good.

    So the accuracy slots stay in the published record. What they may not
    carry is a number nobody counted: this asserted `puckLine == {w: 0, l: 0,
    p: 0}` on a mid-season ledger, and that zero was a constant `load_record`
    returned on every path while nothing tallied a season or graded a puck
    line (tests/test_site_invents_no_season_record.py). Until a tally is
    kept, each slot is None and the page renders it as absent.
    """
    record = _record(MID_SEASON, tmp_path)
    assert set(record) >= {"straightUp", "puckLine", "totals"}
    assert record["puckLine"] is None
    assert record["straightUp"] is None and record["totals"] is None


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
SEALED_PAGE = "Board.dc.html"

#: What a published return looks like on the JS side. Shared by both renderer
#: tests below on purpose: they were one test over one file until the strip
#: moved into the shared module, and two copies of this tuple drifting apart
#: is how the branch got back in.
RETURN_FIELDS = ("roiPct", "ciLow", "ciHigh", "clvPct")


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
    for field in RETURN_FIELDS:
        assert field not in text, (
            f"{SEALED_PAGE} renders {field}, which load_record does not "
            "supply and must not start supplying."
        )


#: The shared adapter module. The three boards render from one file now, so
#: the NHL section of it is the other half of the renderer the page used to
#: be — and the half a page-only grep stopped seeing the moment the strip
#: moved here.
SEALED_ADAPTER = "lib/sports.js"

#: The NHL adapter's bounds inside that shared file. Sliced rather than
#: scanned whole ON PURPOSE: EPL publishes its card's settled record and CBB
#: publishes its per-tier measurement, both legitimately, and both use these
#: same field names. A whole-file assertion would force the sibling boards
#: blank — the exact mistake the note on SEALED_PAGE records.
ADAPTER_SECTION = ("// ---------- NHL ----------", "// ---------- EPL ----------")


def _nhl_adapter_source() -> str:
    text = (PROJECT_ROOT / "web" / SEALED_ADAPTER).read_text(encoding="utf-8")
    start_marker, end_marker = ADAPTER_SECTION
    start = text.find(start_marker)
    end = text.find(end_marker)
    assert start != -1 and end != -1 and start < end, (
        f"{SEALED_ADAPTER} no longer carries the section markers "
        f"{ADAPTER_SECTION!r} that bound the NHL adapter. Without them this "
        "test cannot tell NHL's strip from its siblings', and a guard that "
        "cannot find its subject must fail rather than pass."
    )
    return text[start:end]


def test_the_shared_adapter_renders_no_forward_return() -> None:
    """The page is no longer the only renderer.

    This arrived a fifth time when the board strip moved out of the page and
    into the shared module: `Board.dc.html` was clean, the page-scoped test
    above passed, and the unsealed branch shipped inside `nhlBoard`. The
    seal on the data never stopped the renderer, and neither did a guard
    pointed at the wrong file.
    """
    source = _nhl_adapter_source()
    for field in RETURN_FIELDS:
        assert field not in source, (
            f"the NHL section of {SEALED_ADAPTER} renders {field}, which "
            "load_record does not supply and must not start supplying."
        )


def test_the_sealed_guard_can_still_see_an_unsealed_branch() -> None:
    """A guard proved only by passing is a guard proved by nothing.

    The previous version of this file asserted over the page alone and would
    have passed against the very drop that reintroduced the branch. So this
    plants one and checks the slice actually catches it.
    """
    source = _nhl_adapter_source()
    planted = source + '\n  { label: "Forward ledger \u00b7 ROI", value: fw.roiPct },\n'
    caught = [field for field in RETURN_FIELDS if field in planted]
    assert caught, (
        "a planted unsealed branch was not caught by the field list, so "
        "RETURN_FIELDS no longer describes what a published return looks like"
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


def test_the_empty_state_names_the_gate_that_actually_stopped_the_pick() -> None:
    """Reverted by three separate design drops, so it is pinned now.

    "No market clears the edge bar" reports a model judgement. What
    actually happens is a permission gate: `assess_markets` decides
    eligibility from the allowlist *before* edge is consulted, and
    `staging_provider_policy.json` allowlists nothing, so the card never
    reaches the bar to fail it.

    Naming the bar tells a visitor the model looked and found nothing. The
    truth is that nothing was allowed to be looked at.
    """
    # Reads the adapter, not the page. The empty state moved into the shared
    # module with the rest of the board strip, and this test went on asserting
    # over `Board.dc.html` -- where all three strings are absent, so it failed
    # loudly rather than passing blind. That is the only reason the revert was
    # caught: the sealed-return test next door had no such luck.
    text = _nhl_adapter_source()

    # This asserted the allowlist wording and BANNED the edge-bar wording.
    # That was right while the allowlist was empty and wrong the moment it
    # was not: with markets allowlisted the card does reach the bar, and
    # blaming the allowlist becomes the same error pointing the other way.
    #
    # So the page now carries both and picks by `allowlistedMarkets`, which
    # the board publishes. What this holds is that both arms exist and that
    # the choice is made from the data rather than fixed.
    assert "No market is allowlisted for selection" in text
    assert "No market clears the edge bar" in text
    assert "allowlistedMarkets" in text, (
        "the page hard-codes one of the two empty-state labels instead of "
        "choosing by the published allowlist state"
    )


def test_every_published_page_links_the_favicon() -> None:
    """Also dropped by three drops in a row.

    Cheap to lose, invisible in review, and the only symptom is a blank
    tab — which nobody reports as a bug.
    """
    web = PROJECT_ROOT / "web"
    assert (web / "favicon.svg").is_file(), "favicon.svg is missing from web/"
    missing = [
        p.name
        for p in sorted(web.glob("*.html"))
        if 'rel="icon"' not in p.read_text(encoding="utf-8")
    ]
    assert not missing, f"pages with no favicon link: {missing}"


def test_no_page_lists_the_same_nav_destination_twice() -> None:
    """Two pages shipped with the CBB link in the nav twice.

    It renders as "EPL CBB CBB", which is only visible if someone looks at
    the rendered page rather than at a 200. Every check up to that point
    passed: the file was served, the link worked, the suite was green.

    Cheap to introduce in a hand-written nav and cheap to pin here.
    """
    import re

    web = PROJECT_ROOT / "web"
    offenders: dict[str, list[str]] = {}
    for page in sorted(web.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        hrefs = re.findall(
            r'<a[^>]+href="(https://[a-z]+\.maverickhightower\.com/?[^"]*)"',
            text,
        )
        seen: set[str] = set()
        twice = sorted({h for h in hrefs if h in seen or seen.add(h)})
        if twice:
            offenders[page.name] = twice
    assert not offenders, f"nav destinations listed more than once: {offenders}"
