"""A summer mover is never priced as a player of the club he left.

Gameday refreshes all 32 rosters every run, and losing one club's request is
a partial failure: a warning, exit 0, a card built on 31 rosters. A player
who moved BOS -> TOR, on a night TOR hosts BOS with TOR's roster the one that
failed, has no roster entry — so pricing fell back to the club in his logs,
BOS, and priced him as BOS's away skater against his own club: wrong
opponent factor, wrong venue, frozen into the forward ledger as an ordinary
opinion. BOS's fresh roster was on disk the whole time and did not list him.

The logs are a fallback only for a club whose roster the card does not hold.
A club whose roster it holds and which leaves him off is evidence he has
left, and he is unresolved and named — the same safe failure as a roster
naming a club not in the game.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.data.nhl_api import current_rosters
from nhl_betting_lab.reports.card_pricing import price_props

MOVER = 8478402


class _Rates:
    def __init__(self, team: str) -> None:
        self.team = team
        self.expected_toi_seconds = 1200.0


class _StubModel:
    """Just enough model to see which side of the game he was priced on."""

    def __init__(self, logged_team: str) -> None:
        self.skaters = {MOVER: _Rates(logged_team)}
        self.goalies: dict[int, _Rates] = {}
        self.asked: list[tuple[str, str]] = []

    def resolve_player_in_game(self, name, *, home, away):
        return MOVER

    def over_probability(self, player_id, market, line, *, opponent, venue, **kw):
        self.asked.append((opponent, venue))
        return 0.55


def _prop_row(home: str, away: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-10-08",
                "commence_time": "2026-10-08T23:00:00Z",
                "home_team": home,
                "away_team": away,
                "market": "shots_on_goal",
                "player": "Summer Mover",
                "selection": "over",
                "line": 2.5,
                "american_odds": -110,
                "book": "DraftKings",
            }
        ]
    )


def _cache(tmp_path: Path, rosters: dict[str, list[int]]) -> Path:
    directory = tmp_path / "nhl" / "roster"
    directory.mkdir(parents=True)
    for team, ids in rosters.items():
        (directory / f"{team}_20262027.json").write_text(
            json.dumps({"forwards": [{"id": i} for i in ids]}), encoding="utf-8"
        )
    return tmp_path


def test_a_mover_whose_new_clubs_roster_failed_is_named_not_priced_for_his_old_club(
    tmp_path: Path,
) -> None:
    # TOR's refresh failed; BOS's fresh roster is cached and leaves him off.
    raw = _cache(tmp_path, {"BOS": [1, 2], "MTL": [3]})
    model = _StubModel(logged_team="BOS")

    probabilities, unresolved = price_props(
        _prop_row(home="TOR", away="BOS"),
        model,
        rosters=current_rosters(raw_dir=raw),
    )

    assert model.asked == [], "priced as BOS's away skater against his own club"
    assert probabilities == {}
    assert unresolved == ["Summer Mover"]


def test_the_logs_still_price_a_player_whose_clubs_roster_was_not_fetched(
    tmp_path: Path,
) -> None:
    # His logged club's roster is the one that failed: the logs are all the
    # card has, and a missing roster must never unresolve a player.
    raw = _cache(tmp_path, {"TOR": [1, 2], "MTL": [3]})
    model = _StubModel(logged_team="BOS")

    probabilities, unresolved = price_props(
        _prop_row(home="TOR", away="BOS"),
        model,
        rosters=current_rosters(raw_dir=raw),
    )

    assert unresolved == []
    assert probabilities
    assert model.asked == [("TOR", "away")]


def test_with_no_rosters_at_all_the_logs_decide(tmp_path: Path) -> None:
    model = _StubModel(logged_team="BOS")

    probabilities, unresolved = price_props(
        _prop_row(home="TOR", away="BOS"), model, rosters={}
    )

    assert unresolved == [] and probabilities
    assert model.asked == [("TOR", "away")]


def test_a_roster_that_lists_him_still_wins_over_the_logs(tmp_path: Path) -> None:
    raw = _cache(tmp_path, {"TOR": [MOVER, 1], "BOS": [2]})
    model = _StubModel(logged_team="BOS")

    probabilities, unresolved = price_props(
        _prop_row(home="TOR", away="BOS"),
        model,
        rosters=current_rosters(raw_dir=raw),
    )

    assert unresolved == [] and probabilities
    assert model.asked == [("BOS", "home")]
