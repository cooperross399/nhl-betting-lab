"""The CLV report answers "do the picks we would stake beat the close?"

Cooper, 2026-11-10 ("All", to "Do our picks beat the closing line?"). The
report had two views, every opinion and population B (the measurement bar),
and neither is the card's staked bets. A third view applies the card's
best-bet bar as far as a frozen opinion can show it. These tests pin what it
lets through, that it never claims to be the staked list, and that it adds
nothing that could carry a price.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _opinion(**overrides) -> dict:
    row = {
        "snapshot_date": "2026-10-08",
        "commence_time": "2026-10-08T23:10:00Z",
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "market": "shots_on_goal", "player": "Auston Matthews",
        "selection": "over", "line": 3.5,
        "american_odds": 120, "book": "DraftKings",
        "model_probability": 0.62, "edge": 0.62 - 100 / 220,
        "verdicts_in_force": "",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("market", "edge", "odds", "prob", "expected"),
    [
        ("shots_on_goal", 0.165, 120, 0.62, True),     # clears 12% and its bracket
        ("shots_on_goal", 0.10, 120, 0.55, False),     # under the 12% prop bar
        ("shots_on_goal", 0.13, -170, 0.76, False),    # shorter than -160
        ("shots_on_goal", 0.20, 700, 0.32, False),     # longer than +600
        ("points", 0.20, 120, 0.65, False),            # stake-excluded market
        ("shots_on_goal", 0.13, -150, 0.73, False),    # misses its bracket floor
        ("moneyline", 0.10, 200, 0.43, True),          # team bar 9%, 40%+ to win
        ("moneyline", 0.10, 300, 0.35, False),         # under 40% to win
        ("total_goals", 0.08, -110, 0.60, False),      # under the 9% team bar
        ("total_goals", 0.10, -110, 0.62, True),
        ("shots_on_goal", "nan", 120, 0.62, False),    # no edge is no stake
    ],
)
def test_the_best_bet_bar_applies_what_a_frozen_row_carries(market, edge, odds, prob, expected) -> None:
    from nhl_betting_lab import closing_lines as cl

    assert cl.clears_best_bet_bar(market, edge, odds, prob) is expected


def test_the_bar_reads_the_cards_own_constants() -> None:
    """Built from the card's constants, so it cannot drift from the gate."""
    from nhl_betting_lab import closing_lines as cl
    from nhl_betting_lab.reports.gameday_card import BEST_BET_EDGE, BEST_BET_PROP_EDGE

    assert cl.clears_best_bet_bar("shots_on_goal", BEST_BET_PROP_EDGE, 350, 0.40)
    assert not cl.clears_best_bet_bar("shots_on_goal", BEST_BET_PROP_EDGE - 0.001, 350, 0.40)
    assert cl.clears_best_bet_bar("total_goals", BEST_BET_EDGE, 100, 0.6)
    assert not cl.clears_best_bet_bar("total_goals", BEST_BET_EDGE - 0.001, 100, 0.6)
    note = cl.best_bet_bar_note()
    assert "approximates the bets the card stakes and is not a list of them" in note


def test_the_report_carries_the_best_bet_bar_view(tmp_path: Path) -> None:
    from nhl_betting_lab import closing_lines as cl

    movement = tmp_path / cl.MOVEMENT_DIRNAME
    movement.mkdir(parents=True)
    common = {
        "captured_at": "2026-10-08T21:00:00+00:00",
        "commence_time": "2026-10-08T23:10:00Z",
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "market": "shots_on_goal", "line": 3.5, "book": "Close",
    }
    captures = []
    for player in ("Auston Matthews", "William Nylander"):
        captures += [
            {**common, "player": player, "selection": "over", "american_odds": 105},
            {**common, "player": player, "selection": "under", "american_odds": -125},
        ]
    pd.DataFrame(captures).to_csv(movement / "2026-10-08.csv", index=False)
    opinions = pd.DataFrame([
        # Clears the best-bet bar, taken longer than the close.
        _opinion(player="Auston Matthews"),
        # Population B only: 7% edge.
        _opinion(player="William Nylander", model_probability=0.525,
                 edge=0.525 - 100 / 220),
    ])

    report = cl.build_clv_report(opinions, cl.load_captures(tmp_path))

    assert report["counts"]["best_bar"] == 1
    assert report["counts"]["best_bar_matched"] == 1
    assert report["overall"]["bets"]["bets"] == 2
    assert report["overall"]["best_bar"]["bets"] == 1
    assert report["overall"]["best_bar"]["beat_close"] == 1
    assert report["markets"]["shots_on_goal"]["best_bar"]["bets"] == 1

    rendered = cl.render_clv(report, generated="t")
    assert "## The card's best-bet bar" in rendered
    assert "| `shots_on_goal` | best-bet bar |" in rendered
    # Aggregate only: no book, no price, no line reaches the page.
    assert "Close" not in rendered.split("## The card's best-bet bar", 1)[1].split("## How", 1)[0]
    assert "+105" not in rendered and "-125" not in rendered
