"""The team rest experiment called an empty window "median 0.0 hours".

Found by the failure-shape audit (finding 42, 3/3 refuters, and separately by
its silent-empty-reports lens). On copies of the real team store — 308,944
rows, 247,160 in the `late` window, 61,784 in `early`, none in `card` —
`scripts/run_rest_experiment.py --phase card` used to exit 0 and record
`"ships": []` with "Knowing about back-to-backs costs +0.0u on the priced
sample", withdrawing `team_b2b`, recorded at +5.8u in `late`. #158 made it
refuse a run in which a variant placed no bet, and re-running the finding's
exact command on the base of this change shows that part is fixed: exit 2,
no `rest_experiment.md`, a pre-seeded `rest_experiment.json` byte-identical.

What #158 left is the line that describes the window. It had no empty case,
so the same run printed, on stdout and again inside the `::error::` that
refuses it:

    Priced in the `card` window, median 0.0 hours before face-off.

There was no price to take a median of; 0.0 is `select_price_window`'s
default. #147 fixed the identical sentence in the team measurement; this is
that fix, one caller over. Two neighbours of the case said something false
too: a header-only store, and `--phase auto` over a store whose every row was
captured after face-off, printed "The prices carry no window information" —
they carried it, and nothing was in the window. `--phase all` over such a
store printed "median 0.0 hours" as well.

CLAUDE.md's rule is "a named window that matches nothing measures nothing and
says so". What these tests hold, through the real script's `main`, the real
`select_price_window` and the real `measure_prices`, with only sample
generation stubbed:

* a window that kept no row prints no median, says no price in it was
  captured before face-off, and names the windows the store does hold — on
  stdout and in the refusal — and still writes nothing;
* `all` and `auto` read "in any window", not as a window of that name;
* a priced window still prints its median and its exclusions, and a store
  with no window columns still says it carries no window information.
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
from nhl_betting_lab.providers import team_names as team_names_module


#: Keyed the way `load_team_name_map` keys it: normalized name -> abbreviation.
TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}

#: Evening face-offs in UTC, so the league date is the day before.
GAMES = [
    ("2025-01-09", "2025-01-10T00:00:00Z", 2024020600),
    ("2025-01-11", "2025-01-12T00:00:00Z", 2024020620),
    ("2025-01-14", "2025-01-15T00:00:00Z", 2024020650),
]

#: The sentence #147 prints for the team measurement, and this now prints.
MISSED = (
    "No price row {where} was captured before face-off, so nothing was "
    "measured against a real price. The store's rows by window, before the "
    "face-off filter: {held}."
)

COLUMNS = [
    "date", "commence_time", "snapshot", "home_team", "away_team", "market",
    "selection", "line", "american_odds", "book",
]


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _store(*hours_before: float) -> list[dict]:
    """One home moneyline quote per game at each distance from face-off.

    2.0 hours is the `late` window and 20.0 the `early` one — the two the
    real store holds. At or after face-off (0.0, -1.0) `label_phases` still
    files a quote under `late`, and `select_price_window` drops it. +150 is
    40% implied against the model's 60%, so every kept quote is a bet.
    """
    rows = []
    for day, commence, _ in GAMES:
        for hours in hours_before:
            snapshot = pd.Timestamp(commence) - pd.Timedelta(hours=hours)
            rows.append({
                "date": day,
                "commence_time": commence,
                "snapshot": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "home_team": "Toronto Maple Leafs",
                "away_team": "Boston Bruins",
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "american_odds": 150,
                "book": "DraftKings",
            })
    return rows


def _samples(probability: float) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": day, "game_id": game_id, "home_team": "TOR",
            "away_team": "BOS", "market": "moneyline", "selection": "home",
            "line": None, "model_probability": probability, "outcome": True,
            "push": False,
        }
        for day, _, game_id in GAMES
    ])


class _Walk:
    def summary_line(self) -> str:
        return "stub"


@pytest.fixture(autouse=True)
def _isolated_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test here may read the real `data/processed` or boxscore cache."""
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", tmp_path / "default_processed")
    monkeypatch.setattr(team_names_module, "RAW_DIR", tmp_path / "default_raw")


def _run(tmp_path, monkeypatch, capsys, store: pd.DataFrame, *argv: str):
    """The real script, the real window selection and measurement."""
    module = load_script("run_rest_experiment.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    processed.mkdir()
    store.to_csv(processed / "historical_team_prices.csv", index=False)
    team_names_module.save_team_name_map(TEAM_MAP, processed_dir=processed)
    # A verdict already on disk, as the checkout leaves it in the refresh.
    outputs.mkdir()
    committed = json.dumps({"ships": ["team_b2b"], "verdict": "committed"}).encode()
    (outputs / "rest_experiment.json").write_bytes(committed)

    def generate(games, use_rest):
        # Rest-known a little more confident, so a priced run has a delta.
        return _samples(0.64 if use_rest else 0.60), _Walk()

    monkeypatch.setattr(module, "load_team_games", lambda _: pd.DataFrame([{"g": 1}]))
    monkeypatch.setattr(module, "generate_team_samples", generate)
    code = module.main([
        "--processed-dir", str(processed), "--output-dir", str(outputs), *argv,
    ])
    captured = capsys.readouterr()
    return code, captured.out, captured.err, outputs, committed


def test_a_window_the_store_lacks_prints_no_median(tmp_path, monkeypatch, capsys):
    """The finding's own case: `card` over a store of `late` and `early`."""
    store = pd.DataFrame(_store(2.0, 20.0))

    code, out, err, outputs, committed = _run(
        tmp_path, monkeypatch, capsys, store, "--phase", "card"
    )

    sentence = MISSED.format(
        where="in the `card` window", held="`early` (3 rows), `late` (3 rows)"
    )
    assert code == 2
    assert sentence in out, out
    assert "::error::" in err and "placed no bet" in err
    assert sentence in err, err
    for text in (out, err):
        assert "median" not in text
        assert "0.0 hours" not in text
    # Still refused, still nothing written: #158's guard, unchanged.
    assert (outputs / "rest_experiment.json").read_bytes() == committed
    assert not (outputs / "rest_experiment.md").exists()


@pytest.mark.parametrize(
    ("rows", "argv", "where", "held"),
    [
        # Every row of the named window was captured at or after face-off.
        (_store(0.0, -1.0), (), "in the `late` window", "`late` (6 rows)"),
        # A header-only store: nothing to read, in any window.
        ([], (), "in the `late` window", "none"),
        ([], ("--phase", "card"), "in the `card` window", "none"),
        # `auto` and `all` are not windows; an empty one is "any window".
        (_store(0.0, -1.0), ("--phase", "auto"), "in any window", "`late` (6 rows)"),
        (_store(0.0, -1.0), ("--phase", "all"), "in any window", "`late` (6 rows)"),
    ],
    ids=[
        "late-all-after-face-off", "header-only-late", "header-only-card",
        "auto-all-after-face-off", "all-all-after-face-off",
    ],
)
def test_every_empty_selection_says_so(
    tmp_path, monkeypatch, capsys, rows, argv, where, held
):
    store = pd.DataFrame(rows, columns=COLUMNS)

    code, out, err, outputs, committed = _run(
        tmp_path, monkeypatch, capsys, store, *argv
    )

    sentence = MISSED.format(where=where, held=held)
    assert code == 2
    assert sentence in out, out
    assert sentence in err, err
    for text in (out, err):
        assert "median" not in text
        assert "carry no window information" not in text
    assert (outputs / "rest_experiment.json").read_bytes() == committed


def test_a_priced_window_still_states_its_median(tmp_path, monkeypatch, capsys):
    """The control: the line every committed record carries is unchanged."""
    store = pd.DataFrame(_store(2.0, 20.0, -1.0))

    code, out, _, outputs, _ = _run(tmp_path, monkeypatch, capsys, store)

    line = (
        "Priced in the `late` window, median 2.0 hours before face-off. "
        "3 price row(s) captured at or after face-off and 3 from other "
        "windows were excluded."
    )
    assert code == 0
    assert line in out
    assert line in (outputs / "rest_experiment.md").read_text()
    assert "No price row" not in out
    record = json.loads((outputs / "rest_experiment.json").read_text())
    assert record["phase"] == "late"
    assert record["phase_hours"] == pytest.approx(2.0)
    assert record["results"]["rest_known"]["moneyline"]["bets"] == 3


def test_prices_without_window_columns_still_say_so(tmp_path, monkeypatch, capsys):
    """Not a window asked for and missed: there is no window to ask about,
    so the prices are measured as they are and the line says exactly that."""
    store = pd.DataFrame(_store(2.0)).drop(columns=["commence_time", "snapshot"])

    code, out, _, outputs, _ = _run(tmp_path, monkeypatch, capsys, store)

    assert code == 0
    assert "The prices carry no window information." in out
    assert "No price row" not in out
    assert "The prices carry no window information." in (
        outputs / "rest_experiment.md"
    ).read_text()
