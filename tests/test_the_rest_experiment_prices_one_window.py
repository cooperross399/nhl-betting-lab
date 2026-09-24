"""The rest experiment read every price window, and prices from after face-off.

It is the defect the team measurement had until 2026-09-24, one caller over:
`scripts/run_rest_experiment.py` passed the whole team store to
`measure_prices`, and only `build_team_measurement` restricted it. Traced on
the real store: of the 5,423 bets it measured with rest ignored, 1,070 were
priced at or after face-off and 1,223 took an `early` quote over the `late`
one. Its committed verdict read "+19.4u, improving 2 of 3" and dated from
before one-bet-per-wager counting.

In the `late` window, strictly before face-off, rest-known finishes +5.8u
ahead and improves 1 of 3. The must-not-lose bar still clears, so `team_b2b`
still ships and nothing the card does changes. The record now says why.
"""

from __future__ import annotations

import importlib.util
import json

import pandas as pd
import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.reports import team_markets_measurement as TM

FACE_OFF = "2025-01-10T00:00:00Z"


def _quote(hours_before: float, *, odds: int, book: str = "draftkings") -> dict:
    snapshot = pd.Timestamp(FACE_OFF) - pd.Timedelta(hours=hours_before)
    return {
        "date": "2025-01-09",
        "commence_time": FACE_OFF,
        "snapshot": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "market": "moneyline",
        "player": "",
        "selection": "home",
        "line": None,
        "american_odds": odds,
        "book": book,
    }


def _script():
    path = PROJECT_ROOT / "scripts" / "run_rest_experiment.py"
    spec = importlib.util.spec_from_file_location("_script_run_rest_experiment", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(tmp_path, monkeypatch, store: pd.DataFrame, *argv: str):
    """Run the script with the model stubbed, recording what it measured."""
    module = _script()
    processed = tmp_path / "processed"
    processed.mkdir()
    store.to_csv(processed / "historical_team_prices.csv", index=False)
    seen: list[pd.DataFrame] = []

    def fake_samples(games, use_rest):
        class Walk:
            def summary_line(self):
                return "stub"
        return pd.DataFrame([{"market": "moneyline"}]), Walk()

    def fake_measure(prices, samples, **_):
        seen.append(prices.copy())
        return None

    monkeypatch.setattr(module, "load_team_games", lambda _: pd.DataFrame([{"game": 1}]))
    monkeypatch.setattr(module, "generate_team_samples", fake_samples)
    monkeypatch.setattr(module, "measure_prices", fake_measure)
    code = module.main([
        "--processed-dir", str(processed), "--output-dir", str(tmp_path / "out"), *argv,
    ])
    return code, seen, tmp_path / "out"


def test_only_the_late_window_before_face_off_reaches_the_measurement(tmp_path, monkeypatch):
    """One wager, three quotes: the one a card could have taken, an early quote
    paying more, and an in-play quote paying most."""
    store = pd.DataFrame([
        _quote(2.0, odds=-120),
        _quote(20.0, odds=+130, book="fanduel"),
        _quote(-1.0, odds=+400, book="betmgm"),
    ])

    code, seen, out = _run(tmp_path, monkeypatch, store)

    assert code == 0
    assert seen, "the measurement was never reached"
    for prices in seen:
        assert list(prices["american_odds"]) == [-120]
    record = json.loads((out / "rest_experiment.json").read_text())
    assert record["phase"] == "late"
    assert record["excluded_after_face_off"] == 1
    assert record["excluded_other_windows"] == 1
    assert "`late` window" in (out / "rest_experiment.md").read_text()


def test_the_mixture_is_refused_when_no_window_is_named(tmp_path, monkeypatch):
    store = pd.DataFrame([_quote(2.0, odds=-120), _quote(20.0, odds=+130)])
    code, seen, _ = _run(tmp_path, monkeypatch, store, "--phase", "auto")
    assert code == 2
    assert seen == []


@pytest.mark.parametrize("hours_before", [0.0, -0.5])
def test_the_measurement_refuses_a_price_from_after_face_off(hours_before):
    """Whatever the caller did. Two callers once did nothing. Exactly at the
    start counts: the closing rule is 'strictly before face-off'."""
    prices = pd.DataFrame([_quote(2.0, odds=-120), _quote(hours_before, odds=+300)])
    samples = pd.DataFrame([{"market": "moneyline"}])
    with pytest.raises(ValueError, match="at or after face-off"):
        TM.measure_prices(prices, samples, market="moneyline", team_names={})


def test_the_committed_verdict_is_the_one_window_verdict():
    """The record the card obeys, and what it was measured on."""
    record = json.loads(
        (PROJECT_ROOT / "data" / "outputs" / "rest_experiment.json").read_text()
    )
    assert record["phase"] == "late"
    assert record["ships"] == ["team_b2b"]
    assert record["delta_units"] == pytest.approx(5.81, abs=0.01)
