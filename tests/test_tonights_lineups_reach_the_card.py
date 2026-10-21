"""Tonight's posted lines decide who is out and how much each skater plays.

Cooper, 2026-10-21: tonight's injuries and scratches, with the missing
player's ice time moved to his teammates, and each player's current line and
power-play unit. `lineups.tonight_lineups` reads the day's Daily Faceoff
capture; these hold:

* a club posts only with enough skaters on its lines, and the latest capture
  per club is the one read;
* a skater on a posted club's lines gets his line's and unit's ice time,
  blended with his own; one missing from them gets no opinion and is named;
* a club that did not post decides nothing, and every player on it prices
  as before;
* recent regulars absent tonight take part of their share of the club's
  points off its attack, never below the floor.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import lineups as lu
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.reports.card_pricing import price_props

_SPEC = importlib.util.spec_from_file_location(
    "_varied_logs_lu",
    Path(__file__).resolve().parent / "test_a_walk_forward_model_sees_only_earlier_games.py",
)
_VARIED = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_VARIED)

DAY = "2025-06-01"


def _capture(tmp_path: Path, team: str, names: list[tuple[str, str]], *, when: str) -> None:
    path = tmp_path / lu.LINES_DIRNAME / f"{DAY}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"team_abbreviation": team, "player": name, "group_identifier": group,
         "injury_status": "", "retrieved_at": when}
        for name, group in names
    ]
    frame = pd.DataFrame(rows)
    frame.to_csv(path, mode="a", header=not path.is_file(), index=False)


def _full_lines(stars: list[str]) -> list[tuple[str, str]]:
    """Stars on the first line and unit, filler for the rest of the sheet."""
    out = [(name, "f1") for name in stars] + [(name, "pp1") for name in stars]
    out += [(f"Filler {i}", f"f{2 + i // 3}" if i < 9 else f"d{1 + (i - 9) // 2}") for i in range(16)]
    return out


def test_a_posted_club_names_roles_and_absences(tmp_path) -> None:
    logs = _VARIED.varied_logs()
    # TOR's regulars are Player 1, Player 2 and Player 99; Player 2 is out.
    _capture(tmp_path, "TOR", _full_lines(["Player 1", "Player 99"]), when="2025-06-01T12:00:00+00:00")
    # An older capture of BOS with everyone is superseded by a thin one.
    _capture(tmp_path, "BOS", _full_lines(["Player 11", "Player 12"]), when="2025-06-01T10:00:00+00:00")
    _capture(tmp_path, "BOS", [("Player 11", "f1")], when="2025-06-01T13:00:00+00:00")
    tonight = lu.tonight_lineups(tmp_path, DAY, logs)
    assert tonight.posted("TOR") and not tonight.posted("BOS")
    assert tonight.role("TOR", "Player 1") == ("f1", "pp1")
    assert tonight.role("TOR", "Nobody", "Player 2") is None
    assert tonight.absent["TOR"] == ["Player 2"]
    assert lu.MIN_ATTACK_FACTOR <= tonight.attack_factors["TOR"] < 1.0
    assert tonight.role_minutes is not None
    first_line = tonight.expected_toi("f1", "pp1", 600.0)
    assert first_line > 600.0  # a first-liner on ten minutes is priced up


def test_no_capture_decides_nothing(tmp_path) -> None:
    tonight = lu.tonight_lineups(tmp_path, DAY, _VARIED.varied_logs())
    assert not tonight.roles and not tonight.attack_factors


def test_the_card_withholds_an_absent_skater_and_reprices_the_rest(tmp_path) -> None:
    logs = _VARIED.varied_logs()
    model = PlayerPropsModel().fit(logs)
    _capture(tmp_path, "TOR", _full_lines(["Player 1", "Player 99"]), when="2025-06-01T12:00:00+00:00")
    tonight = lu.tonight_lineups(tmp_path, DAY, logs)
    prices = pd.DataFrame([
        {"market": "shots_on_goal", "player": name, "selection": "over", "line": 1.5,
         "home_team": "TOR", "away_team": "BOS", "commence_time": f"{DAY}T23:00:00Z",
         "provider_event_id": "e1", "bookmaker": "book", "price": 1.9}
        for name in ("Player 1", "Player 2", "Player 11")
    ])
    plain, _ = price_props(prices, model)
    priced, _ = price_props(prices, model, lineups=tonight)
    assert tonight.out_tonight == {"Player 2 (TOR)"}
    assert len(plain) == 3 and len(priced) == 2
    keys = {k: v for k, v in priced.items()}
    # BOS posted nothing, so Player 11 prices exactly as before.
    bos = [k for k in plain if "player 11" in str(k).lower()]
    assert bos and keys[bos[0]] == pytest.approx(plain[bos[0]])
