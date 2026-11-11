"""2026-11-05, Cooper: "reevaluate our leans and totals for NHL on the
website. I want to see that record start to turn around".

Three changes, each pinned here:
- the card learns each side of a market apart (`self_learning.fit_trust`),
- a points under is never listed as a lean (`LEAN_EXCLUDED_SIDES`), and
- the site's Totals record grades the side the model's chance beats the
  price on, not the projected total against the line (`total_side`).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.reports import gameday_card as card
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    LEANS_SECTION,
    PASSES_SECTION,
    build_candidates,
)
from nhl_betting_lab.self_learning import (
    adjusted,
    apply_trust,
    fit_trust,
    side_key,
    side_of,
)

ROOT = Path(__file__).resolve().parents[1]


def _site():
    spec = importlib.util.spec_from_file_location("build_site_json_turnaround", ROOT / "web" / "build_site_json.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ledger(days: int = 60) -> pd.DataFrame:
    """The model leans 60% on both sides of a points line at even money:
    its overs win three in four, its unders one in four."""
    rows = []
    start = pd.Timestamp("2026-10-22")
    for i in range(days):
        day = (start + pd.Timedelta(days=i)).date().isoformat()
        for g in range(4):
            for side, wins in (("over", (i + g) % 4 != 0), ("under", (i + g) % 4 == 0)):
                rows.append(dict(
                    snapshot_date=day, home_team=f"H{g}", away_team=f"A{g}", market="points",
                    player=f"P{side}", selection=side, line=0.5, american_odds=100.0, book="X",
                    model_probability=0.60, outcome="won" if wins else "lost",
                ))
    return pd.DataFrame(rows)


def test_each_side_of_a_market_is_learned_apart() -> None:
    trust = fit_trust(_ledger())
    over, under = trust[side_key("points", "over")], trust[side_key("points", "under")]
    assert adjusted(0.6, 100.0, under) < adjusted(0.6, 100.0, trust["points"]) < adjusted(0.6, 100.0, over)


def test_a_thin_side_reads_as_its_market() -> None:
    whole = fit_trust(_ledger(days=60), by_side=False)["points"]
    thin = fit_trust(_ledger(days=60).iloc[:2].assign(selection="over"))
    assert "points" in thin and side_key("points", "over") in thin
    assert whole.w != 1.0


def test_apply_trust_reads_the_side() -> None:
    trust = fit_trust(_ledger())
    over_key = ("points", "p", "H", "A", "over", 0.5, "2026-12-30")
    under_key = ("points", "p", "H", "A", "under", 0.5, "2026-12-30")
    prices = pd.DataFrame([
        dict(market="points", selection="over", line=0.5, american_odds=100.0),
        dict(market="points", selection="under", line=0.5, american_odds=100.0),
    ])
    keys = iter([over_key, under_key])
    out, moved = apply_trust({over_key: 0.6, under_key: 0.6}, prices, trust, key_for=lambda *a, **k: next(keys))
    assert moved == 2 and out[under_key] < 0.6 < out[over_key]


def test_sides() -> None:
    assert side_of("team_total", "home_over") == "over"
    assert side_of("total_goals", "under", 6.5) == "under"
    assert side_of("puck_line", "home", -1.5) == "home_fav"
    assert side_of("puck_line", "away", 1.5) == "away_dog"
    assert side_of("moneyline", "Home") == "home"


def _row(selection: str) -> dict:
    return {
        "date": "2026-11-05", "commence_time": "2026-11-06T00:00:00Z",
        "provider_event_id": "evt", "home_team": "Toronto Maple Leafs",
        "away_team": "New York Rangers", "market": "points", "player": "Auston Matthews",
        "selection": selection, "line": 0.5, "american_odds": 100, "book": "BetMGM",
        "fetched_at": "2026-11-05T13:00:00Z",
    }


def test_a_points_under_is_never_listed_as_a_lean() -> None:
    for edge in (0.07, 0.15):  # a lean, and a best bet the stake rule demotes
        row = _row("under")
        key = selection_key(SimpleNamespace(**row), market="points", selection="under", line=0.5)
        selections, passes = build_candidates(pd.DataFrame([row]), {key: 0.5 + edge})
        assert not selections
        (candidate,) = passes
        assert candidate.section == PASSES_SECTION
        assert "points unders are not listed as leans" in candidate.demotion_reason


def test_a_points_over_still_leans() -> None:
    row = _row("over")
    key = selection_key(SimpleNamespace(**row), market="points", selection="over", line=0.5)
    selections, _ = build_candidates(pd.DataFrame([row]), {key: 0.57})
    assert [c.section for c in selections] == [LEANS_SECTION]


def test_the_total_side_is_the_better_return_not_the_projection() -> None:
    site = _site()
    # Projected 6.6 against 6.5 calls the over on the old rule; the model's
    # chance of the over is 48%, and the under at -105 is the better return.
    total = {"current": 6.5, "proj": 6.6, "overProb": 0.48, "overPrice": -115, "underPrice": -105}
    # Since 2026-11-11 an under short of the card's 6% bar is no totals call.
    assert site.total_side(total) == site.NO_TOTAL_CALL
    assert site.total_side({**total, "overProb": 0.56}) == "over"
    assert site.total_side({**total, "underPrice": None}) is None


def _total_row(selection: str, line: float = 6.5) -> dict:
    return {
        "date": "2026-11-11", "commence_time": "2026-11-12T00:00:00Z",
        "provider_event_id": "evt", "home_team": "Toronto Maple Leafs",
        "away_team": "New York Rangers", "market": "total_goals", "player": "",
        "selection": selection, "line": line, "american_odds": 100, "book": "BetMGM",
        "fetched_at": "2026-11-11T13:00:00Z",
    }


def _cards(rows_and_probs):
    rows = [r for r, _ in rows_and_probs]
    probs = {
        selection_key(SimpleNamespace(**r), market="total_goals", selection=r["selection"], line=r["line"]): p
        for r, p in rows_and_probs
    }
    return build_candidates(pd.DataFrame(rows), probs)


def test_a_game_total_under_needs_a_half_goal_line_and_a_six_point_edge() -> None:
    """2026-11-11: unders stay, listed only at 5.5 or 6.5 with a 6% edge."""
    for line in (5.5, 6.5):
        selections, _ = _cards([(_total_row("under", line), 0.57)])
        assert len(selections) == 1, line
    for line, prob, words in ((6.5, 0.55, "need a 6% edge"), (6.0, 0.70, "only at 5.5 or 6.5"),
                              (4.5, 0.70, "only at 5.5 or 6.5")):
        selections, passes = _cards([(_total_row("under", line), prob)])
        assert not selections
        (candidate,) = passes
        assert candidate.section == PASSES_SECTION
        assert words in candidate.demotion_reason


def test_one_game_total_under_per_game() -> None:
    selections, passes = _cards([(_total_row("under", 5.5), 0.58), (_total_row("under", 6.5), 0.62)])
    (kept,) = selections
    assert kept.line == 6.5
    (dropped,) = passes
    assert dropped.line == 5.5 and dropped.demotion_reason == card.ONE_UNDER_PER_GAME


def test_a_game_total_over_is_unchanged() -> None:
    selections, _ = _cards([(_total_row("over", 6.0), 0.55)])
    assert len(selections) == 1


def test_the_site_and_the_card_share_the_under_rule() -> None:
    site = _site()
    assert site.TOTAL_UNDER_LINES == card.TOTAL_UNDER_LINES
    assert site.TOTAL_UNDER_MIN_EDGE == card.TOTAL_UNDER_MIN_EDGE
    total = {"current": 6.5, "proj": 6.0, "overProb": 0.40, "overPrice": -115, "underPrice": -105}
    assert site.total_side(total) == "under"
    assert site.total_side({**total, "current": 6.0}) == site.NO_TOTAL_CALL


def test_a_game_with_no_totals_call_is_not_graded(tmp_path, monkeypatch) -> None:
    import json
    from datetime import date

    site = _site()
    day = date(2026, 11, 11)
    game = {"id": "1", "startUtc": "2026-11-12T00:00:00Z",
            "home": {"abbr": "TOR", "projGoals": 3.0}, "away": {"abbr": "NYR", "projGoals": 3.2},
            "total": {"current": 6.5, "proj": 6.2, "side": site.NO_TOTAL_CALL,
                      "overPrice": -110, "underPrice": -110}}
    (tmp_path / f"{day.isoformat()}.json").write_text(json.dumps({"phase": "regular", "games": [game]}))
    final = {"id": 1, "gameState": "OFF", "homeTeam": {"score": 2}, "awayTeam": {"score": 3}}
    monkeypatch.setattr(site, "schedule_for", lambda d: [final])
    results = site.settle(day, tmp_path)
    assert results["summary"]["totals"] == {"w": 0, "l": 0, "p": 0}
    assert results["summary"]["money"]["totals"]["staked"] == 0.0
    (row,) = results["games"]
    assert "total" not in row
    # An over call on the same game is graded as before.
    game["total"]["side"] = "over"
    (tmp_path / f"{day.isoformat()}.json").write_text(json.dumps({"phase": "regular", "games": [game]}))
    assert site.settle(day, tmp_path)["summary"]["totals"] == {"w": 0, "l": 1, "p": 0}


def test_a_game_total_under_needs_two_strong_defences() -> None:
    """Cooper, 2026-11-11: "focus on games with elite goalies/great defenses"."""
    row = _total_row("under", 6.5)
    key = selection_key(SimpleNamespace(**row), market="total_goals", selection="under", line=6.5)
    frame = pd.DataFrame([row])
    listed, _ = build_candidates(frame, {key: 0.57}, strong_defence=lambda home, away: True)
    assert len(listed) == 1
    listed, passes = build_candidates(frame, {key: 0.57}, strong_defence=lambda home, away: False)
    assert not listed
    assert passes[0].demotion_reason == card.STRONG_DEFENCE_REASON
    over = _total_row("over", 6.5)
    okey = selection_key(SimpleNamespace(**over), market="total_goals", selection="over", line=6.5)
    listed, _ = build_candidates(pd.DataFrame([over]), {okey: 0.57}, strong_defence=lambda h, a: False)
    assert len(listed) == 1


def test_strong_defences_are_the_better_half() -> None:
    spec = importlib.util.spec_from_file_location("run_gameday_card_defence", ROOT / "scripts" / "run_gameday_card.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    teams = {c: SimpleNamespace(defence=d) for c, d in (("A", 0.9), ("B", 1.0), ("C", 1.1), ("D", 1.2))}
    assert module.strong_defences(teams) == {"A", "B"}
    assert module.strong_defences({}) == set()
