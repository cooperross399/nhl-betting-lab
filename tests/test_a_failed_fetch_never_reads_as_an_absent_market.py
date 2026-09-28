"""A market whose per-event requests failed was reported as a market no book quotes.

`run_provider_shadow.py` asks `/events/{id}/odds` once per game for every
per-event market: the seven props, the regulation three-way, the team total
and the alternate ladders. #187 made the script exit 4 when one of those
requests fails, but that failure reached the exit code and nothing else.
Both reports and the card still read the missing rows as an absence at the
books.

The failure-shape audit found it, and two of three refuters confirmed it
(reproduce, reachability). They replayed it through the real script, a real
`OddsApiProvider` and a stub transport. The bulk call priced 3 games at 2
books, and all 3 per-event calls answered HTTP 503. The run exited 4, and
then:

* `provider_market_discovery.md` is the file the Provider Market Discovery
  job cats into its summary. It said "No book returned this market. Before
  recording it as not offered, re-run against the alternate ladders and a
  wider region" for `shots_on_goal`, `points`, `goals`, `assists`,
  `goalie_saves`, `blocked_shots`, `hits`, `regulation_3_way` and
  `team_total`. The file was byte-identical to the one from a run in which
  every request was answered and no book quoted anything. It never mentioned
  a failure: 0 matches for fail, 503 or error.
* `provider_shadow_verification.md` listed the same nine as `unavailable |
  0/3 | The provider returned no rows for this market`. The "## Errors"
  section named the 503s, but the table matched the all-answered run.
* The card excluded the nine markets with that same sentence ("Check
  per-bookmaker coverage including alternate lines before concluding it is
  not offered"). So the Gameday comment said, under What went wrong, that
  the per-event fetch failed, and, under Excluded markets, that the provider
  had returned nothing for nine markets. That repeats the "a starved probe
  and an unquoted market must never look alike" failure the discovery
  workflow names as its whole job.
* With one of three games failing, `shots_on_goal` read "Offered, but no
  single book covers the whole slate ... DraftKings at line 2.5, 2 of 3
  games". That blamed the books for a gap the fetch caused.

The remedy the text gave was wrong too. It said to widen the region, which
spends more credits, when the answer is to retry. The same request had also
asked for the alternate ladders.

What these tests check, on the real script over a stub transport, the real
card `main()` with its models stubbed, and the discovery workflow's own
summary step:

* when every game's per-event request fails, the per-event markets read
  `fetch_failed` in the verification report and "Asked, but the per-event
  request ... failed" in the discovery report, with "request failed" in its
  Rows column, a summary clause and a list of the failed requests. That
  holds for a 503, a 429, a timeout, a 422 the core-market fallback cannot
  recover, and a 200 whose payload is unreadable;
* a market that some other request asked for and answered (`puck_line` via
  the bulk `spreads`) is judged on that answer and is never relabelled as a
  failed fetch;
* when one game fails, the verdicts and reasons name that game as the
  fetch's gap and name no game that answered;
* a run in which every request was answered and no book quoted anything
  still reads "No book returned this market." and `unavailable`, so the fix
  cannot pass by deleting the sentence;
* the staging provenance records which games failed and which markets they
  left unanswered, and the card reads it, so its Excluded markets agree with
  What went wrong. The card applies it only to the prices that same run
  staged;
* a failed game is keyed through the staged rows' `provider_event_id`, so it
  lands on the game the slate measures even when the events listing carries
  no team names.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

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
ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}

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

#: What Provider Market Discovery's "Fetch and report coverage" step runs
#: on a dispatch with `include_props` ticked, at its default cap.
DISCOVERY_ARGV = [
    "--live", "--overwrite-staging", "--horizon-days", "0",
    "--max-events", "20", "--props", "--credit-cap", "380",
]

DISCOVERY_WORKFLOW = (
    PROJECT_ROOT / ".github" / "workflows" / "provider-market-discovery.yml"
)


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


def _shots(player: str) -> list[dict]:
    return [{"key": "player_shots_on_goal", "outcomes": [
        {"name": "Over", "description": player, "price": -115, "point": 2.5},
        {"name": "Under", "description": player, "price": -105, "point": 2.5}]}]


def _event(event_id: str, home: str, away: str, commence: str,
           books: list[dict]) -> dict:
    return {"id": event_id, "commence_time": commence, "home_team": home,
            "away_team": away, "bookmakers": books}


def _bulk() -> list[dict]:
    return [
        _event(event_id, home, away, commence,
               [_book("DraftKings", _team_markets(home, away)),
                _book("FanDuel", _team_markets(home, away))])
        for event_id, home, away, commence in GAMES
    ]


def _listing(*, names: bool = True) -> list[dict]:
    if not names:
        return [{"id": event_id, "commence_time": commence}
                for event_id, _, _, commence in GAMES]
    return [{"id": event_id, "commence_time": commence, "home_team": home,
             "away_team": away} for event_id, home, away, commence in GAMES]


def _per_event_ok(event_id: str, *, quoted: bool = True) -> FakeResponse:
    for game_id, home, away, commence in GAMES:
        if game_id == event_id:
            books = [_book("DraftKings", _shots(f"Skater {event_id}"))] if quoted else []
            return FakeResponse(_event(game_id, home, away, commence, books))
    raise AssertionError(event_id)


class Transport:
    """Answers the three endpoints; `per_event` decides each game's answer."""

    def __init__(self, per_event, *, names: bool = True) -> None:
        self.per_event = per_event
        self.names = names
        self.calls: list[str] = []

    def __call__(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(url)
        if "/events/" in url and url.endswith("/odds"):
            event_id = url.split("/events/")[1].split("/")[0]
            return self.per_event(event_id)
        if url.endswith("/events"):
            return FakeResponse(_listing(names=self.names))
        if url.endswith("/odds"):
            return FakeResponse(_bulk())
        raise AssertionError(f"unexpected request: {url}")


def _status(code: int, failing: set[str] | None = None):
    def answer(event_id: str) -> FakeResponse:
        if failing is None or event_id in failing:
            return FakeResponse(status_code=code)
        return _per_event_ok(event_id)
    return answer


def _timeout(event_id: str) -> FakeResponse:
    raise requests.ReadTimeout("read timed out")


def _unreadable(event_id: str) -> FakeResponse:
    """Answered 200, with a payload that is not an event."""
    return FakeResponse([])


def _none_quoted(event_id: str) -> FakeResponse:
    """Every request answered; no book posted anything per-event."""
    return _per_event_ok(event_id, quoted=False)


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


def _shadow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    per_event,
    *,
    argv: list[str] = GAMEDAY_ARGV,
    regions: str = "us",
    names: bool = True,
    outputs: Path | None = None,
) -> SimpleNamespace:
    """The real script with a workflow's own flags, over a stub transport."""
    # The script screens posted events against the cached club schedules,
    # so a checkout holding a real season's cache would screen out every
    # game here; none of the defaults is the checkout's.
    point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    module = _load("run_provider_shadow.py", "_script_shadow_failed_fetch")
    transport = Transport(per_event, names=names)
    real = odds_api.OddsApiProvider
    monkeypatch.setattr(
        module.odds_api, "OddsApiProvider",
        lambda: real(environment=ENVIRONMENT, requester=transport, regions=regions),
    )
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
    outputs = outputs or tmp_path / "outputs"
    staging = tmp_path / "staging"
    capture = _Capture()
    with capture:
        code = module.main(
            argv + ["--staging-dir", str(staging), "--output-dir", str(outputs)]
        )
    return SimpleNamespace(
        code=code, out=capture.out, err=capture.err, transport=transport,
        outputs=outputs, staging=staging,
    )


def _discovery(run: SimpleNamespace) -> str:
    return (run.outputs / "provider_market_discovery.md").read_text(encoding="utf-8")


def _verification(run: SimpleNamespace) -> str:
    return (run.outputs / "provider_shadow_verification.md").read_text(encoding="utf-8")


def _states(run: SimpleNamespace) -> dict[str, dict]:
    payload = json.loads(
        (run.outputs / "provider_shadow_verification.json").read_text(encoding="utf-8")
    )
    return {item["market"]: item for item in payload["markets"]}


def _provenance(run: SimpleNamespace) -> dict:
    return json.loads(
        (run.staging / odds_api.PROVENANCE_FILENAME).read_text(encoding="utf-8")
    )


def _verdicts(markdown: str) -> dict[str, str]:
    found = {}
    for line in markdown.splitlines():
        if line.startswith("- `") and "`: " in line:
            market, _, verdict = line[3:].partition("`: ")
            found[market] = verdict
    return found


def _table_rows(markdown: str) -> dict[str, list[str]]:
    rows = {}
    for line in markdown.splitlines():
        if line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows[cells[0].split("`")[1]] = cells
    return rows


# --------------------------------------------------------------------------
# The two reports.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("per_event", "cause"),
    [(_status(503), "HTTP 503"), (_status(429), "HTTP 429"),
     (_timeout, "ReadTimeout"), (_status(422), "HTTP 422"),
     (_unreadable, "malformed payload")],
    ids=["http-503", "http-429", "read-timeout", "422-and-422-on-the-core-list",
         "unreadable-payload"],
)
def test_every_request_failing_reads_as_a_failed_fetch_in_the_discovery_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, cause: str
) -> None:
    run = _shadow(tmp_path, monkeypatch, per_event)

    assert run.code == 4, run.err
    discovery = _discovery(run)
    verdicts = _verdicts(discovery)
    table = _table_rows(discovery)
    for market in PER_EVENT_ONLY:
        verdict = verdicts[market]
        assert not verdict.startswith("No book returned"), (market, verdict)
        assert verdict.startswith("Asked, but the per-event request"), (market, verdict)
        assert "all 3 game(s) in the slate" in verdict, (market, verdict)
        assert table[market][1] == "request failed", (market, table[market])
    assert "The per-event request failed for 3 game(s)" in discovery
    assert "## Per-event requests that failed" in discovery
    for event_id, key in GAME_KEY.items():
        assert any(
            line.startswith(f"- {key}: ") and event_id in line and cause in line
            for line in discovery.splitlines()
        ), (key, cause)


def test_every_request_failing_reads_as_a_failed_fetch_in_the_verification_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _shadow(tmp_path, monkeypatch, _status(503))

    assert run.code == 4
    states = _states(run)
    rows = _table_rows(_verification(run))
    for market in PER_EVENT_ONLY:
        assert states[market]["state"] == "fetch_failed", (market, states[market])
        assert states[market]["usable_for_picks"] is False
        reason = states[market]["reason"]
        assert "returned no rows" not in reason, (market, reason)
        assert "per-event request" in reason and "failed" in reason, reason
        assert rows[market][1] == "fetch_failed", rows[market]
        assert "returned no rows" not in rows[market][3], rows[market]


def test_a_market_another_request_answered_is_judged_on_that_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`puck_line` rides the per-event request as `alternate_spreads`, but
    the bulk request asked for `spreads` for every game and was answered
    with none. That is an answer, and it must not be relabelled a failed
    fetch; `total_goals`, which the bulk request priced, stays offered."""
    run = _shadow(tmp_path, monkeypatch, _status(503))

    states = _states(run)
    verdicts = _verdicts(_discovery(run))
    assert states["puck_line"]["state"] == "unavailable", states["puck_line"]
    assert verdicts["puck_line"].startswith("No book returned this market."), (
        verdicts["puck_line"]
    )
    assert states["total_goals"]["state"] != "fetch_failed"
    assert verdicts["total_goals"].startswith("Offered."), verdicts["total_goals"]


def test_one_failed_game_is_named_as_the_fetchs_gap_not_the_books(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ev0 answers 503; ev1 and ev2 answer, and quote shots on goal only."""
    run = _shadow(tmp_path, monkeypatch, _status(503, {"ev0"}))

    assert run.code == 4
    failed, answered = GAME_KEY["ev0"], (GAME_KEY["ev1"], GAME_KEY["ev2"])
    states = _states(run)
    verdicts = _verdicts(_discovery(run))

    shots = states["shots_on_goal"]
    assert shots["state"] == "incomplete", shots
    assert failed in shots["reason"] and "per-event request failed" in shots["reason"]
    assert verdicts["shots_on_goal"].startswith("Offered, but"), verdicts["shots_on_goal"]
    assert failed in verdicts["shots_on_goal"]
    assert "per-event request failed" in verdicts["shots_on_goal"]

    for market in set(PER_EVENT_ONLY) - {"shots_on_goal"}:
        # The two games that answered quoted nothing for it: an absence.
        # The third is the fetch's, and says so.
        assert states[market]["state"] == "unavailable", (market, states[market])
        reason = states[market]["reason"]
        assert reason.startswith("The provider returned no rows"), reason
        assert failed in reason and "per-event request failed" in reason, reason
        assert verdicts[market].startswith("No book returned this market."), (
            market, verdicts[market]
        )
        assert failed in verdicts[market], (market, verdicts[market])
    for text in [states[m]["reason"] for m in PER_EVENT_ONLY] + [
        verdicts[m] for m in PER_EVENT_ONLY
    ]:
        assert not any(game in text for game in answered), text


def test_books_that_quoted_nothing_still_read_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every request answered and no book posted a per-event market: the
    answer the probe exists to give. It must read exactly as before."""
    run = _shadow(tmp_path, monkeypatch, _none_quoted)

    assert run.code == 0, run.err
    discovery = _discovery(run)
    verdicts = _verdicts(discovery)
    table = _table_rows(discovery)
    states = _states(run)
    for market in PER_EVENT_ONLY:
        assert verdicts[market].startswith("No book returned this market."), (
            market, verdicts[market]
        )
        assert "per-event request" not in verdicts[market]
        assert table[market][1] == "0", table[market]
        assert states[market]["state"] == "unavailable", states[market]
        assert states[market]["reason"].startswith("The provider returned no rows")
        assert "per-event request" not in states[market]["reason"]
    assert "Per-event requests that failed" not in discovery
    assert "request failed" not in discovery
    assert _provenance(run)["failed_events"] == []


def test_the_provenance_records_which_games_failed_and_what_they_left_unasked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _shadow(tmp_path, monkeypatch, _status(503, {"ev0", "ev2"}))

    failed = _provenance(run)["failed_events"]
    assert [item["provider_event_id"] for item in failed] == ["ev0", "ev2"]
    by_id = {event_id: (home, away, commence)
             for event_id, home, away, commence in GAMES}
    for item in failed:
        home, away, commence = by_id[item["provider_event_id"]]
        assert (item["home_team"], item["away_team"]) == (home, away)
        assert item["date"] == commence[:10]
        assert "HTTP 503" in item["error"]
        # Only what no answered request covered: the bulk request answered
        # moneyline, puck line and totals for every game.
        assert sorted(item["markets"]) == sorted(PER_EVENT_ONLY), item["markets"]


def test_a_failed_game_is_keyed_through_the_staged_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The events listing need not carry team names. The failed request is
    tied to its game through the `provider_event_id` the bulk rows carry,
    so it lands on the same game the slate measures."""
    run = _shadow(tmp_path, monkeypatch, _status(503), names=False)

    assert run.code == 4
    states = _states(run)
    for market in PER_EVENT_ONLY:
        assert states[market]["state"] == "fetch_failed", (market, states[market])
    discovery = _discovery(run)
    for key in GAME_KEY.values():
        assert any(line.startswith(f"- {key}: ") for line in discovery.splitlines()), key


# --------------------------------------------------------------------------
# The discovery workflow's run summary: the file a human reads to decide
# whether to write a market off.
# --------------------------------------------------------------------------

def _summary_step() -> dict:
    document = yaml.safe_load(DISCOVERY_WORKFLOW.read_text(encoding="utf-8"))
    for step in document["jobs"]["discover"]["steps"]:
        if step.get("name") == "Write the coverage report to the run summary":
            return step
    raise AssertionError("no run-summary step")


def test_the_discovery_run_summary_names_the_failed_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "work"
    run = _shadow(
        tmp_path, monkeypatch, _status(503), argv=DISCOVERY_ARGV,
        regions="us,us2", outputs=work / "data" / "outputs",
    )
    assert run.code == 4

    summary = tmp_path / "summary.md"
    env = dict(os.environ)
    env.update({"GITHUB_STEP_SUMMARY": str(summary), "PROBE_OUTCOME": "skipped"})
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
         _summary_step()["run"]],
        cwd=work, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    text = summary.read_text(encoding="utf-8")

    assert "## Per-event requests that failed" in text
    verdicts = _verdicts(text)
    for market in PER_EVENT_ONLY:
        assert verdicts[market].startswith("Asked, but the per-event request"), (
            market, verdicts[market]
        )


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
    module = _load("run_gameday_card.py", "_script_card_failed_fetch")
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
    ("per_event", "fetch_failed"),
    [(_status(503), True), (_none_quoted, False)],
    ids=["every-request-failed", "every-request-answered-nothing-quoted"],
)
def test_the_card_names_the_failed_fetch_for_the_markets_it_excludes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, per_event, fetch_failed: bool
) -> None:
    shadow = _shadow(tmp_path, monkeypatch, per_event)

    result = _card(tmp_path, monkeypatch, shadow.staging)

    assert result.code == 0
    excluded = result.card["excluded_markets"]
    for market in PER_EVENT_ONLY:
        reason = excluded[market]
        assert f"- `{market}`: {reason}" in result.markdown
        if fetch_failed:
            assert "returned no rows" not in reason, (market, reason)
            assert "per-event request" in reason and "failed" in reason, reason
        else:
            assert reason.startswith("The provider returned no rows"), reason
            assert "per-event request" not in reason, reason


def test_the_card_does_not_pin_another_runs_failures_on_these_prices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provenance says which run failed. Prices another run staged
    beside it are judged on their rows alone, and the card says why."""
    shadow = _shadow(tmp_path, monkeypatch, _status(503))
    team_file = shadow.staging / odds_api.STAGING_PRICES_FILENAME
    frame = pd.read_csv(team_file)
    frame["fetched_at"] = (NOW + timedelta(minutes=20)).isoformat(timespec="seconds")
    frame.to_csv(team_file, index=False, lineterminator="\n")

    result = _card(tmp_path, monkeypatch, shadow.staging)

    for market in PER_EVENT_ONLY:
        reason = result.card["excluded_markets"][market]
        assert reason.startswith("The provider returned no rows"), reason
    assert "cannot tie" in result.out, result.out
