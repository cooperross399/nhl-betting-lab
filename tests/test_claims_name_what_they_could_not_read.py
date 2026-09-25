"""The claims document called every unread market "never bought".

Found by the failure-shape audit (silent empty reports). `build_claims_report`
reads measurement JSONs from one directory and never looks at the price store,
yet every market it found no bets for was given the fallback reason "no
historical prices have been bought for it yet" — a statement about purchases
that nothing in the code had checked. Reproduced three ways:

* A Historical Props Purchase run in mode `buy` or `probe` never rebuilds the
  team measurement, and `team_markets_measurement.json` is gitignored and in
  no restored artifact. Its claims step (`if: always()`) still runs, so with
  308,944 bought team price rows on disk the uploaded document said
  moneyline, puck line and totals had never been bought, and the measured
  count fell from 10 markets to 6.
* A team measurement entry that saw prices and placed no bet — seen 48,000,
  unmatched 48,000, bets 0 — printed the same sentence.
* In a fresh checkout or worktree, where every measurement JSON is gitignored,
  the regenerated tracked contract file headlined "Nothing in this repository
  has a demonstrated edge, because nothing has been measured against real
  prices yet", and listed all eleven price-measured markets as never bought.

The rule now: a missing or unreadable measurement output is named as missing,
a measurement that scored prices and placed no bet says where they went, and a
market is described as having no stored price only when the measurement that
read the store says so. Tests drive the real report and the real runner.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as team_names_module
from nhl_betting_lab.reports import team_markets_measurement as tmm
from nhl_betting_lab.reports import what_we_can_claim as claims

NEVER_BOUGHT = "no historical prices have been bought"
TEAM_MARKETS = ("moneyline", "puck_line", "total_goals")


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(directory: Path, name: str, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def _props(directory: Path) -> None:
    """The contract props report, as a purchase run leaves it: six markets."""
    entry = {
        "bets": 9379, "roi": 0.013, "low": -0.008, "high": 0.034,
        "includes_zero": True, "survives_correction": False, "looks": 7,
    }
    _write(
        directory,
        "player_props_backtest.json",
        {
            "phase": "late",
            "phase_hours": 4.07,
            "overall": {"bets": 25911, "roi": -0.003, "includes_zero": True},
            "by_market": {
                market: dict(entry)
                for market in (
                    "shots_on_goal", "points", "goals", "assists",
                    "goalie_saves", "blocked_shots",
                )
            },
        },
    )


def _sentence(report: claims.ClaimsReport, market: str) -> str:
    return next(c for c in report.claims if c.market == market).sentence()


@pytest.fixture
def defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """No test here may read the real `data/processed` or boxscore cache."""
    processed = tmp_path / "default_processed"
    raw = tmp_path / "default_raw"
    processed.mkdir()
    raw.mkdir()
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", processed)
    monkeypatch.setattr(team_names_module, "RAW_DIR", raw)
    return SimpleNamespace(processed=processed, raw=raw)


# --------------------------------------------------------------------------
# A missing measurement output is missing, not unbought.
# --------------------------------------------------------------------------

def test_a_missing_team_measurement_is_named_not_called_unbought(
    tmp_path: Path,
) -> None:
    """The purchase run's shape: props measured, the team JSON never built."""
    _props(tmp_path)

    report = claims.build_claims_report(output_dir=tmp_path)
    rendered = claims.render_claims(report)

    for market in TEAM_MARKETS:
        sentence = _sentence(report, market)
        assert NEVER_BOUGHT not in sentence, sentence
        assert "`team_markets_measurement.json` was not found" in sentence
    # The document says it is incomplete where a reader starts, not only in
    # the per-market lines at the bottom.
    assert "This document is incomplete" in rendered
    assert rendered.index("This document is incomplete") < rendered.index(
        "## Measured against real prices"
    )


def test_an_empty_directory_does_not_say_nothing_was_ever_measured(
    tmp_path: Path,
) -> None:
    """The fresh-worktree headline, and eleven markets called never bought."""
    report = claims.build_claims_report(output_dir=tmp_path)

    assert "nothing has been measured against real prices yet" not in (
        report.headline()
    )
    assert "`player_props_backtest.json`" in report.headline()
    assert "`team_markets_measurement.json`" in report.headline()
    assert report.anything_demonstrated is False
    for claim in report.claims:
        assert NEVER_BOUGHT not in claim.sentence(), claim.sentence()


def test_an_unreadable_measurement_output_is_named_as_unreadable(
    tmp_path: Path,
) -> None:
    """A truncated file is not an empty measurement either."""
    _props(tmp_path)
    (tmp_path / "team_markets_measurement.json").write_text(
        "{broken", encoding="utf-8"
    )

    sentence = _sentence(claims.build_claims_report(output_dir=tmp_path), "moneyline")

    assert NEVER_BOUGHT not in sentence
    assert "`team_markets_measurement.json`" in sentence
    assert "could not be read" in sentence


# --------------------------------------------------------------------------
# A measurement that saw prices says where they went.
# --------------------------------------------------------------------------

def test_prices_scored_without_a_bet_are_counted_not_called_unbought(
    tmp_path: Path,
) -> None:
    """The audit's case: seen 48,000, unmatched 48,000, bets 0."""
    _props(tmp_path)
    _write(
        tmp_path,
        "team_markets_measurement.json",
        {
            "phase": "late",
            "phase_hours": 1.5,
            "markets": [
                {
                    "market": "moneyline",
                    "bets": 0,
                    "has_price_evidence": False,
                    "accounting": {"seen": 48000, "unmatched": 48000},
                }
            ],
        },
    )

    sentence = _sentence(claims.build_claims_report(output_dir=tmp_path), "moneyline")

    assert NEVER_BOUGHT not in sentence
    assert "48,000" in sentence
    assert "48,000 were unmatched" in sentence
    assert "`late` window" in sentence


def test_a_prop_market_the_backtest_placed_no_bet_on_is_not_called_unbought(
    tmp_path: Path,
) -> None:
    """A zero-bet prop market in a present backtest is exactly that."""
    _props(tmp_path)

    sentence = _sentence(claims.build_claims_report(output_dir=tmp_path), "hits")

    assert NEVER_BOUGHT not in sentence
    assert "placed no bet on it" in sentence
    assert "`late` window" in sentence


# --------------------------------------------------------------------------
# "No stored price" survives where the measurement that read the store says so.
# --------------------------------------------------------------------------

def test_the_store_the_measurement_read_is_what_says_none_is_held(
    tmp_path: Path, defaults: SimpleNamespace
) -> None:
    """Producer to consumer, through the JSON, so the words cannot drift.

    The team measurement is built on a store holding moneyline only and saved;
    the claims document then reads it. `team_total` has no stored price and
    says so — which keeps this test from passing by never saying it — while
    moneyline is measured.
    """
    face_off = "2025-01-10T00:00:00Z"
    snapshot = (pd.Timestamp(face_off) - pd.Timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    store = pd.DataFrame(
        [
            {
                "date": "2025-01-09", "commence_time": face_off,
                "snapshot": snapshot, "home_team": "Toronto Maple Leafs",
                "away_team": "Boston Bruins", "market": "moneyline",
                "selection": "home", "line": None, "american_odds": 150,
                "book": "DraftKings",
            }
        ]
    )
    samples = pd.DataFrame(
        [
            {
                "game_id": 1, "date": "2025-01-09", "home_team": "TOR",
                "away_team": "BOS", "market": "moneyline", "selection": "home",
                "line": None, "model_probability": 0.6, "outcome": True,
                "push": False,
            }
        ]
    )
    report = tmm.build_team_measurement(
        samples,
        store,
        team_names={"toronto maple leafs": "TOR", "boston bruins": "BOS"},
        phase="late",
    )
    tmm.save_team_measurement(report, output_dir=tmp_path)
    _props(tmp_path)

    built = claims.build_claims_report(output_dir=tmp_path)
    moneyline = next(c for c in built.claims if c.market == "moneyline")
    team_total = _sentence(built, "team_total")

    assert moneyline.measured is True
    assert "holds no price for it" in team_total
    assert "`team_markets_measurement.json` was not found" not in team_total
    assert "This document is incomplete" not in claims.render_claims(built)


# --------------------------------------------------------------------------
# Through the runner the workflow calls.
# --------------------------------------------------------------------------

def test_the_runner_writes_what_it_could_not_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`run_what_we_can_claim.py` as the purchase workflow runs it."""
    _props(tmp_path)
    module = load_script("run_what_we_can_claim.py")

    code = module.main(["--output-dir", str(tmp_path)])
    out = capsys.readouterr().out
    rendered = (tmp_path / claims.CLAIMS_MARKDOWN_FILENAME).read_text(
        encoding="utf-8"
    )

    assert code == 0
    assert "team_markets_measurement.json" in out
    for market in TEAM_MARKETS:
        line = next(
            row for row in rendered.splitlines() if row.startswith(f"- `{market}`")
        )
        assert NEVER_BOUGHT not in line, line
