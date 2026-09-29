"""Which book holds the best price never changes the selections.

`selection_fingerprint` is documented to exclude prices, so that a moved line
does not send an email. It keyed on the best-price row's display name, and
books spell players differently — "Alexis Lafrenière" at most, "Alexis
Lafreniere" at one. When the best price for the same outcome moved from one
to the other between two runs, the fingerprint changed and the card posted
under "Selections changed" with nothing changed. The fingerprint now keys on
the player as a bet is written (`player_key`), the identity the card already
groups and stakes on.

The fingerprint is persisted in the saved card and compared on the next run,
so a card saved before this fix carries the raw spelling. The previous
fingerprint is recomputed from the saved card's own best bets, so the first
run after the change does not post a spurious "Selections changed".
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


def _prices(dk_price: int, fd_price: int, *, fd_player: str = "Alexis Lafreniere"):
    base = dict(
        date="2026-10-07",
        commence_time="2026-10-07T23:00:00Z",
        provider_event_id="e1",
        home_team="New York Rangers",
        away_team="Boston Bruins",
        market="shots_on_goal",
        selection="over",
        line=2.5,
        fetched_at="2026-10-07T13:30:00+00:00",
    )
    return pd.DataFrame(
        [
            {**base, "player": "Alexis Lafrenière", "american_odds": dk_price, "book": "DraftKings"},
            {**base, "player": fd_player, "american_odds": fd_price, "book": "FanDuel"},
        ]
    )


def _card(prices: pd.DataFrame):
    probabilities = {
        selection_key(row, market="shots_on_goal", selection="over", line=2.5): 0.70
        for row in prices.itertuples()
    }
    eligibility = EligibilityReport(
        provider_name="the_odds_api",
        games_in_slate=1,
        markets=[
            MarketEligibility(
                market="shots_on_goal",
                state="eligible",
                reason="ok",
                games_in_slate=1,
                games_priced=1,
            )
        ],
    )
    return build_card(prices, probabilities, eligibility=eligibility, now=NOW)


def test_a_best_price_moving_to_another_books_spelling_is_not_a_change() -> None:
    morning = _card(_prices(120, 110))  # DraftKings, "Lafrenière", is best
    rerun = _card(_prices(110, 115))  # FanDuel, "Lafreniere", is best
    assert [r["player"] for r in morning.best_bets] == ["Alexis Lafrenière"]
    assert [r["player"] for r in rerun.best_bets] == ["Alexis Lafreniere"]

    decision = decide(rerun, previous_fingerprint=morning.selection_fingerprint())

    assert morning.selection_fingerprint() == rerun.selection_fingerprint()
    assert not decision.selections_changed
    assert not decision.post


def test_a_different_player_is_still_a_change() -> None:
    morning = _card(_prices(120, 110))
    other = _card(_prices(-500, 150, fd_player="Artemi Panarin"))
    assert [r["player"] for r in other.best_bets][0] != "Alexis Lafrenière"

    assert morning.selection_fingerprint() != other.selection_fingerprint()


def test_a_card_saved_before_the_change_does_not_read_as_changed(
    tmp_path: Path,
) -> None:
    morning = _card(_prices(120, 110))
    payload = json.loads(
        Path(save_card(morning, output_dir=tmp_path)["json"]).read_text(
            encoding="utf-8"
        )
    )
    # The fingerprint as the card wrote it before the fix: raw spelling.
    payload["selection_fingerprint"] = "\n".join(
        sorted(
            f"{r['market']}|{r['player'] or ''}|{r['home_team']}|{r['away_team']}|"
            f"{r['selection']}|{r['line']}|{r['date']}"
            for r in payload["best_bets"]
        )
    )
    assert payload["selection_fingerprint"] != morning.selection_fingerprint()

    rerun = _card(_prices(110, 115))
    decision = decide(rerun, previous_fingerprint=previous_fingerprint_from(payload))

    assert not decision.selections_changed


def test_a_saved_card_that_did_change_still_reads_as_changed(tmp_path: Path) -> None:
    other = _card(_prices(-500, 150, fd_player="Artemi Panarin"))
    payload = json.loads(
        Path(save_card(other, output_dir=tmp_path)["json"]).read_text(
            encoding="utf-8"
        )
    )

    decision = decide(
        _card(_prices(120, 110)), previous_fingerprint=previous_fingerprint_from(payload)
    )

    assert decision.selections_changed and decision.post
