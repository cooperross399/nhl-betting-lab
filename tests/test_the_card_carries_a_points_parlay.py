"""Cooper's daily points parlay: one player per game, the best model chance of a point."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from nhl_betting_lab.points_parlay import build_points_parlay, combined, render_section
from nhl_betting_lab.reports.card_pricing import selection_key

NOW = datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)
DAY = "2026-11-27"


def _row(home, away, player, price, book="Book", market="points", selection="over", line=0.5,
         start="2026-11-28T00:00:00Z"):
    return {"home_team": home, "away_team": away, "player": player, "american_odds": price,
            "book": book, "market": market, "selection": selection, "line": line,
            "commence_time": start, "date": DAY}


def _frame():
    return pd.DataFrame([
        _row("Edmonton Oilers", "Seattle Kraken", "Connor McDavid", -380),
        _row("Edmonton Oilers", "Seattle Kraken", "Connor McDavid", -350, book="Other"),
        _row("Edmonton Oilers", "Seattle Kraken", "Jordan Eberle", -120),
        _row("Edmonton Oilers", "Seattle Kraken", "Connor McDavid", 150, line=1.5),
        _row("Boston Bruins", "Toronto Maple Leafs", "David Pastrnak", -280),
        _row("Boston Bruins", "Toronto Maple Leafs", "David Pastrnak", 200, selection="under"),
        _row("Buffalo Sabres", "Pittsburgh Penguins", "", -150, market="moneyline", selection="home"),
        _row("Chicago Blackhawks", "New York Rangers", "Connor Bedard", -200,
             start="2026-11-27T14:00:00Z"),
    ])


def _probabilities(frame):
    chances = {"Connor McDavid": 0.78, "Jordan Eberle": 0.50, "David Pastrnak": 0.76,
               "Connor Bedard": 0.66}
    out = {}
    for row in frame.itertuples():
        if row.market == "points" and row.selection == "over" and row.line == 0.5:
            out[selection_key(row, market="points", selection="over", line=0.5)] = chances[row.player]
    return out


def test_one_leg_per_game_at_the_best_chance_and_best_price():
    frame = _frame()
    parlay = build_points_parlay(frame, _probabilities(frame), now=NOW, day=DAY)
    players = {leg["player"]: leg for leg in parlay.legs}
    assert set(players) == {"Connor McDavid", "David Pastrnak"}
    assert players["Connor McDavid"]["american_odds"] == -350
    assert players["Connor McDavid"]["book"] == "Other"
    assert parlay.missing_games == ["Pittsburgh Penguins @ Buffalo Sabres"]
    # The started game is pulled by the puck-drop guard, never a leg.
    assert parlay.removed_by_guard == 1


def test_combined_price_chance_and_ladder_stake():
    legs = [{"american_odds": -350, "model_probability": 0.78},
            {"american_odds": -280, "model_probability": 0.76}]
    price, chance, stake = combined(legs)
    assert round(chance, 4) == round(0.78 * 0.76, 4)
    assert -140 < price < -130  # 1.2857 x 1.3571 = 1.745 decimal
    assert stake == 1.0
    long = [{"american_odds": 150, "model_probability": 0.5}] * 6
    assert combined(long)[2] == 0.2


def test_the_section_names_legs_and_total():
    frame = _frame()
    parlay = build_points_parlay(frame, _probabilities(frame), now=NOW, day=DAY)
    text = "\n".join(render_section(parlay, lambda row: "8:00 PM ET"))
    assert "## Points parlay" in text
    assert "**Connor McDavid**" in text and "**David Pastrnak**" in text
    assert "2 legs. Combined" in text
    assert "Pittsburgh Penguins @ Buffalo Sabres" in text
