"""The historical props buyer's measured-spend gate was guarded by a grep.

`buy_historical_props` enforces its credit cap with two gates, checked before
every request. The first is the estimate: ten credits a market a region an
event, the provider's documented rate. The second reads the running total of
what the provider says it actually charged (`x-requests-last`), projected one
event ahead at the dearest charge seen (until 2026-09-26 it stopped only once
that total had already reached the cap, so the last event could pass it; see
`test_the_props_buy_never_spends_past_its_cap.py`). The second (#65) exists because the
first has already been wrong in production: a run capped at 200,000 spent
289,984, 107 credits an event against a predicted 70.

The only test that named the second gate,
`test_the_cap_holds_when_the_estimate_is_too_low`, read the source and looked
for the text `buy.credits_spent >= credit_cap`. That text survives
`... >= credit_cap and False:`, and it survives the gate's `break` being
deleted, which records "Stopped at the cap" and then buys anyway. Every test
that ran a buy used an `x-requests-last` of 1 or 2, or none, against an
estimate of at least ten, so the estimate gate always stopped the run first
and the measured gate never decided anything.

Found by the failure-shape audit (finding 75; confirmed by 2 of 3 refuters,
and the third agreed the test could not fail). Switching the gate off left the
whole suite green: 1,768 passed at the audit, 1,860 passed at 25a3e8a. Replayed
through the real function with the lab's seven prop markets on one region, a
provider charging the recorded 107 an event against an estimate of 70, and a
200,000 cap: the real gate stops after 1,870 events at 200,090 (one request
past the cap); switched off, the run buys 2,857 events and spends 305,699.
Four more variants left the whole suite green at 25a3e8a (1,860 passed each):
the gate's `break` deleted, each charge recorded at no more than the
estimate, a response with no cost header counted as free, and the buy's
estimate dropping the region factor.

The overspend needs a provider charging above the estimate. Since #76 the
estimate carries the region factor, and under the provider's documented rule
(ten a market returned, a region) the charge cannot exceed it. The measured
gate is the backstop for when that rule or the estimate is wrong again, which
is when nothing else would stop the run. So these tests drive the real
function with a stubbed requester (no network, no key, no credits), and a
provider that charges MORE than the estimate, so that only the measured gate
can stop the buy:

* the buy refuses any event that the dearest charge seen so far would carry
  past the cap, so it can pass the cap by at most how much the next charge
  exceeds that dearest one, and not at all while charges do not rise; here
  every request costs the same, so only the first event, whose charge
  nothing has measured yet, can end the run past it (and the run then says
  it OVERSPENT; see `test_the_props_buy_never_spends_past_its_cap.py` for
  charges that vary);
* the spend recorded is the sum of what each request was charged;
* the prices it paid for are kept, and the stop is reported as MEASURED.

The last test covers the region factor at the buy site, which also had no
runtime test: every buy test that reached its cap asked for one region, and
dropping the factor there left the whole suite green (1,860 passed).
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

#: Every prop market this lab buys, as the purchase script asks for them by
#: default. Seven, so the one-region estimate is the recorded 70 an event.
ALL_PROP_KEYS = [market.provider_key for market in PROP_MARKETS]


@pytest.fixture(autouse=True)
def _no_default_raw_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Every buy below names its raw_dir. The default is pointed away from the
    real data tree anyway, so a slip cannot write into it, and must stay
    untouched."""
    stray = tmp_path / "default-raw-dir-must-stay-empty"
    monkeypatch.setattr(hist, "RAW_DIR", stray)
    yield
    assert not stray.exists()


def _charging(credits: int | None) -> RecordingRequester:
    """A provider that answers every historical request for the event in its
    URL, charging `credits` a request (no header at all when None)."""

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
        headers = {} if credits is None else {"x-requests-last": str(credits)}
        return FakeResponse(payload, headers=headers)

    return RecordingRequester({"/historical/": answer})


def _events(count: int) -> list[dict[str, str]]:
    return [
        {"event_id": f"evt{index:02d}", "snapshot": SNAPSHOT}
        for index in range(count)
    ]


def _historical_calls(requester: RecordingRequester) -> list[str]:
    return [url for url in requester.urls if "/historical/" in url]


# The provider charges above the estimate in every case, so the estimate gate
# alone would let the run past its cap; only the measured gate can stop it.
#   regions, markets, charged a request, cap -> events bought, credits spent
OVER_ESTIMATE = [
    pytest.param(
        "us", ALL_PROP_KEYS, 107, 700, 6, 642,
        id="recorded-107-against-70-one-region",
    ),
    pytest.param(
        "us,us2", ALL_PROP_KEYS, 214, 1400, 6, 1284,
        id="recorded-ratio-on-two-regions",
    ),
    pytest.param(
        "us", ["player_points"], 25, 100, 4, 100,
        id="spend-lands-exactly-on-the-cap",
    ),
    pytest.param(
        "us", ["player_points"], 150, 100, 1, 150,
        id="one-request-costs-more-than-the-cap",
    ),
]


@pytest.mark.parametrize(
    ("regions", "markets", "charged", "cap", "bought", "spent"), OVER_ESTIMATE
)
def test_measured_spend_stops_a_buy_the_estimate_would_let_through(
    tmp_path: Path,
    regions: str,
    markets: list[str],
    charged: int,
    cap: int,
    bought: int,
    spent: int,
) -> None:
    requester = _charging(charged)
    provider = OddsApiProvider(
        environment={}, requester=requester, regions=regions
    )
    events = _events(20)
    estimate = hist.estimate_credits(
        events=1, markets=len(markets), regions=provider.region_count
    )
    # The fixture has to be one the estimate gate cannot handle, or this test
    # would pass with the measured gate switched off: the provider charges
    # more than the estimate, and the events the estimate alone would admit
    # cost at least a whole request more than the cap.
    assert charged > estimate
    estimate_alone = min(len(events), cap // estimate) * charged
    assert estimate_alone >= cap + charged

    buy = hist.buy_historical_props(
        provider,
        events=events,
        markets=markets,
        credit_cap=cap,
        raw_dir=tmp_path / "raw",
    )

    calls = _historical_calls(requester)
    assert buy.events_bought == bought
    assert len(calls) == bought, "one request per event bought, and no more"
    # The spend recorded is what each request was charged, summed.
    assert buy.credits_spent == spent == bought * charged
    # No request was started that the dearest charge seen said would pass
    # the cap. Every request here costs the same, so only a first request,
    # whose charge nothing had measured yet, can end the run past it.
    if charged <= cap:
        assert buy.credits_spent <= cap
        assert not any("OVERSPENT" in error for error in buy.errors)
    else:
        assert bought == 1
        assert any("OVERSPENT" in error for error in buy.errors), buy.errors
    assert buy.credits_spent + charged > cap, "and it stopped no earlier"
    # It stopped at the first event it could not afford, in order, and kept
    # the prices it paid for.
    assert [url.split("/events/")[1].split("/")[0] for url in calls] == [
        event["event_id"] for event in events[:bought]
    ]
    assert {row["provider_event_id"] for row in buy.rows} == {
        event["event_id"] for event in events[:bought]
    }
    assert buy.events_skipped_for_budget == len(events) - bought
    assert any(
        "MEASURED" in error and f"{cap:,}" in error and f"{spent:,}" in error
        for error in buy.errors
    ), buy.errors
    assert f"{spent} credit(s) actually spent" in buy.summary_line()


def test_a_buy_with_no_cost_header_charges_the_estimate(tmp_path: Path) -> None:
    """The running total the measured gate reads must never make a run look
    cheaper than it was. A response with no `x-requests-last` is charged at
    the pessimistic estimate, as `_measured_cost` documents; counted as free,
    the total would stay at zero and the measured gate could never fire."""
    requester = _charging(None)
    provider = OddsApiProvider(environment={}, requester=requester, regions="us")

    buy = hist.buy_historical_props(
        provider,
        events=_events(10),
        markets=["player_points"],
        credit_cap=25,
        raw_dir=tmp_path / "raw",
    )

    assert buy.events_bought == 2
    assert len(_historical_calls(requester)) == 2
    assert buy.credits_spent == 20, "two requests at the ten-credit estimate"


def test_the_buy_estimate_carries_the_region_factor(tmp_path: Path) -> None:
    """The lab asks for `us,us2`, and the provider bills per region.

    `estimate_credits` has multiplied by regions since #76 and is tested on
    its own, but the buy site passing `provider.region_count` was not: every
    buy test that reached its cap asked for one region, so the estimate gate
    could lose the factor with the suite green, and the only thing then
    holding the cap would be the measured gate above. Here the provider
    charges one credit, so the measured gate cannot fire and the estimate
    alone decides: twenty credits an event on two regions admits one event
    under a cap of 25; ten on one region would admit two."""
    requester = _charging(1)
    provider = OddsApiProvider(
        environment={}, requester=requester, regions="us,us2"
    )
    assert provider.region_count == 2

    buy = hist.buy_historical_props(
        provider,
        events=_events(10),
        markets=["player_points"],
        credit_cap=25,
        raw_dir=tmp_path / "raw",
    )

    assert buy.events_bought == 1
    assert len(_historical_calls(requester)) == 1
    assert buy.events_skipped_for_budget == 9
    assert buy.credits_spent == 1
