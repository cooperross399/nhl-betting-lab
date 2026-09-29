"""A --from/--to window that matched no price row overwrote the contract report.

`run_player_props_backtest.py` filters the bought prices by `--from`/`--to`
before `run_backtest` sees them. A window that matched none of them (the case
`scripts/run_replication.py` records: `--from 2025-10-07 --to 2025-04-30
--label 2025-26`, end year mistyped, 0 of 3,804,233 rows) then:

* printed "No historical prop prices are on disk", one line after printing
  how many were;
* exited 0;
* overwrote the contract `player_props_backtest.json`/`.md` (which
  `save_backtest` always writes, whatever the label) with `rows_read: 0`,
  `bets: 0` and "No snapshot window was filtered" although `--phase late`
  was named — and `what_we_can_claim` reads `rows_read` 0 as a measurement
  that was handed no price, so every prop market left the claims document.

It now refuses the way prices-without-samples does: `::error::` naming the
window and the row count, a non-zero exit, nothing written. A window over an
empty store is still the "nothing has been bought" report, because that is
then true.
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


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TEAM_MAP = {"toronto maple leafs": "TOR", "ottawa senators": "OTT"}
COMMENCE = "2025-10-18T23:10:00Z"  # league date 2025-10-18
LATE = "2025-10-18T19:10:00Z"  # 4.0 hours before face-off


def _quote(player: str, odds: int, book: str) -> dict:
    return {
        "date": "2025-10-18",
        "commence_time": COMMENCE,
        "snapshot": LATE,
        "provider_event_id": "evt1",
        "home_team": "Toronto Maple Leafs",
        "away_team": "Ottawa Senators",
        "market": "shots_on_goal",
        "player": player,
        "selection": "over",
        "line": 2.5,
        "american_odds": odds,
        "book": book,
    }


PRICES = pd.DataFrame(
    [
        _quote("Auston Matthews", -110, "DraftKings"),
        _quote("Auston Matthews", 100, "FanDuel"),
        _quote("Brady Tkachuk", 105, "DraftKings"),
    ]
)

SAMPLES = pd.DataFrame(
    [
        {"date": "2025-10-18", "market": "shots_on_goal",
         "player": "Auston Matthews", "player_id": 1, "team": "TOR",
         "line": 2.5, "mean": 3.4, "dispersion_r": None, "actual": 4.0},
        {"date": "2025-10-18", "market": "shots_on_goal",
         "player": "Brady Tkachuk", "player_id": 2, "team": "OTT",
         "line": 2.5, "mean": 3.0, "dispersion_r": None, "actual": 1.0},
    ]
)

#: A contract report from an earlier, real run. A refusal must leave it alone.
PREVIOUS = {
    "player_props_backtest.md": "# Player props backtest\n\n- late, 550,225 priced outcomes\n",
    "player_props_backtest.json": '{"phase": "late", "rows_read": 3804233}\n',
    "player_props_backtest_bets.csv": "date,market\n2025-10-18,shots_on_goal\n",
}

#: The mistyped window from `scripts/run_replication.py`'s record.
MISTYPED = ("--from", "2025-10-07", "--to", "2025-04-30", "--label", "2025-26")


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    for name in ("RAW_DIR", "PROCESSED_DIR"):
        directory = tmp_path / f"default_{name.lower()}"
        directory.mkdir()
        monkeypatch.setattr(tn, name, directory)
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    processed.mkdir()
    outputs.mkdir()
    tn.save_team_name_map(TEAM_MAP, processed_dir=processed)
    SAMPLES.to_csv(outputs / "prop_calibration_samples.csv", index=False)
    for name, text in PREVIOUS.items():
        (outputs / name).write_text(text, encoding="utf-8")
    return processed, outputs


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def _run(processed: Path, outputs: Path, *extra: str) -> int:
    module = load_script("run_player_props_backtest.py")
    return module.main(
        [*extra, "--processed-dir", str(processed), "--output-dir", str(outputs)]
    )


def test_a_window_matching_no_row_refuses_and_writes_nothing(
    dirs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    processed, outputs = dirs
    PRICES.to_csv(processed / "historical_prop_prices.csv", index=False)
    before = _snapshot(outputs)

    code = _run(processed, outputs, "--phase", "late", *MISTYPED)
    captured = capsys.readouterr()

    assert code == 1, "a window that matched none of 3 rows exited as a measurement"
    assert _snapshot(outputs) == before, (
        "the contract report was overwritten by one that read 0 rows"
    )
    errors = [line for line in captured.err.splitlines() if line.startswith("::error::")]
    assert errors, "the refusal must be an ::error:: annotation"
    assert "2025-10-07" in errors[0] and "2025-04-30" in errors[0], (
        "name the window, so a mistyped date is visible"
    )
    assert "0 of 3 " in errors[0], "name how many rows are on disk"
    assert "on disk" not in captured.out, (
        "said no prices are on disk with 3 rows on disk"
    )


def test_a_one_sided_window_matching_nothing_refuses_too(
    dirs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    processed, outputs = dirs
    PRICES.to_csv(processed / "historical_prop_prices.csv", index=False)
    before = _snapshot(outputs)

    code = _run(processed, outputs, "--phase", "late", "--from", "2026-01-01")

    assert code == 1
    assert _snapshot(outputs) == before
    assert "::error::" in capsys.readouterr().err


def test_a_window_that_matches_rows_still_measures(
    dirs: tuple[Path, Path],
) -> None:
    processed, outputs = dirs
    PRICES.to_csv(processed / "historical_prop_prices.csv", index=False)

    code = _run(
        processed, outputs, "--phase", "late",
        "--from", "2025-10-01", "--to", "2025-10-31", "--label", "october",
    )

    assert code == 0
    assert (outputs / "player_props_backtest_october.json").is_file()


def test_a_window_over_an_empty_store_is_still_the_nothing_bought_report(
    dirs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    # No price file at all: "nothing has been bought" is true, and reported.
    processed, outputs = dirs

    code = _run(processed, outputs, "--phase", "late", *MISTYPED)

    assert code == 0
    assert "No historical prop prices are on disk" in capsys.readouterr().out
