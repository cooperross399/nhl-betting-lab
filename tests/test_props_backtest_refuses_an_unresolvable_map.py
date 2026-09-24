"""The props backtest measured on a team-name map that resolved nothing.

`run_backtest` checks that a priced player's team is one of the two teams in
the priced game — that is what stops a same-named player on another club
binding to the price. It built its map from the boxscore cache, never from the
runner's `--processed-dir`, and with no cache the map is the six Utah/Arizona
alias entries. Its own comment called that "an empty map" and "the
conservative direction". Neither held:

* no team resolved, so the team check was skipped and a lone same-named
  candidate was accepted whatever club they play for;
* in a Utah game the aliases resolve Utah alone, so the check kept only Utah
  players and voided every priced player on the other side.

On the bought store (3,804,233 rows) the full map resolves both teams of every
row; the alias-only map resolves both teams of none, and one side of 229,388.
The primary checkout's `team_names.csv` is identical to a rebuild from its
5,280 boxscores, so reading it through `--processed-dir` changes nothing there.

What these tests hold:

* a store whose games' two teams resolve nowhere REFUSES, and one resolvable
  side (Utah) is not a resolved game — measured anyway, Matthews is voided;
* a real map measures, and a store with no team labels is not refused;
* the runner reads the map from `--processed-dir`, and without one there it
  prints `::error::`, exits 2 and writes no report.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.providers.team_names import UnresolvedTeamsError
from nhl_betting_lab.reports.player_props_backtest import run_backtest


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TEAM_MAP = {
    "toronto maple leafs": "TOR",
    "ottawa senators": "OTT",
    "utah mammoth": "UTA",
}


def _prices(home: str = "Toronto Maple Leafs", away: str = "Ottawa Senators"):
    """One card-window hits quote on Auston Matthews, 9.5 hours out."""
    return pd.DataFrame(
        [
            {
                "date": "2025-10-18",
                "commence_time": "2025-10-18T19:10:00Z",
                "snapshot": "2025-10-18T09:40:00Z",
                "provider_event_id": "evt1",
                "home_team": home,
                "away_team": away,
                "market": "hits",
                "player": "Auston Matthews",
                "selection": "over",
                "line": 1.5,
                "american_odds": 200.0,
                "book": "ESPN BET",
            }
        ]
    )


def _samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2025-10-18",
                "market": "hits",
                "player": "Auston Matthews",
                "player_id": 1,
                "team": "TOR",
                "line": 1.5,
                "mean": 2.4,
                "dispersion_r": None,
                "actual": 3.0,
            }
        ]
    )


def _measure(prices: pd.DataFrame, **kwargs):
    return run_backtest(prices, _samples(), edge_threshold=0.0, phase="card",
                        **kwargs)


@pytest.fixture
def empty_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default raw and processed directories that hold nothing, so the real
    boxscore cache cannot rescue a test or make it pass by checkout."""
    for name in ("RAW_DIR", "PROCESSED_DIR"):
        directory = tmp_path / f"default_{name.lower()}"
        directory.mkdir()
        monkeypatch.setattr(tn, name, directory)


# --------------------------------------------------------------------------
# No game's two teams resolve: refuse.
# --------------------------------------------------------------------------

def test_an_alias_only_map_refuses(empty_cache: None) -> None:
    with pytest.raises(UnresolvedTeamsError) as caught:
        _measure(_prices())

    assert "Toronto Maple Leafs" in str(caught.value)
    assert "Ottawa Senators" in str(caught.value)


def test_one_resolvable_side_is_not_a_resolved_game(empty_cache: None) -> None:
    """Utah resolves from the aliases alone. Measured anyway, the team check
    keeps only Utah players, and Toronto's Matthews is voided."""
    assert tn.resolve_team("Utah Mammoth", tn.build_team_name_map()) == "UTA"

    try:
        report = _measure(_prices(home="Utah Mammoth", away="Toronto Maple Leafs"))
    except UnresolvedTeamsError:
        return
    raise AssertionError(
        "measured instead of refusing: hits bets "
        f"{report.by_market.get('hits').bets if report.by_market.get('hits') else 0}, "
        f"{report.outcomes_without_a_model_opinion} price(s) without a model "
        "opinion — the Toronto player was voided by a map that knew only Utah"
    )


# --------------------------------------------------------------------------
# What must still measure.
# --------------------------------------------------------------------------

def test_a_real_map_measures(empty_cache: None) -> None:
    report = _measure(_prices(), team_names=TEAM_MAP)

    assert report.by_market["hits"].bets == 1


def test_a_utah_game_measures_with_a_real_map(empty_cache: None) -> None:
    report = _measure(
        _prices(home="Utah Mammoth", away="Toronto Maple Leafs"),
        team_names=TEAM_MAP,
    )

    assert report.by_market["hits"].bets == 1


def test_a_partly_resolved_store_is_measured_not_refused(
    empty_cache: None,
) -> None:
    """The guard is for a broken map, not an odd game: one game the map does
    not know must not stop the rest being measured."""
    odd = _prices(home="Seattle Kraken")
    odd["player"] = "Someone Else"
    report = _measure(pd.concat([_prices(), odd], ignore_index=True),
                      team_names=TEAM_MAP)

    assert report.by_market["hits"].bets == 1


def test_a_store_with_no_team_labels_is_not_refused(empty_cache: None) -> None:
    """Nothing to resolve is not a failure to resolve."""
    report = _measure(_prices().drop(columns=["home_team", "away_team"]))

    assert report.by_market["hits"].bets == 1


# --------------------------------------------------------------------------
# Through the runner.
# --------------------------------------------------------------------------

def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    processed.mkdir(exist_ok=True)
    outputs.mkdir(exist_ok=True)
    _prices().to_csv(processed / "historical_prop_prices.csv", index=False)
    _samples().to_csv(outputs / "prop_calibration_samples.csv", index=False)
    module = load_script("run_player_props_backtest.py")
    code = module.main(
        ["--phase", "card", "--processed-dir", str(processed),
         "--output-dir", str(outputs)]
    )
    return code, capsys.readouterr().err


def test_the_runner_reads_the_map_from_its_processed_dir(
    tmp_path: Path, empty_cache: None, capsys: pytest.CaptureFixture[str]
) -> None:
    tn.save_team_name_map(TEAM_MAP, processed_dir=tmp_path / "processed")

    code, _ = _run(tmp_path, capsys)

    assert code == 0
    assert (tmp_path / "outputs" / "player_props_backtest.md").is_file()


def test_the_runner_refuses_without_a_map_and_writes_no_report(
    tmp_path: Path, empty_cache: None, capsys: pytest.CaptureFixture[str]
) -> None:
    code, err = _run(tmp_path, capsys)

    assert code == 2
    assert any(line.startswith("::error::") for line in err.splitlines())
    assert not (tmp_path / "outputs" / "player_props_backtest.md").exists()


def test_the_refusal_names_a_flag_the_runner_accepts(empty_cache: None) -> None:
    with pytest.raises(UnresolvedTeamsError) as caught:
        _measure(_prices())
    assert "--processed-dir" in str(caught.value)

    module = load_script("run_player_props_backtest.py")
    buffer = io.StringIO()
    with pytest.raises(SystemExit) as exit_info, redirect_stdout(buffer):
        module.main(["--help"])

    assert exit_info.value.code == 0
    assert "--processed-dir" in buffer.getvalue()
