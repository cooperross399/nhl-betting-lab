"""A failed events listing crashed the price fetch, and the card then called nine markets "no rows".

`run_provider_shadow.py` fetches the team markets in one bulk `/odds` call,
stages them, and then calls `fetch_player_props`, which asks the free
`/events` endpoint for the slate before it asks `/events/{id}/odds` once per
game. #187 and #193 made a failed per-event request exit 4 and reach the
provenance, both reports and the card as a failed fetch. Neither reached
the listing: it is one request made before the per-event loop and its
`except`, and the script called `fetch_player_props` with no guard of its
own, so a listing that failed escaped as an uncaught `ProviderError`.

Found by the failure-shape sweep (s1x2-run-provider-shadow-269) and
confirmed by three of three refuters (reproduce, reachability, intent),
each replaying it with only the HTTP transport stubbed: the bulk call priced
3 games at 2 books (36 team rows), then `/events` answered HTTP 502. Then:

* the script died with a traceback and exit 1, a code outside its 0/2/3/4
  contract, reading "The odds provider returned HTTP 502. No staging file
  was written." beside a written 36-row `odds_api_prices_staging.csv`;
* no props file, no `staging_provenance.json`, and neither
  `provider_shadow_verification.md` nor `provider_market_discovery.md`;
* the price step writes `price_fetch_incomplete.txt` for exit 4 only, so
  "Record what went wrong" gave the generic "The price fetch failed, so the
  card was built from whatever was already staged";
* the card found no provenance, read no failed request, and excluded all 9
  per-event markets (the seven props, `regulation_3_way`, `team_total`) as
  "The provider returned no rows for this market. That is an absence ...
  Check per-bookmaker coverage including alternate lines before concluding
  it is not offered" — the wording #193 was merged to stop for a failed
  fetch, 9 of 9 markets, where a per-event 502 on the same slate gives 0 of 9;
* a `ConnectionError` took the same path, and the interpreter's traceback
  printed the chained `requests` cause, whose URL carries `apiKey=` in its
  query string. `redact` cleans the `ProviderError` message, not the cause.

What these tests hold, driving the real script with a real `OddsApiProvider`
over a stub transport, the real card `main()` with its models stubbed, and
the workflow's own price and health step blocks under
`bash --noprofile --norc -eo pipefail`:

* a listing that fails (502, 429, a read timeout, a refused connection, or a
  200 that is not a list) exits 4 without raising, asks no per-event
  question and spends no per-event credit, and still writes the team file,
  an empty props file (replacing any earlier one), the provenance and both
  reports; no recorded error claims "No staging file was written";
* the provenance records every game the bulk fetch staged as failed, with
  exactly the nine markets only the per-event request asks for;
* both reports and the card read those nine as a failed fetch, never as "no
  rows", while `puck_line` (asked in bulk, answered with no `spreads`) is
  still judged on that answer and `total_goals` stays offered;
* the health step writes the per-event note, not "whatever was already
  staged";
* the stub credential appears nowhere in anything the run prints or writes;
* a run whose listing answered and whose books quoted nothing still reads
  "The provider returned no rows", so none of this can pass by deleting the
  sentence.

What this does not fix: owner item c3x0. The day's first snapshot still
stands, so a run whose per-event fetch failed freezes the team markets alone
and a later run that day cannot add the props. That is Cooper's call.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.parse import urlencode, urlparse

import pandas as pd
import pytest
import requests
import yaml

from conftest import FakeResponse
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from nhl_betting_lab import config
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.markets import ALL_MARKETS
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult
from nhl_betting_lab.staging_provider_policy import load_policy


#: Never a real credential, and never sent anywhere: the transport is a stub.
STUB_CREDENTIAL = "stub-credential-never-sent"
ENVIRONMENT = {"NHL_ODDS_API_KEY": STUB_CREDENTIAL}

#: 09:30 in New York on a three-game night, when the primary trigger fires.
NOW = datetime(2026, 10, 7, 13, 30, tzinfo=timezone.utc)

GAMES = (
    ("ev0", "Winnipeg Jets", "Colorado Avalanche", "2026-10-07T23:00:00Z"),
    ("ev1", "Washington Capitals", "Pittsburgh Penguins", "2026-10-07T23:30:00Z"),
    ("ev2", "Anaheim Ducks", "Edmonton Oilers", "2026-10-08T02:00:00Z"),
)

#: Each game as the slate keys it: the staged row's date, AWAY@HOME.
GAME_KEY = {
    event_id: f"{commence[:10]} {away}@{home}"
    for event_id, home, away, commence in GAMES
}

#: The nine markets only the per-event request asks for.
PER_EVENT_ONLY = tuple(market.key for market in ALL_MARKETS if market.per_event)

#: What Gameday Refresh's "Fetch prices into staging" step runs.
GAMEDAY_ARGV = [
    "--live", "--props", "--overwrite-staging", "--horizon-days", "1",
    "--credit-cap", "320",
]

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"

STAGING_CLAIM = "No staging file was written"


# --------------------------------------------------------------------------
# The provider, as the transport sees it.
# --------------------------------------------------------------------------

def _book(title: str, markets: list[dict]) -> dict:
    return {"key": title.lower(), "title": title, "markets": markets}


def _team_markets(home: str, away: str) -> list[dict]:
    """Moneyline and totals. No book posts `spreads`, so `puck_line` is a
    market the bulk request asked for and got nothing back for."""
    return [
        {"key": "h2h", "outcomes": [
            {"name": home, "price": -140}, {"name": away, "price": 120}]},
        {"key": "totals", "outcomes": [
            {"name": "Over", "price": -110, "point": 6.5},
            {"name": "Under", "price": -110, "point": 6.5}]},
    ]


def _event(event_id: str, home: str, away: str, commence: str,
           books: list[dict]) -> dict:
    return {"id": event_id, "commence_time": commence, "home_team": home,
            "away_team": away, "bookmakers": books}


def _bulk() -> list[dict]:
    """Three games at two books: 3 x 2 x (2 + 2) = 24 team rows."""
    return [
        _event(event_id, home, away, commence,
               [_book("DraftKings", _team_markets(home, away)),
                _book("FanDuel", _team_markets(home, away))])
        for event_id, home, away, commence in GAMES
    ]


def _listing_ok(url: str, kwargs: dict) -> FakeResponse:
    return FakeResponse([
        {"id": event_id, "commence_time": commence, "home_team": home,
         "away_team": away} for event_id, home, away, commence in GAMES
    ])


def _listing_status(code: int):
    def answer(url: str, kwargs: dict) -> FakeResponse:
        return FakeResponse(status_code=code)
    return answer


def _listing_timeout(url: str, kwargs: dict) -> FakeResponse:
    raise requests.ReadTimeout("read timed out")


def _listing_refused(url: str, kwargs: dict) -> FakeResponse:
    """A refused connection, worded as `requests` words one: urllib3 puts
    the request's path AND query string in the message, and the query
    carries the credential the provider sent."""
    path = urlparse(url).path + "?" + urlencode(kwargs.get("params") or {})
    raise requests.ConnectionError(
        "HTTPSConnectionPool(host='api.the-odds-api.com', port=443): Max "
        f"retries exceeded with url: {path} (Caused by NewConnectionError("
        "'<urllib3.connection.HTTPSConnection object>: Failed to establish a "
        "new connection: [Errno 61] Connection refused'))"
    )


def _listing_not_a_list(url: str, kwargs: dict) -> FakeResponse:
    """Answered 200, with a body that is not the events list."""
    return FakeResponse({"message": "temporarily unavailable"})


def _per_event_quoting_nothing(event_id: str) -> FakeResponse:
    for game_id, home, away, commence in GAMES:
        if game_id == event_id:
            return FakeResponse(_event(game_id, home, away, commence, []))
    raise AssertionError(event_id)


class Transport:
    """The bulk call always answers; `listing` decides the `/events` answer."""

    def __init__(self, listing) -> None:
        self.listing = listing
        self.calls: list[str] = []

    def __call__(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(url)
        if "/events/" in url and url.endswith("/odds"):
            return _per_event_quoting_nothing(url.split("/events/")[1].split("/")[0])
        if url.endswith("/events"):
            return self.listing(url, kwargs)
        if url.endswith("/odds"):
            return FakeResponse(_bulk())
        raise AssertionError(f"unexpected request: {url}")

    @property
    def per_event_requests(self) -> int:
        return sum("/events/" in url and url.endswith("/odds") for url in self.calls)


FAILED_LISTINGS = [
    (_listing_status(502), "HTTP 502"),
    (_listing_status(429), "HTTP 429"),
    (_listing_timeout, "could not be reached (ReadTimeout)"),
    (_listing_refused, "could not be reached (ConnectionError)"),
    (_listing_not_a_list, "The events list is not a JSON list."),
]
FAILED_IDS = ["http-502", "http-429", "read-timeout", "connection-refused",
              "not-a-list"]


# --------------------------------------------------------------------------
# The script.
# --------------------------------------------------------------------------

class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class _Capture:
    def __enter__(self):
        self._out, self._err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        return self

    def __exit__(self, *exc):
        self.out, self.err = sys.stdout.getvalue(), sys.stderr.getvalue()
        sys.stdout, sys.stderr = self._out, self._err
        return False


def _load(name: str, label: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(label, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _shadow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
            listing) -> SimpleNamespace:
    """The real script with Gameday Refresh's own flags, over a stub
    transport, run as `raise SystemExit(main())` runs it: an exception that
    escapes `main` is what the interpreter prints and exits 1 on, so it is
    recorded here as exactly that rather than failing the harness."""
    # The script screens posted events against the cached club schedules,
    # so a checkout holding a real season's cache would screen out every
    # game here; none of the defaults is the checkout's.
    point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    module = _load("run_provider_shadow.py", "_script_shadow_failed_listing")
    transport = Transport(listing)
    real = odds_api.OddsApiProvider
    monkeypatch.setattr(
        module.odds_api, "OddsApiProvider",
        lambda: real(environment=ENVIRONMENT, requester=transport, regions="us"),
    )
    # No `.env` is read, whatever the checkout holds.
    monkeypatch.setattr(
        module, "load_provider_env",
        lambda: ProviderEnvLoadResult(path=tmp_path / ".env"),
    )
    # The nothing-is-allowed policy: every label under test is decided
    # before the allowlist is consulted.
    monkeypatch.setattr(
        module, "load_policy", lambda: load_policy(repository_root=tmp_path)
    )
    monkeypatch.setattr(module, "datetime", _Frozen)
    staging = tmp_path / "staging"
    outputs = tmp_path / "outputs"
    crash = ""
    capture = _Capture()
    with capture:
        try:
            code = module.main(
                GAMEDAY_ARGV
                + ["--staging-dir", str(staging), "--output-dir", str(outputs)]
            )
        except Exception:  # what an uncaught exception prints, and its exit
            crash = traceback.format_exc()
            code = 1
    return SimpleNamespace(
        code=code, crash=crash, out=capture.out, err=capture.err,
        transport=transport, staging=staging, outputs=outputs,
    )


def _provenance(run: SimpleNamespace) -> dict:
    return json.loads(
        (run.staging / odds_api.PROVENANCE_FILENAME).read_text(encoding="utf-8")
    )


def _states(run: SimpleNamespace) -> dict[str, dict]:
    payload = json.loads(
        (run.outputs / "provider_shadow_verification.json").read_text(encoding="utf-8")
    )
    return {item["market"]: item for item in payload["markets"]}


def _discovery(run: SimpleNamespace) -> str:
    return (run.outputs / "provider_market_discovery.md").read_text(encoding="utf-8")


def _verdicts(markdown: str) -> dict[str, str]:
    found = {}
    for line in markdown.splitlines():
        if line.startswith("- `") and "`: " in line:
            market, _, verdict = line[3:].partition("`: ")
            found[market] = verdict
    return found


@pytest.mark.parametrize(("listing", "cause"), FAILED_LISTINGS, ids=FAILED_IDS)
def test_a_failed_listing_exits_4_and_still_writes_what_the_card_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listing, cause: str
) -> None:
    run = _shadow(tmp_path, monkeypatch, listing)

    assert not run.crash, run.crash
    assert run.code == 4, (run.code, run.err)
    # One listing request, no per-event question, no per-event credit.
    assert sum(url.endswith("/events") for url in run.transport.calls) == 1
    assert run.transport.per_event_requests == 0
    team = pd.read_csv(run.staging / odds_api.STAGING_PRICES_FILENAME)
    props = pd.read_csv(run.staging / odds_api.STAGING_PROPS_FILENAME)
    assert len(team) == 24 and len(props) == 0
    provenance = _provenance(run)
    assert provenance["credits_spent"] == len(odds_api.BULK_PROVIDER_MARKETS)
    assert sorted(provenance["staging_files"]) == sorted(
        [odds_api.STAGING_PRICES_FILENAME, odds_api.STAGING_PROPS_FILENAME]
    )
    assert len(provenance["errors"]) == 1, provenance["errors"]
    assert cause in provenance["errors"][0], provenance["errors"]
    assert "events list" in provenance["errors"][0].lower()
    for name in ("provider_shadow_verification.md",
                 "provider_shadow_verification.json",
                 "provider_market_discovery.md"):
        assert (run.outputs / name).is_file(), name
    # The staging claim is false once the team file is written.
    verification = (run.outputs / "provider_shadow_verification.md").read_text(
        encoding="utf-8"
    )
    assert not any(STAGING_CLAIM in item for item in provenance["errors"])
    assert not any(STAGING_CLAIM in item["error"] for item in provenance["failed_events"])
    assert STAGING_CLAIM not in verification
    assert STAGING_CLAIM not in run.err
    assert "per-event request(s) failed" in run.err


def test_the_provenance_names_every_staged_game_as_unasked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _shadow(tmp_path, monkeypatch, _listing_status(502))

    failed = _provenance(run)["failed_events"]
    assert [item["provider_event_id"] for item in failed] == ["ev0", "ev1", "ev2"]
    by_id = {event_id: (home, away, commence)
             for event_id, home, away, commence in GAMES}
    for item in failed:
        home, away, commence = by_id[item["provider_event_id"]]
        assert (item["home_team"], item["away_team"]) == (home, away)
        assert (item["date"], item["commence_time"]) == (commence[:10], commence)
        assert "HTTP 502" in item["error"] and item["provider_event_id"] in item["error"]
        # Only what no answered request covered: the bulk request answered
        # moneyline, puck line and totals for every game.
        assert sorted(item["markets"]) == sorted(PER_EVENT_ONLY), item["markets"]


def test_both_reports_read_the_per_event_markets_as_a_failed_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _shadow(tmp_path, monkeypatch, _listing_status(502))

    states = _states(run)
    discovery = _discovery(run)
    verdicts = _verdicts(discovery)
    for market in PER_EVENT_ONLY:
        assert states[market]["state"] == "fetch_failed", (market, states[market])
        assert "returned no rows" not in states[market]["reason"]
        assert verdicts[market].startswith("Asked, but the per-event request"), (
            market, verdicts[market]
        )
        assert "all 3 game(s) in the slate" in verdicts[market]
    assert "## Per-event requests that failed" in discovery
    for event_id, key in GAME_KEY.items():
        assert any(
            line.startswith(f"- {key}: ") and event_id in line and "HTTP 502" in line
            for line in discovery.splitlines()
        ), key
    # Asked in bulk and answered: judged on that answer, never relabelled.
    assert states["puck_line"]["state"] == "unavailable", states["puck_line"]
    assert verdicts["puck_line"].startswith("No book returned this market.")
    assert states["total_goals"]["state"] != "fetch_failed"
    assert verdicts["total_goals"].startswith("Offered."), verdicts["total_goals"]


def test_a_stale_per_event_file_is_replaced_not_left_beside_fresh_team_prices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An earlier run's props, left in place, sit beside this run's team
    prices; the card would read them as today's staging."""
    staging = tmp_path / "staging"
    staging.mkdir()
    earlier = (NOW - timedelta(days=1)).isoformat(timespec="seconds")
    pd.DataFrame([{
        "date": "2026-10-06", "commence_time": "2026-10-06T23:00:00Z",
        "provider_event_id": "old", "home_team": "Winnipeg Jets",
        "away_team": "Colorado Avalanche", "market": "shots_on_goal",
        "player": "Skater old", "selection": "over", "line": 2.5,
        "american_odds": -115, "book": "DraftKings", "fetched_at": earlier,
    }]).to_csv(staging / odds_api.STAGING_PROPS_FILENAME, index=False)

    run = _shadow(tmp_path, monkeypatch, _listing_status(502))

    assert not run.crash, run.crash
    assert len(pd.read_csv(staging / odds_api.STAGING_PROPS_FILENAME)) == 0


def test_no_credential_reaches_anything_the_run_prints_or_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _shadow(tmp_path, monkeypatch, _listing_refused)

    printed = run.out + run.err + run.crash
    assert STUB_CREDENTIAL not in printed, "the credential was printed"
    assert "apiKey=" not in printed
    for path in list(run.staging.glob("*")) + list(run.outputs.glob("*")):
        assert STUB_CREDENTIAL not in path.read_text(encoding="utf-8"), path
    assert run.code == 4, run.crash


# --------------------------------------------------------------------------
# The card.
# --------------------------------------------------------------------------

class _StubModel:
    report = SimpleNamespace(summary_line=lambda: "stub model")
    ambiguous_names: list = []

    def fit(self, _frame):
        return self


def _card(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
          staging: Path) -> SimpleNamespace:
    """The real card `main()` over the staging a shadow run wrote, the
    models stubbed and every default directory pointed away."""
    monkeypatch.setattr(tn, "RAW_DIR", tmp_path / "default_raw")
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "default_raw")
    module = _load("run_gameday_card.py", "_script_card_failed_listing")
    monkeypatch.setattr(module, "load_player_logs",
                        lambda _dir: pd.DataFrame({"player_id": [1]}))
    monkeypatch.setattr(module, "load_team_games",
                        lambda _dir: pd.DataFrame({"game_id": [1]}))
    monkeypatch.setattr(module, "PlayerPropsModel", _StubModel)
    monkeypatch.setattr(module, "TeamModel", _StubModel)
    monkeypatch.setattr(module, "current_rosters", lambda **_: {})
    monkeypatch.setattr(module, "price_props", lambda *a, **k: ({}, []))
    monkeypatch.setattr(module, "price_team_markets", lambda *a, **k: ({}, []))
    monkeypatch.setattr(
        module, "load_policy", lambda: load_policy(repository_root=tmp_path)
    )
    outputs = tmp_path / "card_outputs"
    raw = tmp_path / "card_raw"
    raw.mkdir(exist_ok=True)
    capture = _Capture()
    with capture:
        code = module.main([
            "--staging-dir", str(staging),
            "--processed-dir", str(tmp_path / "card_processed"),
            "--raw-dir", str(raw),
            "--output-dir", str(outputs),
            "--now", (NOW + timedelta(hours=1)).isoformat(),
        ])
    card = json.loads((outputs / "gameday_card.json").read_text(encoding="utf-8"))
    markdown = (outputs / "gameday_card.md").read_text(encoding="utf-8")
    return SimpleNamespace(code=code, card=card, markdown=markdown, out=capture.out)


@pytest.mark.parametrize(
    ("listing", "fetch_failed"),
    [(_listing_status(502), True), (_listing_timeout, True),
     (_listing_ok, False)],
    ids=["listing-502", "listing-timeout", "listing-answered-nothing-quoted"],
)
def test_the_card_names_the_failed_fetch_for_the_markets_it_excludes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listing, fetch_failed: bool
) -> None:
    shadow = _shadow(tmp_path, monkeypatch, listing)

    result = _card(tmp_path, monkeypatch, shadow.staging)

    assert result.code == 0
    excluded = result.card["excluded_markets"]
    for market in PER_EVENT_ONLY:
        reason = excluded[market]
        assert f"- `{market}`: {reason}" in result.markdown
        if fetch_failed:
            assert "returned no rows" not in reason, (market, reason)
            assert "per-event request" in reason and "failed" in reason, reason
            assert "all 3 game(s) in the slate" in reason, reason
        else:
            assert reason.startswith("The provider returned no rows"), reason
            assert "per-event request" not in reason, reason


# --------------------------------------------------------------------------
# The workflow: the price step and the health step, run from the YAML.
# --------------------------------------------------------------------------

def _step(id_: str) -> dict:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == id_:
                return step
    raise AssertionError(f"no step {id_}")


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions a test names; refuse any it did not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _bash(block: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    # The workflow declares `defaults.run.shell: bash`, which GitHub runs as
    # `bash --noprofile --norc -eo pipefail`.
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def _outputs(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        found[key] = value
    return found


def test_the_run_health_names_the_per_event_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: the real script's exit, through the price step (with
    `python` standing in for that exit), into the note "Record what went
    wrong" writes for the comment and card-feed."""
    run = _shadow(tmp_path, monkeypatch, _listing_status(502))

    work = tmp_path / "work"
    (work / "data" / "processed").mkdir(parents=True)
    (work / "data" / "processed" / "player_game_logs.csv").write_text(
        "player_id\n1\n", encoding="utf-8"
    )
    box = work / "data" / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for game in range(1200):
        (box / f"{game}.json").write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "python"
    stub.write_text(f"#!/bin/sh\nexit {run.code}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    prices_output = tmp_path / "prices_output"
    prices_output.write_text("", encoding="utf-8")
    prices = _bash(
        _render(_step("prices")["run"], {"inputs.props_credit_cap || '320'": "320"}),
        work,
        {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
         "GITHUB_OUTPUT": str(prices_output)},
    )
    outcome = "success" if prices.returncode == 0 else "failure"
    health_output = tmp_path / "health_output"
    health_output.write_text("", encoding="utf-8")
    health = _bash(
        _render(_step("health")["run"], {
            "steps.results.outcome": "success",
            "steps.prices.outputs.empty_slate":
                _outputs(prices_output).get("empty_slate", ""),
            "steps.prices.outcome": outcome,
        }),
        work,
        {**os.environ, "GITHUB_OUTPUT": str(health_output)},
    )
    assert health.returncode == 0, health.stderr
    notes = (work / "run_degraded.txt").read_text(encoding="utf-8")

    assert outcome == "failure"
    assert _outputs(health_output)["degraded"] == "true"
    assert "per-event" in notes and "regulation three-way" in notes, notes
    assert "absent, not unquoted" in notes, notes
    assert "whatever was already staged" not in notes, notes
