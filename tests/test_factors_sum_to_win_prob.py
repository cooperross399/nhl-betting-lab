"""A game's factor steps add up to the win chance they end on.

The game page (Game.dc.html) draws the home win chance built up from a coin
flip in eight steps and prints a rounding note when `0.5 + sum(delta)` misses
the number it ends on by 0.0015 or more. These hold that the builder hands it
eight steps in the page's order, each delta the change from the step before,
summing to the last step's win chance: on the card's own breakdown carried
through `card_factors`, and on the design drop's sample board.

The last step is the CARD's moneyline (`factor_breakdown`, gameday_card.json's
`team_factors`). The board's `home.winProb` is the site's own model, which
reads neither tonight's lineup, starters, referees nor PostHockey, so the two
can differ; the page shows both, and this holds the steps to the number they
were built to reach.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhl_betting_lab.factor_breakdown import breakdown

from test_site_never_calls_an_unpriced_game_a_pass import site_module
from test_the_game_page_shows_where_the_number_comes_from import _model

ROOT = Path(__file__).resolve().parents[1]
ORDER = ["strength", "home_ice", "form", "rest", "lineup", "goalies", "referees", "posthockey"]


def _check(steps: list[dict], ends_on: float) -> None:
    assert len(steps) == 8
    assert [s["key"] for s in steps] == ORDER
    assert abs(0.5 + sum(s["delta"] for s in steps) - ends_on) < 0.0015
    previous = 0.5
    for s in steps:
        assert s["homeWin"] == pytest.approx(previous + s["delta"], abs=1e-3)
        previous = s["homeWin"]


def test_the_cards_breakdown_reaches_the_board_summing_to_its_last_step() -> None:
    model, rated, lineup, goalies = _model()
    steps = breakdown(model, "TOR", "MTL", rated=rated, lineup=lineup, goalies=goalies,
                      form={"TOR": {"attack": 1.05, "defence": 0.98}})
    card = {"team_factors": [{"home_team": "Toronto Maple Leafs", "away_team": "Montreal Canadiens", "steps": steps}]}
    carried = site_module().card_factors(card, ("Toronto Maple Leafs", "Montreal Canadiens"))
    _check(carried, model.moneyline_probabilities("TOR", "MTL")["home"])


def test_the_sample_board_sums_to_its_win_chance() -> None:
    board = json.loads((ROOT / "web" / "data" / "sample" / "board_game.json").read_text(encoding="utf-8"))
    games = [g for g in board["games"] if g.get("factors")]
    assert games
    for g in games:
        _check(g["factors"], g["home"]["winProb"])
