"""The forward report counted every book's quote as its own bet.

The snapshot freezes one row per book and the ledger keeps them all, as it
should: they are evidence, and the CLV report reads them. But
`build_forward_report` counted every ledger row, so a selection quoted by
eight books was eight opinions and eight bets — the per-quote counting this
lab retired on 2026-08-31, still live in the one report the pre-registered
2027-04-25 decision reads ("one bet per wager at the best price the card
could have taken", docs/when_this_ends.md). Replayed on the bought card
window, per-quote reads -1.34% over 114,292 with the interval excluding zero
("Stop"); per-wager reads -0.03% over 28,287, spanning zero. Found by the
failure-shape audit (2/2 refuters, the third interrupted).

What these tests hold, on ledgers shaped as settlement writes them:

* one wager quoted by three books is one opinion and one bet, at the best
  price, paying what that price pays;
* two selections are two wagers, and one player's line on two game days is
  two wagers — the collapse never merges different games;
* void and unsettleable are counted per wager, and the rendered report says
  how many ledger rows collapsed to how many wagers.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.models.value import american_to_implied, profit_on_win


NOW = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
P = 0.62  # the model's probability; +120 implies 45.5%, so every price clears


def _row(odds: int, *, book: str, outcome: str = "won",
         player: str = "Auston Matthews", day: str = "2026-10-08",
         commence: str = "2026-10-09T00:10:00Z", selection: str = "over") -> dict:
    won = outcome == "won"
    return {
        "snapshot_date": day, "commence_time": commence,
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "market": "shots_on_goal", "player": player, "selection": selection,
        "line": 3.5, "american_odds": float(odds), "book": book,
        "model_probability": P, "edge": P - american_to_implied(odds),
        "verdicts_in_force": "x", "settled_at": "2026-10-10T12:00:00+00:00",
        "outcome": outcome, "actual": 5.0 if won else None,
        "profit_units": (profit_on_win(float(odds)) if won
                         else (-1.0 if outcome == "lost" else 0.0)),
    }


def _ledger(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))


def test_three_books_on_one_wager_are_one_bet_at_the_best_price() -> None:
    ledger = _ledger([_row(-110, book="BetMGM"), _row(125, book="DraftKings"),
                      _row(105, book="FanDuel")])

    payload = fe.build_forward_report(ledger, now=NOW)
    entry = payload["markets"]["shots_on_goal"]

    assert payload["rows"] == 3 and payload["wagers"] == 1
    assert entry["opinions"] == 1 and entry["bets"] == 1
    assert entry["profit_units"] == pytest.approx(profit_on_win(125.0))


def test_two_selections_are_two_wagers() -> None:
    ledger = _ledger(
        [_row(o, book=b) for o, b in ((-110, "BetMGM"), (125, "DraftKings"), (105, "FanDuel"))]
        + [_row(o, book=b, player="Mitch Marner")
           for o, b in ((-105, "BetMGM"), (110, "DraftKings"), (100, "FanDuel"))]
    )

    entry = fe.build_forward_report(ledger, now=NOW)["markets"]["shots_on_goal"]

    assert entry["opinions"] == 2 and entry["bets"] == 2


def test_one_players_line_on_two_game_days_is_two_wagers() -> None:
    ledger = _ledger([
        _row(125, book="DraftKings"),
        _row(110, book="FanDuel"),
        _row(120, book="DraftKings", day="2026-10-10",
             commence="2026-10-11T00:10:00Z"),
    ])

    entry = fe.build_forward_report(ledger, now=NOW)["markets"]["shots_on_goal"]

    assert entry["bets"] == 2
    assert entry["profit_units"] == pytest.approx(
        profit_on_win(125.0) + profit_on_win(120.0)
    )


def test_eighteen_books_on_one_losing_wager_are_one_losing_bet() -> None:
    ledger = _ledger([_row(100 + i, book=f"Book{i}", outcome="lost") for i in range(18)])

    entry = fe.build_forward_report(ledger, now=NOW)["markets"]["shots_on_goal"]

    assert entry["bets"] == 1
    assert entry["profit_units"] == pytest.approx(-1.0)


def test_void_is_counted_per_wager_and_the_report_says_what_collapsed() -> None:
    ledger = _ledger(
        [_row(o, book=b, outcome="void") for o, b in ((-110, "BetMGM"), (125, "DraftKings"), (105, "FanDuel"))]
        + [_row(125, book="DraftKings", player="Mitch Marner")]
    )

    payload = fe.build_forward_report(ledger, now=NOW)
    rendered = fe.render_forward_report(payload)

    assert payload["void"] == 1
    assert "Ledger rows: 4 — one per book — on 2 wager(s)" in rendered
