"""The weekly review's scorecard (Cooper, 2026-11-12): aggregates only, a
side is flagged only with enough wagers in both halves, and the staked
record adds up."""

from __future__ import annotations

import pandas as pd

from nhl_betting_lab import weekly_review as wr


def _listing(day, market, selection, line, units):
    return {"day": day, "market": market, "selection": selection, "line": line, "units": units}


def test_the_staked_record_counts_each_outcome_and_both_stakes():
    listings = [
        _listing("2026-11-01", "shots_on_goal", "under", 2.5, 0.5),
        _listing("2026-11-02", "shots_on_goal", "under", 1.5, 0.25),
        _listing("2026-11-09", "shots_on_goal", "under", 1.5, 0.25),
        _listing("2026-11-09", "moneyline", "home", None, 0.5),
    ]
    scored = [
        {"profit": 1.0, "outcome": "won"},
        {"profit": -1.0, "outcome": "lost"},
        {"profit": None, "outcome": "pending"},
        {"profit": 0.0, "outcome": "push"},
    ]
    season = {(r["market"], r["side"]): r for r in wr.staked_record(listings, scored)}
    sog = season[("shots_on_goal", "under")]
    assert (sog["won"], sog["lost"], sog["push"], sog["bets"]) == (1, 1, 0, 2)
    assert sog["units_flat"] == 0.0
    assert sog["units_card"] == 0.5 - 0.25
    assert season[("moneyline", "home")]["push"] == 1
    week = wr.staked_record(listings, scored, since="2026-11-05")
    assert [(r["market"], r["bets"]) for r in week] == [("moneyline", 1)]


def test_volume_is_counted_by_the_day_that_first_listed_it():
    listings = [
        _listing("2026-11-01", "goals", "over", 0.5, 0.25),
        _listing("2026-11-01", "goals", "over", 0.5, 0.5),
        _listing("2026-11-02", "hits", "under", 1.5, 0.25),
    ]
    volume = wr.staked_volume(listings)
    assert volume.to_dict("records") == [
        {"day": "2026-11-01", "best_bets": 2, "units": 0.75},
        {"day": "2026-11-02", "best_bets": 1, "units": 0.25},
    ]


def _population(days, units_first, units_second, n=25):
    rows = []
    half = len(days) // 2
    for i, day in enumerate(days):
        u = units_first if i < half else units_second
        for j in range(n):
            rows.append({"day": day, "game": f"{day}|g{j}", "market": "blocked_shots", "side": "under",
                         "american_odds": -110.0, "edge": 0.08, "units": u})
    return pd.DataFrame(rows)


def test_a_side_losing_in_both_halves_is_flagged():
    days = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]
    trends, split = wr.side_trends(_population(days, -1.0, -1.0))
    assert split == "2026-11-03"
    assert trends[0]["flag"] == "loses in both halves"
    assert trends[0]["games"] == 100


def test_a_side_split_across_the_halves_carries_no_flag():
    days = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]
    trends, _ = wr.side_trends(_population(days, -1.0, 1.0))
    assert trends[0]["flag"] == ""


def test_too_few_wagers_in_a_half_carries_no_flag():
    days = ["2026-11-01", "2026-11-02"]
    trends, _ = wr.side_trends(_population(days, -1.0, -1.0, n=5))
    assert trends[0]["flag"] == ""


def test_below_the_bar_or_outside_the_prices_is_not_counted():
    frame = _population(["2026-11-01", "2026-11-02"], 1.0, 1.0)
    frame.loc[:, "edge"] = 0.05
    assert wr.side_trends(frame)[0] == []
    frame.loc[:, "edge"] = 0.08
    frame.loc[:, "american_odds"] = -200.0
    assert wr.side_trends(frame)[0] == []


def test_one_game_gives_an_unbounded_interval():
    interval = wr.clustered_roi([1.0, -1.0], ["g", "g"])
    assert interval.games == 1 and interval.low == float("-inf")


def test_the_page_carries_no_price_line_book_or_player():
    listings = [_listing("2026-11-09", "shots_on_goal", "under", 2.5, 0.25)]
    scored = [{"profit": 0.91, "outcome": "won"}]
    population = _population(["2026-11-01", "2026-11-02"], 1.0, 1.0)
    review = wr.build_review(listings, scored, population, today="2026-11-12", last_week_from="2026-11-05")
    page = wr.render(review, generated="2026-11-12T00:00:00+00:00")
    assert "2.5" not in page and "-110" not in page
    assert "no demonstrated edge" in page
    assert "Weekly review" in page
