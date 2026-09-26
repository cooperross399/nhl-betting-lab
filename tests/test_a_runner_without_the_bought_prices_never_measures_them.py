"""Gameday Refresh measured prices it did not have, and said nothing had been.

Found by the failure-shape audit (3/3 refuters: reproduce, reachability,
intent). "Rebuild the measurement reports" ran the two props backtests, the
team measurement, the claims document and the allowlist bundle
unconditionally, and the bought price stores are not on that runner. The
state restore takes gameday-state from this workflow's own newest carrier and
lays the purchase's copy in only when no Gameday run carries one
(`restore_state.py` returns at the first carrier), and the carrier the next
run restores, run 33142173149, is 31,815,033 bytes against the purchase's
86,454,131 and holds neither `historical_prop_prices.csv` nor
`historical_team_prices.csv`. `data/processed` is uploaded whole every run, so
the absence carries forward for the season.

Production log of 33142173149, that step: "No historical prop prices are on
disk", "No historical team prices on disk", "0 market(s) have any price-based
evidence", the headline "**Nothing in this repository has a demonstrated
edge, because nothing has been measured against real prices yet.**", and all
12 markets "not supported — no price-based measurement exists". Every command
exited 0 and the reports went to the public gameday-reports artifact, which
Publish Site lays over data/outputs. The committed record they contradict:
ten markets measured, -0.3% over 25,911 `late` bets, `points` -4.4% over
6,194 and `blocked_shots` +4.9% over 4,286. With the two stores copied into a
replay of the same step the headline became "10 market(s) have been measured
against real prices" and only `regulation_3_way` and `team_total` read "no
price-based measurement exists" — the two that really have none.

Carrying the prices into Gameday is not the fix: it uploads data/processed
whole to a public artifact every day, which would republish paid-for prices
daily for the season. So:

* the step rebuilds a price-measured report only from a store this runner
  holds (a row under its header, not merely a file), leaves the checkout's
  committed report standing otherwise, and says so in a notice; the claims
  document, which summarises both measurements, is rebuilt only when both
  were; the bundle is always assembled, because the live shadow and coverage
  reports exist only here;
* and wherever a measurement IS run on an empty store, its JSON records the
  rows it was handed (`rows_read`, beside the team measurement's
  `stored_rows`), and the claims document and the bundle name such an output
  as one they cannot read a verdict from, rather than concluding that
  nothing has been measured or that no measurement exists.

The step is run from the workflow file itself under `bash -eo pipefail` with
a stub `python` that writes each script's report; the second half drives the
real scripts and report modules on the Gameday runner's state.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.markets import ALL_MARKETS
from nhl_betting_lab.providers import team_names as team_names_module
from nhl_betting_lab.reports import player_props_backtest as bt
from nhl_betting_lab.reports import team_markets_measurement as tmm
from nhl_betting_lab.reports import what_we_can_claim as claims


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
STEP = "Rebuild the measurement reports"
FALSE_HEADLINE = "nothing has been measured against real prices yet"
NO_MEASUREMENT = "no price-based measurement exists"

PROP_STORE = "historical_prop_prices.csv"
TEAM_STORE = "historical_team_prices.csv"

#: What each script writes, as the stub `python` below writes it. The
#: committed copies of these sit in the checkout the step runs in.
WRITES = {
    "run_props_calibration.py": ("props_calibration.md",),
    "run_player_props_backtest.py": ("player_props_backtest.md",),
    "run_team_markets_measurement.py": ("team_markets_measurement.md",),
    "run_what_we_can_claim.py": ("what_we_can_claim.md",),
    "run_allowlist_evidence.py": ("allowlist_evidence_bundle.md",),
}
COMMITTED = (
    "props_calibration.md",
    "player_props_backtest.md",
    "player_props_backtest_card.md",
    "team_markets_measurement.md",
    "what_we_can_claim.md",
    "allowlist_evidence_bundle.md",
)
PRICE_MEASURED = (
    "player_props_backtest.md",
    "player_props_backtest_card.md",
    "team_markets_measurement.md",
    "what_we_can_claim.md",
)

#: A store with a header only is not a store holding prices: measured, it
#: reads "nothing bought" exactly as an absent one did.
STORE_BODIES = {
    PROP_STORE: (
        "date,market,player,selection,line,american_odds,book\n",
        "2025-01-09,shots_on_goal,A Player,over,2.5,-110,DraftKings\n",
    ),
    TEAM_STORE: (
        "date,commence_time,home_team,away_team,market,selection,line,american_odds,book\n",
        "2025-01-09,2025-01-10T00:00:00Z,Toronto Maple Leafs,Boston Bruins,"
        "moneyline,home,,150,DraftKings\n",
    ),
}
STATES = ("absent", "header", "rows")


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# The step, from the workflow file.
# --------------------------------------------------------------------------

def _step_block() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    found = [
        step
        for job in document["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == STEP
    ]
    assert len(found) == 1, f"exactly one step named {STEP!r}"
    return found[0]["run"]


def _stub_python(bin_dir: Path) -> None:
    """A `python` that logs its arguments and writes the report it names.

    Writing is the point: a price-measured script that runs is then visible
    as a committed report that changed, not only as a line in a log.
    """
    cases = "\n".join(
        f"  */{script})\n"
        + "".join(
            f'    printf "rebuilt by %s\\n" "$*" > "data/outputs/{name}"\n'
            for name in names
        )
        + "    ;;"
        for script, names in WRITES.items()
    )
    body = (
        "#!/bin/bash\n"
        'printf "%s\\n" "$*" >> "$CALLS_LOG"\n'
        'case "$1" in\n'
        f"{cases}\n"
        "esac\n"
        # The labelled copy the card window's backtest writes beside the
        # contract report.
        'if [ "$1" = scripts/run_player_props_backtest.py ] '
        '&& [[ " $* " == *" --label card "* ]]; then\n'
        '  printf "rebuilt by %s\\n" "$*" > data/outputs/player_props_backtest_card.md\n'
        "fi\n"
        "exit 0\n"
    )
    path = bin_dir / "python"
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _runner(tmp_path: Path, *, props: str, team: str) -> Path:
    """A checkout after the state restore: committed reports, and the stores
    in the state named."""
    root = tmp_path / "runner"
    outputs = root / "data" / "outputs"
    processed = root / "data" / "processed"
    outputs.mkdir(parents=True)
    processed.mkdir(parents=True)
    for name in COMMITTED:
        source = PROJECT_ROOT / "data" / "outputs" / name
        (outputs / name).write_bytes(source.read_bytes())
    for store, state in ((PROP_STORE, props), (TEAM_STORE, team)):
        header, row = STORE_BODIES[store]
        if state == "header":
            (processed / store).write_text(header, encoding="utf-8")
        elif state == "rows":
            (processed / store).write_text(header + row, encoding="utf-8")
    return root


def _run_step(tmp_path: Path, root: Path) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub_python(bin_dir)
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "CALLS_LOG": str(log),
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _step_block()],
        cwd=root, env=env, capture_output=True, text=True,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return result, calls


def _ran(calls: list[str], script: str) -> list[str]:
    return [call for call in calls if call.split(" ", 1)[0] == f"scripts/{script}"]


def test_without_the_bought_prices_the_committed_reports_stand(
    tmp_path: Path,
) -> None:
    """The Gameday runner as it is: neither store came back with the state."""
    root = _runner(tmp_path, props="absent", team="absent")
    before = {
        name: (root / "data" / "outputs" / name).read_bytes() for name in COMMITTED
    }

    result, calls = _run_step(tmp_path, root)

    assert result.returncode == 0, result.stderr
    assert not _ran(calls, "run_player_props_backtest.py"), calls
    assert not _ran(calls, "run_team_markets_measurement.py"), calls
    assert not _ran(calls, "run_what_we_can_claim.py"), calls
    for name in PRICE_MEASURED:
        assert (root / "data" / "outputs" / name).read_bytes() == before[name], (
            f"{name} was rebuilt on a runner holding no bought price"
        )
    # Not a silent skip: the log says which store was absent and what stands.
    notices = [
        line for line in result.stdout.splitlines() if line.startswith("::notice::")
    ]
    assert any(PROP_STORE in line for line in notices), result.stdout
    assert any(TEAM_STORE in line for line in notices), result.stdout
    assert any("what_we_can_claim.md" in line for line in notices), result.stdout


def test_the_parts_that_need_no_price_still_run(tmp_path: Path) -> None:
    """Calibration needs no price, and the bundle is where the live shadow
    and coverage reports meet the measurements; neither waits on a store."""
    root = _runner(tmp_path, props="absent", team="absent")

    result, calls = _run_step(tmp_path, root)

    assert result.returncode == 0, result.stderr
    assert _ran(calls, "run_props_calibration.py"), calls
    assert _ran(calls, "run_allowlist_evidence.py"), calls
    bundle = (root / "data" / "outputs" / "allowlist_evidence_bundle.md")
    assert bundle.read_text(encoding="utf-8").startswith("rebuilt by"), (
        "the bundle was not assembled"
    )


@pytest.mark.parametrize(("props", "team"), list(itertools.product(STATES, STATES)))
def test_each_report_is_rebuilt_only_from_a_store_this_runner_holds(
    tmp_path: Path, props: str, team: str
) -> None:
    root = _runner(tmp_path, props=props, team=team)

    result, calls = _run_step(tmp_path, root)

    assert result.returncode == 0, result.stderr
    backtests = [call.split(" ", 1)[1] for call in _ran(calls, "run_player_props_backtest.py")]
    if props == "rows":
        # Both windows, named, and the contract window last.
        assert backtests == ["--phase card --label card", "--phase late"], calls
    else:
        assert backtests == [], calls
    assert bool(_ran(calls, "run_team_markets_measurement.py")) is (team == "rows"), calls
    assert bool(_ran(calls, "run_what_we_can_claim.py")) is (
        props == "rows" and team == "rows"
    ), calls
    assert _ran(calls, "run_allowlist_evidence.py"), calls
    assert calls[-1].startswith("scripts/run_allowlist_evidence.py"), calls


# --------------------------------------------------------------------------
# The real scripts, on the Gameday runner's state.
# --------------------------------------------------------------------------

@pytest.fixture
def no_default_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test here may read the real `data/processed` or boxscore cache."""
    processed = tmp_path / "default_processed"
    raw = tmp_path / "default_raw"
    processed.mkdir()
    raw.mkdir()
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", processed)
    monkeypatch.setattr(team_names_module, "RAW_DIR", raw)


TEAM_NAMES = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}
TEAM_SAMPLES = pd.DataFrame(
    [
        {
            "game_id": 1, "date": "2025-01-09", "home_team": "TOR",
            "away_team": "BOS", "market": "moneyline", "selection": "home",
            "line": None, "model_probability": 0.6, "outcome": True,
            "push": False,
        }
    ]
)


def _measure_without_a_store(tmp_path: Path) -> Path:
    """What the old step left in data/outputs: every measurement, run with
    the walk-forward samples restored and no bought price beside them."""
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    processed.mkdir()
    outputs.mkdir()
    pd.DataFrame(
        [
            {
                "date": "2025-01-09", "market": "shots_on_goal",
                "player": "A Player", "line": 2.5, "model_probability": 0.55,
                "actual": 3,
            }
        ]
    ).to_csv(outputs / "prop_calibration_samples.csv", index=False)
    backtest = load_script("run_player_props_backtest.py")
    for window in (["--phase", "card", "--label", "card"], ["--phase", "late"]):
        code = backtest.main(
            [*window, "--processed-dir", str(processed), "--output-dir", str(outputs)]
        )
        assert code == 0
    # As `run_team_markets_measurement.py` builds it when the store is absent.
    report = tmm.build_team_measurement(
        TEAM_SAMPLES,
        pd.DataFrame(columns=["market"]),
        phase="late",
        team_names=TEAM_NAMES,
    )
    tmm.save_team_measurement(report, output_dir=outputs)
    return outputs


def test_measurements_handed_no_price_never_read_as_nothing_measured(
    tmp_path: Path, no_default_dirs: None
) -> None:
    outputs = _measure_without_a_store(tmp_path)

    assert load_script("run_what_we_can_claim.py").main(
        ["--output-dir", str(outputs)]
    ) == 0
    assert load_script("run_allowlist_evidence.py").main(
        ["--output-dir", str(outputs)]
    ) == 0
    rendered = (outputs / "what_we_can_claim.md").read_text(encoding="utf-8")
    bundle = (outputs / "allowlist_evidence_bundle.md").read_text(encoding="utf-8")
    report = claims.build_claims_report(output_dir=outputs)

    assert FALSE_HEADLINE not in rendered
    assert "cannot say whether anything would" in report.headline()
    for name in ("player_props_backtest.json", "team_markets_measurement.json"):
        assert f"`{name}`" in report.headline(), report.headline()
    assert "handed no historical price" in report.headline()
    verdicts = [
        line for line in bundle.splitlines()
        if line.startswith("- `") and "supported**" in line
    ]
    assert len(verdicts) == len(ALL_MARKETS), verdicts
    for line in verdicts:
        assert NO_MEASUREMENT not in line, line
        assert "handed no historical price" in line, line


def test_a_prop_market_is_named_unread_when_only_the_props_store_was_empty(
    tmp_path: Path, no_default_dirs: None
) -> None:
    """The props backtest alone handed nothing: its markets say so, and the
    team measurement that read prices keeps its own words."""
    outputs = _measure_without_a_store(tmp_path)
    face_off = "2025-01-10T00:00:00Z"
    snapshot = (pd.Timestamp(face_off) - pd.Timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    store = pd.DataFrame(
        [
            {
                "date": "2025-01-09", "commence_time": face_off,
                "snapshot": snapshot, "home_team": "Toronto Maple Leafs",
                "away_team": "Boston Bruins", "market": "moneyline",
                "selection": "home", "line": None, "american_odds": 150,
                "book": "DraftKings",
            }
        ]
    )
    tmm.save_team_measurement(
        tmm.build_team_measurement(
            TEAM_SAMPLES, store, phase="late", team_names=TEAM_NAMES
        ),
        output_dir=outputs,
    )

    built = claims.build_claims_report(output_dir=outputs)
    by_market = {claim.market: claim.sentence() for claim in built.claims}

    assert "`player_props_backtest.json`" in by_market["shots_on_goal"]
    assert "handed no historical price" in by_market["shots_on_goal"]
    assert "`team_markets_measurement.json`" not in by_market["team_total"]
    assert "holds no price for it" in by_market["team_total"]


def test_the_backtest_json_records_the_rows_it_was_handed(
    tmp_path: Path, no_default_dirs: None
) -> None:
    """The field the two readers above decide on, from the producer: every
    row handed in, before any window, whatever became of it. (No samples:
    `run_backtest` still counts what it was handed, and the model's opinion
    is not what this reads.)"""
    samples = pd.DataFrame(
        columns=["date", "market", "player", "line", "model_probability", "actual"]
    )
    columns = ["date", "market", "player", "selection", "line",
               "american_odds", "book"]
    store = pd.DataFrame(
        [
            ["2025-01-09", "shots_on_goal", "A Player", "over", 2.5, -110, "DraftKings"],
            ["2025-01-09", "shots_on_goal", "A Player", "under", 2.5, -110, "FanDuel"],
        ],
        columns=columns,
    )
    for name, prices, handed in (
        ("empty", pd.DataFrame(columns=columns), 0),
        ("bought", store, 2),
    ):
        report = bt.run_backtest(
            prices, samples, edge_threshold=0.0, phase="",
            team_names=TEAM_NAMES,
        )
        bt.save_backtest(report, output_dir=tmp_path / name)
        path = tmp_path / name / bt.BACKTEST_JSON_FILENAME
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert payload["rows_read"] == handed
        # Handed nothing: no verdict to read. Handed rows: read, whatever it
        # concluded from them.
        assert bool(claims.unread_reason(path)) is (handed == 0)
