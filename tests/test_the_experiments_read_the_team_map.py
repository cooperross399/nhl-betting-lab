"""The two prop experiments read the team-name map from --processed-dir.

#117 fixed the backtest runner, which had built its map from the boxscore
cache. Where that cache is absent (a worktree, a scratch directory) the map is
six Utah/Arizona aliases. The team check is then skipped, and in Utah games the
other side is voided: 902 bets in the `late` window, every one of them in a
Utah game. The correction and props-rest experiments call the same
`run_backtest` and had the same gap, and their committed records were written
on it. They now pass the map from the directory the prices come from, and
refuse, exiting 2, when it resolves nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.providers.team_names import UnresolvedTeamsError

TEAM_MAP = {"Toronto Maple Leafs": "TOR", "Utah Mammoth": "UTA"}


def _script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Report:
    by_market: dict = {}
    overall = None


def _prices(processed: Path) -> None:
    processed.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "commence_time": "2025-01-06T00:10:00Z", "date": "2025-01-05",
        "market": "shots_on_goal", "player": "Auston Matthews",
        "selection": "over", "line": 3.5, "american_odds": 110,
    }]).to_csv(processed / "historical_prop_prices.csv", index=False)


def _correction(tmp_path, monkeypatch, *, raises=None):
    module = _script("run_correction_experiment.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    _prices(processed)
    outputs.mkdir()
    # Recording the policy it was generated under, as every sample file now
    # does: no verdict here ships props_b2b, so rest-ignored. Without it the
    # experiment refuses the file before any backtest runs, and the refusal
    # test below would pass on that instead of on the map.
    pd.DataFrame([{"market": "shots_on_goal", "use_rest": False}]).to_csv(
        outputs / "prop_calibration_samples.csv", index=False
    )
    seen = []

    def fake_backtest(prices, samples, **kwargs):
        seen.append(kwargs.get("team_names"))
        if raises:
            raise raises
        return _Report()

    class _Timeline:
        pooled: dict = {}
        bucketed: dict = {}

    monkeypatch.setattr(module, "expand_to_lines", lambda s: s)
    monkeypatch.setattr(module, "build_timeline", lambda g: _Timeline())
    monkeypatch.setattr(module, "run_backtest", fake_backtest)
    code = module.main(["--processed-dir", str(processed), "--output-dir", str(outputs)])
    return code, seen


def _props_rest(tmp_path, monkeypatch, *, raises=None):
    module = _script("run_props_rest_experiment.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    _prices(processed)
    seen = []

    class _Walk:
        def summary_line(self):
            return "stub"

    def fake_backtest(prices, samples, **kwargs):
        seen.append(kwargs.get("team_names"))
        if raises:
            raise raises
        return _Report()

    monkeypatch.setattr(module, "load_player_logs", lambda p: pd.DataFrame([{"x": 1}]))
    monkeypatch.setattr(module, "generate_prop_samples", lambda logs, use_rest: (pd.DataFrame(), _Walk()))
    monkeypatch.setattr(module, "run_backtest", fake_backtest)
    code = module.main(["--processed-dir", str(processed), "--output-dir", str(outputs)])
    return code, seen


@pytest.mark.parametrize("run", [_correction, _props_rest], ids=["correction", "props_rest"])
def test_the_map_comes_from_the_processed_dir(tmp_path, monkeypatch, run):
    tn.save_team_name_map(TEAM_MAP, processed_dir=tmp_path / "processed")
    code, seen = run(tmp_path, monkeypatch)
    assert seen, "run_backtest was never reached"
    for passed in seen:
        assert passed is not None, "no map passed: run_backtest builds its own from the cache"
        assert passed == TEAM_MAP


@pytest.mark.parametrize("run", [_correction, _props_rest], ids=["correction", "props_rest"])
def test_a_map_that_resolves_nothing_is_a_refusal_not_a_report(tmp_path, monkeypatch, run):
    tn.save_team_name_map(TEAM_MAP, processed_dir=tmp_path / "processed")
    code, _ = run(tmp_path, monkeypatch, raises=UnresolvedTeamsError("nothing resolves"))
    assert code == 2
    assert not list((tmp_path / "outputs").glob("*experiment*"))
