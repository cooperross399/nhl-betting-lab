"""The historical props buy could spend past its cap by one event, and now cannot.

`buy_historical_props` gated its second, MEASURED, gate on
`buy.credits_spent >= credit_cap`: it asked whether the running total had
already reached the cap, never what the next event would cost. So the last
event it started could carry the total straight past the cap. Its siblings,
`historical_team_prices.buy_team_prices` and
`probe_retention_under_cap`, project one request ahead at the dearest charge
seen so far (`credits_spent + largest_charge > cap`), and CLAUDE.md says the
cap is "enforced against the measured running total", the gate that "cannot
be mis-specified".

Found by the sweep and proven with a stub (no network, no key, no credits):
seven markets on one region, an estimate of 70 an event, a provider charging
the recorded 107, and a cap of 200. The estimate gate admitted a second event
(140 of 200 worst case), the measured gate saw 107 < 200 and let it through,
and the run spent **214** against its cap of 200 with `buy.errors` empty, so
nothing in the output said the cap had been passed.

The gate now matches its siblings. The dearest measured charge is tracked,
seeded with the per-event estimate (which carries the region factor), and an
event is refused when `spent + largest > cap`. A refusal is a budget skip,
counted in `events_skipped_for_budget` for every event it refuses, and the
buy carries on, so an event already on disk further down is still read.

What these tests hold:

* the recorded repro ends at or under its cap, and says the measured gate
  stopped it;
* before any event is measured the gate can only use the estimate, so a cap
  of exactly one estimate buys the first event and a cap one below buys none;
* spend landing exactly on the cap is allowed, and one credit less refuses;
* every refused event is counted as skipped for budget, and a cached event
  after the refusal is still read, free.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.markets import PROP_MARKETS
from nhl_betting_lab.providers import historical_props as hist
from nhl_betting_lab.providers.odds_api import OddsApiProvider


SNAPSHOT = "2025-01-05T19:00:00Z"

#: Every prop market the lab buys by default. Seven, so the one-region
#: estimate is the recorded 70 an event.
ALL_PROP_KEYS = [market.provider_key for market in PROP_MARKETS]

#: What the provider actually charged an event in production.
RECORDED_CHARGE = 107


@pytest.fixture(autouse=True)
def _no_default_raw_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Every buy below names its raw_dir; the default is pointed away from
    the real data tree so a slip cannot write into it."""
    stray = tmp_path / "default-raw-dir-must-stay-empty"
    monkeypatch.setattr(hist, "RAW_DIR", stray)
    yield
    assert not stray.exists()


def _charging(credits: int) -> RecordingRequester:
    """A provider that answers every historical event request, charging
    `credits` a request in `x-requests-last`."""

    def answer(url: str, **_kwargs: Any) -> FakeResponse:
        event_id = url.split("/events/")[1].split("/")[0]
        payload = {
            "timestamp": SNAPSHOT,
            "data": {
                "id": event_id,
                "commence_time": "2025-01-05T23:00:00Z",
                "home_team": "Toronto Maple Leafs",
                "away_team": "Boston Bruins",
                "bookmakers": [
                    {
                        "key": "draftkings",
                        "title": "DraftKings",
                        "markets": [
                            {
                                "key": "player_points",
                                "outcomes": [
                                    {
                                        "name": "Over",
                                        "description": "Auston Matthews",
                                        "price": -115,
                                        "point": 0.5,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        }
        return FakeResponse(payload, headers={"x-requests-last": str(credits)})

    return RecordingRequester({"/historical/": answer})


def _events(count: int) -> list[dict[str, str]]:
    return [
        {"event_id": f"evt{index:02d}", "snapshot": SNAPSHOT}
        for index in range(count)
    ]


def _calls(requester: RecordingRequester) -> list[str]:
    return [url for url in requester.urls if "/historical/" in url]


def _buy(
    tmp_path: Path,
    *,
    charged: int,
    cap: int,
    markets: list[str],
    events: int = 10,
    regions: str = "us",
) -> tuple[hist.HistoricalBuy, RecordingRequester, OddsApiProvider]:
    requester = _charging(charged)
    provider = OddsApiProvider(
        environment={}, requester=requester, regions=regions
    )
    buy = hist.buy_historical_props(
        provider,
        events=_events(events),
        markets=markets,
        credit_cap=cap,
        raw_dir=tmp_path / "raw",
    )
    return buy, requester, provider


def test_the_recorded_overcharge_ends_inside_the_cap(tmp_path: Path) -> None:
    """The repro: 70 estimated, 107 charged, cap 200. It used to buy two and
    spend 214 with no error. It buys one, and refuses the next because 107
    more would pass 200."""
    buy, requester, provider = _buy(
        tmp_path, charged=RECORDED_CHARGE, cap=200, markets=ALL_PROP_KEYS
    )
    estimate = hist.estimate_credits(
        events=1, markets=len(ALL_PROP_KEYS), regions=provider.region_count
    )
    # The fixture must be one the estimate gate lets past the cap on its own,
    # or this would pass with the measured gate switched off.
    assert estimate == 70
    assert 2 * estimate <= 200 < 2 * RECORDED_CHARGE

    assert buy.credits_spent <= 200, buy.summary_line()
    assert buy.events_bought == 1
    assert len(_calls(requester)) == 1
    assert buy.credits_spent == RECORDED_CHARGE
    # Every event it did not buy is a budget skip, and the measured stop is
    # said once, with the cap, the spend and the charge it projected.
    assert buy.events_skipped_for_budget == 9
    measured = [error for error in buy.errors if "MEASURED" in error]
    assert len(measured) == 1, buy.errors
    assert "200" in measured[0] and f"{RECORDED_CHARGE}" in measured[0]
    assert "9 event(s) skipped for budget" in buy.summary_line()


def test_the_first_event_is_gated_on_the_estimate(tmp_path: Path) -> None:
    """Before anything is measured, the only forecast of a charge is the
    estimate: ten a market a region. A cap of exactly one estimate buys the
    first event (and learns it costs 25); a cap one below buys nothing."""
    at, at_requester, provider = _buy(
        tmp_path / "at", charged=25, cap=20, markets=["player_points"],
        regions="us,us2",
    )
    assert hist.estimate_credits(
        events=1, markets=1, regions=provider.region_count
    ) == 20
    assert at.events_bought == 1
    assert len(_calls(at_requester)) == 1
    assert at.credits_spent == 25
    assert at.events_skipped_for_budget == 9

    below, below_requester, _ = _buy(
        tmp_path / "below", charged=25, cap=19, markets=["player_points"],
        regions="us,us2",
    )
    assert below.events_bought == 0
    assert _calls(below_requester) == []
    assert below.credits_spent == 0
    assert below.events_skipped_for_budget == 10


@pytest.mark.parametrize(
    ("markets", "charged", "cap", "bought"),
    [
        pytest.param(ALL_PROP_KEYS, RECORDED_CHARGE, 214, 2, id="107-twice-is-214"),
        pytest.param(ALL_PROP_KEYS, RECORDED_CHARGE, 213, 1, id="one-short-of-214"),
        pytest.param(["player_points"], 25, 100, 4, id="25-four-times-is-100"),
        pytest.param(["player_points"], 25, 99, 3, id="one-short-of-100"),
    ],
)
def test_spend_may_land_exactly_on_the_cap_and_no_further(
    tmp_path: Path, markets: list[str], charged: int, cap: int, bought: int
) -> None:
    """`spent + largest == cap` is inside the cap and is bought; a cap one
    credit lower refuses that same event."""
    buy, requester, _ = _buy(tmp_path, charged=charged, cap=cap, markets=markets)

    assert buy.events_bought == bought
    assert len(_calls(requester)) == bought
    assert buy.credits_spent == bought * charged
    assert buy.credits_spent <= cap
    assert buy.events_skipped_for_budget == 10 - bought


def test_a_refusal_is_a_skip_and_a_cached_event_is_still_read(
    tmp_path: Path,
) -> None:
    """The measured gate used to `break`, counting one skip however many
    events were left and never reading an event already on disk further
    down. A refused event is skipped like any other budget skip, and the
    cached one at the end is read for nothing."""
    raw = tmp_path / "raw"
    # Put the last event on disk first.
    warm_provider = OddsApiProvider(
        environment={}, requester=_charging(RECORDED_CHARGE), regions="us"
    )
    warm = hist.buy_historical_props(
        warm_provider,
        events=[{"event_id": "evt09", "snapshot": SNAPSHOT}],
        markets=ALL_PROP_KEYS,
        credit_cap=1_000,
        raw_dir=raw,
    )
    assert warm.events_bought == 1

    requester = _charging(RECORDED_CHARGE)
    provider = OddsApiProvider(environment={}, requester=requester, regions="us")
    buy = hist.buy_historical_props(
        provider,
        events=_events(10),
        markets=ALL_PROP_KEYS,
        credit_cap=200,
        raw_dir=raw,
    )

    assert buy.credits_spent == RECORDED_CHARGE <= 200
    assert [url.split("/events/")[1].split("/")[0] for url in _calls(requester)] == [
        "evt00"
    ]
    assert buy.events_bought == 1
    assert buy.events_from_cache == 1
    assert buy.events_skipped_for_budget == 8
    assert {row["provider_event_id"] for row in buy.rows} == {"evt00", "evt09"}
