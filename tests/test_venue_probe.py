"""The low-vig venue probe: one event, capped, and it never leaks the key."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.providers.odds_api import OddsApiProvider


SECRET = "venue-secret-must-not-be-written"
#: A fake id on purpose. A real provider event id is a bare 32-hex string —
#: the shape of the credential — and the secrets scan rightly refuses it.
EVENT = "evt-venue-1"
SNAPSHOT = "2025-01-14T20:10:00Z"
WHICH = ["--event-id", EVENT, "--snapshot", SNAPSHOT]
ENVIRONMENT = {"NHL_ODDS_API_KEY": SECRET}
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_low_vig_venues.py"


def _load():
    spec = importlib.util.spec_from_file_location("_probe_low_vig_venues", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _quote(name: str, point: float, over: int, under: int) -> list[dict]:
    return [
        {"description": name, "name": "Over", "point": point, "price": over},
        {"description": name, "name": "Under", "point": point, "price": under},
    ]


def _event(books: dict[str, dict[str, list[dict]]]) -> dict:
    """A historical per-event response: `data` wraps the event."""
    return {
        "timestamp": "2025-01-14T20:10:00Z",
        "data": {
            "id": EVENT,
            "bookmakers": [
                {
                    "key": book,
                    "markets": [
                        {"key": market, "outcomes": outcomes}
                        for market, outcomes in markets.items()
                    ],
                }
                for book, markets in books.items()
            ],
        },
    }


def _provider(cost: str = "10", remaining: str = "3000000", event: dict | None = None):
    payload = event if event is not None else _event({})
    requester = RecordingRequester(
        {
            "/historical/": FakeResponse(
                payload,
                headers={"x-requests-last": cost, "x-requests-remaining": remaining},
            ),
            "/v4/sports": FakeResponse(
                [], headers={"x-requests-last": "0", "x-requests-remaining": remaining}
            ),
        }
    )
    return OddsApiProvider(environment=ENVIRONMENT, requester=requester), requester


def test_a_dry_run_sends_nothing_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load()
    provider, requester = _provider()

    code = module.main(
        [*WHICH, "--raw-dir", str(tmp_path), "--output-dir", str(tmp_path)],
        provider=provider,
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "Nothing was sent" in out
    assert EVENT in out
    assert "worst case" in out.lower()
    assert requester.calls == []
    assert not any(tmp_path.rglob("*"))


def test_live_without_a_cap_is_refused() -> None:
    module = _load()

    with pytest.raises(SystemExit) as exit_info:
        module.main(["--live"])

    assert exit_info.value.code == 2


def test_no_credential_means_no_request(tmp_path: Path) -> None:
    module = _load()
    requester = RecordingRequester()
    provider = OddsApiProvider(environment={}, requester=requester)

    code = module.main(
        ["--live", "--credit-cap", "100", *WHICH, "--raw-dir", str(tmp_path),
         "--output-dir", str(tmp_path)],
        provider=provider,
    )

    assert code == 2
    assert requester.calls == []


def test_a_venue_with_the_moneyline_and_no_props_is_reported_as_such(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The decisive negative: a book listing h2h and nothing else offers
    nothing for a props opinion to be placed against."""
    module = _load()
    event = _event(
        {
            "pinnacle": {"h2h": [
                {"name": "Anaheim Ducks", "price": 150},
                {"name": "Washington Capitals", "price": -170},
            ]},
            "novig": {
                "h2h": [{"name": "Anaheim Ducks", "price": 148}, {"name": "Washington Capitals", "price": -160}],
                "player_points": _quote("Tom Wilson", 0.5, -105, -105),
            },
        }
    )
    provider, requester = _provider(cost="10", event=event)

    code = module.main(
        ["--live", "--credit-cap", "400", "--regions", "eu", *WHICH,
         "--raw-dir", str(tmp_path), "--output-dir", str(tmp_path)],
        provider=provider,
    )
    out = capsys.readouterr().out

    assert code == 0
    result = json.loads((tmp_path / module.JSON_FILENAME).read_text(encoding="utf-8"))
    assert result["venues"]["pinnacle"]["h2h"] is True
    assert result["venues"]["pinnacle"]["prop_markets"] == {}
    assert result["venues"]["novig"]["h2h"] is True
    assert "player_points" in result["venues"]["novig"]["prop_markets"]
    assert result["venues"]["novig"]["prop_markets"]["player_points"]["n_two_sided"] == 1
    assert "novig" in result["verdict"]
    assert "novig" in out
    # -105 / -105 is a 2.44% two-sided margin.
    margin = result["venues"]["novig"]["prop_markets"]["player_points"]["median_margin"]
    assert abs(margin - 0.0244) < 0.001


def test_nothing_returned_is_the_decisive_negative(tmp_path: Path) -> None:
    module = _load()
    provider, _ = _provider(cost="0", event=_event({}))

    module.main(
        ["--live", "--credit-cap", "400", "--regions", "eu", *WHICH,
         "--raw-dir", str(tmp_path), "--output-dir", str(tmp_path)],
        provider=provider,
    )

    result = json.loads((tmp_path / module.JSON_FILENAME).read_text(encoding="utf-8"))
    assert result["spent"] == 0
    assert "cannot carry the props model" in result["verdict"]


def test_the_cap_is_enforced_against_measured_spend_before_each_call(
    tmp_path: Path,
) -> None:
    """Every call reports 60 credits. With a cap of 100 the first props call
    (worst case 70) starts, the h2h after it (60 + 10) starts, and the third
    (120 + 70) must not: a request that might breach the cap is never sent."""
    module = _load()
    provider, requester = _provider(cost="60", event=_event({}))

    module.main(
        ["--live", "--credit-cap", "100", "--regions", "eu,uk", *WHICH,
         "--raw-dir", str(tmp_path), "--output-dir", str(tmp_path)],
        provider=provider,
    )

    result = json.loads((tmp_path / module.JSON_FILENAME).read_text(encoding="utf-8"))
    live = [c for c in result["calls"] if "measured_cost" in c]
    skipped = [c for c in result["calls"] if "skipped" in c]
    assert len(live) == 2, [c["step"] for c in live]
    assert result["spent"] == 120
    assert skipped and all("would breach the cap" in c["skipped"] for c in skipped)
    # The quota listing plus exactly the two live calls.
    assert len([u for u in requester.urls if "/historical/" in u]) == 2


def test_a_short_quota_stops_the_probe_before_it_asks(tmp_path: Path) -> None:
    module = _load()
    provider, requester = _provider(remaining="50", event=_event({}))

    code = module.main(
        ["--live", "--credit-cap", "400", *WHICH, "--raw-dir", str(tmp_path),
         "--output-dir", str(tmp_path)],
        provider=provider,
    )

    assert code == 3
    assert not any("/historical/" in u for u in requester.urls)


def test_the_credential_never_reaches_disk_or_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load()
    event = _event({"novig": {"player_points": _quote("Tom Wilson", 0.5, -110, -110)}})
    provider, _ = _provider(event=event)

    module.main(
        ["--live", "--credit-cap", "400", "--regions", "eu", *WHICH,
         "--raw-dir", str(tmp_path), "--output-dir", str(tmp_path)],
        provider=provider,
    )
    out = capsys.readouterr()

    assert SECRET not in out.out and SECRET not in out.err
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SECRET not in path.read_text(encoding="utf-8"), path


def test_the_reference_comparison_reads_the_stores_own_cache(tmp_path: Path) -> None:
    """When the raw cache holds the same event at the same snapshot, the
    verdict compares margins like with like. When it does not, it says so
    rather than comparing against nothing."""
    module = _load()
    cache = tmp_path / "historical_props"
    cache.mkdir(parents=True)
    compact = SNAPSHOT.replace("-", "").replace(":", "")
    (cache / f"{EVENT}_{compact}.json").write_text(
        json.dumps(_event({"draftkings": {"player_points": _quote("Tom Wilson", 0.5, -115, -115)}})),
        encoding="utf-8",
    )
    event = _event({"novig": {"player_points": _quote("Tom Wilson", 0.5, -105, -105)}})
    provider, _ = _provider(event=event)

    module.main(
        ["--live", "--credit-cap", "400", "--regions", "eu", *WHICH,
         "--raw-dir", str(tmp_path), "--output-dir", str(tmp_path)],
        provider=provider,
    )

    result = json.loads((tmp_path / module.JSON_FILENAME).read_text(encoding="utf-8"))
    assert result["reference"]["available"] is True
    assert "draftkings" in result["reference"]["books"]
    assert "against the store's best" in result["verdict"]
    assert "points" in result["verdict"]


def test_the_event_is_never_a_literal_but_comes_from_the_cache_or_the_caller(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A provider event id is a bare 32-hex string, the shape of the key, and
    the secrets scan cannot tell them apart. So the script carries none:
    it reads the raw cache, or it is told. With neither, it refuses."""
    module = _load()
    provider, requester = _provider()

    code = module.main(
        ["--live", "--credit-cap", "400", "--raw-dir", str(tmp_path),
         "--output-dir", str(tmp_path)],
        provider=provider,
    )

    assert code == 2
    assert "No event to ask about" in capsys.readouterr().err
    assert requester.calls == []

    cache = tmp_path / "historical_props"
    cache.mkdir(parents=True)
    hexid = "0123456789abcdef" * 2
    (cache / f"{hexid}_20250114T201000Z.json").write_text("{}", encoding="utf-8")
    (cache / f"{hexid}_20250114T201000Z_8785e9c0.json").write_text("{}", encoding="utf-8")
    (cache / f"{'fedcba9876543210' * 2}_20241001T160000Z.json").write_text("{}", encoding="utf-8")

    code = module.main(["--list-events", "--raw-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "2 cached event(s)" in out, "two ids, whatever the hash suffix"
    assert out.index(hexid) < out.index("fedcba"), "newest snapshot first"
    assert "--snapshot 2025-01-14T20:10:00Z" in out

    code = module.main(["--raw-dir", str(tmp_path), "--output-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert f"event {hexid} at 2025-01-14T20:10:00Z" in out, "defaults to the newest"
