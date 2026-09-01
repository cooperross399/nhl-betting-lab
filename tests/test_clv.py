"""Closing-line value reads what is already being captured.

CLV is a diagnostic here and never gates a decision — Cooper, 2026-08-29:
profit and ROI are the objective. It earns its place by converging faster
than settled results, which makes it an early anomaly signal rather than a
criterion.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_clv_reads_the_movement_store_rather_than_re_buying_the_board(
    tmp_path: Path,
) -> None:
    """A second capture job would pay twice for the same prices.

    The line-movement capture already runs five times a day in season and
    writes every column a closing price needs, including a snapshot at
    face-off for an evening start. Scheduling a dedicated closing-line
    capture would cost about 24,600 credits a season to collect what is
    already on disk, and add another scheduled surface to keep correct.
    """
    from nhl_betting_lab import closing_lines as cl

    movement = tmp_path / cl.MOVEMENT_DIRNAME
    movement.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "captured_at": "2026-10-08T21:00:00+00:00",
                "commence_time": "2026-10-08T23:10:00Z",
                "home_team": "TOR", "away_team": "BOS",
                "market": "shots_on_goal", "player": "Auston Matthews",
                "selection": "over", "line": 3.5,
                "american_odds": -115, "book": "DraftKings",
            },
            {   # later, and still before face-off: this is the closing price
                "captured_at": "2026-10-08T23:00:00+00:00",
                "commence_time": "2026-10-08T23:10:00Z",
                "home_team": "TOR", "away_team": "BOS",
                "market": "shots_on_goal", "player": "Auston Matthews",
                "selection": "over", "line": 3.5,
                "american_odds": -135, "book": "DraftKings",
            },
        ]
    ).to_csv(movement / "2026-10-08.csv", index=False)

    captures = cl.load_captures(tmp_path)

    assert len(captures) == 2, "the movement store is the fallback source"
    closing = cl.closing_prices(captures)
    assert closing, "a capture before face-off must produce a closing price"
    odds = [entry.get("american_odds") for entry in closing.values()]
    assert -135 in odds, "the LAST capture before face-off is the close"
