"""A window that measured no bets was reported as one where nothing survived.

`scripts/run_replication.py` refused a window only when `load_backtest`
returned an empty dict, that is when the file was missing or unreadable. A
backtest payload that measured nothing is a well-formed dict with 17 keys, so
it passed. `reports.replication.compare` then never looked at how many bets
either window held. The report said "Nothing survived correction on
**<discovery>**, so there is no result to replicate. That is not a failure of
the test window." Every market read "untestable: Nothing survived correction
on the first window". The run exited 0 and wrote `replication.md` and
`replication.json`, and `allowlist_evidence` reads the latter. Found by the
failure-shape audit (finding 46; 2 of 3 refuters).

The input is easy to produce. `run_player_props_backtest.py` exits 0 and
writes a labelled window with `bets: 0, by_market: {}` whenever its window
matches nothing. Reproduced on the real bought store (read-only, outputs to
scratch): `--phase late --from 2025-10-07 --to 2025-04-30 --label 2025-26`,
with the end year mistyped, printed "0 of 3,804,233 price rows" and exited 0.
Passed as `--discovery` against the home checkout's 2024-25 window, that file
made the replication run exit 0 with all six markets "untestable — Nothing
survived correction on the first window". Against the same test window, the
home checkout's measured 2025-26 file (2026-08-28, per-quote era) returns
three markets that are not untestable: `points` replicated, `goalie_saves` not
confirmed, `shots_on_goal` contradicted. A comparison that never happened was
recorded as a null. A test window that measured nothing is the mirror case:
with a survivor on the first window, the headline said it "did **not**
replicate" on a window that tested nothing.

What these tests hold:

* through the real backtest runner and the real replication script, a window
  that measured no bets is refused in either role. The script exits 1, names
  the window, says it measured no bets and writes nothing, so the previous
  record stays byte-identical;
* every shape of "measured nothing" that `compare` would read as zero is
  refused: an empty `by_market`, a `by_market` with no market above 0 bets, a
  `by_market` of null, and a payload with no `by_market` at all, even one
  whose top-level `bets` claims a count;
* two measured windows are still compared, however thin. Two bets that
  survive nothing are still "Nothing survived correction";
* in `compare` itself, a market the first window never measured is "not
  measured on the first window (0 bets)", not a failed correction, and the
  headline for a window with no bets says so instead of "Nothing survived
  correction" or "did **not** replicate". The state stays `untestable`, so no
  verdict that `allowlist_evidence` reads changes.
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
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.reports import replication as rep


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

#: The 2025-26 window as meant, and as typed with the end year one short.
#: The second matches no price row, which is how the real store produced a
#: zero-bet labelled window.
MEANT = ("--from", "2025-10-07", "--to", "2026-04-16")
MISTYPED = ("--from", "2025-10-07", "--to", "2025-04-30")


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


def _prices() -> pd.DataFrame:
    """Three late quotes on two wagers."""
    return pd.DataFrame(
        [
            _quote("Auston Matthews", -110, "DraftKings"),
            _quote("Auston Matthews", 100, "FanDuel"),
            _quote("Brady Tkachuk", 105, "DraftKings"),
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


def _backtest(tmp_path: Path, label: str, window: tuple[str, ...]) -> Path:
    """Run the real backtest runner on one window; return its labelled JSON."""
    processed = tmp_path / "processed"
    outputs = tmp_path / "backtest"
    if not processed.is_dir():
        processed.mkdir()
        outputs.mkdir()
        tn.save_team_name_map(TEAM_MAP, processed_dir=processed)
        _prices().to_csv(processed / "historical_prop_prices.csv", index=False)
        _samples().to_csv(outputs / "prop_calibration_samples.csv", index=False)
    code = load_script("run_player_props_backtest.py").main(
        [
            "--phase", "late", *window, "--label", label,
            "--processed-dir", str(processed), "--output-dir", str(outputs),
        ]
    )
    assert code == 0, "the backtest runner exits 0 on a window it measured or not"
    return outputs / f"player_props_backtest_{label}.json"


#: A replication record from an earlier, real run. A refusal must leave it.
PREVIOUS = {
    "replication.md": "# Replication\n\n- Discovery window: **2024-25**\n",
    "replication.json": '{"markets": [{"market": "points", "state": "untestable"}]}\n',
}


def _record_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "replication"
    directory.mkdir()
    for name, text in PREVIOUS.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def _replicate(discovery: Path, test: Path, output_dir: Path) -> int:
    return load_script("run_replication.py").main(
        [
            "--discovery", str(discovery),
            "--test", str(test),
            "--output-dir", str(output_dir),
        ]
    )


# --------------------------------------------------------------------------
# Through both real scripts, as an operator runs them.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["discovery", "test"])
def test_a_window_the_backtest_measured_nothing_is_refused_not_compared(
    tmp_path: Path, empty_cache: None, capsys: pytest.CaptureFixture[str],
    role: str,
) -> None:
    measured = _backtest(tmp_path, "2025-26", MEANT)
    unmeasured = _backtest(tmp_path, "2025-26-mistyped", MISTYPED)
    produced = json.loads(unmeasured.read_text(encoding="utf-8"))
    assert produced["bets"] == 0 and produced["by_market"] == {}, (
        "the premise: the runner writes a window that measured nothing"
    )
    assert json.loads(measured.read_text(encoding="utf-8"))["bets"] == 2
    records = _record_dir(tmp_path)
    before = _snapshot(records)
    capsys.readouterr()

    if role == "discovery":
        code = _replicate(unmeasured, measured, records)
    else:
        code = _replicate(measured, unmeasured, records)
    out = capsys.readouterr().out

    assert code == 1, (
        f"a {role} window of 0 bets was compared and the run exited {code}"
    )
    assert "measured no bets" in out
    assert str(unmeasured) in out, "name the window that measured nothing"
    assert str(measured) not in out, "the measured window is not the problem"
    assert "Nothing survived correction" not in out
    assert "did **not** replicate" not in out
    assert _snapshot(records) == before, (
        "the previous replication record was replaced by a comparison with "
        "a window that measured nothing"
    )


def test_two_measured_windows_are_still_compared_however_thin(
    tmp_path: Path, empty_cache: None, capsys: pytest.CaptureFixture[str],
) -> None:
    """The refusal is for a window with no bets, not for a window with few.
    Two bets that survive nothing are, truthfully, nothing surviving."""
    first = _backtest(tmp_path, "2025-26", MEANT)
    second = _backtest(tmp_path, "2025-26-again", MEANT)
    records = _record_dir(tmp_path)
    capsys.readouterr()

    code = _replicate(first, second, records)
    out = capsys.readouterr().out

    assert code == 0, out
    saved = json.loads((records / "replication.json").read_text(encoding="utf-8"))
    assert [item["market"] for item in saved["markets"]] == ["shots_on_goal"]
    assert saved["markets"][0]["discovery_bets"] == 2
    assert saved["headline"].startswith(
        "Nothing survived correction on **player_props_backtest_2025-26**"
    )


#: Every payload `compare` would read as zero bets on every market.
UNMEASURED = {
    "empty-by-market": {"bets": 0, "by_market": {}, "overall": None},
    "no-market-above-zero": {
        "bets": 0,
        "by_market": {
            "points": {"bets": 0, "roi": None, "survives_correction": False},
            "goals": {"bets": 0, "roi": None, "survives_correction": False},
        },
    },
    "by-market-null": {"bets": 0, "by_market": None},
    "no-by-market-though-bets-claimed": {"bets": 37469, "generated_at": "x"},
}

MEASURED = {
    "bets": 2,
    "by_market": {
        "shots_on_goal": {"bets": 2, "roi": 0.0, "survives_correction": False},
    },
}


@pytest.mark.parametrize("role", ["discovery", "test"])
@pytest.mark.parametrize("shape", sorted(UNMEASURED))
def test_every_shape_of_an_unmeasured_window_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], shape: str, role: str,
) -> None:
    unmeasured = tmp_path / f"{shape}.json"
    unmeasured.write_text(json.dumps(UNMEASURED[shape]), encoding="utf-8")
    measured = tmp_path / "measured.json"
    measured.write_text(json.dumps(MEASURED), encoding="utf-8")
    records = _record_dir(tmp_path)
    before = _snapshot(records)

    if role == "discovery":
        code = _replicate(unmeasured, measured, records)
    else:
        code = _replicate(measured, unmeasured, records)
    out = capsys.readouterr().out

    assert code == 1, f"{shape} as {role} was compared"
    assert "measured no bets" in out and str(unmeasured) in out
    assert str(measured) not in out
    assert _snapshot(records) == before


def test_one_bet_on_one_market_is_a_measured_window(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """The count is summed over markets: one market measured is enough."""
    sparse = tmp_path / "sparse.json"
    sparse.write_text(
        json.dumps(
            {
                "bets": 1,
                "by_market": {
                    "goals": {"bets": 0, "roi": None, "survives_correction": False},
                    "points": {"bets": 1, "roi": -1.0, "survives_correction": False},
                },
            }
        ),
        encoding="utf-8",
    )
    measured = tmp_path / "measured.json"
    measured.write_text(json.dumps(MEASURED), encoding="utf-8")
    records = _record_dir(tmp_path)

    code = _replicate(sparse, measured, records)

    assert code == 0, capsys.readouterr().out
    saved = json.loads((records / "replication.json").read_text(encoding="utf-8"))
    assert [item["market"] for item in saved["markets"]] == [
        "goals", "points", "shots_on_goal",
    ]


# --------------------------------------------------------------------------
# In compare itself: a market or a window with no bets says so.
# --------------------------------------------------------------------------


def _result(bets: int, roi: float | None, survives: bool) -> dict:
    return {"bets": bets, "roi": roi, "survives_correction": survives}


def _compare(discovery: dict, test: dict) -> rep.ReplicationReport:
    return rep.compare(
        discovery, test, discovery_label="2025-26", test_label="2024-25"
    )


def test_a_market_the_first_window_never_measured_is_not_a_failed_correction() -> None:
    report = _compare(
        {"by_market": {"shots_on_goal": _result(263, 0.181, True)}},
        {
            "by_market": {
                "shots_on_goal": _result(240, 0.121, True),
                "points": _result(200, -0.05, False),
            }
        },
    )
    points = next(item for item in report.markets if item.market == "points")
    shots = next(item for item in report.markets if item.market == "shots_on_goal")

    assert points.state == rep.UNTESTABLE, "the verdict does not move"
    assert "Nothing survived correction" not in points.reason, (
        "the first window never measured `points`; nothing was corrected"
    )
    assert "Not measured on the first window (0 bets)" in points.reason
    assert shots.state == rep.REPLICATED, "a measured market is unaffected"
    assert "`shots_on_goal` held on **2024-25**" in report.headline(), (
        "one market unmeasured is not a window unmeasured"
    )


def test_a_market_measured_on_the_first_window_that_failed_still_says_so() -> None:
    """Forty bets is thin, and it is not zero: they were measured and
    corrected, and nothing survived."""
    report = _compare(
        {"by_market": {"points": _result(40, -0.164, False)}},
        {"by_market": {"points": _result(200, -0.05, False)}},
    )

    assert report.markets[0].reason.startswith("Nothing survived correction")
    assert report.headline().startswith("Nothing survived correction on **2025-26**")


def test_a_discovery_window_with_no_bets_is_headlined_as_unmeasured() -> None:
    report = _compare(
        {"bets": 0, "by_market": {}},
        {"by_market": {"points": _result(7374, -0.035, True)}},
    )
    headline = report.headline()
    rendered = rep.render_replication(report)

    assert "**2025-26** measured no bets" in headline
    assert "Nothing survived correction" not in headline
    assert "Nothing survived correction" not in rendered
    assert report.markets[0].state == rep.UNTESTABLE


def test_a_test_window_with_no_bets_is_not_headlined_as_a_failure_to_replicate() -> None:
    report = _compare(
        {"by_market": {"points": _result(9047, -0.044, True)}},
        {"bets": 0, "by_market": {}},
    )
    headline = report.headline()

    assert "did **not** replicate" not in headline, (
        "a window with no bets tested nothing, so nothing failed on it"
    )
    assert "**2024-25** measured no bets" in headline
    assert "`points`" in headline, "name what is waiting to be tested"
    assert report.markets[0].state == rep.UNTESTABLE


def test_a_test_window_that_missed_one_market_is_not_called_empty() -> None:
    """The test window measured `points` and not `shots_on_goal`. That is a
    market unmeasured, which the per-market reason states, not a window."""
    report = _compare(
        {"by_market": {"shots_on_goal": _result(263, 0.181, True)}},
        {"by_market": {"points": _result(200, -0.05, False)}},
    )

    assert "measured no bets" not in report.headline()
    shots = next(item for item in report.markets if item.market == "shots_on_goal")
    assert "Only 0 bet(s) in the test window" in shots.reason


def test_a_thin_test_window_is_still_headlined_as_it_was() -> None:
    """Only a test window with no bets at all changes the headline. A thin one
    keeps its per-market "below the 100 needed" reason and its headline."""
    report = _compare(
        {"by_market": {"points": _result(9047, -0.044, True)}},
        {"by_market": {"points": _result(40, -0.02, False)}},
    )

    assert "did **not** replicate" in report.headline()
    assert "below the" in report.markets[0].reason
