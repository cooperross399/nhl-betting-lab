"""`buy_historical_props.py --probe --live --credit-cap N` paid for every event it picked, whatever N said.

`--credit-cap` is documented as "Hard cap. Required with --live; the run stops
rather than exceed it", and the script's docstring says the cap "is enforced
before each request rather than checked afterwards". On the buy path it is:
`buy_historical_props` gates every uncached event on the pessimistic estimate
and on measured spend. The `--probe` branch looped over its selected events
calling `probe_retention` with no running total at all, so the cap was checked
only to be positive and then ignored. Historical Props Purchase's `mode:
probe` (its default mode) passes the dispatch's `credit_cap` (default "60")
straight to that branch.

Found by the failure-shape sweep (finding xr2, "a guard that cannot fire, on a
path that spends provider credits"; confirmed by 3 of 3 refuters). Replayed on
cfb0ed3 through the real `main()` with the workflow's own probe flags and a
requester that bills without touching the network:

* cap 60, a seven-game slate, the recorded 107 credits an event: five
  per-event requests, 536 credits, exit 0, and `credits_spent: 536` written
  into the retention record, after the script's own quote of 70 to 700;
* the same slate through the BUY path at the same cap: every event skipped
  for budget, 1 credit spent;
* cap 60, sixteen games and `--probe-events 16`: 1,713 credits;
* cap 1: 536.

The probe grew from one event (`events[:1]`, which the workflow's default of
60 was sized for: six markets, one region, measured at 50) to
`--probe-events` events (default five) in af780be, and the lab went to two
regions in #76. The cap was never passed to the loop, and three comments kept
saying "one event, so the cost is bounded". A second hole sat under the
first: the historical events listing, one credit a day, was paid for before
the cap was consulted at all, so a wide `--from/--to` could spend past the cap
on listings alone, on the buy path too.

What these tests hold, each through the real `main()`:

* a cap that cannot afford one uncached event (140 credits at seven markets
  and two regions) sends no per-event request, leaves the retention record it
  would have thinned alone, and exits 2 -- the workflow's default of 60
  included;
* the probe admits only what its cap affords on the estimate, stops on
  MEASURED spend projected at the dearest charge seen when the provider bills
  above the estimate, charges a failed request against the worst case, and
  prices the region factor;
* the listing is paid out of the same cap, and stops listing at it;
* an event already bought costs nothing and is read under any cap, including
  one past the point where buying stopped;
* a probe the cap cut short records the cut and exits nonzero; one the cap
  covers probes every selected event and exits 0;
* the documented probe commands name a window and hold their cap.
"""

from __future__ import annotations

import json
import re
import shlex
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from conftest import FakeResponse
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.markets import PROP_MARKETS
from nhl_betting_lab.providers import historical_props as hist
from nhl_betting_lab.providers.odds_api import OddsApiProvider
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from test_scripts import load_script


#: The Historical Props Purchase workflow's default probe day.
DAY = "2025-10-08"

#: Every prop market the lab buys; the probe asks for all of them by default.
ALL_PROP_KEYS = [market.provider_key for market in PROP_MARKETS]

#: The regions production asks (`odds_api.DEFAULT_REGIONS`), stated here so
#: the arithmetic below does not move with an environment variable.
REGIONS = "us,us2"

#: The pessimistic bound one uncached event is gated at: 10 x 7 x 2.
PER_EVENT = 140


@pytest.fixture(autouse=True)
def _isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """No default data directory is the checkout's, and the historical
    cache's default is a directory that must stay empty: every run below
    names its own."""
    point_default_data_dirs_at(monkeypatch, tmp_path / "checkout_defaults")
    stray = tmp_path / "default-raw-dir-must-stay-empty"
    monkeypatch.setattr(hist, "RAW_DIR", stray)
    yield
    assert not stray.exists()


def _slate(day: str, games: int) -> list[dict[str, str]]:
    """`games` evening games on `day`, fifteen minutes apart, as the
    historical events listing returns them."""
    first = datetime.fromisoformat(f"{day}T23:00:00+00:00")
    return [
        {
            "id": f"{day}-evt{index:02d}",
            "commence_time": (first + timedelta(minutes=15 * index))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
        }
        for index in range(games)
    ]


def _snapshot_for(event: dict[str, str], hours_before: float = 4.0) -> str:
    when = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
    return (
        (when - timedelta(hours=hours_before))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _odds(event_id: str, snapshot: str, markets: list[str]) -> dict:
    """One historical per-event snapshot carrying every market asked for."""
    return {
        "timestamp": snapshot,
        "data": {
            "id": event_id,
            "commence_time": snapshot,
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": key,
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Auston Matthews",
                                    "price": -115,
                                    "point": 0.5,
                                }
                            ],
                        }
                        for key in markets
                    ],
                }
            ],
        },
    }


class _Historical:
    """The two historical endpoints the probe calls, billing every ask.

    `charge` is what a per-event request is billed and reported as in
    `x-requests-last`; None withholds the header and bills the documented
    `10 x markets x regions`. `fail` answers every per-event request with an
    HTTP 500. `listing_fail` answers the listings of those days (every day,
    when True) with an HTTP 500 that still bills its credit, which is the
    case a failed request is held against the cap for, and
    `listing_charge` is what a listing that answers is billed. `billed` is
    the provider's side of the ledger, kept whatever the script believes it
    spent. Nothing reaches the network."""

    def __init__(
        self,
        *,
        games: int = 7,
        charge: int | None = 107,
        fail: bool = False,
        listing_fail: bool | set[str] = False,
        listing_charge: int = 1,
    ) -> None:
        self.games = games
        self.charge = charge
        self.fail = fail
        self.listing_fail = listing_fail
        self.listing_charge = listing_charge
        self.listings: list[str] = []
        self.asked: list[str] = []
        self.billed = 0

    def __call__(self, url: str, *, params: dict, timeout: float) -> FakeResponse:
        if url.endswith("/odds"):
            event_id = url.split("/events/")[1].split("/")[0]
            self.asked.append(event_id)
            if self.fail:
                return FakeResponse(status_code=500)
            markets = params["markets"].split(",")
            regions = len(params["regions"].split(","))
            bill = (
                10 * len(markets) * regions if self.charge is None else self.charge
            )
            self.billed += bill
            headers = {"x-requests-remaining": "1000000"}
            if self.charge is not None:
                headers["x-requests-last"] = str(self.charge)
            return FakeResponse(
                _odds(event_id, params["date"], markets), headers=headers
            )
        if url.endswith("/events"):
            day = params["date"][:10]
            self.listings.append(day)
            if self.listing_fail is True or (
                isinstance(self.listing_fail, set) and day in self.listing_fail
            ):
                self.billed += 1
                return FakeResponse(status_code=500)
            self.billed += self.listing_charge
            return FakeResponse(
                {"timestamp": params["date"], "data": _slate(day, self.games)},
                headers={
                    "x-requests-last": str(self.listing_charge),
                    "x-requests-remaining": "1000000",
                },
            )
        return FakeResponse(status_code=404)


def _script(monkeypatch: pytest.MonkeyPatch, fake: _Historical) -> ModuleType:
    """The real script, with the one door to the provider answered by `fake`
    and `.env` never read."""
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


def _dirs(tmp_path: Path) -> list[str]:
    return [
        "--raw-dir", str(tmp_path / "raw"),
        "--output-dir", str(tmp_path / "out"),
        "--processed-dir", str(tmp_path / "processed"),
    ]


def _probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake: _Historical,
    *,
    cap: int,
    start: str = DAY,
    end: str = DAY,
    extra: tuple[str, ...] = (),
) -> int:
    """The Historical Props Purchase probe step, as it runs it."""
    return _script(monkeypatch, fake).main(
        [
            "--probe", "--live",
            "--from", start, "--to", end,
            "--credit-cap", str(cap),
            "--hours-before", "4",
            *_dirs(tmp_path),
            *extra,
        ]
    )


def _record(tmp_path: Path) -> dict:
    return json.loads(
        (tmp_path / "out" / "historical_props_retention.json").read_text(
            encoding="utf-8"
        )
    )


def _selected(games: int = 7) -> list[dict[str, str]]:
    """The events the probe picks: spread across the slate, five of them."""
    slate = _slate(DAY, games)
    step = max(1, len(slate) // hist.MINIMUM_PROBES_FOR_ABSENCE)
    return slate[::step][: hist.MINIMUM_PROBES_FOR_ABSENCE]


def _cache(tmp_path: Path, event: dict[str, str]) -> None:
    """An event already bought at the probe's snapshot and market list."""
    snapshot = _snapshot_for(event)
    path = hist._cache_path(
        event["id"], snapshot, raw_dir=tmp_path / "raw", markets=ALL_PROP_KEYS
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_odds(event["id"], snapshot, ALL_PROP_KEYS)), encoding="utf-8"
    )


def _assert_the_arithmetic() -> None:
    """What the numbers in these tests rest on: seven markets, two regions,
    140 an event, five events picked from the front of a seven-game slate,
    and every game inside the listing's twenty-four hours from noon UTC."""
    provider = OddsApiProvider(environment={}, regions=REGIONS)
    assert len(ALL_PROP_KEYS) == 7
    assert provider.region_count == 2
    assert hist.estimate_credits(
        events=1, markets=len(ALL_PROP_KEYS), regions=provider.region_count
    ) == PER_EVENT
    assert hist.MINIMUM_PROBES_FOR_ABSENCE == 5
    assert [event["id"] for event in _selected()] == [
        f"{DAY}-evt{index:02d}" for index in range(5)
    ]
    noon = datetime.fromisoformat(f"{DAY}T12:00:00+00:00")
    for event in _slate(DAY, 7):
        when = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
        assert noon <= when.astimezone(timezone.utc) < noon + timedelta(days=1)


# -- a cap that affords nothing buys nothing ------------------------------


def test_the_workflows_default_cap_probes_nothing_it_cannot_afford(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The finding's replay: cap 60, seven games, 107 an event. It sent five
    requests and spent 536. One uncached event is gated at 140, so 60 affords
    none, and the retention record it would have replaced is kept."""
    _assert_the_arithmetic()
    out = tmp_path / "out"
    out.mkdir()
    kept = out / "historical_props_retention.json"
    kept.write_text('{"events_probed": 2723}\n', encoding="utf-8")
    fake = _Historical(charge=107)

    code = _probe(tmp_path, monkeypatch, fake, cap=60)
    printed = capsys.readouterr()

    assert fake.asked == [], "no per-event request fits inside a cap of 60"
    assert fake.billed == 1 <= 60, "the day's listing, and nothing more"
    assert code == 2
    assert kept.read_text(encoding="utf-8") == '{"events_probed": 2723}\n'
    assert "Total spend this run: 1 credit(s), against a cap of 60." in printed.out
    assert "5 event(s) skipped for budget" in printed.out + printed.err


def test_the_listing_is_paid_out_of_the_same_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cap of 140 is exactly one event at the documented rate, and the
    listing has already taken one credit of it. Leaving the listing out of the
    budget would buy that event and bill 141."""
    fake = _Historical(charge=PER_EVENT)

    code = _probe(tmp_path, monkeypatch, fake, cap=PER_EVENT)

    assert fake.asked == []
    assert fake.billed == 1 <= PER_EVENT
    assert code == 2


# -- the two gates ----------------------------------------------------------


def test_the_cap_admits_only_what_the_estimate_affords(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cap 300 leaves 299 after the listing: two events at 140. The last
    selected event is already bought, so it is read for nothing after the
    two it could not afford were skipped."""
    selected = _selected()
    _cache(tmp_path, selected[4])
    fake = _Historical(charge=107)

    code = _probe(tmp_path, monkeypatch, fake, cap=300)
    printed = capsys.readouterr()

    assert fake.asked == [selected[0]["id"], selected[1]["id"]]
    assert fake.billed == 1 + 2 * 107 == 215 <= 300
    record = _record(tmp_path)
    assert record["events_probed"] == 3
    assert record["events_from_cache"] == 1
    assert record["events_skipped_for_budget"] == 2
    assert record["events_selected"] == 5
    assert record["credit_cap"] == 300
    assert record["credits_spent"] == 215
    assert "Total spend this run: 215 credit(s), against a cap of 300." in printed.out
    # Cut short by the cap: the record says so, and so does the exit code.
    assert code == 3


def test_a_charge_above_the_estimate_stops_on_measured_spend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Billed 400 an event against an estimate of 140, capped at 1,001.

    The estimate alone admits all five (700 <= 1,000) and bills 2,001.
    Projected at the dearest charge seen, a third request would take the
    running total to 1,200, past the cap, so it is never started; the event
    already bought beyond it is still read."""
    selected = _selected()
    _cache(tmp_path, selected[4])
    fake = _Historical(charge=400)
    assert 5 * PER_EVENT <= 1000 and 1 + 4 * 400 > 1001

    code = _probe(tmp_path, monkeypatch, fake, cap=1001)
    printed = capsys.readouterr()

    assert fake.asked == [selected[0]["id"], selected[1]["id"]]
    assert fake.billed == 801 <= 1001
    assert "MEASURED" in printed.out + printed.err
    record = _record(tmp_path)
    assert record["events_probed"] == 3
    assert record["events_skipped_for_budget"] == 2
    assert record["credits_spent"] == 801
    assert code == 3


def test_a_failed_request_is_charged_the_worst_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A request that failed may still have cost quota. Counted as free, a run
    of failures walks past its cap: here all five would be asked."""
    fake = _Historical(fail=True)

    code = _probe(tmp_path, monkeypatch, fake, cap=300)

    assert len(fake.asked) == 2
    assert code != 0


def test_the_estimate_carries_the_region_factor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Billed one credit a request, so measured spend can never stop the run
    and the estimate alone decides: 140 an event at two regions admits two
    under 299; seventy at one region would admit four."""
    fake = _Historical(charge=1)

    _probe(tmp_path, monkeypatch, fake, cap=300)

    assert len(fake.asked) == 2
    assert fake.billed == 3


# -- what a cap that covers the probe does ---------------------------------


def test_a_cap_that_covers_the_probe_probes_every_selected_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """701 is five events at 140 plus the listing, exactly. The whole probe
    fits, so it runs as before and exits 0."""
    fake = _Historical(charge=107)

    code = _probe(tmp_path, monkeypatch, fake, cap=701)
    printed = capsys.readouterr()

    assert fake.asked == [event["id"] for event in _selected()]
    assert fake.billed == 1 + 5 * 107 == 536 <= 701
    assert code == 0
    record = _record(tmp_path)
    assert record["events_probed"] == 5
    assert record["events_skipped_for_budget"] == 0
    assert record["credits_spent"] == 536
    assert record["credit_cap"] == 701
    assert "Total spend this run: 536 credit(s), against a cap of 701." in printed.out


def test_an_event_already_bought_costs_nothing_under_any_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The listing and all five events are on disk. A cap of one affords no
    purchase, and none is needed: the probe is answered from the cache."""
    raw = tmp_path / "raw"
    listing = hist._cache_path("events", f"{DAY}T12:00:00Z", raw_dir=raw)
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text(json.dumps({"data": _slate(DAY, 7)}), encoding="utf-8")
    for event in _selected():
        _cache(tmp_path, event)
    fake = _Historical(charge=107)

    code = _probe(tmp_path, monkeypatch, fake, cap=1)

    assert fake.listings == [] and fake.asked == [] and fake.billed == 0
    assert code == 0
    record = _record(tmp_path)
    assert record["events_probed"] == 5
    assert record["events_from_cache"] == 5
    assert record["credits_spent"] == 0


# -- the listing, on both paths ---------------------------------------------


@pytest.mark.parametrize("probe", [True, False], ids=["probe", "buy"])
def test_listing_a_wide_window_stops_at_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, probe: bool
) -> None:
    """A day's listing costs a credit and was paid for before the cap was
    read, so thirty-one days spent thirty-one credits against a cap of ten
    whatever else the run did."""
    fake = _Historical(charge=107)
    module = _script(monkeypatch, fake)

    module.main(
        [
            *(["--probe"] if probe else []),
            "--live",
            "--from", "2025-10-01", "--to", "2025-10-31",
            "--credit-cap", "10",
            *_dirs(tmp_path),
        ]
    )

    assert fake.billed <= 10, f"billed {fake.billed} against a cap of 10"
    assert len(fake.listings) == 10
    assert fake.asked == []


def test_a_failed_listing_is_held_against_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A listing that failed may still have cost its credit. Held against the
    cap at the worst case, as a failed purchase is, a month of failures under
    a cap of ten asks ten days; counted as free, it asked all thirty-one."""
    fake = _Historical(listing_fail=True)
    module = _script(monkeypatch, fake)

    module.main(
        [
            "--live",
            "--from", "2025-10-01", "--to", "2025-10-31",
            "--credit-cap", "10",
            *_dirs(tmp_path),
        ]
    )

    assert len(fake.listings) == 10
    assert fake.billed <= 10
    assert fake.asked == []


def test_a_failed_listing_leaves_less_for_the_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two days' listings fail and still bill their credit; the third answers.
    Three credits are held of 142, which leaves 139: not one event at 140.
    Leaving the failures out of the budget would buy one and bill 143."""
    fake = _Historical(
        charge=PER_EVENT, listing_fail={"2025-10-06", "2025-10-07"}
    )

    code = _probe(
        tmp_path, monkeypatch, fake, cap=142, start="2025-10-06", end=DAY
    )

    assert fake.listings == ["2025-10-06", "2025-10-07", DAY]
    assert fake.asked == []
    assert fake.billed == 3 <= 142
    assert code == 2


def test_a_listing_already_on_disk_is_read_past_the_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A cap of ten pays for ten days' listings, and the last day's is
    already bought: it is read for nothing, so its seven games are on the
    slate, and the twenty days between are named as not listed."""
    raw = tmp_path / "raw"
    last = "2025-10-31"
    listing = hist._cache_path("events", f"{last}T12:00:00Z", raw_dir=raw)
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text(json.dumps({"data": _slate(last, 7)}), encoding="utf-8")
    fake = _Historical(charge=107)

    _script(monkeypatch, fake).main(
        [
            "--live",
            "--from", "2025-10-01", "--to", last,
            "--credit-cap", "10",
            *_dirs(tmp_path),
        ]
    )
    printed = capsys.readouterr()

    assert len(fake.listings) == 10 and last not in fake.listings
    assert fake.billed == 10
    assert "77 event(s) found in the window; the listings cost 10 credit(s)." in printed.out
    assert "20 day(s) of the window were not listed" in printed.err


def test_a_listing_billed_above_its_rate_is_projected_at_that_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Listings billed two credits each under a cap of eleven: five fit, and
    a sixth, projected at the two it was charged rather than the documented
    one, would take the total to twelve."""
    fake = _Historical(listing_charge=2)
    module = _script(monkeypatch, fake)

    module.main(
        [
            "--live",
            "--from", "2025-10-01", "--to", "2025-10-31",
            "--credit-cap", "11",
            *_dirs(tmp_path),
        ]
    )

    assert len(fake.listings) == 5
    assert fake.billed == 10 <= 11


# -- the commands the docs tell an operator to run ---------------------------


def _documented_probe_commands() -> list[tuple[str, list[str]]]:
    """Every `buy_historical_props.py --probe ...` command in the script's
    docstring and the README, as argument lists."""
    found: list[tuple[str, list[str]]] = []
    for relative in ("scripts/buy_historical_props.py", "README.md"):
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        joined = re.sub(r"\\\n\s*", " ", text)
        for line in joined.splitlines():
            if "buy_historical_props.py" not in line or "--probe" not in line:
                continue
            words = shlex.split(line.strip())
            script = next(
                index
                for index, word in enumerate(words)
                if word.endswith("buy_historical_props.py")
            )
            found.append((relative, words[script + 1:]))
    return found


def test_the_documented_probe_commands_name_a_window_and_hold_their_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both said `--probe --live --credit-cap 60`, which names no window and
    exits 2 before it looks at anything; the one path that did run, the
    workflow's, spent 536 under that cap."""
    commands = _documented_probe_commands()
    assert {relative for relative, _ in commands} == {
        "scripts/buy_historical_props.py",
        "README.md",
    }, commands

    for index, (relative, argv) in enumerate(commands):
        assert "--live" in argv and "--credit-cap" in argv, (relative, argv)
        cap = int(argv[argv.index("--credit-cap") + 1])
        start = date.fromisoformat(argv[argv.index("--from") + 1])
        fake = _Historical(charge=107)
        run = tmp_path / f"run{index}"

        _script(monkeypatch, fake).main([*argv, *_dirs(run)])

        assert fake.listings == [start.isoformat()], (relative, argv)
        assert fake.billed <= cap, (relative, argv, fake.billed)


def test_the_probe_path_passes_its_cap_to_the_gated_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gates live beside `buy_historical_props` in the provider module,
    so the probe and the buy cannot drift apart again. The script reaches it
    with the budget the listing left: the cap less what the listing cost."""
    seen: dict[str, Any] = {}
    real = hist.probe_retention_under_cap

    def recording(provider: OddsApiProvider, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return real(provider, **kwargs)

    fake = _Historical(charge=107)
    module = _script(monkeypatch, fake)
    monkeypatch.setattr(module.hist, "probe_retention_under_cap", recording)

    module.main(
        [
            "--probe", "--live", "--from", DAY, "--to", DAY,
            "--credit-cap", "500", *_dirs(tmp_path),
        ]
    )

    assert seen["credit_cap"] == 499
    assert [event["event_id"] for event in seen["events"]] == [
        event["id"] for event in _selected()
    ]
    assert list(seen["markets"]) == ALL_PROP_KEYS
    assert len(fake.asked) == 3
    assert fake.billed == 1 + 3 * 107 <= 500
