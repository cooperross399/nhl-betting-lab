"""An experiment that measured nothing recorded a verdict anyway.

`scripts/run_props_rest_experiment.py` names its window (`--phase card`) and
hands it to `run_backtest`, which — correctly — measures nothing when the
store holds no row in that window and says so in `report.notes`. The
experiment never read the note and never counted its bets: with both variants
at zero, `delta = 0 - 0` and `ships = delta > 0` is False, so it wrote
`"ships": []`, `"markets_measured": 0` and the verdict "Knowing about
back-to-backs costs +0.0u on the priced sample ... It does not ship", exit 0.
Found by the failure-shape audit (finding 40; 3/3 refuters). Reproduced with
the real script on the real four-hour store — 1,259,312 `late` rows, 749,115
walk-forward samples per variant — and the real `check_verdict_drift.py`
then reported `props_b2b` moving from in force to off and exited 1, the code
on which Experiment Refresh opens "A recorded verdict moved on the accumulated
data". The committed verdict it would have overturned is +18.7u over 7
markets. `--phase all`, which the backtest's own error message suggests, did
the same thing, because this script's `--phase` accepted any string.

The two siblings had the same shape. `run_correction_experiment.py` scored a
season window with no bets as a tie, so "beats raw on both windows" could be
written from one window, and an entirely empty run wrote `ships: []` — equal
to the committed record, so the drift check reported "Nothing moved", a clean
bill from a run that measured nothing. `run_rest_experiment.py` (team) summed
`None` markets to +0.0u and withdrew `team_b2b` the same way.

What these tests hold, driving the real `run_backtest` and the real team
`select_price_window`/`measure_prices` with sample generation stubbed:

* a store with no row in the named window, and a header-only store, make each
  experiment exit 2, write no file, and leave a verdict already on disk
  byte-identical — so the drift check reads it as "not re-decided" and the
  refresh fails instead of opening a pull request;
* a correction run in which one season window measured nothing is refused;
* the props experiments accept only a named window (`card`, `late`, `early`)
  and refuse `all` before generating anything;
* the control stores in the named window still record a verdict, and the
  props record now states the window it was measured in.
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
from nhl_betting_lab import verdicts
from nhl_betting_lab.providers import team_names as tn


#: Keyed the way production keys it: normalized lowercase provider names.
TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}

#: 7pm ET on the 9th is midnight UTC on the 10th; the league date is the 9th.
GAMES = {
    "2024-25": ("2025-01-10T00:00:00Z", "2025-01-09", 2024020600),
    "2025-26": ("2026-01-10T00:00:00Z", "2026-01-09", 2025020600),
}
CARD_HOURS = 9.5
LATE_HOURS = 4.0


def _script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _isolated_team_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No default directory is ever read: a missing map would otherwise be
    rebuilt from the real boxscore cache."""
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    monkeypatch.setattr(tn, "RAW_DIR", tmp_path / "default_raw")


@pytest.fixture(autouse=True)
def _no_recorded_verdicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No verdict is recorded anywhere these experiments look. Since #151 a
    directory that records no verdict reads the repository's recorded one
    (data/outputs ships props_b2b), so "no verdict in this output directory"
    would otherwise mean "the real repository's", and the rest-ignored
    samples below would be refused as the wrong policy."""
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", tmp_path / "recorded_verdicts")


def _prop_quote(season: str, hours_before: float, *, odds: int = 120) -> dict:
    commence, day, _ = GAMES[season]
    snapshot = pd.Timestamp(commence) - pd.Timedelta(hours=hours_before)
    return {
        "date": commence[:10], "commence_time": commence,
        "snapshot": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provider_event_id": f"evt-{day}", "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins", "market": "shots_on_goal",
        "player": "Auston Matthews", "selection": "over", "line": 3.5,
        "american_odds": odds, "book": "draftkings",
    }


def _prop_samples(*, mean: float = 4.2, use_rest: bool = True) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": day, "game_id": game_id, "player_id": 8479318,
                "player": "Auston Matthews", "team": "TOR", "opponent": "BOS",
                "venue": "home", "market": "shots_on_goal", "mean": mean,
                "dispersion_r": float("nan"), "actual": 5.0,
                "toi_seconds": 1200, "expected_toi_seconds": 1180.0,
                "use_rest": use_rest,
            }
            for _, day, game_id in GAMES.values()
        ]
    )


def _store(processed: Path, rows: list[dict], name: str) -> None:
    processed.mkdir(parents=True, exist_ok=True)
    columns = list(_prop_quote("2024-25", CARD_HOURS)) if "prop" in name else None
    pd.DataFrame(rows, columns=columns).to_csv(processed / name, index=False)
    tn.save_team_name_map(TEAM_MAP, processed_dir=processed)


class _Walk:
    def summary_line(self) -> str:
        return "stub"


# --------------------------------------------------------------------------
# The props rest experiment.
# --------------------------------------------------------------------------

def _props_rest(tmp_path, monkeypatch, rows: list[dict], *argv: str):
    module = _script("run_props_rest_experiment.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    _store(processed, rows, "historical_prop_prices.csv")
    generated: list[bool] = []

    def generate(logs, use_rest):
        generated.append(use_rest)
        # Rest-known prices a little higher, so a measured run has a delta.
        return _prop_samples(mean=4.4 if use_rest else 4.2), _Walk()

    monkeypatch.setattr(module, "load_player_logs", lambda _: pd.DataFrame([{"x": 1}]))
    monkeypatch.setattr(module, "generate_prop_samples", generate)
    code = module.main([
        "--processed-dir", str(processed), "--output-dir", str(outputs),
        "--edge-threshold", "-1", *argv,
    ])
    return code, outputs, generated


def _committed_record(outputs: Path, filename: str) -> bytes:
    """A verdict already on disk, as the checkout leaves it in the refresh."""
    outputs.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"ships": ["kept"], "verdict": "committed"}).encode()
    (outputs / filename).write_bytes(body)
    return body


@pytest.mark.parametrize(
    "rows",
    [
        [_prop_quote("2024-25", LATE_HOURS), _prop_quote("2025-26", LATE_HOURS)],
        [],
    ],
    ids=["only-the-late-window", "header-only-store"],
)
def test_the_props_rest_experiment_refuses_a_window_it_did_not_measure(
    tmp_path, monkeypatch, capsys, rows
):
    committed = _committed_record(tmp_path / "outputs", "props_rest_experiment.json")

    code, outputs, generated = _props_rest(tmp_path, monkeypatch, rows)
    err = capsys.readouterr().err

    assert code == 2
    assert generated == [False, True], "both variants ran and measured nothing"
    assert (outputs / "props_rest_experiment.json").read_bytes() == committed
    assert not (outputs / "props_rest_experiment.md").exists()
    assert "::error::" in err and "`card`" in err
    assert "placed no bet" in err


def test_the_props_rest_experiment_still_records_a_measured_window(
    tmp_path, monkeypatch
):
    rows = [_prop_quote("2024-25", CARD_HOURS), _prop_quote("2025-26", CARD_HOURS),
            _prop_quote("2025-26", LATE_HOURS, odds=300)]

    code, outputs, _ = _props_rest(tmp_path, monkeypatch, rows)

    assert code == 0
    record = json.loads((outputs / "props_rest_experiment.json").read_text())
    assert record["markets_measured"] == 1
    assert record["results"]["rest_known"]["shots_on_goal"]["bets"] == 2
    # The window a drift reader is told to check is now on the record.
    assert record["phase"] == "card"
    assert record["phase_hours"] == pytest.approx(CARD_HOURS)
    assert "`card` window" in (outputs / "props_rest_experiment.md").read_text()


@pytest.mark.parametrize("script", [
    "run_props_rest_experiment.py", "run_correction_experiment.py",
])
@pytest.mark.parametrize("phase", ["all", "auto", "Card"])
def test_the_props_experiments_accept_only_a_named_window(
    tmp_path, monkeypatch, script, phase
):
    """`all` measured the mixture as a window named "all" that matches
    nothing; it is refused by the parser, before anything is generated."""
    module = _script(script)
    touched: list[str] = []
    monkeypatch.setattr(module, "pd", None)  # any read of a store would crash
    if hasattr(module, "load_player_logs"):
        monkeypatch.setattr(module, "load_player_logs",
                            lambda _: touched.append("logs") or pd.DataFrame())
    with pytest.raises(SystemExit) as exit_:
        module.main(["--phase", phase, "--processed-dir", str(tmp_path),
                     "--output-dir", str(tmp_path / "outputs")])
    assert exit_.value.code == 2
    assert touched == []
    assert not (tmp_path / "outputs").exists()


# --------------------------------------------------------------------------
# The correction experiment.
# --------------------------------------------------------------------------

def _correction(tmp_path, rows: list[dict]):
    module = _script("run_correction_experiment.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    _store(processed, rows, "historical_prop_prices.csv")
    outputs.mkdir(parents=True, exist_ok=True)
    # No verdict in this output directory ships props_b2b, so the samples
    # the experiment may use are the rest-ignored ones.
    _prop_samples(use_rest=False).to_csv(
        outputs / "prop_calibration_samples.csv", index=False
    )
    code = module.main([
        "--processed-dir", str(processed), "--output-dir", str(outputs),
        "--edge-threshold", "-1",
    ])
    return code, outputs


@pytest.mark.parametrize(
    "rows",
    [
        [_prop_quote("2024-25", LATE_HOURS), _prop_quote("2025-26", LATE_HOURS)],
        # One season window measured, the other empty: "beats raw on both
        # windows" would be written from one.
        [_prop_quote("2024-25", LATE_HOURS), _prop_quote("2025-26", CARD_HOURS)],
        [],
    ],
    ids=["only-the-late-window", "one-season-window-empty", "header-only-store"],
)
def test_the_correction_experiment_refuses_a_window_it_did_not_measure(
    tmp_path, capsys, rows
):
    committed = _committed_record(tmp_path / "outputs", "correction_experiment.json")

    code, outputs = _correction(tmp_path, rows)
    err = capsys.readouterr().err

    assert code == 2
    assert (outputs / "correction_experiment.json").read_bytes() == committed
    assert not (outputs / "correction_experiment.md").exists()
    assert "::error::" in err and "placed no bet" in err
    assert "2024-25" in err


def test_the_correction_experiment_still_records_measured_windows(tmp_path):
    rows = [_prop_quote("2024-25", CARD_HOURS), _prop_quote("2025-26", CARD_HOURS)]

    code, outputs = _correction(tmp_path, rows)

    assert code == 0
    record = json.loads((outputs / "correction_experiment.json").read_text())
    assert record["results"]["2024-25"]["raw"]["bets"] == 1
    assert record["results"]["2025-26"]["by_toi"]["bets"] == 1


# --------------------------------------------------------------------------
# The team rest experiment.
# --------------------------------------------------------------------------

def _team_quote(hours_before: float) -> dict:
    commence, _, _ = GAMES["2024-25"]
    snapshot = pd.Timestamp(commence) - pd.Timedelta(hours=hours_before)
    return {
        "date": commence[:10], "commence_time": commence,
        "snapshot": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "market": "moneyline", "player": "", "selection": "home", "line": None,
        "american_odds": -120, "book": "draftkings",
    }


def _team_samples(probability: float) -> pd.DataFrame:
    _, day, game_id = GAMES["2024-25"]
    return pd.DataFrame([{
        "date": day, "game_id": game_id, "home_team": "TOR", "away_team": "BOS",
        "market": "moneyline", "selection": "home", "line": None,
        "model_probability": probability, "outcome": True, "push": False,
    }])


def _team_rest(tmp_path, monkeypatch, rows: list[dict]):
    module = _script("run_rest_experiment.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    processed.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(_team_quote(2.0))).to_csv(
        processed / "historical_team_prices.csv", index=False
    )
    tn.save_team_name_map(TEAM_MAP, processed_dir=processed)

    def generate(games, use_rest):
        return _team_samples(0.66 if use_rest else 0.62), _Walk()

    monkeypatch.setattr(module, "load_team_games", lambda _: pd.DataFrame([{"g": 1}]))
    monkeypatch.setattr(module, "generate_team_samples", generate)
    code = module.main([
        "--processed-dir", str(processed), "--output-dir", str(outputs),
        "--edge-threshold", "-1",
    ])
    return code, outputs


@pytest.mark.parametrize(
    "rows", [[_team_quote(20.0)], []], ids=["only-the-early-window", "header-only-store"]
)
def test_the_team_rest_experiment_refuses_a_window_it_did_not_measure(
    tmp_path, monkeypatch, capsys, rows
):
    committed = _committed_record(tmp_path / "outputs", "rest_experiment.json")

    code, outputs = _team_rest(tmp_path, monkeypatch, rows)
    err = capsys.readouterr().err

    assert code == 2
    assert (outputs / "rest_experiment.json").read_bytes() == committed
    assert not (outputs / "rest_experiment.md").exists()
    assert "::error::" in err and "placed no bet" in err


def test_the_team_rest_experiment_still_records_a_measured_window(
    tmp_path, monkeypatch
):
    code, outputs = _team_rest(tmp_path, monkeypatch, [_team_quote(2.0)])

    assert code == 0
    record = json.loads((outputs / "rest_experiment.json").read_text())
    assert record["results"]["rest_known"]["moneyline"]["bets"] == 1
    assert record["phase"] == "late"
