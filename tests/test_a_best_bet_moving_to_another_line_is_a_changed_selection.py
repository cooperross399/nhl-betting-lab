"""A best bet that moves to a different line is a changed selection; the same
line priced differently is not.

Over 2.5 shots and over 3.5 shots are different bets: a reader who placed
the morning's over 2.5 holds a bet the rerun's card no longer recommends.
`selection_fingerprint_of` keys the line for exactly that, and nothing else
in the suite pinned it — the fingerprint with `line` removed passed every
test, and would have kept silent (no "Selections changed" post) when the
card moved a player's recommendation from one rung to another. Prices still
never count: the same line at a new price is not a change.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.market_eligibility import EligibilityReport, MarketEligibility
from nhl_betting_lab.reports.card_notification import decide, previous_fingerprint_from
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import build_card, save_card

NOW = datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc)
PLAYER = "Artemi Panarin"


def _card(line: float, price: int):
    prices = pd.DataFrame([dict(
        date="2026-10-07",
        commence_time="2026-10-07T23:00:00Z",
        provider_event_id="e1",
        home_team="New York Rangers",
        away_team="Boston Bruins",
        market="shots_on_goal",
        selection="over",
        line=line,
        player=PLAYER,
        american_odds=price,
        book="DraftKings",
        fetched_at="2026-10-07T13:30:00+00:00",
    )])
    probabilities = {
        selection_key(row, market="shots_on_goal", selection="over", line=line): 0.70
        for row in prices.itertuples()
    }
    eligibility = EligibilityReport(
        provider_name="the_odds_api",
        games_in_slate=1,
        markets=[MarketEligibility(market="shots_on_goal", state="eligible",
                                   reason="ok", games_in_slate=1, games_priced=1)],
    )
    card = build_card(prices, probabilities, eligibility=eligibility, now=NOW)
    # The premise: one best bet, same player/market/selection, on `line`.
    assert [(r["player"], r["market"], r["selection"], r["line"])
            for r in card.best_bets] == [(PLAYER, "shots_on_goal", "over", line)]
    return card


def test_the_best_bet_moving_to_another_line_is_a_changed_selection() -> None:
    morning = _card(2.5, 120)
    rerun = _card(3.5, 120)

    decision = decide(rerun, previous_fingerprint=morning.selection_fingerprint())

    assert decision.selections_changed is True, (
        "over 2.5 became over 3.5 and the card called the selections unchanged")
    assert decision.post


def test_the_same_line_at_a_new_price_is_not_a_changed_selection() -> None:
    morning = _card(2.5, 120)
    rerun = _card(2.5, 105)

    decision = decide(rerun, previous_fingerprint=morning.selection_fingerprint())

    assert decision.selections_changed is False
    assert not decision.post


def test_a_saved_card_on_another_line_reads_as_changed(tmp_path: Path) -> None:
    """The previous fingerprint is recomputed from the saved card's rows
    (`previous_fingerprint_from`); the line must survive that path too."""
    morning = _card(2.5, 120)
    payload = json.loads(
        Path(save_card(morning, output_dir=tmp_path)["json"]).read_text(encoding="utf-8")
    )
    previous = previous_fingerprint_from(payload)

    assert decide(_card(3.5, 120), previous_fingerprint=previous).selections_changed is True
    assert decide(_card(2.5, 105), previous_fingerprint=previous).selections_changed is False
