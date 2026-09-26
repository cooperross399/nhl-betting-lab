"""The scheduled probe never asked for a per-event market, then reported each one as unquoted.

Provider Market Discovery runs once on a cron (`0 16 15 10 *`) so the in-season
revisit of props, ladders and team totals happens without anyone remembering
it. A scheduled run has no inputs, so `inputs.include_props == true` is false
and `--props` is dropped, and `inputs.probe_every_market == true` is false and
the individual-market probe is skipped. `run_provider_shadow.py` then asks the
provider for the three bulk markets only (`h2h,spreads,totals`, about 6
credits) — and the reports it writes read every other market as the provider's
absence:

* `provider_market_discovery.md`: "3 of 12 markets returned prices", and for
  `shots_on_goal`, `points`, `goals`, `assists`, `goalie_saves`,
  `blocked_shots`, `hits`, `regulation_3_way` and `team_total`: "No book
  returned this market."
* `provider_shadow_verification.md`: the same nine as `unavailable`, "The
  provider returned no rows for this market."

Both are false: the provider was never asked. That is the "starved probe reads
like an unquoted market" failure the workflow's own comments say it exists to
prevent, on the one unattended run built to answer that question. And the run
summary silently omitted the individual-probe section, so nothing said the
deferred candidate markets were not asked either.

Found by the failure-shape audit (3 of 3 refuters: reproduce, reachability,
intent), reproduced offline through `run_provider_shadow.main` with the argv
the schedule renders.

Whether the scheduled run should ASK for the per-event markets spends credits
on a cron, which is Cooper's decision and is not made here. What these tests
hold is the reporting half, which spends nothing:

* a live run reports a market it never requested as "not asked in this run"
  (discovery) and `not_requested` (verification), never as a market no book
  quotes;
* a market that WAS asked for and came back empty still reads as absent, so
  the new label cannot swallow the answer the probe exists to give;
* a market with rows is judged on its rows whatever the requested set says,
  and an offline assessment — which cannot know what was asked — keeps the
  old wording rather than inventing a claim;
* the run summary says when the individual-market probe was not asked for,
  and says something different when it ran and wrote nothing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
import yaml

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.market_eligibility import assess_markets
from nhl_betting_lab.markets import ALL_MARKETS
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.reports import market_discovery
from nhl_betting_lab.staging_provider_policy import load_policy


ENVIRONMENT = {"NHL_ODDS_API_KEY": "k" * 24}

#: The argv `provider-market-discovery.yml` renders on its schedule: the
#: inputs context is empty, so `--props` is dropped and the cap falls back to
#: its default. `--live` reaches a recording requester, never the network.
SCHEDULED_ARGV = [
    "--live", "--overwrite-staging",
    "--horizon-days", "0", "--max-events", "20",
    "--credit-cap", "380",
]

BULK_MARKETS = ("moneyline", "puck_line", "total_goals")
PER_EVENT_MARKETS = tuple(
    market.key for market in ALL_MARKETS if market.key not in BULK_MARKETS
)

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "provider-market-discovery.yml"


# -- fixtures ------------------------------------------------------------


def _load_shadow_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_provider_shadow.py"
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Loaded:
    warnings: list = []

    @staticmethod
    def summary_line() -> str:
        return "credential: stubbed for the test"


def _bulk_event(index: int) -> dict:
    home, away = f"Home {index}", f"Away {index}"
    return {
        "id": f"evt{index}",
        "commence_time": f"2026-10-15T23:{index:02d}:00Z",
        "home_team": home,
        "away_team": away,
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": home, "price": -120},
                        {"name": away, "price": 100},
                    ]},
                    {"key": "spreads", "outcomes": [
                        {"name": home, "price": 150, "point": -1.5},
                        {"name": away, "price": -180, "point": 1.5},
                    ]},
                    {"key": "totals", "outcomes": [
                        {"name": "Over", "price": -110, "point": 5.5},
                        {"name": "Under", "price": -110, "point": 5.5},
                    ]},
                ],
            }
        ],
    }


def _per_event_payload(url: str, **_kwargs) -> FakeResponse:
    """One book quotes shots on goal and nothing else, for every event."""
    event_id = url.split("/events/", 1)[1].split("/", 1)[0]
    index = int(event_id.removeprefix("evt"))
    home, away = f"Home {index}", f"Away {index}"
    return FakeResponse(
        {
            "id": event_id,
            "commence_time": f"2026-10-15T23:{index:02d}:00Z",
            "home_team": home,
            "away_team": away,
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {"key": "player_shots_on_goal", "outcomes": [
                            {"name": "Over", "description": f"Skater {index}",
                             "price": -115, "point": 2.5},
                            {"name": "Under", "description": f"Skater {index}",
                             "price": -105, "point": 2.5},
                        ]},
                    ],
                }
            ],
        }
    )


def _requester(events: int = 3) -> RecordingRequester:
    board = [_bulk_event(index) for index in range(events)]
    listing = [
        {"id": item["id"], "commence_time": item["commence_time"]}
        for item in board
    ]
    return RecordingRequester(
        {
            "/events/": _per_event_payload,
            "/events": FakeResponse(listing),
            "/odds": FakeResponse(board, headers={"x-requests-remaining": "19000"}),
        }
    )


def _run(
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    requester: RecordingRequester | None = None,
) -> tuple[int, Path]:
    module = _load_shadow_script()
    real_provider = odds_api.OddsApiProvider
    monkeypatch.setattr(module, "load_provider_env", lambda: _Loaded())
    # No policy file under tmp_path: the nothing-is-allowed policy. The
    # labels under test are decided before the allowlist is consulted.
    monkeypatch.setattr(
        module, "load_policy", lambda: load_policy(repository_root=tmp_path)
    )
    if requester is not None:
        monkeypatch.setattr(
            module.odds_api,
            "OddsApiProvider",
            lambda: real_provider(
                environment=ENVIRONMENT, requester=requester, regions="us,us2"
            ),
        )
    outputs = tmp_path / "outputs"
    code = module.main(
        argv
        + [
            "--staging-dir", str(tmp_path / "staging"),
            "--output-dir", str(outputs),
        ]
    )
    return code, outputs


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


def _states(outputs: Path) -> dict[str, str]:
    payload = json.loads(
        (outputs / "provider_shadow_verification.json").read_text(encoding="utf-8")
    )
    return {item["market"]: item["state"] for item in payload["markets"]}


# -- the scheduled run's reports ---------------------------------------


def test_the_scheduled_bulk_only_run_says_it_never_asked_for_per_event_markets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requester = _requester()

    code, outputs = _run(SCHEDULED_ARGV, tmp_path, monkeypatch, requester)
    capsys.readouterr()

    assert code == 0
    # The precondition, measured: one request, the three bulk markets.
    assert [call[1]["params"]["markets"] for call in requester.calls] == [
        "h2h,spreads,totals"
    ]

    discovery = (outputs / "provider_market_discovery.md").read_text(
        encoding="utf-8"
    )
    verdicts = _verdicts(discovery)
    table = _table_rows(discovery)
    for market in PER_EVENT_MARKETS:
        assert verdicts[market].startswith("Not asked in this run."), (
            market, verdicts[market]
        )
        assert table[market][1] == "not asked", (market, table[market])
    for market in BULK_MARKETS:
        assert verdicts[market].startswith("Offered."), (market, verdicts[market])
    assert "No book returned" not in discovery
    assert "3 of 3 markets asked returned prices across 3 game(s)" in discovery
    assert "9 of 12 were not asked in this run" in discovery

    verification = (outputs / "provider_shadow_verification.md").read_text(
        encoding="utf-8"
    )
    assert "returned no rows" not in verification
    rows = _table_rows(verification)
    states = _states(outputs)
    for market in PER_EVENT_MARKETS:
        assert rows[market][1] == "not_requested", (market, rows[market])
        assert states[market] == "not_requested", market
    for market in BULK_MARKETS:
        assert states[market] != "not_requested", market


def test_a_market_the_run_asked_for_and_nobody_quoted_still_reads_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With `--props` every market is asked. The book quotes shots on goal
    only, so the other eight per-event markets are the answer the probe
    exists to give — absent — and must not be relabelled as unasked."""
    requester = _requester()

    code, outputs = _run(
        SCHEDULED_ARGV[:-2] + ["--props", "--credit-cap", "380"],
        tmp_path, monkeypatch, requester,
    )
    capsys.readouterr()

    assert code == 0
    assert sum(1 for url in requester.urls if "/events/" in url) == 3

    discovery = (outputs / "provider_market_discovery.md").read_text(
        encoding="utf-8"
    )
    verdicts = _verdicts(discovery)
    table = _table_rows(discovery)
    assert "not asked" not in discovery.lower()
    assert verdicts["shots_on_goal"].startswith("Offered.")
    for market in set(PER_EVENT_MARKETS) - {"shots_on_goal"}:
        assert verdicts[market].startswith("No book returned this market."), (
            market, verdicts[market]
        )
        assert table[market][1] == "0", (market, table[market])
    assert "4 of 12 markets returned prices across 3 game(s)" in discovery

    states = _states(outputs)
    assert "not_requested" not in states.values()
    for market in set(PER_EVENT_MARKETS) - {"shots_on_goal"}:
        assert states[market] == "unavailable", market


def test_an_offline_assessment_does_not_claim_to_know_what_was_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Offline, the run asked nothing and cannot know what the run that
    staged the files asked. It keeps the absent wording rather than
    inventing either claim."""
    rows = [
        row
        for index in range(2)
        for row in odds_api.normalize_event(_bulk_event(index), fetched_at="t")
    ]
    odds_api.write_staging(
        rows, filename=odds_api.STAGING_PRICES_FILENAME,
        staging_dir=tmp_path / "staging",
    )

    code, outputs = _run([], tmp_path, monkeypatch)
    capsys.readouterr()

    assert code == 0
    discovery = (outputs / "provider_market_discovery.md").read_text(
        encoding="utf-8"
    )
    verdicts = _verdicts(discovery)
    assert "not asked" not in discovery.lower()
    for market in PER_EVENT_MARKETS:
        assert verdicts[market].startswith("No book returned this market.")
    assert "not_requested" not in _states(outputs).values()


def test_rows_are_never_hidden_behind_not_asked() -> None:
    """A market outside the requested set that nonetheless has rows is
    judged on its rows, in both reports."""
    frame = pd.DataFrame(
        [
            {"date": "2026-10-15", "home_team": "Home 0", "away_team": "Away 0",
             "market": market, "book": "DraftKings", "line": line,
             "selection": "over", "american_odds": -110}
            for market, line in (("moneyline", None), ("points", 0.5))
        ]
    )

    discovery = market_discovery.discover_coverage(
        frame, markets=["moneyline", "points", "hits"], requested={"moneyline"}
    )
    by_market = {item.market: item for item in discovery.markets}
    eligibility = assess_markets(
        frame,
        slate_games=["2026-10-15 Away 0@Home 0"],
        policy=load_policy(repository_root=Path("/nonexistent")),
        provider_name="the_odds_api",
        markets=["moneyline", "points", "hits"],
        requested={"moneyline"},
    )
    states = {item.market: item.state for item in eligibility.markets}

    assert by_market["points"].verdict().startswith("Offered.")
    assert by_market["hits"].verdict().startswith("Not asked in this run.")
    assert states["points"] != "not_requested"
    assert states["hits"] == "not_requested"


# -- the run summary ----------------------------------------------------


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["discover"]["steps"]


def _summary_step() -> dict:
    for step in _steps():
        if step.get("name") == "Write the coverage report to the run summary":
            return step
    raise AssertionError("no run-summary step")


def _run_summary(tmp_path: Path, *, outcome: str, probe_json: bool) -> str:
    step = _summary_step()
    outputs = tmp_path / "data" / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "provider_market_discovery.md").write_text(
        "# Provider market discovery\n", encoding="utf-8"
    )
    if probe_json:
        (outputs / "nhl_market_discovery.json").write_text(
            '{"served": ["h2h_p1"]}\n', encoding="utf-8"
        )
    summary = tmp_path / "summary.md"
    env = dict(os.environ)
    env.update({"GITHUB_STEP_SUMMARY": str(summary), "PROBE_OUTCOME": outcome})
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return summary.read_text(encoding="utf-8")


def test_the_summary_reads_the_probe_steps_own_outcome() -> None:
    probe = [step for step in _steps() if step.get("id") == "probe"]
    assert len(probe) == 1
    assert "scripts/discover_nhl_markets.py" in probe[0]["run"]
    assert _summary_step()["env"]["PROBE_OUTCOME"] == "${{ steps.probe.outcome }}"


def test_the_summary_says_the_individual_probe_was_not_asked_for(
    tmp_path: Path,
) -> None:
    text = _run_summary(tmp_path, outcome="skipped", probe_json=False)

    assert "### Markets the provider serves" in text
    assert "Not asked in this run." in text
    assert "# Provider market discovery" in text


def test_the_summary_tells_a_failed_probe_from_one_never_asked(
    tmp_path: Path,
) -> None:
    text = _run_summary(tmp_path, outcome="failure", probe_json=False)

    assert "Not asked in this run." not in text
    assert "outcome: failure" in text
    assert "wrote no result" in text


def test_the_summary_prints_the_probe_result_when_there_is_one(
    tmp_path: Path,
) -> None:
    text = _run_summary(tmp_path, outcome="success", probe_json=True)

    assert '{"served": ["h2h_p1"]}' in text
    assert "Not asked in this run." not in text
    assert "wrote no result" not in text
