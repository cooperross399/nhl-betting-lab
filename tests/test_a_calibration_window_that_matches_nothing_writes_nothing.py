"""A calibration window that yields no sample writes nothing and fails.

`scripts/run_props_calibration.py --start-date/--end-date` named a window the
logs did not reach — a mistyped year, or an end date before the first refit
had its 200 games of history — and `generate_prop_samples` returned an empty
frame. The runner then wrote a header-only samples cache, overwrote the
contract output `props_calibration.md`/`.json` with "not measured", replaced
the committed `current_corrections.json` (7 pooled and 26 bucketed curves)
with an empty one, and exited 0. The props backtest runner had the same defect
and was fixed to refuse; this is the calibration runner's copy.

What these tests hold:

* a named window that yields no sample from non-empty logs exits 1, prints an
  `::error::` naming the window and the range the logs do cover, and leaves
  the samples cache, both report files and the live corrections untouched;
* an unwindowed run that yields no sample never saves an empty set of
  corrections over a file that holds curves;
* the standing note in the calibration report never says the props backtest
  "measures nothing, because no historical prices have been bought" — it
  measured 25,911 bets against bought prices — and says whether a correction
  is in force only from the recorded verdict.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data.build_datasets import PLAYER_LOG_COLUMNS
from nhl_betting_lab.reports.props_calibration import (
    build_calibration_report,
    render_calibration,
)


def _script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CURVES = {
    "fitted_at": "2026-09-20T00:00:00+00:00",
    "pooled": {
        "shots_on_goal": {"intercept": 0.1, "slope": 0.9, "fitted_on": 5000},
    },
    "bucketed": {
        "shots_on_goal|15-18": {"intercept": 0.2, "slope": 0.8, "fitted_on": 900},
    },
}
REPORT_MD = "# Player props calibration\n\nthe committed measurement\n"
REPORT_JSON = '{"committed": true}\n'
SAMPLES_CSV = "date,game_id,player_id\n2025-10-08,1,1\n"


def _world(tmp_path: Path) -> tuple[Path, Path]:
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    processed.mkdir(parents=True)
    outputs.mkdir(parents=True)
    rows = []
    for index, (day, player) in enumerate(
        [("2025-10-08", 1), ("2025-10-10", 2), ("2025-10-12", 3)]
    ):
        row = {column: 0 for column in PLAYER_LOG_COLUMNS}
        row.update(
            game_id=2025020001 + index, season=20252026, game_type=2,
            date=day, start_time_utc=f"{day}T23:00:00Z", player_id=player,
            player=f"P{player}", boxscore_name=f"P{player}", role="skater",
            position="C", team="TOR", opponent="MTL", venue="home",
            toi_seconds=1000, shots_on_goal=2,
        )
        rows.append(row)
    pd.DataFrame(rows).to_csv(processed / "player_game_logs.csv", index=False)
    (processed / "current_corrections.json").write_text(
        json.dumps(CURVES), encoding="utf-8"
    )
    (outputs / "props_calibration.md").write_text(REPORT_MD, encoding="utf-8")
    (outputs / "props_calibration.json").write_text(REPORT_JSON, encoding="utf-8")
    (outputs / "prop_calibration_samples.csv").write_text(
        SAMPLES_CSV, encoding="utf-8"
    )
    return processed, outputs


def _untouched(processed: Path, outputs: Path) -> None:
    assert json.loads(
        (processed / "current_corrections.json").read_text(encoding="utf-8")
    ) == CURVES
    assert (outputs / "props_calibration.md").read_text(encoding="utf-8") == REPORT_MD
    assert (
        (outputs / "props_calibration.json").read_text(encoding="utf-8")
        == REPORT_JSON
    )
    assert (
        (outputs / "prop_calibration_samples.csv").read_text(encoding="utf-8")
        == SAMPLES_CSV
    )


@pytest.mark.parametrize(
    "window",
    [["--start-date", "2052-10-01"], ["--end-date", "2025-10-09"]],
    ids=["start-after-the-logs", "end-before-any-history"],
)
def test_a_named_window_with_no_sample_refuses_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], window: list[str]
) -> None:
    processed, outputs = _world(tmp_path)
    runner = _script("run_props_calibration.py")
    code = runner.main(
        [*window, "--processed-dir", str(processed), "--output-dir", str(outputs)]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "::error::" in err
    assert window[1] in err, err
    # The range the logs do cover, so a mistyped year reads as one.
    assert "2025-10-08" in err and "2025-10-12" in err, err
    _untouched(processed, outputs)


def test_an_unwindowed_run_with_no_sample_keeps_the_live_curves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    processed, outputs = _world(tmp_path)
    runner = _script("run_props_calibration.py")
    runner.main(["--processed-dir", str(processed), "--output-dir", str(outputs)])
    out = capsys.readouterr().out
    assert json.loads(
        (processed / "current_corrections.json").read_text(encoding="utf-8")
    ) == CURVES
    assert "no correction on file" not in out.split("Live corrections")[-1][:80]


def test_an_empty_fit_is_still_saved_where_no_curve_was_on_file(
    tmp_path: Path,
) -> None:
    processed, outputs = _world(tmp_path)
    (processed / "current_corrections.json").unlink()
    runner = _script("run_props_calibration.py")
    runner.main(["--processed-dir", str(processed), "--output-dir", str(outputs)])
    saved = json.loads(
        (processed / "current_corrections.json").read_text(encoding="utf-8")
    )
    assert saved["pooled"] == {} and saved["bucketed"] == {}


def _samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": f"2025-11-{1 + i % 28:02d}", "game_id": 100 + i,
             "player_id": 7, "market": "shots_on_goal", "mean": 2.9,
             "dispersion_r": float("nan"), "actual": i % 6,
             "toi_seconds": 1100, "expected_toi_seconds": 1100.0}
            for i in range(60)
        ]
    )


def test_the_report_never_says_no_prices_were_bought() -> None:
    for in_force in (None, False, True):
        text = render_calibration(
            build_calibration_report(_samples(), by_toi_ships=in_force)
        )
        assert "no historical prices have been bought" not in text
        assert "currently measures nothing" not in text


def test_whether_a_correction_is_in_force_comes_from_the_verdict() -> None:
    off = render_calibration(
        build_calibration_report(_samples(), by_toi_ships=False)
    )
    on = render_calibration(
        build_calibration_report(_samples(), by_toi_ships=True)
    )
    unread = render_calibration(build_calibration_report(_samples()))
    assert "Neither correction is in force on the card" in off
    assert "Neither correction is in force" not in on
    assert "by-ice-time correction is in force on the card" in on
    assert "Neither correction is in force" not in unread
    assert "correction_experiment.json" in unread


def test_the_runner_passes_the_recorded_by_toi_verdict(tmp_path: Path) -> None:
    """The committed verdict ships nothing, so the runner's report says
    neither correction is in force; a verdict that ships by_toi says so."""
    runner = _script("run_props_calibration.py")
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    seen: list[object] = []
    original = runner.build_calibration_report

    def spy(samples, **kwargs):
        seen.append(kwargs.get("by_toi_ships"))
        return original(samples, **kwargs)

    runner.build_calibration_report = spy
    (outputs / "correction_experiment.json").write_text(
        json.dumps({"ships": ["by_toi"]}), encoding="utf-8"
    )
    processed = tmp_path / "processed"
    processed.mkdir()
    _world_logs = _world(tmp_path / "w")[0] / "player_game_logs.csv"
    (processed / "player_game_logs.csv").write_bytes(_world_logs.read_bytes())
    runner.main(["--processed-dir", str(processed), "--output-dir", str(outputs)])
    (outputs / "correction_experiment.json").write_text(
        json.dumps({"ships": []}), encoding="utf-8"
    )
    runner.main(["--processed-dir", str(processed), "--output-dir", str(outputs)])
    assert seen == [True, False]
