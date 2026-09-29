"""A game the puck-drop guard withheld is in neither population.

#246's `closing_lines.measurement_bar_note()` — printed under population B
on the forward page and as the Bets definition on the CLV page — listed
"rows whose stake the puck-drop guard pulled" among the opinions the card
did not stake, then said "Every such opinion is still counted here." It
cannot be. `forward_evidence.write_snapshot` runs every row through the
card's own puck-drop rule (`puck_drop.check_commence_time`) at the same
`moment` `build_card`'s `apply_puck_drop_guard` uses, and withholds any row
that is not playable, tallying it as "started" or "unconfirmed". So every
row the card's guard quarantines is missing from the snapshot, the ledger,
both populations and the CLV opinions. The note told the reader that games
already under way when the card ran are in the forward sample.

Found by sweep 4. These tests tie the note to the withholding: on a slate
with one game under way, one whose start cannot be confirmed and one still
to play, the guard pulls two, the snapshot withholds the same two, and the
note says such games are withheld from the snapshot and appear in neither
population — and no longer that they are counted.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.closing_lines import measurement_bar_note
from nhl_betting_lab.puck_drop import apply_puck_drop_guard
from nhl_betting_lab.reports.card_pricing import selection_key

NOW = datetime(2026, 10, 10, 23, 30, tzinfo=timezone.utc)
#: (commence time, home club): under way, unconfirmable, still to play.
SLATE = (
    ("2026-10-10T23:00:00Z", "Toronto Maple Leafs"),
    ("", "Edmonton Oilers"),
    ("2026-10-11T02:00:00Z", "Vancouver Canucks"),
)


def _prices() -> pd.DataFrame:
    return pd.DataFrame([
        {"commence_time": commence, "home_team": home,
         "away_team": "Calgary Flames", "market": "moneyline", "player": "",
         "selection": "home", "line": None, "american_odds": 150.0,
         "book": "fanduel"}
        for commence, home in SLATE
    ])


def test_the_guard_and_the_snapshot_withhold_the_same_games(tmp_path) -> None:
    prices = _prices()
    probabilities = {
        selection_key(row, market="moneyline", selection="home", line=None): 0.55
        for row in prices.itertuples()
    }
    guarded = apply_puck_drop_guard(
        [row._asdict() for row in prices.itertuples()], now=NOW
    )
    pulled = {row["home_team"] for row in guarded.quarantined}
    assert pulled == {"Toronto Maple Leafs", "Edmonton Oilers"}

    tally: dict = {}
    path = fe.write_snapshot(
        prices, probabilities, key_for=selection_key, verdicts_line="v",
        snapshot_date="2026-10-10", now=NOW, archive_dir=tmp_path, tally=tally,
    )
    frozen = pd.read_csv(path)
    assert (tally["started"], tally["unconfirmed"], tally["frozen"]) == (1, 1, 1)
    assert not pulled & set(frozen["home_team"]), (
        "a row the guard pulled was frozen"
    )


def test_the_note_says_such_games_are_in_neither_population() -> None:
    note = measurement_bar_note()
    lowered = note.lower()
    assert "puck-drop guard pulled" not in lowered
    # The note still ends by saying the reasons it lists are counted — but
    # the guard is no longer among them, and it says where those games are.
    counted = note.split("Every such opinion is still counted here.", 1)
    assert len(counted) == 2, "the counted reasons are still stated"
    assert "puck-drop" not in counted[0]
    after = counted[1]
    assert "withheld from the snapshot" in after
    assert "neither population" in after
    assert "started" in after and "cannot be confirmed" in after


def test_the_forward_page_prints_the_corrected_note(tmp_path) -> None:
    ledger = pd.DataFrame([{
        "snapshot_date": "2026-10-10", "commence_time": "2026-10-11T02:00:00Z",
        "home_team": "Vancouver Canucks", "away_team": "Calgary Flames",
        "market": "moneyline", "player": "", "selection": "home",
        "line": None, "american_odds": 150.0, "book": "fanduel",
        "model_probability": 0.55, "edge": 0.15, "verdicts_in_force": "v",
        "settled_at": "2026-10-12T12:00:00Z", "outcome": "won",
        "actual": 1.0, "profit_units": 1.5,
    }], columns=list(fe.LEDGER_COLUMNS))
    page = fe.render_forward_report(fe.build_forward_report(ledger, now=NOW))
    assert "puck-drop guard pulled" not in page
    assert "withheld from the snapshot" in page
    assert "neither population" in page
