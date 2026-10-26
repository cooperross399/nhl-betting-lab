"""The game page, the track record and the methods page (2026-10-26).

Cooper asked for the site to be "perfect like PostHockey": a page per game
showing what moved its line, a track record, and a methods page. These hold:

* the breakdown reprices one model layer by layer, ends exactly at the
  card's own moneyline, and its steps add up to that number;
* the builder carries the card's breakdown onto the game it priced, and
  nowhere else;
* the track record buckets the published win chances against the finals,
  scores the market beside the model, and reads the board's own line series
  for which way the market moved after a moneyline pick; it publishes no
  return;
* each new page's script parses.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from nhl_betting_lab.factor_breakdown import STEPS, breakdown
from nhl_betting_lab.models.team_model import TeamModel, TeamRates
from nhl_betting_lab.reports.gameday_card import CARD_JSON_FILENAME

import test_the_site_board_carries_the_drought_list as drought_page
from test_site_never_calls_an_unpriced_game_a_pass import CLUBS, make_lab, site_module

ROOT = Path(__file__).resolve().parents[1]


def _model() -> tuple[TeamModel, dict, dict, dict]:
    model = TeamModel()
    model.home_advantage = 1.05
    rated = {"TOR": TeamRates("TOR", 82, 1.10, 0.95), "MTL": TeamRates("MTL", 82, 0.95, 1.05)}
    lineup = {"TOR": TeamRates("TOR", 82, 1.05, 0.95), "MTL": TeamRates("MTL", 82, 0.95, 1.02)}
    goalies = {"TOR": TeamRates("TOR", 82, 1.05, 1.00), "MTL": TeamRates("MTL", 82, 0.95, 0.98)}
    model.teams = dict(goalies)
    model.home_ice = {"TOR": 0.03, "MTL": -0.01}
    model.game_factors = {frozenset({"TOR", "MTL"}): 1.04}
    model.pregame_targets = {("TOR", "MTL"): 0.60}
    model.pregame_weight = 0.5
    return model, rated, lineup, goalies


def test_the_steps_add_up_to_the_cards_own_number() -> None:
    model, rated, lineup, goalies = _model()
    form = {"TOR": {"attack": 1.05, "defence": 0.98}}
    steps = breakdown(model, "TOR", "MTL", rated=rated, lineup=lineup, goalies=goalies, form=form)
    assert [s["key"] for s in steps] == [k for k, _ in STEPS]
    final = model.moneyline_probabilities("TOR", "MTL")["home"]
    assert steps[-1]["homeWin"] == pytest.approx(final, abs=1e-4)
    assert 0.5 + sum(s["delta"] for s in steps) == pytest.approx(steps[-1]["homeWin"], abs=1e-3)
    # Form divided back out: the first step rates TOR's attack at 1.10 / 1.05.
    plain = TeamModel()
    plain.home_advantage = 1.05
    plain.teams = {"TOR": TeamRates("TOR", 82, 1.10 / 1.05, 0.95 / 0.98), "MTL": rated["MTL"]}
    assert steps[0]["homeWin"] == pytest.approx(plain.moneyline_probabilities("TOR", "MTL")["home"], abs=1e-4)
    # The model handed in is not changed.
    assert model.teams == goalies and model.pregame_weight == 0.5


def test_the_board_carries_the_cards_breakdown_onto_its_game(tmp_path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    card_path = lab / "data" / "outputs" / CARD_JSON_FILENAME
    card = json.loads(card_path.read_text(encoding="utf-8"))
    steps = [{"key": k, "label": label, "homeWin": 0.5 + 0.01 * i, "delta": 0.01 if i else 0.0,
              "homeGoals": 3.0, "awayGoals": 2.8} for i, (k, label) in enumerate(STEPS)]
    card["team_factors"] = [{"home_team": CLUBS["TOR"][2], "away_team": CLUBS["MTL"][2], "home": "TOR",
                             "away": "MTL", "date": "2026-10-08", "steps": steps}]
    card_path.write_text(json.dumps(card), encoding="utf-8")
    board = drought_page.build(lab, tmp_path / "out", monkeypatch)
    by_home = {g["home"]["abbr"]: g for g in board["games"]}
    assert [s["key"] for s in by_home["TOR"]["factors"]] == [k for k, _ in STEPS]
    assert by_home["TOR"]["factors"][-1]["homeWin"] == pytest.approx(0.57)
    assert "factors" not in by_home["NYI"]
    assert all("_provider" not in g for g in board["games"])
    assert (tmp_path / "out" / "record.json").is_file()
    assert (tmp_path / "out" / "ratings.json").is_file()


def _frozen(history: Path, day: str, games: list[dict]) -> None:
    history.mkdir(parents=True, exist_ok=True)
    (history / f"{day}.json").write_text(json.dumps({"phase": "regular", "games": games}), encoding="utf-8")


def test_the_record_is_calibration_and_movement_and_no_return(tmp_path) -> None:
    module = site_module()
    history = tmp_path / "history"
    games = [
        {"id": "1", "home": {"abbr": "TOR", "winProb": 0.62}, "away": {"abbr": "MTL", "winProb": 0.38},
         "moneyline": {"current": {"home": -150, "away": 130}},
         "pick": {"kind": "bet", "market": "Moneyline", "side": "home", "label": "TOR"}},
        {"id": "2", "home": {"abbr": "NYI", "winProb": 0.45}, "away": {"abbr": "BOS", "winProb": 0.55},
         "moneyline": {"current": {"home": 110, "away": -130}},
         "pick": {"kind": "bet", "market": "Moneyline", "side": "away", "label": "BOS"}},
        {"id": "3", "home": {"abbr": "EDM"}, "away": {"abbr": "CGY"}},  # not projected
    ]
    _frozen(history, "2026-10-20", games)
    (history / "finals").mkdir()
    (history / "finals" / "2026-10-20.json").write_text(json.dumps({"1": [4, 2], "2": [3, 1], "3": [1, 0]}))
    (history / "lines").mkdir()
    (history / "lines" / "2026-10-20.json").write_text(json.dumps({
        "1": {"ml_home": [{"t": "a", "v": -150}, {"t": "b", "v": -170}]},  # moved toward TOR
        "2": {"ml_home": [{"t": "a", "v": 110}, {"t": "b", "v": 105}]},    # moved toward NYI, against BOS
    }))
    record = module.track_record(date(2026, 10, 21), history)
    assert record["games"] == 2 and record["nights"] == 1
    sixty = next(b for b in record["buckets"] if b["low"] == 0.60)
    fifty_five = next(b for b in record["buckets"] if b["low"] == 0.55)
    assert sixty["games"] == 1 and sixty["actual"] == 1.0
    assert fifty_five["games"] == 1 and fifty_five["actual"] == 0.0
    assert record["brier"]["games"] == 2
    assert record["movement"] == {"toward": 1, "against": 1, "flat": 0, "picks": 2}
    text = json.dumps(record)
    for key in ("roi", "profit", "units", "clv"):
        assert f'"{key}' not in text
    # A night on or after the build day is not in the record.
    assert module.track_record(date(2026, 10, 20), history)["games"] == 0


def test_the_slate_gets_one_breakdown_per_priced_game() -> None:
    import pandas as pd

    from nhl_betting_lab.factor_breakdown import slate_breakdowns

    model, rated, lineup, goalies = _model()
    prices = pd.DataFrame([
        {"market": "moneyline", "home_team": "TOR", "away_team": "MTL", "selection": s, "date": "2026-10-26",
         "commence_time": "2026-10-26T23:00:00Z", "book": b}
        for s in ("home", "away") for b in ("dk", "fd")
    ] + [{"market": "total_goals", "home_team": "BOS", "away_team": "NYI", "selection": "over",
          "date": "2026-10-26", "commence_time": "2026-10-26T23:00:00Z", "book": "dk"}])
    rows = slate_breakdowns(prices, model, team_names={}, rated=rated, lineup=lineup, goalies=goalies)
    assert [(r["home"], r["away"]) for r in rows] == [("TOR", "MTL")]
    assert rows[0]["steps"][-1]["homeWin"] == pytest.approx(model.moneyline_probabilities("TOR", "MTL")["home"], abs=1e-4)
