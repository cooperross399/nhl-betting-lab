"""The card's team markets are priced on the site's xG ratings.

Cooper chose the "full switch" on 2026-10-05: the card's team markets read
the same ratings as the public board (`models.team_ratings`), and the
2027-04-25 verdict on team markets covers only games priced on them. These
hold:

* the card applies the ratings file when it runs through the latest game,
  and falls back to goals, saying why, when it is missing or stale;
* the forward report sets aside team-market rows frozen before
  `XG_RATINGS_FROM`, counts them, and leaves props measured as before.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.models.team_ratings import RATINGS_FILE, XG_RATINGS_FROM, apply_xg_ratings
from nhl_betting_lab.models.value import american_to_implied, profit_on_win


def _games() -> pd.DataFrame:
    teams = ["AAA", "BBB", "CCC", "DDD"]
    rows, number = [], 1
    for day in range(1, 29):
        for home, away in ((teams[day % 4], teams[(day + 1) % 4]), (teams[(day + 2) % 4], teams[(day + 3) % 4])):
            rows.append({"game_id": 2024020000 + number, "season": 20242025, "game_type": 2,
                         "date": f"2024-11-{day:02d}", "home_team": home, "away_team": away,
                         "home_goals": 3 + (home == "AAA"), "away_goals": 2, "regulation": True})
            number += 1
    return pd.DataFrame(rows)


def _ratings(through: str) -> dict:
    return {"variant": "xg_luck", "home_advantage": 1.05, "last_game_date": through,
            "teams": {"AAA": {"attack": 0.8, "defence": 1.3}, "BBB": {"attack": 1.2, "defence": 0.9}}}


def test_the_card_prices_on_current_ratings_and_falls_back_on_stale(tmp_path) -> None:
    games = _games()
    goals = TeamModel().fit(games)
    goals_win = goals.moneyline_probabilities("AAA", "BBB")["home"]

    missing = TeamModel().fit(games)
    assert apply_xg_ratings(missing, games, tmp_path)[0] == "goals"
    assert missing.moneyline_probabilities("AAA", "BBB")["home"] == pytest.approx(goals_win)

    (tmp_path / RATINGS_FILE).write_text(json.dumps(_ratings("2024-11-01")), encoding="utf-8")
    stale = TeamModel().fit(games)
    ratings, detail = apply_xg_ratings(stale, games, tmp_path)
    assert ratings == "goals" and "2024-11-01" in detail

    (tmp_path / RATINGS_FILE).write_text(json.dumps(_ratings("2024-11-28")), encoding="utf-8")
    rated = TeamModel().fit(games)
    assert apply_xg_ratings(rated, games, tmp_path)[0] == "xg"
    assert rated.teams["AAA"].attack == pytest.approx(0.8)
    assert rated.teams["BBB"].defence == pytest.approx(0.9)
    assert rated.teams["CCC"].attack == pytest.approx(goals.teams["CCC"].attack)
    assert rated.moneyline_probabilities("AAA", "BBB")["home"] < goals_win


def _row(market: str, day: str, index: int, won: bool) -> dict:
    odds, p = 100.0, 0.62
    return {
        "snapshot_date": day, "commence_time": f"{day}T23:10:00Z",
        "home_team": f"Home {market} {day} {index}", "away_team": "Boston Bruins",
        "market": market, "player": f"Player {index}" if market == "shots_on_goal" else "",
        "selection": "over" if market != "moneyline" else "home", "line": 0.5 if market != "moneyline" else None,
        "american_odds": odds, "book": "DraftKings", "model_probability": p,
        "edge": p - american_to_implied(odds), "verdicts_in_force": "x",
        "settled_at": f"{day}T12:00:00+00:00", "outcome": "won" if won else "lost",
        "actual": 1.0 if won else 0.0, "profit_units": profit_on_win(odds) if won else -1.0,
    }


def test_the_forward_report_sets_aside_goals_priced_team_rows() -> None:
    before, after = "2026-10-03", XG_RATINGS_FROM
    rows = (
        [_row("moneyline", before, i, True) for i in range(5)]
        + [_row("moneyline", after, i, i % 2 == 0) for i in range(4)]
        + [_row("shots_on_goal", before, i, True) for i in range(3)]
    )
    payload = fe.build_forward_report(
        pd.DataFrame(rows), now=datetime(2026, 12, 1, tzinfo=timezone.utc)
    )
    assert payload["superseded_team_rows"] == 5
    assert payload["markets"]["moneyline"]["opinions"] == 4
    assert payload["markets"]["moneyline"]["first_date"] == after
    assert payload["markets"]["shots_on_goal"]["opinions"] == 3
    text = fe.render_forward_report(payload)
    assert f"5 team-market ledger row(s) frozen before {XG_RATINGS_FROM}" in text


def test_a_ledger_with_nothing_before_the_switch_says_nothing_about_it() -> None:
    payload = fe.build_forward_report(
        pd.DataFrame([_row("moneyline", XG_RATINGS_FROM, 0, True)]),
        now=datetime(2026, 12, 1, tzinfo=timezone.utc),
    )
    assert payload["superseded_team_rows"] == 0
    assert "Set aside" not in fe.render_forward_report(payload)
