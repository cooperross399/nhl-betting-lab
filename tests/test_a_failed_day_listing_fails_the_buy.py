"""A day whose listing failed was dropped without a word, and the buy stayed green.

`buy_historical_props.py` walks the historical events endpoint one day at a
time (`_events_in_window`), and a day whose listing raised `ProviderError`
printed one stderr line ("  2025-10-02: The odds provider returned HTTP
500 ...") and was skipped. Nothing else carried it: the "N event(s) found in
the window" line counted only the days that answered, no summary named the
day, and the run exited 0. So:

* on the buy path, a window of three days whose middle listing failed bought
  two days, reported success, and left the Historical Props Purchase "Buy a
  window" step green, with nothing to say a night of the window was never
  asked for;
* when EVERY listing failed the run printed "0 event(s) found in the window"
  and "No events in scope." and exited 0 -- which reads as "there was
  nothing to buy", where the truth is "the provider could not be asked";
* on the probe path, a failed day thinned the window the probe spread its
  events across and the retention record was written anyway, exit 0 (#202
  refuses a probe that answers fewer events than were asked, for the reason
  that applies here too).

That is the shape #207 closed for the live fetch ("a failed events listing
reads as a failed per-event fetch, never as no rows"). Here a failed day is
now collected, named with its cause in the run's own summary, and the run
exits 2, the house code for a fault. What the other days listed is still
bought -- a purchase is additive and cached, so buying it now costs nothing
a re-run would not, and the re-run asks again only for the days that
failed -- but a probe asks nothing and writes nothing, because its record
would describe a window it did not see.

The second half of this file holds the twenty-four-hour window by behaviour.
Until now it was held only by a grep for its source text
(`tests/test_repository_discipline.py`), so widening `<` to `<=`, or deleting
the filter, stayed green. Here the listing carries a game at each edge, just
inside and just outside, and the test reads which ones the run asked the
provider to price.

Everything below drives the real `main()` over a fake transport: nothing
reaches the network and no credit is spent.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from conftest import FakeResponse
from nhl_betting_lab.providers import historical_props as hist
from nhl_betting_lab.providers.odds_api import OddsApiProvider
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from test_scripts import load_script
from test_the_retention_probe_holds_its_cap import _dirs, _odds


REGIONS = "us,us2"

#: Enough for every listing and every event below at the pessimistic 140 an
#: event, so the cap never decides what these tests see.
CAP = "100000"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """No default data directory is the checkout's, and the historical
    cache's default must stay empty: every run names its own."""
    point_default_data_dirs_at(monkeypatch, tmp_path / "checkout_defaults")
    stray = tmp_path / "default-raw-dir-must-stay-empty"
    monkeypatch.setattr(hist, "RAW_DIR", stray)
    yield
    assert not stray.exists()


def _iso(when: datetime) -> str:
    return when.isoformat(timespec="seconds").replace("+00:00", "Z")


def _evening(day: str, games: int = 2) -> list[dict[str, str]]:
    """`games` evening games on `day`, inside that day's listing window."""
    first = datetime.fromisoformat(f"{day}T23:00:00+00:00")
    return [
        {
            "id": f"{day}-evt{index}",
            "commence_time": _iso(first + timedelta(minutes=30 * index)),
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
        }
        for index in range(games)
    ]


class _Historical:
    """The two historical endpoints, answered without the network.

    `slates` maps a day to what its listing returns (default: two evening
    games). A day in `failing` answers its listing with an HTTP 500. Every
    per-event request is answered with a price and recorded in `asked`."""

    def __init__(
        self,
        *,
        failing: set[str] = frozenset(),  # type: ignore[assignment]
        slates: dict[str, list[dict[str, str]]] | None = None,
    ) -> None:
        self.failing = set(failing)
        self.slates = slates or {}
        self.listings: list[str] = []
        self.asked: list[str] = []

    def __call__(self, url: str, *, params: dict, timeout: float) -> FakeResponse:
        if url.endswith("/odds"):
            event_id = url.split("/events/")[1].split("/")[0]
            self.asked.append(event_id)
            markets = params["markets"].split(",")
            return FakeResponse(
                _odds(event_id, params["date"], markets),
                headers={"x-requests-last": "20", "x-requests-remaining": "1000000"},
            )
        if url.endswith("/events"):
            day = params["date"][:10]
            self.listings.append(day)
            if day in self.failing:
                return FakeResponse(status_code=500)
            return FakeResponse(
                {"timestamp": params["date"], "data": self.slates.get(day, _evening(day))},
                headers={"x-requests-last": "1", "x-requests-remaining": "1000000"},
            )
        return FakeResponse(status_code=404)


def _script(monkeypatch: pytest.MonkeyPatch, fake: _Historical) -> ModuleType:
    module = load_script("buy_historical_props.py")
    monkeypatch.setattr(module, "load_provider_env", lambda *a, **k: None)
    monkeypatch.setattr(
        module,
        "OddsApiProvider",
        lambda *a, **k: OddsApiProvider(
            environment={}, requester=fake, regions=REGIONS
        ),
    )
    return module


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake: _Historical,
    *,
    start: str,
    end: str,
    probe: bool = False,
) -> int:
    return _script(monkeypatch, fake).main(
        [
            *(["--probe"] if probe else []),
            "--live",
            "--from", start, "--to", end,
            "--credit-cap", CAP,
            "--hours-before", "4",
            *_dirs(tmp_path),
        ]
    )


# -- a failed listing is a fault, not an empty day ---------------------------


def test_one_failed_day_is_named_and_the_run_exits_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Three days, the middle listing fails. The two days that answered are
    still bought -- the cache keeps them and a re-run pays nothing for them
    -- but the day that was never asked is named with its cause and the run
    exits 2, where it exited 0 and named it nowhere but one stderr line."""
    fake = _Historical(failing={"2025-10-02"})

    code = _run(tmp_path, monkeypatch, fake, start="2025-10-01", end="2025-10-03")
    printed = capsys.readouterr()

    assert fake.listings == ["2025-10-01", "2025-10-02", "2025-10-03"]
    assert sorted(fake.asked) == sorted(
        e["id"] for day in ("2025-10-01", "2025-10-03") for e in _evening(day)
    )
    assert code == 2
    assert "1 day(s) of the window could not be listed" in printed.err
    assert "2025-10-02" in printed.err
    assert "HTTP 500" in printed.err
    # The count of what was found says what it leaves out.
    assert "4 event(s) found in the window" in printed.out
    assert "1 day(s) could not be listed" in printed.out
    assert (tmp_path / "processed" / "historical_prop_prices.csv").is_file()


def test_every_listing_failing_is_not_nothing_to_buy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every listing fails. This printed "0 event(s) found" and "No events
    in scope." and exited 0: "nothing to buy", where the truth is "could not
    ask". It now exits 2 and names every day."""
    days = ["2025-10-01", "2025-10-02", "2025-10-03"]
    fake = _Historical(failing=set(days))

    code = _run(tmp_path, monkeypatch, fake, start=days[0], end=days[-1])
    printed = capsys.readouterr()

    assert fake.listings == days
    assert fake.asked == []
    assert code == 2
    assert "3 day(s) of the window could not be listed" in printed.err
    for day in days:
        assert day in printed.err
    assert "No events in scope." not in printed.out
    assert not (tmp_path / "processed" / "historical_prop_prices.csv").exists()


def test_a_failed_listing_is_named_last_after_the_buy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The run's closing lines are what a reader of the step log sees; the
    failed day is restated after the purchase summary, not only before it."""
    fake = _Historical(failing={"2025-10-02"})

    _run(tmp_path, monkeypatch, fake, start="2025-10-01", end="2025-10-03")
    err = capsys.readouterr().err.strip().splitlines()

    assert "could not be listed" in err[-2], err[-2:]
    assert err[-1].strip().startswith("2025-10-02: The odds provider returned HTTP 500")
    # The script stages nothing, so the provider error's staging sentence
    # is not repeated as though it did.
    assert "No staging file was written." not in err[-1]


def test_a_probe_over_a_failed_listing_asks_nothing_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A probe spreads its events across the window. With a day missing it
    would describe a window it did not see and write that over the record,
    exit 0. It now asks no per-event request, leaves the record alone and
    exits 2, as #202 does for a probe with a failed request."""
    record = tmp_path / "out" / "historical_props_retention.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text('{"events_probed": 2723}\n', encoding="utf-8")
    fake = _Historical(failing={"2025-10-02"})

    code = _run(
        tmp_path, monkeypatch, fake, start="2025-10-01", end="2025-10-03", probe=True
    )
    printed = capsys.readouterr()

    assert code == 2
    assert fake.asked == []
    assert record.read_text(encoding="utf-8") == '{"events_probed": 2723}\n'
    assert "2025-10-02" in printed.err


def test_a_single_failed_day_probe_names_the_failure_not_the_season(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The workflow probes one day. Its listing failing used to be reported
    as "Give --from/--to over days the season was being played", advice
    about the dates, when the dates were fine and the provider did not
    answer."""
    fake = _Historical(failing={"2025-10-08"})

    code = _run(
        tmp_path, monkeypatch, fake, start="2025-10-08", end="2025-10-08", probe=True
    )
    printed = capsys.readouterr()

    assert code == 2
    assert "could not be listed" in printed.err
    assert "the season was being played" not in printed.err


def test_a_window_that_lists_cleanly_still_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: nothing failed, so nothing here changes a clean buy."""
    fake = _Historical()

    code = _run(tmp_path, monkeypatch, fake, start="2025-10-01", end="2025-10-02")

    assert code == 0
    assert len(fake.asked) == 4


# -- the twenty-four-hour window, by behaviour --------------------------------


DAY = "2025-10-08"
NOON = datetime.fromisoformat(f"{DAY}T12:00:00+00:00")
ONE_SECOND = timedelta(seconds=1)

#: A listing carrying a game at each edge of `DAY`'s window, [noon, noon + 24h).
EDGES = {
    "before-window": NOON - ONE_SECOND,
    "at-window-start": NOON,
    "evening": NOON + timedelta(hours=11),
    "last-second-inside": NOON + timedelta(days=1) - ONE_SECOND,
    "at-window-end": NOON + timedelta(days=1),
    "a-day-later": NOON + timedelta(days=1, hours=11),
}
INSIDE = {"at-window-start", "evening", "last-second-inside"}


def _edge_slate() -> list[dict[str, str]]:
    return [
        {
            "id": event_id,
            "commence_time": _iso(when),
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
        }
        for event_id, when in EDGES.items()
    ]


@pytest.mark.parametrize("probe", [False, True], ids=["buy", "probe"])
def test_the_window_keeps_exactly_the_twenty_four_hours_after_noon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, probe: bool
) -> None:
    """One listing, six games: one second before noon UTC, at noon, in the
    evening, one second before the next noon, at the next noon, and the next
    evening. Only the three inside [noon, next noon) are priced. Deleting the
    filter prices all six; `<=` at the end prices the next noon's game; `<`
    at the start drops the noon game."""
    fake = _Historical(slates={DAY: _edge_slate()})

    code = _run(tmp_path, monkeypatch, fake, start=DAY, end=DAY, probe=probe)

    assert fake.listings == [DAY]
    assert set(fake.asked) == INSIDE
    assert code == 0


def test_the_window_is_not_the_utc_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug the window replaced: a UTC-date filter keeps the game one
    second before noon (same UTC date) and drops the evening's late games
    that fall past midnight UTC. A 7pm ET face-off on DAY is 23:00 UTC; a
    10pm ET one is 02:00 UTC the next day and belongs to DAY's slate."""
    late = NOON + timedelta(hours=14)  # 02:00 UTC on DAY + 1
    morning = NOON - timedelta(hours=11)  # 01:00 UTC on DAY: yesterday's night
    slate = [
        {"id": "late-night", "commence_time": _iso(late),
         "home_team": "Vancouver Canucks", "away_team": "Calgary Flames"},
        {"id": "yesterdays-late-game", "commence_time": _iso(morning),
         "home_team": "Seattle Kraken", "away_team": "Edmonton Oilers"},
    ]
    fake = _Historical(slates={DAY: slate})

    code = _run(tmp_path, monkeypatch, fake, start=DAY, end=DAY)

    assert fake.asked == ["late-night"]
    assert code == 0
