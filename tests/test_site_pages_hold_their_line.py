"""What the public pages hold to, apart from what they measure.

This file was `test_site_publishes_no_forward_return.py`, which sealed the
forward return off every page until 2027-04-25. Cooper reversed that on
2026-10-26 ("All results" drop): units, records and return for every graded
best bet are published on `Tracker.dc.html`. The seal tests were retired
then; what stays here is the rest of what the file held (the schedule fetch's
user agent, the empty-state wording, the favicon, the nav), plus the one line
the reversal kept: the Due List is tracked, never presented as a model bet.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "web" / "build_site_json.py"


def _module():
    spec = importlib.util.spec_from_file_location("bsj", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The shared adapter module. The three boards render from one file now, so
#: the NHL section of it is the other half of the renderer the page used to
#: be — and the half a page-only grep stopped seeing the moment the strip
#: moved here.
ADAPTER = "lib/sports.js"

#: The NHL adapter's bounds inside that shared file.
ADAPTER_SECTION = ("// ---------- NHL ----------", "// ---------- EPL ----------")


def _nhl_adapter_source() -> str:
    text = (PROJECT_ROOT / "web" / ADAPTER).read_text(encoding="utf-8")
    start_marker, end_marker = ADAPTER_SECTION
    start = text.find(start_marker)
    end = text.find(end_marker)
    assert start != -1 and end != -1 and start < end, (
        f"{ADAPTER} no longer carries the section markers "
        f"{ADAPTER_SECTION!r} that bound the NHL adapter. Without them this "
        "test cannot tell NHL's strip from its siblings', and a guard that "
        "cannot find its subject must fail rather than pass."
    )
    return text[start:end]


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


def test_the_due_list_is_tracked_and_never_called_a_bet() -> None:
    """The Due List sits on All results at a notional stake. It is Cooper's
    list, not the model's pick: the page says so on its card, and the builder
    keeps its rows out of the best bets and their record."""
    page = (PROJECT_ROOT / "web" / "Tracker.dc.html").read_text(encoding="utf-8")
    assert 'key === "due" ? `Cooper\'s list · ${base.dueStake}u per entry, not bet`' in page
    module = _module()
    night = {"resultsDate": "2026-10-20", "games": [], "props": {"status": "ok", "rows": []},
             "dueList": {"rows": [{"market": "goals", "player": "A", "playerId": 1, "team": "TOR",
                                    "opp": "MTL", "price": 150, "result": "win", "units": 0.375}]}}
    rows = module.tracker_rows(night)
    assert [r["group"] for r in rows] == ["due"]
    assert rows[0]["staked"] == module.DUE_LIST_STAKE
