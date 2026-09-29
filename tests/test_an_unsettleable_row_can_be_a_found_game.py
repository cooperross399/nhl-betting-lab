"""The forward page said every unsettleable row was a game with no result.

`settle_snapshots` marks a row unsettleable when its game never produced a
final result inside the patience window, and also when the game WAS found
and is final but the row cannot be graded against it: `_settle_prop_row`
for a name that reaches two players (the two Sebastian Ahos in CAR v NYI),
a goalie whose ice time was not recorded, a missing stat, line or known
selection; `_settle_team_row` for a level final or a missing line. The
"What this stream is and is not" bullet said "An unsettleable row is a game
that never produced a final result inside the patience window", while the
nothing-settled branch of the same page already added "or a row that could
not be settled against its game". One count, two meanings, and a join
problem sent to the results fetch.

Found by sweep 6 (forward-unsettleable-definition-omits-found-games). These
tests pin that both branches give the same definition, that it names the
found-game causes, and that it is built from `PATIENCE_DAYS`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.models.player_props import player_name_aliases

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def _two_ahos_row() -> tuple:
    """A found, final CAR v NYI game whose logs hold two Sebastian Ahos."""
    index: dict = {}
    for pid, team in ((1, "CAR"), (2, "NYI")):
        for alias in player_name_aliases("Sebastian Aho"):
            index.setdefault(alias, {})[pid] = (
                team, {"shots_on_goal": 3.0}, 1100.0,
            )
    row = SimpleNamespace(market="shots_on_goal", player="Sebastian Aho",
                          line=2.5, selection="over", american_odds=110)
    return fe._settle_prop_row(row, index, {"CAR", "NYI"})


def _row(market: str, player: str, outcome: str, profit: float) -> dict:
    return {
        "snapshot_date": "2026-10-10", "commence_time": "2026-10-10T23:00:00Z",
        "home_team": "Carolina Hurricanes", "away_team": "New York Islanders",
        "market": market, "player": player, "selection": "over",
        "line": 2.5, "american_odds": 110.0, "book": "dk",
        "model_probability": 0.6, "edge": 0.08, "verdicts_in_force": "v",
        "settled_at": "2026-10-12T12:00:00Z", "outcome": outcome,
        "actual": None, "profit_units": profit,
    }


def _page(*, with_a_result: bool) -> str:
    rows = [_row("shots_on_goal", "Sebastian Aho", "unsettleable", 0.0)]
    if with_a_result:
        rows.append(_row("shots_on_goal", "Brock Nelson", "won", 1.1))
    ledger = pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))
    payload = fe.build_forward_report(ledger, now=NOW)
    assert payload["unsettleable"] == 1
    return fe.render_forward_report(payload)


def _definition(page: str) -> str:
    parts = [p for p in page.split("\n\n") if "An unsettleable row is" in p]
    assert len(parts) == 1, "the page does not say (once) what an unsettleable row is"
    match = re.search(r"An unsettleable row is (.*?)(?: —|\.\s|\.$)", parts[0], re.S)
    assert match, parts[0]
    return match.group(1)


def test_a_found_final_game_can_leave_a_row_unsettleable() -> None:
    """The premise: settlement marks a found game's row unsettleable."""
    assert _two_ahos_row()[0] == "unsettleable"


def _names_both_causes(sentence: str) -> None:
    assert "no final result" in sentence
    assert "patience window" in sentence
    assert "found" in sentence, "the found-game cause is missing"
    assert "two players" in sentence
    assert "ice time" in sentence
    assert "missing line or stat" in sentence
    assert "level final" in sentence


def test_both_branches_name_the_found_game_causes() -> None:
    with_result = _definition(_page(with_a_result=True))
    without = _definition(_page(with_a_result=False))
    _names_both_causes(with_result)
    _names_both_causes(without)
    assert with_result == without, "the two branches disagree"


def test_the_definition_is_built_from_the_patience_window(monkeypatch) -> None:
    monkeypatch.setattr(fe, "PATIENCE_DAYS", 9)
    for with_a_result in (True, False):
        sentence = _definition(_page(with_a_result=with_a_result))
        assert "9-day patience window" in sentence
