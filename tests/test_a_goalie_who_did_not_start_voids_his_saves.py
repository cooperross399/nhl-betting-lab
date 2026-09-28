"""A saves prop on a goalie who did not start is void, never graded.

Books post a total-saves line for the expected starter and void it when he
does not start. The boxscore lists every goalie who dressed, so the backup
who sat all night is in the logs with no ice time and no saves, and settling
him grades a saves under as a win the book would have refunded. The
historical backtest never scored those games at all: a goalie appearance
under `walk_forward.GOALIE_START_SECONDS` produces no sample, so it produces
no bet. The forward ledger must settle by the same rule, or the 2027-04-25
decision reads a stream of free under wins the backtest never saw.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.backtest.walk_forward import GOALIE_START_SECONDS
from nhl_betting_lab.reports.card_pricing import selection_key


NOW = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)
FROZEN_AT = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
TEAM_NAMES = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}


def _saves_row(selection: str) -> dict:
    return {
        "commence_time": "2026-10-09T00:10:00Z",  # league date 2026-10-08
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "market": "goalie_saves",
        "player": "Joseph Woll",
        "selection": selection,
        "line": 25.5,
        "american_odds": -110,
        "book": "DraftKings",
    }


def _goalie_logs(toi_seconds: object, saves: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-10-08",
                "player_id": 8479361,
                "player": "Joseph Woll",
                "team": "TOR",
                "role": "goalie",
                "toi_seconds": toi_seconds,
                "shots_on_goal": 0.0,
                "points": 0.0,
                "goals": 0.0,
                "assists": 0.0,
                "blocked_shots": 0.0,
                "hits": 0.0,
                "saves": saves,
            }
        ]
    )


def _games() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": 1,
                "date": "2026-10-08",
                "home_team": "TOR",
                "away_team": "BOS",
                "home_goals": 4,
                "away_goals": 2,
                "regulation": True,
            }
        ]
    )


def _settle_one(tmp_path: Path, selection: str, logs: pd.DataFrame):
    raw = _saves_row(selection)
    key = selection_key(
        SimpleNamespace(**raw),
        market="goalie_saves",
        selection=selection,
        line=25.5,
    )
    fe.write_snapshot(
        pd.DataFrame([raw]),
        {key: 0.62},
        key_for=selection_key,
        verdicts_line="props_b2b=in force",
        snapshot_date="2026-10-08",
        now=FROZEN_AT,
        archive_dir=tmp_path,
    )
    fe.settle_snapshots(
        logs,
        _games(),
        team_names=TEAM_NAMES,
        archive_dir=tmp_path,
        processed_dir=tmp_path / "processed",
        now=NOW,
    )
    return fe.load_ledger(tmp_path / "processed").iloc[0]


def test_a_backup_who_dressed_and_never_played_voids(tmp_path: Path) -> None:
    """Zero ice time, zero saves: the under must not be a free win."""
    row = _settle_one(tmp_path, "under", _goalie_logs(0, 0.0))

    assert row["outcome"] == "void"
    assert row["profit_units"] == 0.0


def test_a_relief_appearance_voids(tmp_path: Path) -> None:
    """He came in cold in the second period; nobody sold a line on that."""
    row = _settle_one(
        tmp_path, "under", _goalie_logs(GOALIE_START_SECONDS - 600, 9.0)
    )

    assert row["outcome"] == "void"
    assert row["profit_units"] == 0.0


def test_a_goalie_whose_ice_time_is_unrecorded_is_not_graded(
    tmp_path: Path,
) -> None:
    """Unknown is not a start. Grading it would guess at the one fact the
    void rests on."""
    row = _settle_one(tmp_path, "under", _goalie_logs(float("nan"), 0.0))

    assert row["outcome"] == "unsettleable"
    assert row["profit_units"] == 0.0


def test_a_start_still_settles_both_ways(tmp_path: Path) -> None:
    won = _settle_one(tmp_path / "a", "over", _goalie_logs(3600, 31.0))
    lost = _settle_one(tmp_path / "b", "under", _goalie_logs(3600, 31.0))

    assert won["outcome"] == "won"
    assert won["profit_units"] == pytest.approx(100 / 110)
    assert lost["outcome"] == "lost"


def test_the_rule_is_the_backtest_rule_at_its_boundary(tmp_path: Path) -> None:
    """Exactly the historical threshold is a start, as it is in
    `walk_forward` (which drops `toi < GOALIE_START_SECONDS`)."""
    row = _settle_one(tmp_path, "over", _goalie_logs(GOALIE_START_SECONDS, 31.0))

    assert row["outcome"] == "won"


def test_a_skater_is_untouched_by_the_goalie_rule(tmp_path: Path) -> None:
    """A skater's ice time never voids his own props."""
    raw = {**_saves_row("over"), "market": "shots_on_goal",
           "player": "Auston Matthews", "line": 2.5}
    key = selection_key(
        SimpleNamespace(**raw), market="shots_on_goal", selection="over",
        line=2.5,
    )
    fe.write_snapshot(
        pd.DataFrame([raw]), {key: 0.62}, key_for=selection_key,
        verdicts_line="x", snapshot_date="2026-10-08", now=FROZEN_AT,
        archive_dir=tmp_path,
    )
    logs = _goalie_logs(600, 0.0).assign(
        player_id=8479318, player="Auston Matthews", role="skater",
        shots_on_goal=4.0,
    )
    fe.settle_snapshots(
        logs, _games(), team_names=TEAM_NAMES, archive_dir=tmp_path,
        processed_dir=tmp_path / "processed", now=NOW,
    )

    assert fe.load_ledger(tmp_path / "processed").iloc[0]["outcome"] == "won"


def test_logs_without_an_ice_time_column_grade_no_goalie(tmp_path: Path) -> None:
    """A log frame that never carried ice time is the unrecorded case for
    every goalie in it, not a start for all of them."""
    logs = _goalie_logs(3600, 31.0).drop(columns=["toi_seconds"])
    row = _settle_one(tmp_path, "over", logs)

    assert row["outcome"] == "unsettleable"
