"""The team measurement read its team-name map from the default directory.

`measure_prices` called `load_team_name_map()` with no directory, so it read
`data/processed/team_names.csv` whatever `--processed-dir` the runner was
given. That file is gitignored. In a worktree, where it does not exist and no
boxscores are cached to rebuild it from, the fallback map holds only the Utah
and Arizona aliases. Measured on the bought `late` window (212,964 rows): that
map resolved ONE side of 14,514 rows (every Utah game) and BOTH sides of none.
Every price joined nothing, every market measured zero bets, and the report
printed "0 market(s) have any price-based evidence", which
`what_we_can_claim.md` renders as "no historical prices have been bought".
Copying the file into the worktree reproduced the committed report exactly
(moneyline 954, puck line 1,117, totals 1,216 bets).

What these tests hold:

* prices with a map that resolves no row REFUSE, through the report and
  through the runner (`::error::`, exit 2, no report written), and an explicit
  empty map is not quietly swapped for the default directory's;
* one resolvable side is not a resolved row, because the aliases alone always
  supply one side of a Utah game, and a guard counting sides would never fire;
* the directory passed is the one read, in both directions: a map only in the
  passed directory measures, and a map only in the default directory does not
  rescue a passed directory that lacks one;
* the unresolved count is recorded when it is zero and when it is not.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as team_names_module
from nhl_betting_lab.providers.team_names import (
    TEAM_NAMES_FILENAME,
    build_team_name_map,
    resolve_team,
    save_team_name_map,
)
from nhl_betting_lab.reports import team_markets_measurement as tmm
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: Keyed exactly as `load_team_name_map` returns it: normalized name -> abbrev.
TEAM_MAP = {
    "toronto maple leafs": "TOR",
    "boston bruins": "BOS",
    "seattle kraken": "SEA",
}

#: Evening face-offs in UTC, so the league date is the day before.
GAMES = [
    ("2025-01-09", "2025-01-10T00:00:00Z"),
    ("2025-01-11", "2025-01-12T00:00:00Z"),
    ("2025-01-14", "2025-01-15T00:00:00Z"),
]


def _samples(home: str = "TOR", away: str = "BOS") -> pd.DataFrame:
    """The model says 60% home on every game; the home side wins them all."""
    return pd.DataFrame(
        [
            {
                "game_id": index,
                "date": day,
                "home_team": home,
                "away_team": away,
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "model_probability": 0.60,
                "outcome": True,
                "push": False,
            }
            for index, (day, _) in enumerate(GAMES)
        ]
    )


def _prices(
    home: str = "Toronto Maple Leafs", away: str = "Boston Bruins"
) -> pd.DataFrame:
    """One `late`-window moneyline quote per game, named as the provider names
    teams. +150 is 40% implied against the model's 60%, so each is a bet."""
    rows = []
    for day, commence in GAMES:
        snapshot = pd.Timestamp(commence) - pd.Timedelta(hours=4)
        rows.append(
            {
                "date": day,
                "commence_time": commence,
                "snapshot": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "home_team": home,
                "away_team": away,
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "american_odds": 150,
                "book": "DraftKings",
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Point the default processed and raw directories at empty scratch ones.

    Without this the tests would read the real `data/processed/team_names.csv`
    and boxscore cache wherever they exist, and pass or fail by checkout —
    which is the defect under test. Every other default goes too: the two
    runner tests read the tracked verdicts through their scratch
    `--output-dir` (#151) until it did.
    """
    point_default_data_dirs_at(monkeypatch, tmp_path / "checkout_defaults")
    processed = tmp_path / "default_processed"
    raw = tmp_path / "default_raw"
    processed.mkdir()
    raw.mkdir()
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", processed)
    monkeypatch.setattr(team_names_module, "RAW_DIR", raw)
    return SimpleNamespace(processed=processed, raw=raw)


# --------------------------------------------------------------------------
# No row resolves: refuse.
# --------------------------------------------------------------------------

def test_an_explicit_empty_map_refuses_rather_than_reporting_zero_bets(
    defaults: SimpleNamespace,
) -> None:
    """And is not swapped for the default directory's map on the way.

    `team_names or load_team_name_map()` treated `{}` as "none passed". A
    valid map sits in the default directory here, so that swap would measure
    three bets and this would not raise.
    """
    save_team_name_map(TEAM_MAP, processed_dir=defaults.processed)

    with pytest.raises(tmm.UnresolvedTeamsError) as caught:
        tmm.build_team_measurement(
            _samples(), _prices(), team_names={}, phase="late"
        )

    message = str(caught.value)
    assert "Toronto Maple Leafs" in message and "Boston Bruins" in message
    assert "3 `moneyline` price row(s)" in message


def test_an_absent_team_name_file_refuses_too(
    tmp_path: Path, defaults: SimpleNamespace
) -> None:
    """The worktree case: no `team_names.csv`, no boxscores to rebuild from."""
    passed = tmp_path / "passed"
    passed.mkdir()

    with pytest.raises(tmm.UnresolvedTeamsError):
        tmm.build_team_measurement(
            _samples(), _prices(), processed_dir=passed, phase="late"
        )


def test_one_resolvable_side_is_not_a_resolved_row(
    tmp_path: Path, defaults: SimpleNamespace
) -> None:
    """The fallback map always resolves Utah, so a per-side guard never fires.

    On the bought late window the alias-only map resolved one side of 14,514
    rows and both sides of none. This is that shape in miniature.
    """
    aliases_only = build_team_name_map(defaults.raw)
    assert resolve_team("Utah Mammoth", aliases_only) == "UTA"
    assert resolve_team("Toronto Maple Leafs", aliases_only) is None

    with pytest.raises(tmm.UnresolvedTeamsError):
        tmm.build_team_measurement(
            _samples(home="UTA", away="TOR"),
            _prices(home="Utah Mammoth", away="Toronto Maple Leafs"),
            processed_dir=tmp_path / "absent",
            phase="late",
        )


def test_a_row_already_keyed_by_abbreviation_needs_no_map(
    defaults: SimpleNamespace,
) -> None:
    """Hand-built stores say "TOR". That is not an unresolved name."""
    report = tmm.build_team_measurement(
        _samples(), _prices(home="TOR", away="BOS"), team_names={}, phase="late"
    )

    assert report.markets[0].priced.bets == 3
    assert report.unresolved_team_rows == 0


# --------------------------------------------------------------------------
# The passed directory is the one read, in both directions.
# --------------------------------------------------------------------------

def test_a_map_only_in_the_passed_directory_is_used(
    tmp_path: Path, defaults: SimpleNamespace
) -> None:
    passed = tmp_path / "passed"
    save_team_name_map(TEAM_MAP, processed_dir=passed)
    assert not (defaults.processed / TEAM_NAMES_FILENAME).exists()

    report = tmm.build_team_measurement(
        _samples(), _prices(), processed_dir=passed, phase="late"
    )
    direct = tmm.measure_prices(
        _prices(), _samples(), market="moneyline", processed_dir=passed
    )

    assert report.markets[0].priced.bets == 3
    assert report.unresolved_team_rows == 0
    assert direct is not None and direct.bets == 3


def test_a_map_only_in_the_default_directory_does_not_rescue_the_passed_one(
    tmp_path: Path, defaults: SimpleNamespace
) -> None:
    """The old code read the default directory, so this measured three bets."""
    save_team_name_map(TEAM_MAP, processed_dir=defaults.processed)
    passed = tmp_path / "passed"
    passed.mkdir()

    with pytest.raises(tmm.UnresolvedTeamsError) as caught:
        tmm.build_team_measurement(
            _samples(), _prices(), processed_dir=passed, phase="late"
        )

    assert str(passed) in str(caught.value)


# --------------------------------------------------------------------------
# Through the runner, the way a workflow calls it.
# --------------------------------------------------------------------------

def _run_script(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    processed: Path,
    outputs: Path,
) -> tuple[int, str, str]:
    module = load_script("run_team_markets_measurement.py")
    # The walk-forward is not what is under test; the wiring from
    # `--processed-dir` to the team-name map is.
    monkeypatch.setattr(
        module, "load_team_games", lambda _dir: pd.DataFrame({"game_id": [0]})
    )
    monkeypatch.setattr(
        module,
        "generate_team_samples",
        lambda *_a, **_k: (_samples(), SimpleNamespace(summary_line=lambda: "")),
    )
    code = module.main(
        [
            "--phase", "late",
            "--processed-dir", str(processed),
            "--output-dir", str(outputs),
        ]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_runner_reads_the_map_from_its_processed_dir(
    tmp_path: Path,
    defaults: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    save_team_name_map(TEAM_MAP, processed_dir=processed)
    _prices().to_csv(processed / "historical_team_prices.csv", index=False)

    code, out, _ = _run_script(monkeypatch, capsys, processed, outputs)
    payload = json.loads(
        (outputs / tmm.MEASUREMENT_JSON_FILENAME).read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["markets"][0]["bets"] == 3
    assert payload["unresolved_team_rows"] == 0
    assert "Unresolved team names: 0 priced row(s)." in out


def test_the_runner_refuses_when_its_processed_dir_has_no_map(
    tmp_path: Path,
    defaults: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 2 and `::error::`, as for a mixed window, and no report at all.

    A valid map sits in the default directory, which is what made the
    worktree run look like a measurement.
    """
    save_team_name_map(TEAM_MAP, processed_dir=defaults.processed)
    processed = tmp_path / "processed"
    processed.mkdir()
    outputs = tmp_path / "outputs"
    _prices().to_csv(processed / "historical_team_prices.csv", index=False)

    code, _, err = _run_script(monkeypatch, capsys, processed, outputs)

    assert code == 2
    assert any(line.startswith("::error::") for line in err.splitlines())
    assert "Toronto Maple Leafs" in err
    assert not (outputs / tmm.MEASUREMENT_MARKDOWN_FILENAME).exists()
    assert not (outputs / tmm.MEASUREMENT_JSON_FILENAME).exists()


def test_the_refusal_names_a_flag_the_runner_accepts() -> None:
    """An error instructing an impossible action reads as operator error."""
    with pytest.raises(tmm.UnresolvedTeamsError) as caught:
        tmm.measure_prices(
            _prices(), _samples(), market="moneyline", team_names={}
        )
    assert "--processed-dir" in str(caught.value)

    module = load_script("run_team_markets_measurement.py")
    buffer = io.StringIO()
    with pytest.raises(SystemExit) as exit_info, redirect_stdout(buffer):
        module.main(["--help"])

    assert exit_info.value.code == 0
    assert "--processed-dir" in buffer.getvalue()


# --------------------------------------------------------------------------
# The count is recorded either way.
# --------------------------------------------------------------------------

def test_a_fully_resolved_store_records_zero_unresolved(
    tmp_path: Path, defaults: SimpleNamespace
) -> None:
    report = tmm.build_team_measurement(
        _samples(), _prices(), team_names=TEAM_MAP, phase="late"
    )
    tmm.save_team_measurement(report, output_dir=tmp_path)
    payload = json.loads(
        (tmp_path / tmm.MEASUREMENT_JSON_FILENAME).read_text(encoding="utf-8")
    )

    assert payload["unresolved_team_rows"] == 0
    assert payload["unresolved_team_names"] == []
    assert payload["markets"][0]["accounting"]["unresolved"] == 0
    assert any(
        note.startswith("Team names: 0 of the 3 prices scored")
        for note in report.notes
    )


def test_a_partly_resolved_store_counts_and_names_what_did_not_resolve(
    tmp_path: Path, defaults: SimpleNamespace
) -> None:
    """Counted apart from `unmatched`, which blames the grid, and reconciled."""
    samples = pd.concat(
        [_samples(), _samples(home="VAN", away="BOS").assign(game_id=99)],
        ignore_index=True,
    )
    prices = pd.concat(
        [_prices(), _prices(home="Vancouver Canucks").iloc[:1]],
        ignore_index=True,
    )

    report = tmm.build_team_measurement(
        samples, prices, team_names=TEAM_MAP, phase="late"
    )
    moneyline = report.markets[0]
    tmm.save_team_measurement(report, output_dir=tmp_path)
    payload = json.loads(
        (tmp_path / tmm.MEASUREMENT_JSON_FILENAME).read_text(encoding="utf-8")
    )
    rendered = tmm.render_team_measurement(report)

    assert moneyline.priced.bets == 3
    assert moneyline.accounting["seen"] == 4
    assert moneyline.accounting["unresolved"] == 1
    assert moneyline.accounting.get("unmatched", 0) == 0
    assert report.unresolved_team_rows == 1
    assert report.unresolved_team_names == ["Vancouver Canucks"]
    assert payload["unresolved_team_rows"] == 1
    assert payload["unresolved_team_names"] == ["Vancouver Canucks"]
    assert "Team names: 1 of the 4 prices scored" in rendered
    assert "Vancouver Canucks" in rendered
    assert "1 naming a team the map could not resolve" in rendered
    assert "DOES NOT RECONCILE" not in rendered
