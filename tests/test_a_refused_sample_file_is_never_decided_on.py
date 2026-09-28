"""Samples the calibration refused must never be read as fresh.

`run_props_calibration.py --reuse-samples` checks restored samples before
reusing them — the policy they record and every game the logs hold (see
tests/test_samples_remember_their_policy_and_their_games.py). When it refused
them it left the file where it was and went on to regenerate. If the
regeneration never happened — no player logs, so it returned 1 before writing,
or the generation crashed — the refused file was still on disk, unchanged.
Experiment Refresh runs the calibration under `|| true`, and its "samples absent
and could not be built" check only asked whether the file was non-empty, which
the refused file is. The correction experiment then read it, checking only the
policy it recorded, not which games it covered, and re-decided `by_toi` on
samples the logs had outgrown; the weekly drift check reported that decision as
current.

What these tests hold:

* the real calibration runner removes a cache it refuses before regenerating,
  so a rebuild that fails (no logs, or a crash) leaves no samples on disk, and
  a current cache is still reused untouched;
* the correction experiment refuses samples the logs have outgrown, with the
  same reach check the calibration uses, before fitting anything, and writes
  no verdict; samples that cover the logs go on to be decided on as before;
* Experiment Refresh's restore step, running the real calibration against a
  restored cache it refuses and cannot rebuild, fails instead of passing the
  refused file on to the experiments.
"""

from __future__ import annotations

import importlib.util
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
from nhl_betting_lab.markets import prop_market_keys
from nhl_betting_lab.providers import team_names as tn


def _script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    monkeypatch.setattr(tn, "RAW_DIR", tmp_path / "default_raw")


def _games(count: int) -> list[tuple[int, str]]:
    start = pd.Timestamp("2025-01-01")
    return [
        (1000 + index, (start + pd.Timedelta(days=index)).strftime("%Y-%m-%d"))
        for index in range(count)
    ]


def _samples(count: int, *, use_rest: bool = False,
             markets: tuple[str, ...] = ("shots_on_goal",)) -> pd.DataFrame:
    """A sample file of the shape the runner writes, one row per game and
    market."""
    return pd.DataFrame([
        {"date": day, "game_id": game_id, "player_id": 8479318,
         "player": "Auston Matthews", "team": "TOR", "opponent": "BOS",
         "venue": "home", "market": market, "mean": 3.4,
         "dispersion_r": float("nan"), "actual": 4.0, "toi_seconds": 1200,
         "expected_toi_seconds": 1180.0, "use_rest": use_rest}
        for game_id, day in _games(count) for market in markets
    ])


def _no_policy_ships(outputs: Path) -> None:
    """This directory's own verdict: props_b2b off, so rest-ignored samples
    are the policy in force. Without it the recorded verdict is read."""
    (outputs / "props_rest_experiment.json").write_text(
        json.dumps({"ships": []}), encoding="utf-8"
    )


def _logs(count: int) -> pd.DataFrame:
    return pd.DataFrame([
        {"game_id": game_id, "date": day, "player_id": 8479318,
         "player": "Auston Matthews", "role": "skater", "team": "TOR"}
        for game_id, day in _games(count)
    ])


# --------------------------------------------------------------------------
# The calibration runner removes what it refuses.
# --------------------------------------------------------------------------

def _calibration(tmp_path, monkeypatch, *, cache: pd.DataFrame,
                 logs: pd.DataFrame | None, crash: bool = False):
    module = _script("run_props_calibration.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    processed.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    _no_policy_ships(outputs)
    if logs is not None:
        logs.to_csv(processed / "player_game_logs.csv", index=False)
    path = outputs / "prop_calibration_samples.csv"
    cache.to_csv(path, index=False, lineterminator="\n")
    before = path.read_bytes()
    if crash:
        def boom(*args, **kwargs):
            raise RuntimeError("generation crashed")

        monkeypatch.setattr(module, "generate_prop_samples", boom)
    # A market list this cache satisfies, so the policy and reach checks are
    # the ones that decide.
    monkeypatch.setattr(module, "prop_market_keys", lambda: ("shots_on_goal",))
    argv = ["--reuse-samples", "--processed-dir", str(processed),
            "--output-dir", str(outputs)]
    if crash:
        with pytest.raises(RuntimeError, match="generation crashed"):
            module.main(argv)
        code = None
    else:
        code = module.main(argv)
    return code, before, path


def test_a_refused_cache_with_no_logs_to_rebuild_from_is_removed(
    tmp_path, monkeypatch, capsys
):
    code, _, path = _calibration(tmp_path, monkeypatch, cache=_samples(20), logs=None)
    out = capsys.readouterr().out

    assert code == 1
    assert "Not reusing the cached samples" in out
    assert not path.exists(), "the refused samples were left for the experiments"


def test_a_refused_cache_whose_rebuild_crashes_is_removed(tmp_path, monkeypatch):
    """Outgrown: the logs hold five games the cache never priced."""
    _, _, path = _calibration(
        tmp_path, monkeypatch, cache=_samples(20), logs=_logs(25), crash=True
    )

    assert not path.exists(), "the refused samples outlived a crashed rebuild"


def test_a_cache_of_the_other_policy_whose_rebuild_crashes_is_removed(
    tmp_path, monkeypatch
):
    _, _, path = _calibration(
        tmp_path, monkeypatch, cache=_samples(20, use_rest=True), logs=_logs(20),
        crash=True,
    )

    assert not path.exists()


def test_a_current_cache_is_still_reused_untouched(tmp_path, monkeypatch, capsys):
    module = _script("run_props_calibration.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    processed.mkdir(parents=True)
    outputs.mkdir(parents=True)
    _no_policy_ships(outputs)
    _logs(20).to_csv(processed / "player_game_logs.csv", index=False)
    path = outputs / "prop_calibration_samples.csv"
    _samples(20).to_csv(path, index=False, lineterminator="\n")
    before = path.read_bytes()
    monkeypatch.setattr(module, "prop_market_keys", lambda: ("shots_on_goal",))

    def never(*args, **kwargs):
        raise AssertionError("a current cache was regenerated")

    monkeypatch.setattr(module, "generate_prop_samples", never)
    # Stop once the reuse is decided: the report is not what this is about.
    monkeypatch.setattr(module, "build_calibration_report",
                        lambda s: (_ for _ in ()).throw(StopIteration("reused")))
    with pytest.raises(StopIteration):
        module.main(["--reuse-samples", "--processed-dir", str(processed),
                     "--output-dir", str(outputs)])

    assert capsys.readouterr().out.startswith("Reusing ")
    assert path.read_bytes() == before


# --------------------------------------------------------------------------
# The correction experiment checks reach as well as policy.
# --------------------------------------------------------------------------

class _Reached(Exception):
    """The experiment went on to fit: the samples were accepted."""


def _correction(tmp_path, monkeypatch, *, samples: pd.DataFrame,
                logs: pd.DataFrame | None):
    module = _script("run_correction_experiment.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    processed.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"commence_time": "2025-01-10T00:00:00Z",
                   "market": "shots_on_goal"}]).to_csv(
        processed / "historical_prop_prices.csv", index=False
    )
    if logs is not None:
        logs.to_csv(processed / "player_game_logs.csv", index=False)
    _no_policy_ships(outputs)
    samples.to_csv(outputs / "prop_calibration_samples.csv", index=False)

    def reached(_):
        raise _Reached()

    monkeypatch.setattr(module, "expand_to_lines", reached)
    try:
        code = module.main(["--processed-dir", str(processed),
                            "--output-dir", str(outputs)])
    except _Reached:
        code = "reached"
    return code, outputs


@pytest.mark.parametrize("extra", [1, 7])
def test_the_correction_experiment_refuses_samples_the_logs_have_outgrown(
    tmp_path, monkeypatch, capsys, extra
):
    code, outputs = _correction(
        tmp_path, monkeypatch, samples=_samples(20), logs=_logs(20 + extra)
    )
    err = capsys.readouterr().err

    assert code == 2, "it went on to decide on samples the logs have outgrown"
    assert "::error::" in err and f"{extra} game(s)" in err
    assert not list(outputs.glob("correction_experiment*"))


def test_the_correction_experiment_refuses_samples_whose_reach_cannot_be_checked(
    tmp_path, monkeypatch, capsys
):
    code, outputs = _correction(tmp_path, monkeypatch, samples=_samples(20), logs=None)
    err = capsys.readouterr().err

    assert code == 2
    assert "cannot be checked" in err
    assert not list(outputs.glob("correction_experiment*"))


def test_the_correction_experiment_decides_on_samples_that_cover_the_logs(
    tmp_path, monkeypatch
):
    code, _ = _correction(tmp_path, monkeypatch, samples=_samples(20), logs=_logs(20))

    assert code == "reached"


# --------------------------------------------------------------------------
# Experiment Refresh, with the real calibration inside its restore step.
# --------------------------------------------------------------------------

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "experiment-refresh.yml"

#: Every python call is logged; the calibration is the real script, run by
#: the real interpreter against the job's own data directories. Nothing else
#: runs, so no player logs are built and the calibration cannot regenerate.
FAKE_PYTHON = f"""#!/bin/bash
echo "$*" >> "$FAKE_PYTHON_LOG"
if [ "$1" = "scripts/run_props_calibration.py" ]; then
  shift
  exec "{sys.executable}" "{PROJECT_ROOT / 'scripts' / 'run_props_calibration.py'}" \\
    "$@" --processed-dir data/processed --output-dir data/outputs
fi
exit 0
"""


def _restore_block() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "restore":
                return step["run"]
    raise AssertionError("no restore step")


def test_experiment_refresh_fails_when_refused_samples_cannot_be_rebuilt(tmp_path):
    boxscores = tmp_path / "data" / "raw" / "nhl" / "boxscore"
    boxscores.mkdir(parents=True)
    for game in range(500):
        # Final, so the fixture clears the floor whether the restore counts
        # every cached boxscore or only final ones.
        (boxscores / f"{game}.json").write_text(
            '{"gameState": "OFF"}', encoding="utf-8"
        )
    (tmp_path / "data" / "processed").mkdir(parents=True)
    (tmp_path / "data" / "processed" / "historical_prop_prices.csv").write_text("x\n")
    outputs = tmp_path / "data" / "outputs"
    outputs.mkdir(parents=True)
    # Restored, non-empty, every market, and of the policy in force —
    # refused only because there are no logs to hold its reach against.
    _samples(20, markets=prop_market_keys()).to_csv(
        outputs / "prop_calibration_samples.csv", index=False
    )
    _no_policy_ships(outputs)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python"
    python.write_text(FAKE_PYTHON, encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "python.log"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
           "FAKE_PYTHON_LOG": str(log), "PYTHONPATH": str(PROJECT_ROOT / "src"),
           "PYTHONSAFEPATH": "1"}

    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _restore_block()],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )

    assert "Not reusing the cached samples" in result.stdout, result.stdout + result.stderr
    assert "cannot be checked" in result.stdout
    assert result.returncode != 0, (
        "the refresh passed refused samples on to the experiments:\n"
        + result.stdout + result.stderr
    )
    assert "could not be built" in result.stdout
    assert not (outputs / "prop_calibration_samples.csv").exists()
