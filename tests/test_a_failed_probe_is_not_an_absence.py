"""A retention probe whose request failed was counted as an event that did not see any market.

`probe_retention` catches a `ProviderError` (an HTTP 503, a 401 from a key out
of quota, a timeout) and returns the probe with `error` set, `markets_requested`
still filled and `markets_returned` empty. A 200 whose body is not a JSON object
comes back the same way. `_retention_by_market` never read `error`, so a request
that got no answer counted as an event that asked for every market and saw
none. `retention_table` then printed "not offered in any of N events", and
`unmeasurable_markets` wrote "cannot be measured against real prices".
`buy_historical_props.py --probe --live` appended every probe, wrote the
retention file over whatever it held, and exited 0.

Found by the failure-shape audit and confirmed by 3 of 3 refuters. They
replayed the real `main()` with only the transport stubbed, on
`--probe --live --from 2025-01-14 --to 2025-01-14 --credit-cap 600`. The listing
answered with six games and every per-event request answered HTTP 503:

* "Probe failed: ... HTTP 503" was printed five times.
* The table then gave all 7 markets as "**not offered in any of 5 events**".
* The file recorded `events_probed` 5, `markets_seen` [] and 7 unmeasurable
  markets.
* The script spent 1 credit and exited 0.

The same happened with the listing cached and a 401 on every event, at 0
credits. A partial outage crossed the floor as well. Two answers without
`player_goals` plus three 503s wrote `goals` as "Not offered on any of 5 probed
events", when two answered events are below the floor of five. One answer plus
four 503s named three markets unmeasurable.

The false verdicts reached the reports. The Historical Props Purchase workflow
runs `run_player_props_backtest.py` (`if: always()`), and that script reads this
file. Over the real store, the late contract report listed `hits` under "Named
as unmeasurable ... no price-based evidence at all", although the card window
of the same run had measured it at 5,207 bets. The report also blamed the six
measured markets' verdict on "a narrower set of books". A local probe
overwrote the cache-derived record (2,723 events, `unmeasurable` {}), which
every later local backtest reads.

What these tests hold:

* A failed probe counts neither as an event probed nor as an absence.
  Absence and the floor count only probes that got an answer. The table says
  how many requests failed, and a probe in which every request failed reads as
  **unknown**.
* An answered event still counts. Five answers that never carried a market
  still call it not offered, whatever else failed beside them.
* `buy_historical_props.py --probe` writes nothing and exits 2 when any probe
  request failed. An existing record is left byte for byte. The answered
  responses are already in the raw cache, so a re-run asks again only for
  the ones that failed. A probe that every event answered still writes its
  record and exits 0.
* The workflow's own "Probe retention" step, run under `bash -eo pipefail`,
  goes red on that exit. It carries no `continue-on-error` that would turn the
  run green again.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.markets import PROP_MARKETS
from nhl_betting_lab.providers import historical_props as hist
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult
from nhl_betting_lab.providers.odds_api import OddsApiProvider
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "historical-props-purchase.yml"

#: Every prop market, as the probe asks for them by default.
ALL = tuple(market.provider_key for market in PROP_MARKETS)
SOG = "player_shots_on_goal"
GOALS = "player_goals"
HITS = "player_hits"

#: What `OddsApiProvider._get` raises on a 503, as a probe records it.
OUTAGE = "The odds provider returned HTTP 503. No staging file was written."

#: The finding's window: one night, six games on the board.
NIGHT = "2025-01-14"

#: Never a real credential, and never sent anywhere: the transport is a stub.
ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}

#: What the retention record held before the probe: the cache-derived one.
KEPT = '{"events_probed": 2723, "unmeasurable": {}}\n'


@pytest.fixture(autouse=True)
def _no_checkout_data(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Nothing here reads or writes the checkout's data/ tree.

    Every run below names its own directories. `historical_props` binds
    `RAW_DIR` at import, so it is pointed away too, and must stay unused.
    """
    point_default_data_dirs_at(
        monkeypatch, tmp_path_factory.mktemp("checkout_defaults")
    )
    stray = tmp_path_factory.mktemp("stray") / "default-raw-dir-must-stay-empty"
    monkeypatch.setattr(hist, "RAW_DIR", stray)
    yield
    assert not stray.exists()


def _row(table: str, market: str) -> str:
    rows = [line for line in table.splitlines() if line.startswith(f"| `{market}` |")]
    assert len(rows) == 1, table
    return rows[0]


def _answered(index: int, returned: tuple[str, ...]) -> hist.RetentionProbe:
    return hist.RetentionProbe(
        event_id=f"answered{index}",
        snapshot="2025-01-14T20:00:00Z",
        markets_requested=ALL,
        markets_returned=returned,
    )


def _failed(index: int, error: str = OUTAGE) -> hist.RetentionProbe:
    """What `probe_retention` returns when its request raised."""
    return hist.RetentionProbe(
        event_id=f"failed{index}",
        snapshot="2025-01-14T20:00:00Z",
        markets_requested=ALL,
        error=error,
    )


# --------------------------------------------------------------------------
# The retention table and the unmeasurable list.
# --------------------------------------------------------------------------


def test_a_probe_whose_every_request_failed_calls_no_market_absent() -> None:
    """The finding's case: five 503s were "not offered in any of 5 events"."""
    probes = [_failed(index) for index in range(hist.MINIMUM_PROBES_FOR_ABSENCE)]

    table = hist.retention_table(probes)

    assert hist.unmeasurable_markets(probes) == {}, (
        "a request that got no answer wrote 'cannot be measured' for every market"
    )
    assert "not offered" not in table
    assert "**unknown**" in table
    assert f"All {len(probes)} retention probe request(s) failed" in table
    assert hist.events_probed(probes) == 0


def test_a_partial_outage_cannot_clear_the_absence_floor() -> None:
    """Two answers without goals and three 503s are two events, not five."""
    returned = tuple(market for market in ALL if market != GOALS)
    probes = [_answered(0, returned), _answered(1, returned)] + [
        _failed(index) for index in range(3)
    ]

    table = hist.retention_table(probes)

    assert _row(table, GOALS) == (
        f"| `{GOALS}` | 2 | 0 | not seen in 2 event(s) — too few to call it "
        "absent |"
    )
    assert _row(table, SOG) == f"| `{SOG}` | 2 | 2 | measurable (2/2) |", (
        "a failed request is not an event that asked"
    )
    assert hist.unmeasurable_markets(probes) == {}
    assert hist.events_probed(probes) == 2
    assert "Only 2 event(s) probed." in table
    assert (
        "3 probe request(s) failed and are counted neither as probed nor as "
        "not seen"
    ) in table
    assert "responses were read" not in table, (
        "five probes over two answered events are not responses per event"
    )


def test_answered_events_still_carry_an_absence_past_a_failure() -> None:
    """A failure removes no evidence either: five answers are still five."""
    returned = tuple(market for market in ALL if market != HITS)
    events = hist.MINIMUM_PROBES_FOR_ABSENCE
    probes = [_answered(index, returned) for index in range(events)] + [
        _failed(0),
        _failed(1),
    ]

    table = hist.retention_table(probes)
    missing = hist.unmeasurable_markets(probes)

    assert _row(table, HITS) == (
        f"| `{HITS}` | {events} | 0 | **not offered in any of {events} events** |"
    )
    assert _row(table, SOG) == (
        f"| `{SOG}` | {events} | {events} | measurable ({events}/{events}) |"
    )
    assert set(missing) == {HITS}
    assert f"any of {events} probed events" in missing[HITS]


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(FakeResponse(status_code=503), id="http-503"),
        pytest.param(FakeResponse(status_code=401), id="http-401-out-of-quota"),
        pytest.param(FakeResponse(["not", "an", "object"]), id="not-an-object"),
    ],
)
def test_a_failed_request_through_the_real_probe_is_not_an_absence(
    tmp_path: Path, response: FakeResponse
) -> None:
    """Both of `probe_retention`'s failure paths, through the real function."""
    provider = OddsApiProvider(
        regions="us",
        environment=ENVIRONMENT,
        requester=RecordingRequester({"/historical/": response}),
    )
    probes = [
        hist.probe_retention(
            provider,
            event_id=f"evt{index}",
            snapshot="2025-01-14T20:00:00Z",
            raw_dir=tmp_path,
        )
        for index in range(hist.MINIMUM_PROBES_FOR_ABSENCE)
    ]

    assert all(probe.error for probe in probes)
    assert hist.unmeasurable_markets(probes) == {}
    assert "not offered" not in hist.retention_table(probes)


# --------------------------------------------------------------------------
# The purchase script, driven through main() over a stub transport.
# --------------------------------------------------------------------------


def _event_id(index: int) -> str:
    return f"{index + 1:032x}"


def _listing(count: int) -> dict:
    return {
        "timestamp": f"{NIGHT}T12:00:00Z",
        "data": [
            {
                "id": _event_id(index),
                "sport_key": "icehockey_nhl",
                "commence_time": f"2025-01-15T0{index}:00:00Z",
                "home_team": "Toronto Maple Leafs",
                "away_team": "Boston Bruins",
            }
            for index in range(count)
        ],
    }


def _odds(event_id: str, markets: tuple[str, ...]) -> dict:
    return {
        "timestamp": "2025-01-14T20:00:00Z",
        "data": {
            "id": event_id,
            "commence_time": "2025-01-15T00:00:00Z",
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": market,
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Auston Matthews",
                                    "price": -115,
                                    "point": 0.5,
                                }
                            ],
                        }
                        for market in markets
                    ],
                }
            ],
        },
    }


class Transport:
    """The provider as the wire sees it: a listing, then one call per event.

    `answer(position)` decides each per-event request in the order asked:
    a tuple of markets is a 200 carrying them, and None is an HTTP 503.
    """

    def __init__(
        self, events: int, answer: Callable[[int], tuple[str, ...] | None]
    ) -> None:
        self.events = events
        self.answer = answer
        self.per_event = 0
        self.listings = 0

    def __call__(self, url: str, **_kwargs: Any) -> FakeResponse:
        if "/odds" in url:
            position = self.per_event
            self.per_event += 1
            markets = self.answer(position)
            if markets is None:
                return FakeResponse(status_code=503)
            event_id = url.split("/events/")[1].split("/")[0]
            return FakeResponse(
                _odds(event_id, markets), headers={"x-requests-last": "60"}
            )
        if url.endswith("/events"):
            self.listings += 1
            return FakeResponse(
                _listing(self.events), headers={"x-requests-last": "1"}
            )
        return FakeResponse(status_code=404)


def _probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transport: Transport,
    *extra: str,
) -> tuple[int, str, str]:
    """The real `main()`, with the workflow's probe flags, over the stub."""
    from test_scripts import load_script

    module = load_script("buy_historical_props.py")
    real = OddsApiProvider
    monkeypatch.setattr(
        module,
        "OddsApiProvider",
        lambda: real(environment=ENVIRONMENT, requester=transport, regions="us"),
    )
    # No `.env` is read, whatever the checkout holds.
    monkeypatch.setattr(
        module,
        "load_provider_env",
        lambda: ProviderEnvLoadResult(path=tmp_path / ".env"),
    )
    capture = _Capture()
    with capture:
        code = module.main(
            [
                "--probe",
                "--live",
                "--from",
                NIGHT,
                "--to",
                NIGHT,
                "--credit-cap",
                "600",
                "--raw-dir",
                str(tmp_path / "raw"),
                "--processed-dir",
                str(tmp_path / "processed"),
                "--output-dir",
                str(tmp_path / "outputs"),
                *extra,
            ]
        )
    return code, capture.out, capture.err


class _Capture:
    """stdout and stderr of one call."""

    def __enter__(self) -> "_Capture":
        import io

        self._out, self._err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        return self

    def __exit__(self, *exc: object) -> bool:
        self.out, self.err = sys.stdout.getvalue(), sys.stderr.getvalue()
        sys.stdout, sys.stderr = self._out, self._err
        return False


def _retention(tmp_path: Path) -> Path:
    return tmp_path / "outputs" / "historical_props_retention.json"


def _seed(tmp_path: Path) -> Path:
    path = _retention(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(KEPT.encode("utf-8"))
    return path


def test_an_outage_probe_leaves_the_retention_record_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The finding's replay: six games listed, every per-event request 503."""
    kept = _seed(tmp_path)
    transport = Transport(6, lambda position: None)

    code, out, err = _probe(tmp_path, monkeypatch, transport)

    assert transport.per_event == hist.MINIMUM_PROBES_FOR_ABSENCE
    assert code == 2, "an outage probe exited 0 and overwrote the record"
    assert kept.read_bytes() == KEPT.encode("utf-8")
    assert out.count("Probe failed") == 5
    assert "not offered" not in out
    assert "5 of 5 probe request(s) failed" in err
    assert "left as it is" in err


def test_a_partial_outage_probe_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two answers without goals, then three 503s: two events, not five."""
    returned = tuple(market for market in ALL if market != GOALS)
    transport = Transport(6, lambda position: returned if position < 2 else None)

    code, out, err = _probe(tmp_path, monkeypatch, transport)

    assert code == 2
    assert not _retention(tmp_path).exists(), (
        "a probe that failed must not write a record, even where none stood"
    )
    assert _row(out, GOALS) == (
        f"| `{GOALS}` | 2 | 0 | not seen in 2 event(s) — too few to call it "
        "absent |"
    )
    assert "3 of 5 probe request(s) failed" in err


def test_a_failure_beside_enough_answers_still_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Five answers clear the floor; the sixth request failing is still a
    degraded probe, and its answers are already in the raw cache, so a
    re-run asks again only for the one that failed."""
    kept = _seed(tmp_path)
    returned = tuple(market for market in ALL if market != HITS)
    transport = Transport(6, lambda position: returned if position < 5 else None)

    code, out, err = _probe(tmp_path, monkeypatch, transport, "--probe-events", "6")

    assert transport.per_event == 6
    assert code == 2
    assert kept.read_bytes() == KEPT.encode("utf-8")
    assert "1 of 6 probe request(s) failed" in err
    cached = sorted((tmp_path / "raw" / hist.CACHE_DIRNAME).glob("0*.json"))
    assert len(cached) == 5, "the answered responses are kept for the re-run"

    # The refusal says a re-run asks again only for what failed. It does:
    # the same command, once the provider answers, makes one request.
    rerun = Transport(6, lambda position: returned)
    code, out, err = _probe(tmp_path, monkeypatch, rerun, "--probe-events", "6")

    assert rerun.per_event == 1
    assert rerun.listings == 0, "the listing was cached by the first run"
    assert code == 0, err
    record = json.loads(kept.read_text(encoding="utf-8"))
    assert record["events_probed"] == 6
    assert set(record["unmeasurable"]) == {"hits"}


def test_a_probe_every_event_answered_still_writes_its_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: nothing failed, so the record is written as before."""
    kept = _seed(tmp_path)
    returned = tuple(market for market in ALL if market != HITS)
    transport = Transport(6, lambda position: returned)

    code, out, err = _probe(tmp_path, monkeypatch, transport)

    assert code == 0, err
    record = json.loads(kept.read_text(encoding="utf-8"))
    assert record["events_probed"] == 5
    assert record["unmeasurable"] == {
        "hits": (
            "Not offered on any of 5 probed events, so it cannot be measured "
            "against real prices."
        )
    }
    assert record["markets_seen"] == sorted(returned)
    assert "failed" not in err


# --------------------------------------------------------------------------
# The workflow step that runs it.
# --------------------------------------------------------------------------


def _probe_step() -> dict:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == "Probe retention":
                return step
    raise AssertionError("no Probe retention step")


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions a test names; refuse any it did not."""

    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]

    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


#: Stands in for `python` on the runner: the real interpreter, running the
#: real script, with only the transport and the default directories swapped.
SHIM = textwrap.dedent(
    """
    import os, runpy, sys
    from pathlib import Path

    scratch = Path(os.environ["PROBE_SCRATCH"])
    from nhl_betting_lab import config
    config.RAW_DIR = scratch / "raw"
    config.PROCESSED_DIR = scratch / "processed"
    config.OUTPUTS_DIR = scratch / "outputs"
    from nhl_betting_lab.providers import env_file, odds_api
    env_file.load_provider_env = lambda *a, **k: env_file.ProviderEnvLoadResult(
        path=scratch / ".env"
    )
    answer = os.environ["PROBE_ANSWER"]
    commence = [f"2025-01-15T0{index}:00:00Z" for index in range(6)]

    class Response:
        def __init__(self, payload=None, status=200, headers=None):
            self._payload, self.status_code = payload, status
            self.headers = headers or {}

        def json(self):
            return self._payload

    def requester(url, **kwargs):
        if "/odds" in url:
            if answer == "outage":
                return Response(status=503)
            event_id = url.split("/events/")[1].split("/")[0]
            return Response(
                {"timestamp": "2025-01-14T20:00:00Z", "data": {
                    "id": event_id, "commence_time": commence[0],
                    "home_team": "Toronto Maple Leafs",
                    "away_team": "Boston Bruins",
                    "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                        "markets": [{"key": "player_points", "outcomes": [
                            {"name": "Over", "description": "Auston Matthews",
                             "price": -115, "point": 0.5}]}]}]}},
                headers={"x-requests-last": "10"},
            )
        if url.endswith("/events"):
            return Response(
                {"timestamp": "2025-01-14T12:00:00Z", "data": [
                    {"id": f"{index + 1:032x}", "commence_time": when,
                     "home_team": "Toronto Maple Leafs",
                     "away_team": "Boston Bruins"}
                    for index, when in enumerate(commence)]},
                headers={"x-requests-last": "1"},
            )
        return Response(status=404)

    odds_api._default_requester = requester
    script = Path(sys.argv[1])
    if not script.is_absolute():
        script = Path(os.environ["PROBE_PROJECT_ROOT"]) / script
    sys.argv = [str(script), *sys.argv[2:]]
    runpy.run_path(str(script), run_name="__main__")
    """
)


def _run_probe_step(tmp_path: Path, answer: str) -> subprocess.CompletedProcess:
    step = _probe_step()
    block = _render(
        step["run"],
        {
            "inputs.start_date": NIGHT,
            # Five uncached events at 7 markets x 2 regions x 10 = 140 each,
            # plus 1 for the day's listing. This read "60" while the probe
            # ignored its cap; held to it, 60 affords no uncached event and
            # the step would send no request at all.
            "inputs.credit_cap": "701",
            "inputs.hours_before": "4",
        },
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = tmp_path / "shim.py"
    shim.write_text(SHIM, encoding="utf-8")
    python = bin_dir / "python"
    python.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{shim}" "$@"\n', encoding="utf-8"
    )
    python.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"NHL_ODDS_API_KEY", "PYTHONPATH"}
    }
    env.update(
        {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
            "PYTHONSAFEPATH": "1",
            "PROBE_SCRATCH": str(tmp_path / "scratch"),
            "PROBE_PROJECT_ROOT": str(PROJECT_ROOT),
            "PROBE_ANSWER": answer,
        }
    )
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_an_outage_probe_turns_the_purchase_run_red(tmp_path: Path) -> None:
    """The dispatch that printed a false table used to finish green."""
    step = _probe_step()
    assert not step.get("continue-on-error"), (
        "a probe that exits 2 must fail the run, not be absorbed by the step"
    )

    result = _run_probe_step(tmp_path, "outage")

    assert result.returncode != 0, result.stdout + result.stderr
    assert "probe request(s) failed" in result.stderr
    assert not (
        tmp_path / "scratch" / "outputs" / "historical_props_retention.json"
    ).exists()


def test_a_probe_every_event_answered_keeps_the_run_green(tmp_path: Path) -> None:
    result = _run_probe_step(tmp_path, "answered")

    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(
        (
            tmp_path / "scratch" / "outputs" / "historical_props_retention.json"
        ).read_text(encoding="utf-8")
    )
    assert record["events_probed"] == 5
