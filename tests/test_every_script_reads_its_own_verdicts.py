"""A script given --output-dir must read the recorded verdicts from it.

`verdicts.ships(policy, output_dir=...)` falls back to the default
`data/outputs` when no directory is passed. The card and the props calibration
pass theirs; the team measurement did not, so
`run_team_markets_measurement.py --output-dir O` measured with the rest
adjustment on whenever the default directory said `team_b2b` ships, even when
O's own `rest_experiment.json` had withdrawn it — and a card run with the same
O priced without it. The measurement and the card then described two
different policies. (Found by the failure-shape audit; reproduced with the
real `run_rest_experiment.py` writing `{"ships": []}` into a scratch O.)

What these tests hold:

* the runner's `use_rest` follows the verdict in its --output-dir in BOTH
  directions, with the default directory holding the opposite verdict each
  time, so neither a hard-coded value nor the default read can pass;
* every call to a `nhl_betting_lab.verdicts` reader in a script that defines
  --output-dir passes `output_dir=`, read off the syntax tree so a new call
  site cannot be added without it.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import verdicts
from nhl_betting_lab.config import PROJECT_ROOT


SCRIPTS = PROJECT_ROOT / "scripts"


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _record(directory: Path, ships: list[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / verdicts.VERDICT_FILES["team_b2b"]).write_text(
        json.dumps({"ships": ships}), encoding="utf-8"
    )


def _samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2025-01-05", "game_id": 1, "home_team": "TOR",
                "away_team": "BOS", "market": "moneyline", "selection": "home",
                "line": None, "model_probability": 0.55, "outcome": True,
                "push": False,
            }
        ]
    )


@pytest.mark.parametrize(
    ("in_output_dir", "in_default_dir", "expected"),
    [([], ["team_b2b"], False), (["team_b2b"], [], True)],
)
def test_the_team_measurement_uses_the_verdict_in_its_output_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    in_output_dir: list[str],
    in_default_dir: list[str],
    expected: bool,
) -> None:
    default = tmp_path / "default_outputs"
    outputs = tmp_path / "outputs"
    _record(default, in_default_dir)
    _record(outputs, in_output_dir)
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", default)

    module = load_script("run_team_markets_measurement.py")
    used: list[bool] = []
    monkeypatch.setattr(
        module, "load_team_games", lambda _dir: pd.DataFrame({"game_id": [1]})
    )

    def generate(_games, **kwargs):
        used.append(kwargs["use_rest"])
        return _samples(), SimpleNamespace(summary_line=lambda: "")

    monkeypatch.setattr(module, "generate_team_samples", generate)

    code = module.main(
        ["--processed-dir", str(tmp_path / "processed"),
         "--output-dir", str(outputs)]
    )
    capsys.readouterr()

    assert code == 0
    assert used == [expected]


def _verdict_readers(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "nhl_betting_lab.verdicts":
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _defines_output_dir(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Constant) and node.value == "--output-dir"
        for node in ast.walk(tree)
    )


def test_every_verdict_read_in_a_script_passes_its_output_dir() -> None:
    offenders: list[str] = []
    checked = 0
    for path in sorted(SCRIPTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        readers = _verdict_readers(tree) & {"ships", "describe_verdicts", "describe"}
        if not readers or not _defines_output_dir(tree):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in readers
            ):
                checked += 1
                if not any(kw.arg == "output_dir" for kw in node.keywords):
                    offenders.append(f"{path.name}:{node.lineno} {node.func.id}()")

    # The card, the props calibration and the team measurement read verdicts;
    # a scan that checked nothing would pass for the wrong reason.
    assert checked >= 6, f"only {checked} verdict read(s) found in scripts/"
    assert offenders == [], (
        "these read the recorded verdicts from the default directory although "
        f"the script was given --output-dir: {offenders}"
    )
