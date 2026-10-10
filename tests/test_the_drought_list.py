"""Cooper's Due List on the card: a selection list, built from the same function as the evidence.

The rule (2026-10-07 evening): 70+ points, 30+ goals or 30+ assists last regular season,
listed in that category when the drought reaches EITHER bar: the tier bar from last
season's total (3/4/5 games by band) or the surprise bar from his own hit rate (the
smallest n with (1-p)^n <= 0.05). On the card it is an UNSTAKED list Cooper picks from.
These tests hold what makes the list honest: the qualifiers are `prepare_logs`' own, the
bars are the ones the module states, the hit rate counts games he dressed for, a missing
price stays "not posted", heavy juice is a flag and never a reason to hide a row, a started
game is never listed, a name that will not resolve is never guessed, a band's record comes
from the committed backtest or is null, and the list publishes on a night with no prices.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import pandas as pd
import pytest

from nhl_betting_lab import drought_rule as dr
from nhl_betting_lab.reports.gameday_card import GamedayCard, render_card

DAY = "2026-10-08"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
TEAM_NAMES = {"edmonton oilers": "EDM", "calgary flames": "CGY", "winnipeg jets": "WPG",
              "montreal canadiens": "MTL", "toronto maple leafs": "TOR", "boston bruins": "BOS"}
STARTS = {(DAY, "EDM", "CGY"): "2026-10-08T23:00:00Z", (DAY, "WPG", "MTL"): "2026-10-08T23:30:00Z",
          (DAY, "TOR", "BOS"): "2026-10-08T11:00:00Z"}  # TOR @ BOS has already faced off at NOW
ROSTERS = {1: "EDM", 2: "EDM", 3: "WPG", 4: "TOR", 9: "EDM"}


def _games(pid, name, season, start, n, *, goals=0, assists=0, game_type=2, role="skater", offset=0):
    day = pd.Timestamp(start)
    return [{"game_id": pid * 1000 + int(season) % 1000 + offset + i + (500 if game_type == 1 else 0), "season": season,
             "game_type": game_type, "date": (day + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
             "player_id": pid, "player": name, "role": role, "goals": goals, "assists": assists,
             "points": goals + assists} for i in range(n)]


def make_logs() -> pd.DataFrame:
    """Last season's hit segment always comes LAST, so each drought entering 2026-27 starts at zero."""
    rows = []
    # 1: 31 assists in 62 games last season (p = 0.5: surprise bar 5; 30-44 band: tier bar 5), then 5 games
    #    this season without one: listed, drought 5, both bars.
    rows += _games(1, "Assist Man", 20252026, "2025-10-10", 31)
    rows += _games(1, "Assist Man", 20252026, "2025-11-10", 31, assists=1, offset=31)
    rows += _games(1, "Assist Man", 20262027, "2026-10-01", 5)
    # 2: 32 goals in 64 games (25-39 band: tier bar 10), only 4 games dry: below the bar.
    rows += _games(2, "Four Dry", 20252026, "2025-10-10", 32)
    rows += _games(2, "Four Dry", 20252026, "2025-11-11", 32, goals=1, offset=32)
    rows += _games(2, "Four Dry", 20262027, "2026-10-01", 4)
    # 3: 40 goals in 73 games (40+ band: tier bar 5; goals have no surprise bar), then 3 dry games LAST
    #    season and 2 this season: the drought crosses the boundary.
    rows += _games(3, "Test Scorer", 20252026, "2025-10-10", 30)
    rows += _games(3, "Test Scorer", 20252026, "2025-11-09", 40, goals=1, offset=30)
    rows += _games(3, "Test Scorer", 20252026, "2026-03-01", 3, offset=70)
    rows += _games(3, "Test Scorer", 20262027, "2026-10-01", 2)
    # 4: 70 points, all assists, in 105 games (p = 0.667: surprise bar 3; points tier bar 5, assists tier
    #    bar 3), 5 dry; a preseason point must not break the run. Plays a game already under way.
    rows += _games(4, "Point Man", 20252026, "2025-10-10", 35)
    rows += _games(4, "Point Man", 20252026, "2025-11-14", 70, assists=1, offset=35)
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


# -- the bars ----------------------------------------------------------------


def test_the_tier_bar_and_its_band_at_every_boundary():
    cases = [
        ("points", 69, None, None), ("points", 70, 5, "70-84"), ("points", 84, 5, "70-84"),
        ("points", 85, 4, "85-99"), ("points", 99, 4, "85-99"), ("points", 100, 3, "100+"), ("points", 153, 3, "100+"),
        ("goals", 24, None, None), ("goals", 25, 10, "25-39"), ("goals", 34, 10, "25-39"),
        ("goals", 39, 10, "25-39"), ("goals", 40, 5, "40+"), ("goals", 64, 5, "40+"),
        ("assists", 29, None, None), ("assists", 30, 5, "30-44"), ("assists", 44, 5, "30-44"),
        ("assists", 45, 4, "45-59"), ("assists", 59, 4, "45-59"), ("assists", 60, 3, "60+"),
    ]
    for market, total, bar, band in cases:
        assert dr.tier_bar(market, total) == bar, (market, total)
        assert dr.band_label(market, total) == band, (market, total)
    assert dr.tier_bar("points", float("nan")) is None and dr.band_label("goals", None) is None
    assert dr.TIERS == {"points": ((100, 3), (85, 4), (70, 5)), "goals": ((40, 5), (25, 10)),
                        "assists": ((60, 3), (45, 4), (30, 5))}
    assert dr.THRESHOLDS == {"points": 70, "goals": 25, "assists": 30}
    assert dr.SURPRISE_MARKETS == ("points", "assists"), "goals left the surprise bar on 2026-10-10"


def test_the_surprise_bar_is_the_smallest_drought_at_or_under_the_level():
    assert dr.SURPRISE_LEVEL == 0.05
    assert dr.surprise_bar(0) is None and dr.surprise_bar(0.0) is None and dr.surprise_bar(float("nan")) is None
    assert dr.surprise_bar(1) == 1 and dr.surprise_bar(1.0) == 1
    assert dr.surprise_bar(0.75) == 3 and dr.surprise_bar(0.55) == 4 and dr.surprise_bar(0.3) == 9
    assert dr.surprise_bar(0.5) == 5, "0.5^4 = 0.0625 is above the level; 0.5^5 = 0.03125 is under it"
    assert dr.surprise_bar(19 / 20) == 1, "(1 - 19/20)^1 is the level itself, whatever the float says"
    assert dr.surprise_bar(1e-17) is None, "1 - p is 1.0 at this p: undefined, as p == 0 is, not a division by zero"
    assert dr.surprise_bar(1 / 85) == 254, "the smallest hit rate a season of games dressed can give"
    for hits in range(1, 82):
        p = hits / 82
        n = dr.surprise_bar(p)
        assert (1 - p) ** n <= dr.SURPRISE_LEVEL + 1e-12, (p, n)
        assert n == 1 or (1 - p) ** (n - 1) > dr.SURPRISE_LEVEL, (p, n)
        assert n == max(1, math.ceil(math.log(dr.SURPRISE_LEVEL) / math.log(1 - p))) or math.isclose(
            (1 - p) ** (n - 1), dr.SURPRISE_LEVEL, rel_tol=1e-9), (p, n)


def test_the_drought_counts_a_hit_at_one_or_more_and_refuses_a_missing_stat():
    assert dr.drought_before([0, 0, 1, 0, 2, 0, 0]) == [0, 1, 2, 0, 1, 0, 1]
    assert dr.drought_before([]) == [] and dr.drought_before([3]) == [0]
    # Counted as a hit (NaN == 0 is False), a missing stat would end a drought nobody saw end; it is refused instead.
    for missing in (float("nan"), None):
        with pytest.raises(ValueError, match="no stat recorded"):
            dr.drought_before([0, 0, missing, 0])


def _either_bar_logs() -> pd.DataFrame:
    """Four profiles whose droughts sit on different sides of the two bars."""
    rows = []
    # 11: 100 points (50 games with two assists) in 100 games: p = 0.5 (surprise 5); 100+ band (tier 3).
    #     Drought 3 reaches the tier bar only.
    rows += _games(11, "Tier Only", 20252026, "2025-10-10", 50)
    rows += _games(11, "Tier Only", 20252026, "2025-11-29", 50, assists=2, offset=50)
    rows += _games(11, "Tier Only", 20262027, "2026-10-01", 3)
    # 12: 70 points (28 goals in 14 games, then 42 assists in 42) in 76 games, 56 with a point: p = 0.737
    #     (surprise 3); 70-84 band (tier 5). Drought 4 reaches the surprise bar only. His 42 assists
    #     (p = 0.553: surprise 4; 30-44 band: tier 5) do the same; 28 goals reach the 25-39 bar (10) on a 46-game drought.
    rows += _games(12, "Surprise Only", 20252026, "2025-10-10", 20)
    rows += _games(12, "Surprise Only", 20252026, "2025-10-30", 14, goals=2, offset=20)
    rows += _games(12, "Surprise Only", 20252026, "2025-11-13", 42, assists=1, offset=34)
    rows += _games(12, "Surprise Only", 20262027, "2026-10-01", 4)
    # 13: 100 points in 80 games, 60 with a point: p = 0.75 (surprise 3); tier 3. Drought 5 reaches both.
    rows += _games(13, "Both Bars", 20252026, "2025-10-10", 20)
    rows += _games(13, "Both Bars", 20252026, "2025-10-30", 40, assists=2, offset=20)
    rows += _games(13, "Both Bars", 20252026, "2025-12-09", 20, assists=1, offset=60)
    rows += _games(13, "Both Bars", 20262027, "2026-10-01", 5)
    # 14 and 15: 70 points (29 goals in 29 games, then 41 assists in 41) in 140 games: p = 0.5 for points
    #     (surprise 5, tier 5), 0.293 for assists (surprise 9, tier 5); 29 goals reach 10 on 45 and 46. Drought 4
    #     reaches nothing; drought 5 reaches both bars for points and the tier bar alone for assists.
    for pid, name, dry in ((14, "Neither", 4), (15, "Then Five", 5)):
        rows += _games(pid, name, 20252026, "2025-10-10", 70)
        rows += _games(pid, name, 20252026, "2025-12-19", 29, goals=1, offset=70)
        rows += _games(pid, name, 20252026, "2026-01-17", 41, assists=1, offset=99)
        rows += _games(pid, name, 20262027, "2026-10-01", dry)
    return pd.DataFrame(rows)


def test_a_player_is_listed_when_either_bar_is_reached_and_the_rule_names_which():
    q = dr.qualifiers_entering(_either_bar_logs(), DAY)

    assert set(zip(q.player_id, q.market, q.rule)) == {
        (11, "points", "tier"), (11, "assists", "tier"),
        (12, "points", "surprise"), (12, "assists", "surprise"),
        (13, "points", "both"), (13, "assists", "both"),
        (15, "points", "both"), (15, "assists", "tier"),
        # 28 and 29 goals clear 25, and none since: droughts of 46, 45 and 46 reach the 25-39 band's bar of 10.
        (12, "goals", "tier"), (14, "goals", "tier"), (15, "goals", "tier"),
    }, "14 (drought 4 in points and assists, every bar at 5 or more) is listed only in goals"
    by = q.set_index(["player_id", "market"])
    tier_only = by.loc[(11, "points")]
    assert (tier_only.tier_bar, tier_only.surprise_bar, tier_only.hit_rate, tier_only.band, tier_only.drought) == (3, 5, 0.5, "100+", 3)
    surprise_only = by.loc[(12, "points")]
    assert (surprise_only.tier_bar, surprise_only.surprise_bar, surprise_only.hit_rate, surprise_only.band, surprise_only.rarity) == (
        5, 3, 0.737, "70-84", 0.0048), "0.263^4"
    assert surprise_only.one_in == 209, "1 / (20/76)^4 = 208.5 from the unrounded figure; 1 / 0.0048 would say 208"
    assert (by.loc[(12, "assists")].tier_bar, by.loc[(12, "assists")].surprise_bar, by.loc[(12, "assists")].hit_rate) == (5, 4, 0.553)
    both = by.loc[(13, "points")]
    assert (both.tier_bar, both.surprise_bar, both.hit_rate, both.rarity, both.one_in) == (3, 3, 0.75, 0.001, 1024), "0.25^5"
    assert (by.loc[(15, "assists")].tier_bar, by.loc[(15, "assists")].surprise_bar, by.loc[(15, "assists")].band,
            by.loc[(15, "assists")].drought) == (5, 9, "30-44", 5)
    assert [(by.loc[(pid, "goals")].drought, by.loc[(pid, "goals")].tier_bar, by.loc[(pid, "goals")].band) for pid in (12, 14, 15)] == [
        (46, 10, "25-39"), (45, 10, "25-39"), (46, 10, "25-39")]
    assert all(pd.isna(by.loc[(pid, "goals")].surprise_bar) for pid in (12, 14, 15)), "goals carry no surprise bar"
    assert (by.loc[(15, "points")].tier_bar, by.loc[(15, "points")].surprise_bar, by.loc[(15, "points")].hit_rate) == (5, 5, 0.5)
    assert dr.bars_reached("points", 70, 0.5, 4) is None and dr.bars_reached("points", 69, 1.0, 50) is None
    assert dr.bars_reached("assists", 60, 0.0, 3) == {"tier_bar": 3, "surprise_bar": None, "hit_rate": 0.0, "rarity": 1.0, "one_in": 1,
                                                      "rule": "tier", "band": "60+"}, "p = 0: the surprise bar is undefined"
    # Goals: the tier bar alone. A 40+ scorer on 4 dry games is not listed however high his hit rate; on 5 he is.
    assert dr.bars_reached("goals", 45, 0.9, 4) is None
    assert dr.bars_reached("goals", 45, 0.9, 5)["rule"] == "tier" and dr.bars_reached("goals", 45, 0.9, 5)["surprise_bar"] is None
    assert dr.bars_reached("goals", 30, 0.6, 9) is None and dr.bars_reached("goals", 30, 0.6, 10)["tier_bar"] == 10
    assert dr.bars_reached("goals", 24, 0.6, 20) is None


def test_one_in_is_computed_from_the_unrounded_figure_not_the_four_dp_rarity():
    # 0.25^7 = 1 / 16,384 rounds to a rarity of 0.0001, which would read as 1 in 10,000; 0.25^8 rounds to 0.0.
    seven, eight = dr.bars_reached("points", 70, 0.75, 7), dr.bars_reached("points", 70, 0.75, 8)
    assert (seven["rarity"], seven["one_in"]) == (0.0001, 16384) and (eight["rarity"], eight["one_in"]) == (0.0, 65536)
    assert dr.rarity_text(seven) == "1 in 16,384 for him" and dr.rarity_text(eight) == "1 in 65,536 for him"
    assert dr.bars_reached("points", 100, 0.9, 5)["one_in"] == 100000 and dr.one_in(0.9, 5) == 100000
    assert dr.one_in(1.0, 3) is None and dr.rarity_text(dr.bars_reached("points", 100, 1.0, 3)) == "never last season"
    assert dr.one_in(0.0, 4) == 1 and dr.one_in(0.5, 5) == 32 and dr.one_in(float("nan"), 2) == 1
    assert dr.one_in(0.9, 400) is None, "a float underflow is 0, not a division by zero"


def test_the_hit_rate_and_rarity_count_the_games_he_dressed_for_not_his_teams():
    rows = _games(21, "Iron Man", 20252026, "2025-10-10", 82, goals=1)  # the team's 82 games, through a teammate
    # 22 dressed for 60 of them: 15 without an assist, then 45 with one. p = 45/60 = 0.75, not 45/82 = 0.549.
    rows += _games(22, "Missed Games", 20252026, "2025-10-10", 15)
    rows += _games(22, "Missed Games", 20252026, "2025-10-25", 45, assists=1, offset=15)
    rows += _games(22, "Missed Games", 20262027, "2026-10-01", 4)
    q = dr.qualifiers_entering(pd.DataFrame(rows), DAY).set_index(["player_id", "market"]).loc[(22, "assists")]

    assert (q.hit_rate, q.surprise_bar, q.tier_bar, q.rule) == (0.75, 3, 4, "both"), "at 45/82 the surprise bar would be 4"
    assert q.rarity == 0.0039 and q.one_in == 256, "0.25^4; at 45/82 it would be 0.0413"
    prepared = dr.prepare_logs(pd.DataFrame(rows)).set_index(["player_id", "season_start"])
    assert (prepared.loc[(22, 2026), "prior_gp"].iloc[0], prepared.loc[(22, 2026), "prior_hit_assists"].iloc[0]) == (60, 45)
    assert prepared.loc[(22, 2026), "prior_assists"].iloc[0] == 45 and prepared.loc[(22, 2025), "prior_gp"].isna().all()


# -- the list ----------------------------------------------------------------


def test_the_qualifiers_are_the_evidences_own_drought_and_last_seasons_totals():
    q = dr.qualifiers_entering(make_logs(), DAY).set_index(["player_id", "market"])

    assert q.loc[(1, "assists"), "drought"] == 5 and q.loc[(1, "assists"), "last_season"] == 31
    assert q.loc[(3, "goals"), "drought"] == 5, "3 dry games last season + 2 this season"
    assert q.loc[(4, "points"), "drought"] == 5, "a preseason point is not a regular-season game"
    assert (2, "goals") not in q.index, "4 dry games is below the 25-39 band's bar of 10"
    assert tuple(q.loc[(3, "goals"), ["tier_bar", "rule", "band", "last_season"]]) == (5, "tier", "40+", 40)
    assert pd.isna(q.loc[(3, "goals"), "surprise_bar"]), "goals carry no surprise bar"
    assert not any(pid == 9 for pid, _ in q.index), "goalies never qualify"
    assert (1, "points") not in q.index and (1, "goals") not in q.index
    assert list(q.columns) == [c for c in dr.QUALIFIER_COLUMNS if c not in ("player_id", "market")]
    assert tuple(q.loc[(1, "assists"), ["tier_bar", "surprise_bar", "hit_rate", "rule", "band"]]) == (5, 5, 0.5, "both", "30-44")
    assert tuple(q.loc[(4, "assists"), ["tier_bar", "surprise_bar", "rule", "band"]]) == (3, 3, "both", "60+")


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
    assert drb.THRESHOLDS is dr.THRESHOLDS and drb.TIERS is dr.TIERS and drb.SURPRISE_LEVEL == dr.SURPRISE_LEVEL
    assert drb.tier_bar is dr.tier_bar and drb.surprise_bar is dr.surprise_bar and drb.band_label is dr.band_label
    assert drb.SHIPPED_BUCKET == dr.SHIPPED_BUCKET and drb.tier_bucket is dr.tier_bucket


def test_the_list_publishes_with_not_posted_prices_when_no_book_has_posted():
    result = build()

    names = [(r["player"], r["market"]) for r in result.rows]
    assert names == [("Test Scorer", "goals"), ("Assist Man", "assists")]
    assert all(r["american_odds"] is None and r["book"] == "" and not r["heavy_juice"] for r in result.rows)
    assert all(r["cell_record"] is None for r in result.rows), "no backtest records were given: none is guessed"
    assert dr.price_text(result.rows[0]) == "not posted"
    row = result.rows[1]
    assert (row["tier_bar"], row["surprise_bar"], row["hit_rate"], row["rarity"], row["one_in"], row["rule"], row["band"]) == (
        5, 5, 0.5, 0.0312, 32, "both", "30-44")


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
    assert not next(r for r in build([quote("Assist Man", "assists", -160, "X")]).rows if r["player"] == "Assist Man")["heavy_juice"]


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


def test_rows_sort_by_category_then_rarest_first_not_longest_drought():
    # 8: 60 assists in 75 games (p = 0.8), 5 dry: rarity 0.2^5 = 0.0003, the rarest streak on the list.
    # 10: 31 assists in 62 games (p = 0.5), 7 dry (the 8th game is dated DAY: tonight, not history): 0.5^7 = 0.0078.
    # Assist Man: p = 0.5, 5 dry: 0.0312. A longer drought at a lower hit rate sorts AFTER a shorter, rarer one.
    # 16: 36 assists in 82 games (p = 0.439), 6 dry: 0.561^6 = 0.03117, which is 0.0312 at 4 dp, the same rarity as
    #     Assist Man's 0.03125. At equal rarity the LONGER drought is listed first (the registered tiebreak).
    extra = (_games(8, "Short Rare", 20252026, "2025-10-10", 15)
             + _games(8, "Short Rare", 20252026, "2025-10-25", 60, assists=1, offset=15)
             + _games(8, "Short Rare", 20262027, "2026-10-01", 5)
             + _games(10, "Long Dry", 20252026, "2025-10-10", 31)
             + _games(10, "Long Dry", 20252026, "2025-11-10", 31, assists=1, offset=31)
             + _games(10, "Long Dry", 20262027, "2026-10-01", 8)
             + _games(16, "Tied Rare", 20252026, "2025-10-10", 46)
             + _games(16, "Tied Rare", 20252026, "2025-11-25", 36, assists=1, offset=46)
             + _games(16, "Tied Rare", 20262027, "2026-10-01", 6))
    result = build(logs=pd.concat([make_logs(), pd.DataFrame(extra)]), rosters={**ROSTERS, 8: "CGY", 10: "CGY", 16: "CGY"})

    assert [(r["market"], r["player"], r["drought"], r["rarity"]) for r in result.rows] == [
        ("goals", "Test Scorer", 5, 0.0189), ("assists", "Short Rare", 5, 0.0003),
        ("assists", "Long Dry", 7, 0.0078), ("assists", "Tied Rare", 6, 0.0312), ("assists", "Assist Man", 5, 0.0312)]
    assert [r["rule"] for r in result.rows] == ["tier"] + ["both"] * 4
    assert [r["one_in"] for r in result.rows] == [53, 3125, 128, 32, 32]


# -- the band's record, read from the backtest ------------------------------


def _bucket(market, bucket, *, window="card", season="both", wagers=184, roi=0.105, lo=-0.017, hi=0.239):
    return {"window": window, "market": market, "bucket": bucket, "season": season, "wagers": wagers,
            "roi": roi, "ci_low": lo, "ci_high": hi, "nights": 100, "hit_rate": 0.4, "implied": 0.4,
            "median_odds": 150, "units": 1.0, "mde": 0.1}


def test_the_cell_record_is_the_bands_card_window_bucket_and_null_when_the_file_lacks_it(tmp_path):
    (tmp_path / dr.BACKTEST_JSON).write_text(json.dumps({"buckets": [
        _bucket("assists", "TIER 30-44 @5"),
        _bucket("assists", "TIER 30-44 @5", season="2024", wagers=1), _bucket("assists", "TIER 30-44 @5", window="late", wagers=2),
        _bucket("assists", "TIER 30-44 ==5", wagers=3), _bucket("assists", "TIER 60+ @4", wagers=4),  # 60+ is @3 today: stale
        _bucket("points", "TIER 100+ @3", wagers=5, roi=-0.2, lo=-0.5, hi=0.1),
        _bucket("goals", "SHIPPED: either bar", wagers=6),
    ]}))

    records = dr.cell_records(tmp_path)

    assert records == {("assists", "30-44"): {"wagers": 184, "roi": 0.105, "ci_low": -0.017, "ci_high": 0.239},
                       ("points", "100+"): {"wagers": 5, "roi": -0.2, "ci_low": -0.5, "ci_high": 0.1}}
    assert dr.cell_records(tmp_path / "nowhere") == {} and dr.cell_records(None, fallback=tmp_path) == records
    (tmp_path / "broken" ).mkdir()
    (tmp_path / "broken" / dr.BACKTEST_JSON).write_text("{not json")
    assert dr.cell_records(tmp_path / "broken") == {}

    rows = {r["player"]: r for r in build(records=records).rows}
    assert rows["Assist Man"]["cell_record"] == {"wagers": 184, "roi": 0.105, "ci_low": -0.017, "ci_high": 0.239}
    assert rows["Test Scorer"]["cell_record"] is None, "goals 40+ has no bucket in this file"
    assert dr.record_text(rows["Assist Man"]) == "band 30-44 @5: +10.5% over 184 (95% -1.7% to +23.9%)"
    assert dr.record_text(rows["Test Scorer"]) == "no record"
    assert dr.tier_bucket("60+", 3) == "TIER 60+ @3" and dr.tier_bucket("60+", 3, exactly=True) == "TIER 60+ ==3"


def test_the_committed_backtest_carries_a_record_for_every_band():
    records = dr.cell_records(dr.Path(__file__).resolve().parents[1] / "data" / "outputs")

    assert set(records) == {(m, dr.band_label(m, floor)) for m, tiers in dr.TIERS.items() for floor, _ in tiers}
    assert all(r["wagers"] > 0 and r["ci_low"] <= r["roi"] <= r["ci_high"] for r in records.values())


# -- the card ----------------------------------------------------------------


def test_the_row_texts_read_the_bar_the_rarity_and_the_record():
    assert dr.bar_text({"rule": "both", "tier_bar": 5, "surprise_bar": 3}) == "5 (both)"
    assert dr.bar_text({"rule": "tier", "tier_bar": 3, "surprise_bar": 5}) == "3 (tier)"
    assert dr.bar_text({"rule": "surprise", "tier_bar": 5, "surprise_bar": 3}) == "3 (surprise)"
    assert dr.bar_text({"rule": "tier", "tier_bar": 3, "surprise_bar": None}) == "3 (tier)" and dr.bar_text({}) == "-"
    assert dr.bars_text({"tier_bar": 5, "surprise_bar": 3}) == "tier 5 / surprise 3"
    assert dr.bars_text({"tier_bar": 3, "surprise_bar": None}) == "tier 3 / surprise -"
    assert dr.rarity_text({"rarity": 0.0001, "hit_rate": 0.75, "one_in": 16384}) == "1 in 16,384 for him"
    assert dr.rarity_text({"rarity": 0.0, "hit_rate": 0.9, "one_in": 100000}) == "1 in 100,000 for him"
    assert dr.rarity_text({"rarity": 0.0312, "hit_rate": 0.5, "one_in": 32.0}) == "1 in 32 for him"
    # A row written before `one_in` existed reads N off the 4-dp rarity, and names the two ends that rounding reaches.
    assert dr.rarity_text({"rarity": 0.0039, "hit_rate": 0.75}) == "1 in 256 for him"
    assert dr.rarity_text({"rarity": 0.0312, "hit_rate": 0.5, "one_in": None}) == "1 in 32 for him"
    assert dr.rarity_text({"rarity": 0.0312, "hit_rate": 0.5, "one_in": float("nan")}) == "1 in 32 for him"
    assert dr.rarity_text({"rarity": 0.0, "hit_rate": 1.0}) == "never last season"
    assert dr.rarity_text({"rarity": 0.0, "hit_rate": 0.9}) == "rarer than 1 in 10,000 for him"
    assert dr.rarity_text({}) == "-"


def test_the_section_is_a_list_with_no_units_no_stakes_and_one_headline_line():
    card = GamedayCard(generated_at=NOW.isoformat(), card_generated=False, blockers=["Stale prices."])
    result = build([quote("Assist Man", "assists", 170, "DraftKings")],
                   records={("assists", "30-44"): {"wagers": 184, "roi": 0.105, "ci_low": -0.017, "ci_high": 0.239}})
    card.drought_built, card.drought_rows = True, result.rows
    card.drought_notes, card.drought_unresolved = ["a note"], ["Somebody (goals, A @ B)"]
    card.drought_headline = "HEADLINE LINE"

    text = render_card(card)
    section = text[text.index(f"## {dr.SECTION_TITLE}"):]
    section = section[: section.index("\n## ", 5)] if "\n## " in section[5:] else section

    assert dr.SECTION_TITLE == "Due List" and "Drought rule" not in text
    assert "Assist Man" in section and "+170" in section and "DraftKings" in section and "over 0.5" in section
    assert "| 5 (both) | tier 5 / surprise 5 | 1 in 32 for him | band 30-44 @5: +10.5% over 184 (95% -1.7% to +23.9%) |" in section
    assert "| Test Scorer |" in section and "| no record |" in section
    assert section.splitlines()[2] == "HEADLINE LINE"
    assert "| Units" not in section and "Tier" not in section and "Edge" not in section and "Stake" not in section
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


def test_the_headline_is_read_from_the_shipped_bucket_of_the_backtest_json(tmp_path):
    def bucket(m, roi, lo, hi, n, label=dr.SHIPPED_BUCKET):
        return {"window": "card", "market": m, "bucket": label, "season": "both", "roi": roi, "ci_low": lo, "ci_high": hi, "wagers": n}
    (tmp_path / dr.BACKTEST_JSON).write_text(json.dumps({"buckets": [
        bucket("points", -0.158, -0.359, 0.069, 69), bucket("goals", -0.043, -0.146, 0.049, 971),
        bucket("assists", -0.104, -0.171, -0.043, 1804),
        bucket("points", 0.9, 0.5, 0.99, 7, label="RULE: drought 5+")]}))

    line = dr.backtest_headline(tmp_path)

    assert "points -15.8% over 69 wagers" in line and "goals -4.3% over 971" in line and "assists -10.4% over 1804" in line
    assert "no category's interval sits above zero" in line and "\n" not in line and "either bar" in line
    assert "unavailable" in dr.backtest_headline(tmp_path / "nowhere")

    (tmp_path / dr.BACKTEST_JSON).write_text(json.dumps({"buckets": [
        bucket("points", -0.158, -0.359, 0.069, 69), bucket("goals", 0.12, 0.01, 0.2, 971),
        bucket("assists", -0.104, -0.171, -0.043, 1804)]}))
    assert "goals sits above zero" in dr.backtest_headline(tmp_path)


def test_the_committed_backtest_headline_reads_its_file():
    line = dr.backtest_headline(dr.Path(__file__).resolve().parents[1] / "data" / "outputs")

    # The committed JSON's SHIPPED bucket (either bar), card window, both seasons. The flat rule read 69 / 971 / 1804.
    assert "points -1.6% over 311 wagers" in line and "goals -7.0% over 1355 wagers" in line and "assists -8.4% over 2135 wagers" in line
    assert "unavailable" not in line and "no category's interval sits above zero" in line
