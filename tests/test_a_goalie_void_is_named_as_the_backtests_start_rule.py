"""The forward page named every void "a player who never entered".

Since #208 `_settle_prop_row` voids a `goalie_saves` row whenever the
goalie's time on ice is under `GOALIE_START_SECONDS` — the backtest's start
rule — and that includes a starter pulled after 30 minutes, a bet a book
grades as action. `render_forward_report` still said "A void is a player who
never entered (stake returned, as books do)", and its nothing-settled branch
"A void is a player who never entered a game that was found". So the
published void count held opinions the page said were not there, and gave
the book's rule as the reason for one that is not the book's.

Found by sweep 4. These tests pin that both sentences name the goalie rule,
say it is the backtest's and not a book's, and are built from
`GOALIE_START_SECONDS` so they cannot drift from it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.models.player_props import player_name_aliases

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def _pulled_starter_void() -> tuple:
    """A goalie who started and was pulled at 30 minutes, 14 saves."""
    index: dict = {}
    for alias in player_name_aliases("Joseph Woll"):
        index.setdefault(alias, {})[1] = ("TOR", {"saves": 14.0}, 1800.0)
    row = SimpleNamespace(market="goalie_saves", player="Joseph Woll",
                          line=24.5, selection="under", american_odds=-110)
    return fe._settle_prop_row(row, index, {"TOR"})


def _row(market: str, player: str, outcome: str, profit: float) -> dict:
    return {
        "snapshot_date": "2026-10-10", "commence_time": "2026-10-10T23:00:00Z",
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "market": market, "player": player, "selection": "under",
        "line": 24.5, "american_odds": -110.0, "book": "dk",
        "model_probability": 0.6, "edge": 0.08, "verdicts_in_force": "v",
        "settled_at": "2026-10-12T12:00:00Z", "outcome": outcome,
        "actual": None, "profit_units": profit,
    }


def _page(*, with_a_result: bool) -> str:
    rows = [_row("goalie_saves", "Joseph Woll", "void", 0.0)]
    if with_a_result:
        rows.append(_row("shots_on_goal", "Auston Matthews", "won", 0.91))
    ledger = pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))
    payload = fe.build_forward_report(ledger, now=NOW)
    assert payload["void"] == 1
    return fe.render_forward_report(payload)


def _void_sentence(page: str) -> str:
    (line,) = [
        part for part in page.split("\n\n")
        if "A void is" in part
    ] or [""]
    assert line, "the page does not say what a void is"
    return line


def test_a_pulled_starter_is_a_void() -> None:
    """The premise: the ledger voids a goalie who played."""
    assert _pulled_starter_void() == ("void", None, 0.0)


def _names_the_goalie_rule(sentence: str, minutes: str) -> None:
    assert "never entered" in sentence
    assert "goalie" in sentence
    assert f"under {minutes} minutes" in sentence
    assert "backtest's start rule" in sentence
    assert "not a book's" in sentence
    # "as books do" may only describe the player who never entered.
    assert "as books do" not in sentence.split("goalie", 1)[1]


def test_both_void_sentences_name_the_goalie_rule() -> None:
    minutes = f"{fe.GOALIE_START_SECONDS / 60:g}"
    _names_the_goalie_rule(_void_sentence(_page(with_a_result=True)), minutes)
    _names_the_goalie_rule(_void_sentence(_page(with_a_result=False)), minutes)


def test_the_sentences_are_built_from_the_rule(monkeypatch) -> None:
    monkeypatch.setattr(fe, "GOALIE_START_SECONDS", 3000)
    for with_a_result in (True, False):
        sentence = _void_sentence(_page(with_a_result=with_a_result))
        assert "under 50 minutes" in sentence
        assert "under 40 minutes" not in sentence
