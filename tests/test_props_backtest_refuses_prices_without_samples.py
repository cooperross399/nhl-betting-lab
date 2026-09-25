"""Prices on disk and no model samples wrote a report saying nothing was bought.

`run_player_props_backtest.py` reads the bought prices from `--processed-dir`
and the walk-forward samples from `--output-dir`. With prices present and the
samples absent — a worktree (the samples file is gitignored), or a purchase
`probe` run, which skips the step that builds them — `run_backtest` returned at
`if prices.empty or samples.empty: return report`, before the phase filter.
The runner exited 0 and overwrote the contract report with:

* "No snapshot window was filtered", although `--phase late` was named;
* "No historically-priced outcome cleared the edge threshold with a model
  opinion behind it ... Priced outcomes seen: 0", over 20,000 price rows;

and `run_what_we_can_claim.py` then said every prop market has "no historical
prices have been bought for it yet" — with 3,804,233 bought rows on disk. A
samples file that exists and fails to parse took the same road: `_load`
swallowed the ParserError, stdout said "No walk-forward samples are on disk",
and a copy of the real contract report went from `late` / 550,225 priced
outcomes to no window / 0. A damaged price store read as "no prices". The
early return also skipped the #117 team-map refusal. Found by the
failure-shape audit (3/3 refuters).

What these tests hold:

* prices with no samples REFUSE: `::error::` naming the samples file, a
  non-zero exit, and the previous contract report byte-identical;
* a samples file or a price store that exists and cannot be parsed refuses
  and says so, rather than reading as absent;
* `run_backtest` itself, handed no samples, still applies and records the
  named window, counts that window's wagers as outcomes without a model
  opinion, says why, and still refuses an alias-only team map.

No prices at all is unchanged: the report says nothing is measured and exits
0 (`tests/test_scripts.py::test_the_backtest_script_reports_that_nothing_is_measured`).
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
from nhl_betting_lab.reports import player_props_backtest as bt


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: Keyed the way production keys it: normalized lowercase names.
TEAM_MAP = {"toronto maple leafs": "TOR", "ottawa senators": "OTT"}

COMMENCE = "2025-10-18T23:10:00Z"  # 7:10pm ET, league date 2025-10-18
LATE = "2025-10-18T19:10:00Z"  # 4.0 hours before face-off
CARD = "2025-10-18T13:40:00Z"  # 9.5 hours before face-off


def _quote(snapshot: str, player: str, odds: int, book: str) -> dict:
    return {
        "date": "2025-10-18",
        "commence_time": COMMENCE,
        "snapshot": snapshot,
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


def _prices() -> pd.DataFrame:
    """Two windows: three late quotes on two wagers, three card quotes."""
    return pd.DataFrame(
        [
            _quote(LATE, "Auston Matthews", -110, "DraftKings"),
            _quote(LATE, "Auston Matthews", 100, "FanDuel"),
            _quote(LATE, "Brady Tkachuk", 105, "DraftKings"),
            _quote(CARD, "Auston Matthews", -120, "DraftKings"),
            _quote(CARD, "Brady Tkachuk", 100, "DraftKings"),
            _quote(CARD, "William Nylander", 110, "DraftKings"),
        ]
    )


def _samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": "2025-10-18", "market": "shots_on_goal",
             "player": "Auston Matthews", "player_id": 1, "team": "TOR",
             "line": 2.5, "mean": 3.4, "dispersion_r": None, "actual": 4.0},
            {"date": "2025-10-18", "market": "shots_on_goal",
             "player": "Brady Tkachuk", "player_id": 2, "team": "OTT",
             "line": 2.5, "mean": 3.0, "dispersion_r": None, "actual": 1.0},
        ]
    )


@pytest.fixture
def empty_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default raw and processed directories that hold nothing, so the real
    boxscore cache can neither rescue a test nor decide it by checkout."""
    for name in ("RAW_DIR", "PROCESSED_DIR"):
        directory = tmp_path / f"default_{name.lower()}"
        directory.mkdir()
        monkeypatch.setattr(tn, name, directory)


#: A contract report from an earlier, real run. A refusal must leave it alone.
PREVIOUS = {
    "player_props_backtest.md": "# Player props backtest\n\n- late, 550,225 priced outcomes\n",
    "player_props_backtest.json": '{"phase": "late", "priced_outcomes": 550225}\n',
    "player_props_backtest_bets.csv": "date,market\n2025-10-18,shots_on_goal\n",
    "player_props_backtest_card.md": "# card window\n",
    "player_props_backtest_card.json": '{"phase": "card"}\n',
}


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    processed.mkdir(exist_ok=True)
    outputs.mkdir(exist_ok=True)
    tn.save_team_name_map(TEAM_MAP, processed_dir=processed)
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


# --------------------------------------------------------------------------
# Through the runner, as both workflows call it.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flags", [("--phase", "card", "--label", "card"), ("--phase", "late")],
    ids=["card", "late"],
)
def test_prices_without_samples_refuse_and_leave_the_report_alone(
    tmp_path: Path, empty_cache: None, capsys: pytest.CaptureFixture[str],
    flags: tuple[str, ...],
) -> None:
    processed, outputs = _dirs(tmp_path)
    _prices().to_csv(processed / "historical_prop_prices.csv", index=False)
    before = _snapshot(outputs)

    code = _run(processed, outputs, *flags)
    captured = capsys.readouterr()

    assert code != 0, (
        "exited 0 having measured 6 price rows against no model at all"
    )
    errors = [line for line in captured.err.splitlines() if line.startswith("::error::")]
    assert errors, "the refusal must be an ::error:: annotation, not a stdout line"
    assert "prop_calibration_samples.csv" in errors[0], (
        "name the file that is missing, so the fix is obvious"
    )
    assert _snapshot(outputs) == before, (
        "the previous contract report was overwritten by one that says "
        "nothing was measured"
    )


@pytest.mark.parametrize(
    "content",
    [
        "date,market,player,player_id,team,line,mean,dispersion_r,actual\n"
        "2025-10-18,shots_on_goal,Auston Matthews,1,TOR,2.5,3.4,,4\n"
        "2025-10-18,shots_on_goal,Brady Tkachuk,2,OTT,2.5,3.0,,1,x,y,z\n",
        "",
    ],
    ids=["a-row-with-too-many-fields", "zero-bytes"],
)
def test_an_unreadable_samples_file_refuses_rather_than_reading_as_absent(
    tmp_path: Path, empty_cache: None, capsys: pytest.CaptureFixture[str],
    content: str,
) -> None:
    processed, outputs = _dirs(tmp_path)
    _prices().to_csv(processed / "historical_prop_prices.csv", index=False)
    (outputs / "prop_calibration_samples.csv").write_text(content, encoding="utf-8")
    before = _snapshot(outputs)

    code = _run(processed, outputs, "--phase", "late")
    captured = capsys.readouterr()

    assert code != 0
    assert "No walk-forward samples are on disk" not in captured.out, (
        "the file is on disk; it could not be read, which is a different fault"
    )
    errors = [line for line in captured.err.splitlines() if line.startswith("::error::")]
    assert errors and "prop_calibration_samples.csv" in errors[0]
    assert "could not be read" in errors[0]
    assert _snapshot(outputs) == before


def test_an_unreadable_price_store_refuses_rather_than_reading_as_no_prices(
    tmp_path: Path, empty_cache: None, capsys: pytest.CaptureFixture[str],
) -> None:
    processed, outputs = _dirs(tmp_path)
    _samples().to_csv(outputs / "prop_calibration_samples.csv", index=False)
    good = _prices().to_csv(index=False)
    (processed / "historical_prop_prices.csv").write_text(
        good + "2025-10-18,a,b,c,d,e,f,g,h,i,j,k,l,m,n,o\n", encoding="utf-8"
    )
    before = _snapshot(outputs)

    code = _run(processed, outputs, "--phase", "late")
    captured = capsys.readouterr()

    assert code != 0
    assert "No historical prop prices are on disk" not in captured.out, (
        "a damaged store is not an empty one; the report built on it told "
        "every summary that no prices had been bought"
    )
    errors = [line for line in captured.err.splitlines() if line.startswith("::error::")]
    assert errors and "historical_prop_prices.csv" in errors[0]
    assert _snapshot(outputs) == before


def test_prices_and_samples_together_still_measure(
    tmp_path: Path, empty_cache: None, capsys: pytest.CaptureFixture[str],
) -> None:
    """The refusal is for a missing model, not a reason to stop measuring."""
    processed, outputs = _dirs(tmp_path)
    _prices().to_csv(processed / "historical_prop_prices.csv", index=False)
    _samples().to_csv(outputs / "prop_calibration_samples.csv", index=False)

    code = _run(processed, outputs, "--phase", "late", "--edge-threshold", "-1")

    assert code == 0, capsys.readouterr().err
    markdown = (outputs / "player_props_backtest.md").read_text(encoding="utf-8")
    assert "(`late` window)" in markdown
    assert "Bets placed: 2" in markdown


# --------------------------------------------------------------------------
# In the measurement itself: no samples still names the window it measured.
# --------------------------------------------------------------------------


def test_no_samples_still_records_the_named_window(empty_cache: None) -> None:
    report = bt.run_backtest(
        _prices(), _samples().iloc[0:0], edge_threshold=0.0, phase="late",
        team_names=TEAM_MAP,
    )
    rendered = bt.render_backtest(report)

    assert report.phase == "late"
    assert report.phase_hours == pytest.approx(4.0)
    assert "No snapshot window was filtered" not in rendered, (
        "`--phase late` was named; saying no window was filtered is false"
    )
    # The late window's two wagers were seen, and neither had an opinion.
    assert report.priced_outcomes == 2
    assert report.outcomes_without_a_model_opinion == 2
    assert not report.bets
    assert any("No walk-forward samples were supplied" in n for n in report.notes)
    assert "Not one historically-priced outcome had a model opinion" in rendered, (
        "the report blamed the edge threshold for what the missing model did"
    )


def test_no_samples_does_not_skip_the_team_map_refusal(empty_cache: None) -> None:
    """#117 refuses a map that resolves no priced game. The early return sat
    above it, so the one run most likely to lack a map as well as samples — a
    probe whose state restore failed — skipped the refusal and wrote a report."""
    with pytest.raises(UnresolvedTeamsError):
        bt.run_backtest(
            _prices(), _samples().iloc[0:0], edge_threshold=0.0, phase="late"
        )
