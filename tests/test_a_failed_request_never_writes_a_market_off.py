"""The market probe wrote off any market whose request failed as "not a market at all".

`scripts/discover_nhl_markets.py` asks the provider about 43 candidate
markets one at a time, on one event, so that no market is recorded as
unavailable on bad evidence: its docstring says "a market that answers is
served; a market that 422s is not". Its loop did not check for a 422. It
caught every `ProviderError` the same way, put the market in `refused`,
wrote that list to `nhl_market_discovery.json` as `not_a_market`, counted it
in the summary line as "not a market at all", and returned 0. `_get` raised
the same bare `ProviderError` for a 422, a 503, a 429, a 500, a 401 and a
read timeout, with no status on it, so the loop could not have told them
apart if it had tried.

Found by the failure-shape audit (confirmed by 3 of 3 refuters: reproduce,
reachability, intent), replayed through the real `main()` with only the
transport stubbed:

* alternate_spreads 503, player_points 429, player_goals 500, player_hits a
  read timeout, and totals_p1 a genuine 422 gave
  `not_a_market: [alternate_spreads, totals_p1, player_points, player_goals,
  player_hits]`, "38 priced now, 0 valid but unpriced, 5 not a market at
  all. 76 credits spent.", and exit 0;
* a 401 (out of credits) from the 21st request on gave "20 priced now, 0
  valid but unpriced, 23 not a market at all": every player market written
  off, exit 0;
* an account already at zero credits gave "0 priced now, 0 valid but
  unpriced, 43 not a market at all", `h2h` itself recorded as not a market,
  exit 0.

Provider Market Discovery runs the probe as a continue-on-error step and
prints the JSON into the run summary under "### Markets the provider
serves"; `docs/periphery_markets_decision.md` rests its deferred-market
decisions on this probe. A green step with a live market listed as "not a
market" is the write-off that workflow exists to prevent.

What these tests hold, driving the real `main()` with a real
`OddsApiProvider` over a stub transport (no network, no credential, no
`.env`), and the workflow's own summary step under `bash -eo pipefail`:

* only a 422 is a verdict that a market does not exist, and only once `h2h`
  — the one market every sport serves — has been answered on the same event:
  a 422 on `h2h` itself, or before `h2h` answered, is the provider refusing
  the request, not the market;
* every other failure — 5xx, a timeout, a dropped connection, unreadable
  JSON, and a 422 the control does not vouch for — is recorded under
  `not_answered` with its reason, and is never counted as "not a market";
* a 401 or a 429 stops the probe, because every request after it would fail
  the same way, and the markets it never asked are listed under `not_asked`
  rather than written off; a credit-cap stop lists them there too;
* the script exits 4 whenever any candidate has no verdict, so the step's
  outcome is `failure`, the JSON is still written, and the run summary says
  the probe is incomplete; a probe that got a verdict for every candidate
  still exits 0;
* `ProviderError` carries the HTTP status (`None` when the provider was never
  reached), so nothing has to match on text.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import requests
import yaml

from conftest import FakeResponse
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult


SCRIPT = PROJECT_ROOT / "scripts" / "discover_nhl_markets.py"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "provider-market-discovery.yml"

#: Never a real credential, and never sent anywhere: the transport is a stub.
ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}

EVENT_ID = "ev0"

#: The old keys of the discovery record. The fix adds to them; it removes none.
RECORD_KEYS = {
    "event_id", "credits_spent", "served_and_priced", "valid_but_unpriced",
    "not_a_market", "served_but_unmapped",
}


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_script_discover_nhl_markets_failures", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CANDIDATES: tuple[str, ...] = load_script().CANDIDATE_MARKETS


# --------------------------------------------------------------------------
# The provider, as the transport sees it.
# --------------------------------------------------------------------------

def _quoted(market: str) -> FakeResponse:
    """One book pricing the market: a 200 that bills one credit."""
    return FakeResponse(
        {
            "id": EVENT_ID,
            "bookmakers": [{
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [{"key": market, "outcomes": [
                    {"name": "Over", "description": "Skater", "price": -110,
                     "point": 2.5},
                    {"name": "Under", "description": "Skater", "price": -110,
                     "point": 2.5},
                ]}],
            }],
        },
        headers={"x-requests-last": "1"},
    )


def _unquoted(market: str) -> FakeResponse:
    """A valid market nobody is pricing on this event: a free 200."""
    return FakeResponse({"id": EVENT_ID, "bookmakers": []},
                        headers={"x-requests-last": "0"})


def _status(code: int) -> FakeResponse:
    return FakeResponse(status_code=code)


class Transport:
    """The free events list, then one `/events/{id}/odds` answer per market.

    `answers` maps a market to a response, an exception to raise, or a
    callable; any market it does not name is quoted by one book.
    """

    def __init__(self, answers: dict[str, Any] | None = None) -> None:
        self.answers = dict(answers or {})
        self.asked: list[str] = []

    def __call__(self, url: str, **kwargs: Any) -> FakeResponse:
        if url.endswith("/events"):
            return FakeResponse([{
                "id": EVENT_ID, "commence_time": "2026-10-15T23:00:00Z",
                "home_team": "Winnipeg Jets", "away_team": "Colorado Avalanche",
            }])
        if url.endswith(f"/events/{EVENT_ID}/odds"):
            market = kwargs["params"]["markets"]
            self.asked.append(market)
            answer = self.answers.get(market, _quoted)
            if isinstance(answer, BaseException):
                raise answer
            if callable(answer):
                return answer(market)
            return answer
        raise AssertionError(f"unexpected request: {url}")


def _refuse_the_network(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("a test tried to reach the network")


def _probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    transport: Transport,
    *,
    cap: int = 200,
) -> tuple[int, str, dict[str, Any]]:
    """The real script, `--live`, over a stub transport. Nothing leaves."""
    module = load_script()
    real = odds_api.OddsApiProvider
    monkeypatch.setattr(
        module, "OddsApiProvider",
        lambda: real(environment=ENVIRONMENT, requester=transport, regions="us"),
    )
    # No `.env` is read, whatever the checkout holds.
    monkeypatch.setattr(
        module, "load_provider_env",
        lambda: ProviderEnvLoadResult(path=tmp_path / ".env"),
    )
    # Belt and braces: were the stub ever bypassed, this fails, not fetches.
    monkeypatch.setattr(odds_api, "_default_requester", _refuse_the_network)
    monkeypatch.setattr(requests, "get", _refuse_the_network)
    monkeypatch.setattr(requests.Session, "request", _refuse_the_network)

    outputs = tmp_path / "outputs"
    code = module.main([
        "--live", "--credit-cap", str(cap), "--output-dir", str(outputs),
    ])
    captured = capsys.readouterr()
    record = json.loads(
        (outputs / module.DISCOVERY_FILENAME).read_text(encoding="utf-8")
    )
    return code, captured.out + captured.err, record


def _counted_as_not_a_market(output: str) -> int:
    match = re.search(r"(\d+) not a market at all", output)
    assert match, output
    return int(match.group(1))


# --------------------------------------------------------------------------
# What the probe records.
# --------------------------------------------------------------------------

def test_only_a_422_is_recorded_as_not_a_market(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The finding's replay, without the 429 (which stops the probe; see
    below): one genuine 422 among five requests that simply failed."""
    failed = {
        "alternate_spreads": _status(503),
        "player_points": _status(502),
        "player_goals": _status(500),
        "player_hits": requests.ReadTimeout("read timed out"),
        "player_assists": requests.ConnectionError("connection reset"),
        "player_takeaways": FakeResponse(raises=ValueError("not JSON")),
    }
    transport = Transport({**failed, "totals_p1": _status(422)})

    code, output, record = _probe(tmp_path, monkeypatch, capsys, transport)

    assert record["not_a_market"] == ["totals_p1"]
    assert set(record["not_answered"]) == set(failed)
    assert "503" in record["not_answered"]["alternate_spreads"]
    assert "500" in record["not_answered"]["player_goals"]
    assert "ReadTimeout" in record["not_answered"]["player_hits"]
    assert "ConnectionError" in record["not_answered"]["player_assists"]
    assert "unreadable" in record["not_answered"]["player_takeaways"]
    assert record["not_asked"] == []
    assert record["probe_complete"] is False
    assert len(record["served_and_priced"]) == len(CANDIDATES) - 1 - len(failed)
    # Each market asked exactly once: nothing was retried and nothing skipped.
    assert transport.asked == list(CANDIDATES)
    assert _counted_as_not_a_market(output) == 1
    assert f"{len(failed)} asked and not answered" in output
    assert code == 4, "a probe with unanswered markets must not read as clean"


@pytest.mark.parametrize("status", [401, 429])
def test_a_quota_or_rate_limit_stops_the_probe_and_writes_nothing_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], status: int,
) -> None:
    """The finding's quota scenario: the account runs out at the 21st
    request, and every player market after it used to read "not a market"."""
    first = CANDIDATES.index("player_points")
    transport = Transport({market: _status(status) for market in CANDIDATES[first:]})

    code, output, record = _probe(tmp_path, monkeypatch, capsys, transport)

    assert record["not_a_market"] == []
    assert list(record["not_answered"]) == ["player_points"]
    assert f"HTTP {status}" in record["not_answered"]["player_points"]
    assert record["not_asked"] == list(CANDIDATES[first + 1:])
    assert f"HTTP {status}" in record["stopped_because"]
    assert len(record["served_and_priced"]) == first
    # The probe stopped asking: every request after the refusal would have
    # failed the same way.
    assert transport.asked == list(CANDIDATES[: first + 1])
    assert _counted_as_not_a_market(output) == 0
    assert f"{len(CANDIDATES) - first - 1} not asked" in output
    assert code == 4


def test_an_account_with_no_credits_writes_off_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The free events list answers; every odds request is a 401. This used
    to read "0 priced now, 0 valid but unpriced, 43 not a market at all",
    `h2h` included."""
    transport = Transport({market: _status(401) for market in CANDIDATES})

    code, output, record = _probe(tmp_path, monkeypatch, capsys, transport)

    assert record["not_a_market"] == []
    assert record["served_and_priced"] == {}
    assert list(record["not_answered"]) == ["h2h"]
    assert record["not_asked"] == list(CANDIDATES[1:])
    assert record["credits_spent"] == 0
    assert _counted_as_not_a_market(output) == 0
    assert code == 4


def test_a_422_on_h2h_is_the_request_refused_not_every_market(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If the one market every sport serves is refused, a 422 says the
    request is wrong (the event, the regions), not that 43 markets do not
    exist. `h2h` is asked first so that no 422 is read before it answers."""
    assert CANDIDATES[0] == "h2h"
    transport = Transport({market: _status(422) for market in CANDIDATES})

    code, output, record = _probe(tmp_path, monkeypatch, capsys, transport)

    assert record["not_a_market"] == []
    # The record is written with sorted keys, so compare as a set.
    assert set(record["not_answered"]) == set(CANDIDATES)
    assert "h2h" in record["not_answered"]["totals_p1"]
    assert "refusing the request" in record["not_answered"]["h2h"]
    assert _counted_as_not_a_market(output) == 0
    assert code == 4


def test_a_422_before_h2h_has_answered_is_no_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`h2h` timed out, so nothing shows the request itself was good. Other
    markets answering does not vouch for it: only the control does."""
    transport = Transport({
        "h2h": requests.ReadTimeout("read timed out"),
        "totals_p1": _status(422),
    })

    code, output, record = _probe(tmp_path, monkeypatch, capsys, transport)

    assert record["not_a_market"] == []
    assert set(record["not_answered"]) == {"h2h", "totals_p1"}
    assert "422" in record["not_answered"]["totals_p1"]
    assert "spreads" in record["served_and_priced"]
    assert code == 4


def test_a_probe_with_a_verdict_for_every_market_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The fix must not turn an ordinary answer into a failure: served,
    valid-but-unpriced and a genuine 422 are all verdicts."""
    transport = Transport({
        "totals_p1": _status(422),
        "player_takeaways": _status(422),
        "player_hits": _unquoted,
        "team_totals": _unquoted,
    })

    code, output, record = _probe(tmp_path, monkeypatch, capsys, transport)

    assert RECORD_KEYS <= set(record)
    assert record["not_a_market"] == ["totals_p1", "player_takeaways"]
    assert record["valid_but_unpriced"] == ["team_totals", "player_hits"]
    assert record["not_answered"] == {}
    assert record["not_asked"] == []
    assert record["stopped_because"] is None
    assert record["probe_complete"] is True
    assert _counted_as_not_a_market(output) == 2
    assert code == 0


def test_a_credit_cap_stop_names_what_it_did_not_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The cap stop used to leave the unasked markets out of every list, so
    the record could not say the probe was incomplete."""
    transport = Transport()

    code, output, record = _probe(
        tmp_path, monkeypatch, capsys, transport, cap=5
    )

    assert transport.asked == list(CANDIDATES[:5])
    assert record["credits_spent"] == 5
    assert record["not_asked"] == list(CANDIDATES[5:])
    assert "5-credit cap" in record["stopped_because"]
    assert record["not_a_market"] == []
    assert record["probe_complete"] is False
    assert code == 4


# --------------------------------------------------------------------------
# The adapter: the status travels on the error.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "answer, status",
    [
        (_status(422), 422),
        (_status(503), 503),
        (_status(429), 429),
        (_status(401), 401),
        (requests.ReadTimeout("read timed out"), None),
        (requests.ConnectionError("connection reset"), None),
        (FakeResponse(raises=ValueError("not JSON")), None),
    ],
    ids=["422", "503", "429", "401", "timeout", "connection", "unreadable"],
)
def test_a_provider_failure_carries_its_http_status(
    answer: Any, status: int | None
) -> None:
    def requester(url: str, **kwargs: Any) -> FakeResponse:
        if isinstance(answer, BaseException):
            raise answer
        return answer

    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester, regions="us"
    )
    with pytest.raises(odds_api.ProviderError) as caught:
        provider._get(  # noqa: SLF001
            f"{provider.base_url}/v4/sports/{provider.sport_key}/events/"
            f"{EVENT_ID}/odds",
            provider._params(markets="h2h"),  # noqa: SLF001
        )

    assert caught.value.status == status


# --------------------------------------------------------------------------
# The run summary.
# --------------------------------------------------------------------------

def _summary_step() -> dict:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in document["jobs"]["discover"]["steps"]:
        if step.get("name") == "Write the coverage report to the run summary":
            return step
    raise AssertionError("no run-summary step")


def _run_summary(tmp_path: Path, *, outcome: str, record: str) -> str:
    workdir = tmp_path / "workflow"
    outputs = workdir / "data" / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "nhl_market_discovery.json").write_text(record, encoding="utf-8")
    summary = workdir / "summary.md"
    env = dict(os.environ)
    env.update({"GITHUB_STEP_SUMMARY": str(summary), "PROBE_OUTCOME": outcome})
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
         _summary_step()["run"]],
        cwd=workdir, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return summary.read_text(encoding="utf-8")


INCOMPLETE = "did not get a verdict on every candidate market"


def test_the_summary_says_an_incomplete_probe_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The record a failed request leaves, as the run summary prints it."""
    transport = Transport({"alternate_spreads": _status(503)})
    code, _, record = _probe(tmp_path, monkeypatch, capsys, transport)
    assert code == 4

    text = _run_summary(
        tmp_path, outcome="failure", record=json.dumps(record, indent=2)
    )

    assert "### Markets the provider serves" in text
    assert INCOMPLETE in text
    assert '"not_answered"' in text
    assert "alternate_spreads" in text
    assert text.index(INCOMPLETE) < text.index('"not_answered"')


def test_the_summary_says_nothing_extra_for_a_complete_probe(
    tmp_path: Path,
) -> None:
    text = _run_summary(
        tmp_path, outcome="success", record='{"not_a_market": []}\n'
    )

    assert '{"not_a_market": []}' in text
    assert INCOMPLETE not in text
