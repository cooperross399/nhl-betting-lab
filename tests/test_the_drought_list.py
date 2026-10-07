"""Cooper's drought rule on the card: a selection list, built from the same function as the evidence.

The rule (2026-10-07): 70+ points, 30+ goals or 30+ assists last regular season and
5+ straight games without one in that category is a bet on the over 0.5. On the
card it is an UNSTAKED list Cooper picks from. These tests hold what makes the
list honest: the qualifiers are `prepare_logs`' own, a missing price stays
"not posted", heavy juice is a flag and never a reason to hide a row, a started
game is never listed, a name that will not resolve is never guessed, and the list
publishes on a night with no prices at all.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from nhl_betting_lab import drought_rule as dr
from nhl_betting_lab.reports.gameday_card import GamedayCard, render_card

DAY = "2026-10-08"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
TEAM_NAMES = {"edmonton oilers": "EDM", "calgary flames": "CGY", "winnipeg jets": "WPG",
              "montreal canadiens": "MTL", "toronto maple leafs": "TOR", "boston bruins": "BOS"}
STARTS = {(DAY, "EDM", "CGY"): "2026-10-08T23:00:00Z", (DAY, "WPG", "MTL"): "2026-10-08T23:30:00Z",
          (DAY, "TOR", "BOS"): "2026-10-08T11:00:00Z"}  # TOR @ BOS has already faced off at NOW
ROSTERS = {1: "EDM", 2: "EDM", 3: "WPG", 4: "TOR", 9: "EDM"}


def _games(pid, name, season, start, n, *, goals=0, assists=0, game_type=2, role="skater"):
    day = pd.Timestamp(start)
    return [{"game_id": pid * 1000 + int(season) % 1000 + i + (500 if game_type == 1 else 0), "season": season,
             "game_type": game_type, "date": (day + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
             "player_id": pid, "player": name, "role": role, "goals": goals, "assists": assists,
             "points": goals + assists} for i in range(n)]


def make_logs() -> pd.DataFrame:
    rows = []
    # 1: 31 assists last season, then 5 games without one: an assists qualifier, drought 5.
    rows += _games(1, "Assist Man", 20252026, "2025-10-10", 31, assists=1)
    rows += _games(1, "Assist Man", 20262027, "2026-10-01", 5)
    # 2: 32 goals, but only 4 games dry this season: below the drought bar.
    rows += _games(2, "Four Dry", 20252026, "2025-10-10", 32, goals=1)
    rows += _games(2, "Four Dry", 20262027, "2026-10-01", 4)
    # 3: 30 goals, then 3 dry games LAST season and 2 this season: the drought crosses the boundary.
    rows += _games(3, "Test Scorer", 20252026, "2025-10-10", 30, goals=1)
    rows += _games(3, "Test Scorer", 20252026, "2026-03-01", 3)
    rows += _games(3, "Test Scorer", 20262027, "2026-10-01", 2)
    # 4: 70 points, 5 dry; a preseason point must not break the run. Plays a game already under way.
    rows += _games(4, "Point Man", 20252026, "2025-10-10", 70, assists=1)
    rows += _games(4, "Point Man", 20262027, "2026-10-01", 5)
    rows += _games(4, "Point Man", 20262027, "2026-09-25", 1, assists=1, game_type=1)
    # 9: a goalie never qualifies.
    rows += _games(9, "Goalie Guy", 20252026, "2025-10-10", 80, role="goalie")
    # A game on the day itself is tonight, not history: it must not reset player 1's run.
    rows += _games(1, "Assist Man", 20262027, DAY, 1, assists=1)
    return pd.DataFrame(rows)


def quote(player, market, odds, book, home="Edmonton Oilers", away="Calgary Flames"):
    return {"date": DAY, "commence_time": "2026-10-08T23:00:00Z", "home_team": home, "away_team": away,
            "market": market, "player": player, "selection": "over", "line": 0.5, "american_odds": odds, "book": book}


def build(prices=None, **overrides):
    args = dict(logs=make_logs(), rosters=ROSTERS, starts=STARTS,
                prices=pd.DataFrame(prices or [], columns=list(quote("x", "goals", 1, "b"))),
                team_names=TEAM_NAMES, day=DAY, now=NOW)
    args.update(overrides)
    return dr.build_drought_list(**args)


def test_the_qualifiers_are_the_evidences_own_drought_and_last_seasons_totals():
    q = dr.qualifiers_entering(make_logs(), DAY).set_index(["player_id", "market"])

    assert q.loc[(1, "assists"), "drought"] == 5 and q.loc[(1, "assists"), "last_season"] == 31
    assert q.loc[(3, "goals"), "drought"] == 5, "3 dry games last season + 2 this season"
    assert q.loc[(4, "points"), "drought"] == 5, "a preseason point is not a regular-season game"
    assert (2, "goals") not in q.index, "4 dry games is below the bar"
    assert not any(pid == 9 for pid, _ in q.index), "goalies never qualify"
    assert (1, "points") not in q.index and (1, "goals") not in q.index


def test_a_game_on_the_day_is_entered_not_played():
    # The 2026-10-08 game player 1 scored in is tonight's; the list must not see it.
    assert dr.qualifiers_entering(make_logs(), DAY).query("player_id == 1").drought.tolist() == [5]
    seen = dr.qualifiers_entering(make_logs(), "2026-10-09")
    assert seen.query("player_id == 1").empty, "once tonight's assist is history the drought is over"


def test_the_card_and_the_backtest_share_one_function():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "drb", Path(__file__).resolve().parents[1] / "scripts" / "run_drought_rule_backtest.py")
    drb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drb)
    assert drb.prepare_logs is dr.prepare_logs and drb.drought_before is dr.drought_before
    assert drb.THRESHOLDS is dr.THRESHOLDS and drb.MIN_DROUGHT == dr.MIN_DROUGHT


def test_the_list_publishes_with_not_posted_prices_when_no_book_has_posted():
    result = build()

    names = [(r["player"], r["market"]) for r in result.rows]
    assert names == [("Assist Man", "assists"), ("Test Scorer", "goals")] or sorted(names) == sorted(
        [("Assist Man", "assists"), ("Test Scorer", "goals")])
    assert all(r["american_odds"] is None and r["book"] == "" and not r["heavy_juice"] for r in result.rows)
    assert dr.price_text(result.rows[0]) == "not posted"


def test_the_team_is_the_rosters_not_the_logs_last_club():
    logs = make_logs()
    logs["team"] = "XXX"  # whatever the log last said
    result = build(logs=logs, rosters={**ROSTERS, 3: "MTL"})

    row = next(r for r in result.rows if r["player_id"] == 3)
    assert (row["team"], row["opponent"], row["home_team"], row["away_team"]) == ("MTL", "WPG", "WPG", "MTL")
    assert build(rosters={}).rows == [] and "rosters" in build(rosters={}).notes[0]


def test_the_best_price_and_its_book_are_shown_and_heavy_juice_is_a_flag_not_a_filter():
    result = build([
        quote("Assist Man", "assists", 150, "FanDuel"), quote("Assist Man", "assists", 170, "DraftKings"),
        quote("Test Scorer", "goals", -170, "BetMGM", home="Winnipeg Jets", away="Montreal Canadiens"),
        quote("Test Scorer", "goals", -190, "Caesars", home="Winnipeg Jets", away="Montreal Canadiens"),
    ])
    by = {r["player"]: r for r in result.rows}

    assert (by["Assist Man"]["american_odds"], by["Assist Man"]["book"]) == (170, "DraftKings")
    assert not by["Assist Man"]["heavy_juice"]
    assert by["Test Scorer"]["american_odds"] == -170 and by["Test Scorer"]["heavy_juice"], "-170 is shorter than -160"
    # exactly -160 is not shorter than -160
    assert not build([quote("Assist Man", "assists", -160, "X")]).rows[0]["heavy_juice"]


def test_only_the_over_half_line_in_that_players_category_prices_a_row():
    result = build([
        {**quote("Assist Man", "assists", 500, "X"), "line": 1.5},
        {**quote("Assist Man", "assists", 500, "X"), "selection": "under"},
        quote("Assist Man", "goals", 500, "X"),
        quote("Assist Man", "assists", 175, "Y", home="Toronto Maple Leafs", away="Boston Bruins"),
    ])

    assert next(r for r in result.rows if r["player"] == "Assist Man")["american_odds"] is None


def test_a_started_game_is_never_listed_and_the_guard_is_counted():
    result = build()

    assert "Point Man" not in [r["player"] for r in result.rows]
    assert result.removed_by_guard == 2, "his points AND his assists both qualify; both are off the list"
    assert build(now=datetime(2026, 10, 8, 23, 5, tzinfo=timezone.utc)).rows == [] or all(
        r["player"] != "Assist Man" for r in build(now=datetime(2026, 10, 8, 23, 5, tzinfo=timezone.utc)).rows)


def test_an_unconfirmable_start_is_not_listed():
    starts = {**STARTS, (DAY, "EDM", "CGY"): ""}
    assert "Assist Man" not in [r["player"] for r in build(starts=starts).rows]


def test_a_name_two_players_share_resolves_to_neither_and_is_listed_unresolved():
    logs = pd.concat([make_logs(), pd.DataFrame(_games(7, "Assist Man", 20252026, "2025-10-10", 3, assists=1))])
    result = build([quote("Assist Man", "assists", 170, "DraftKings")], logs=logs, rosters={**ROSTERS, 7: "CGY"})

    assert next(r for r in result.rows if r["player_id"] == 1)["american_odds"] is None
    assert result.unresolved and "Assist Man" in result.unresolved[0]


def test_rows_sort_by_category_then_longest_drought_first():
    logs = pd.concat([make_logs(), pd.DataFrame(
        _games(8, "Long Dry", 20252026, "2025-10-10", 31, assists=1) + _games(8, "Long Dry", 20262027, "2026-10-01", 8))])  # the 8th is dated DAY: tonight, not history
    result = build(logs=logs, rosters={**ROSTERS, 8: "CGY"})

    assert [(r["market"], r["drought"]) for r in result.rows] == [("goals", 5), ("assists", 7), ("assists", 5)]


def test_the_section_is_a_list_with_no_units_no_tiers_and_one_headline_line():
    card = GamedayCard(generated_at=NOW.isoformat(), card_generated=False, blockers=["Stale prices."])
    result = build([quote("Assist Man", "assists", 170, "DraftKings")])
    card.drought_built, card.drought_rows = True, result.rows
    card.drought_notes, card.drought_unresolved = ["a note"], ["Somebody (goals, A @ B)"]
    card.drought_headline = "HEADLINE LINE"

    text = render_card(card)
    section = text[text.index(f"## {dr.SECTION_TITLE}"):]
    section = section[: section.index("\n## ", 5)] if "\n## " in section[5:] else section

    assert "Assist Man" in section and "+170" in section and "DraftKings" in section and "over 0.5" in section
    assert section.splitlines()[2] == "HEADLINE LINE"
    assert "| Units" not in section and "Tier" not in section and "Edge" not in section
    assert "No card" in text, "a card blocked for prices still publishes the list"
    assert "not posted" in render_card(_with_rows(build().rows))


def _with_rows(rows):
    card = GamedayCard(generated_at=NOW.isoformat(), card_generated=False, blockers=["x"])
    card.drought_built, card.drought_rows, card.drought_headline = True, rows, "H"
    return card


def test_a_card_that_never_asked_renders_no_section():
    assert dr.SECTION_TITLE not in render_card(GamedayCard(generated_at=NOW.isoformat()))


def test_the_list_never_reaches_the_selection_fingerprint_or_the_stakes():
    card = _with_rows(build().rows)
    bare = GamedayCard(generated_at=NOW.isoformat(), card_generated=False, blockers=["x"])

    assert card.selection_fingerprint() == bare.selection_fingerprint()
    assert card.total_units == 0 and card.best_bets == [] and card.leans == [] and card.passes == []


def test_the_headline_is_read_from_the_backtest_json(tmp_path):
    import json

    bucket = lambda m, roi, lo, hi, n: {"window": "card", "market": m, "bucket": "RULE: drought 5+", "season": "both",
                                          "roi": roi, "ci_low": lo, "ci_high": hi, "wagers": n}
    (tmp_path / dr.BACKTEST_JSON).write_text(json.dumps({"buckets": [
        bucket("points", -0.158, -0.359, 0.069, 69), bucket("goals", -0.043, -0.146, 0.049, 971),
        bucket("assists", -0.104, -0.171, -0.043, 1804)]}))

    line = dr.backtest_headline(tmp_path)

    assert "points -15.8% over 69 wagers" in line and "goals -4.3% over 971" in line and "assists -10.4% over 1804" in line
    assert "no category's interval sits above zero" in line and "\n" not in line
    assert "unavailable" in dr.backtest_headline(tmp_path / "nowhere")


def test_the_committed_backtest_headline_reads_its_file():
    line = dr.backtest_headline(dr.Path(__file__).resolve().parents[1] / "data" / "outputs")

    assert "points" in line and "69 wagers" in line and "971" in line and "1804" in line
