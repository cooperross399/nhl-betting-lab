"""PostHockey's pre-game win probability moves the moneyline, not the total.

Cooper, 2026-10-25. `posthockey` reads PostHockey's number for each game not
yet started; these hold:

* only the pre-game kind is read, never a live in-game number;
* the latest read of a game wins, and an out-of-range number is refused;
* the team model moves its moneyline `BLEND_WEIGHT` of the way to it, keeps
  the expected total, and moves nothing when the weight is zero or the game
  has no number;
* the card sets the weight, so every walk-forward prices as before.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from nhl_betting_lab import posthockey as ph
from nhl_betting_lab.models.team_model import TeamModel

_SPEC = importlib.util.spec_from_file_location(
    "_varied_logs_ph",
    Path(__file__).resolve().parent / "test_a_walk_forward_model_sees_only_earlier_games.py",
)
_VARIED = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_VARIED)

DAY = "2026-10-25"
ROOT = Path(__file__).resolve().parents[1]


def _game(state: str, kind: str, p_home: float, home: str = "DAL", away: str = "NYI") -> dict:
    # The shape PostHockey's /api/v1/live served on 2026-10-25, trimmed.
    return {
        "game_id": 2026020181, "game_type": 2, "is_preseason": False, "game_state": state,
        "home": {"abbrev": home}, "away": {"abbrev": away},
        "win_prob": {"p_home": p_home, "kind": kind, "p_home_pre": p_home,
                     "goalie_home_status": "listed", "goalie_away_status": "listed"},
    }


def test_only_the_pre_game_number_is_read() -> None:
    payload = {"games": [_game("FUT", "pre", 0.656), _game("LIVE", "live", 0.415, "CHI", "FLA")]}
    rows = ph.pregame_rows(payload, DAY, "2026-10-25T12:00:00+00:00")
    assert [(r["home_team"], r["away_team"], r["p_home"]) for r in rows] == [("DAL", "NYI", 0.656)]
    with pytest.raises(ValueError):
        ph.pregame_rows({"detail": "Not Found"}, DAY, "x")


def test_the_latest_read_wins_and_a_wild_number_is_refused(tmp_path) -> None:
    path = tmp_path / ph.TONIGHT_DIRNAME / f"{DAY}.csv"
    ph.append_rows(path, ph.pregame_rows({"games": [_game("FUT", "pre", 0.60)]}, DAY, "2026-10-25T12:00:00+00:00"))
    ph.append_rows(path, ph.pregame_rows({"games": [_game("FUT", "pre", 0.66)]}, DAY, "2026-10-25T22:30:00+00:00"))
    wild = _game("FUT", "pre", 0.99, "WPG", "MTL")
    wild["game_id"] = 2026020182
    ph.append_rows(path, ph.pregame_rows({"games": [wild]}, DAY, "2026-10-25T22:30:00+00:00"))
    assert ph.tonight_targets(tmp_path, DAY) == {("DAL", "NYI"): 0.66}
    assert ph.tonight_targets(tmp_path, "2026-10-26") == {}


def test_the_moneyline_moves_toward_posthockey_and_the_total_stays() -> None:
    model = TeamModel().fit(_VARIED.varied_games())
    home, away = model.expected_goals("TOR", "BOS")
    own = model.moneyline_probabilities("TOR", "BOS")["home"]
    target = min(0.9, own + 0.2)
    model.pregame_targets = {("TOR", "BOS"): target}
    assert model.expected_goals("TOR", "BOS") == pytest.approx((home, away))  # weight 0
    model.pregame_weight = ph.BLEND_WEIGHT
    moved_home, moved_away = model.expected_goals("TOR", "BOS")
    assert moved_home + moved_away == pytest.approx(home + away)
    assert moved_home > home
    blended = model.moneyline_probabilities("TOR", "BOS")["home"]
    assert blended == pytest.approx(own + ph.BLEND_WEIGHT * (target - own), abs=1e-4)
    # The other direction, and a game with no number.
    model.pregame_targets = {("TOR", "BOS"): max(0.1, own - 0.2), }
    assert model.moneyline_probabilities("TOR", "BOS")["home"] < own
    assert model.expected_goals("BOS", "TOR") == pytest.approx(
        TeamModel().fit(_VARIED.varied_games()).expected_goals("BOS", "TOR")
    )


def test_the_card_reads_it_and_gameday_refresh_fetches_it() -> None:
    card = (ROOT / "scripts" / "run_gameday_card.py").read_text(encoding="utf-8")
    assert "posthockey.tonight_targets(" in card
    assert "team_model.pregame_weight = posthockey.BLEND_WEIGHT" in card
    workflow = (ROOT / ".github" / "workflows" / "gameday-refresh.yml").read_text(encoding="utf-8")
    fetch = workflow.index("python scripts/fetch_posthockey_pregame.py")
    assert fetch < workflow.index("python scripts/run_gameday_card.py")
