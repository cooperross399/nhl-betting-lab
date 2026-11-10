"""Stakes sized by closing-line value, and picks measured by the run that
first listed them (Cooper, 2026-11-10, "ALL")."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from nhl_betting_lab import clv_staking, pick_timing
from nhl_betting_lab.reports.gameday_card import TIER_UNITS


def _row(wagers, games, low, high, mean=0.01):
    return {"wagers": wagers, "games": games, "mean_clv": mean, "low": low, "high": high}


def test_the_rule_reads_the_interval_and_the_sample() -> None:
    assert clv_staking.classify(_row(2213, 300, 0.0266, 0.0439)) == (clv_staking.BEATS, 1.5)
    assert clv_staking.classify(_row(521, 100, -0.004, 0.02)) == (clv_staking.SPANS, 0.5)
    assert clv_staking.classify(_row(400, 100, -0.03, -0.001)) == (clv_staking.LOSES, 0.25)
    # Under the minimum sample nothing moves, however far from zero it reads.
    assert clv_staking.classify(_row(80, 40, 0.01, 0.05)) == (clv_staking.THIN, 1.0)
    assert clv_staking.classify(_row(500, 10, 0.01, 0.05)) == (clv_staking.THIN, 1.0)


def test_the_table_is_aggregate_and_built_from_the_bets_view() -> None:
    report = {"markets": {
        "shots_on_goal": {"bets": {"bets": 2213, "games": 300, "mean_clv_pct": 0.0353,
                                   "clv_low": 0.0266, "clv_high": 0.0439, "beat_rate": 0.6},
                          "opinions": {"bets": 99999}},
        "hits": {"bets": {"bets": 0}},
    }}
    table = clv_staking.market_table(report, generated="2026-11-10T14:00:00+00:00")
    assert set(table["markets"]) == {"shots_on_goal"}
    row = table["markets"]["shots_on_goal"]
    assert row["wagers"] == 2213 and row["multiplier"] == 1.5
    assert set(row) == {"wagers", "games", "mean_clv", "low", "high", "beat_rate", "verdict", "multiplier"}


def test_a_stale_or_missing_table_moves_nothing(tmp_path) -> None:
    table, note = clv_staking.load_table(tmp_path)
    assert table is None and "tier" in note
    now = datetime(2026, 11, 10, 14, tzinfo=timezone.utc)
    old = {"generated_at": (now - timedelta(days=9)).isoformat(), "markets": {"goals": _row(300, 50, 0.01, 0.02)}}
    (tmp_path / clv_staking.TABLE_FILENAME).write_text(json.dumps(old), encoding="utf-8")
    table, note = clv_staking.load_table(tmp_path, now=now)
    assert table is None and "days old" in note
    fresh = {**old, "generated_at": now.isoformat()}
    (tmp_path / clv_staking.TABLE_FILENAME).write_text(json.dumps(fresh), encoding="utf-8")
    table, _ = clv_staking.load_table(tmp_path, now=now)
    assert clv_staking.stake_multiplier("goals", table)[0] == 1.5
    assert clv_staking.stake_multiplier("moneyline", table) == (1.0, "")


def test_the_card_sizes_a_best_bet_by_its_market(tmp_path) -> None:
    from nhl_betting_lab.reports.card_pricing import selection_key
    from nhl_betting_lab.reports.gameday_card import BEST_BETS_SECTION, build_candidates

    prices = pd.DataFrame([{
        "date": "2026-11-10", "commence_time": "2026-11-11T00:00:00Z",
        "home_team": "Boston Bruins", "away_team": "Florida Panthers",
        "market": "total_goals", "player": "", "selection": "over", "line": 6.0,
        "american_odds": 104, "book": "Book",
    }])
    row = next(prices.itertuples())
    key = selection_key(row, market="total_goals", selection="over", line=6.0)
    probabilities = {key: 0.63}
    plain, _ = build_candidates(prices, probabilities)
    table = {"generated_at": "x", "markets": {"total_goals": _row(408, 80, -0.002, 0.016)}}
    sized, _ = build_candidates(prices, probabilities, clv_table=table)
    assert plain[0].section == sized[0].section == BEST_BETS_SECTION
    assert plain[0].suggested_units == TIER_UNITS[plain[0].tier]
    assert sized[0].suggested_units == round(plain[0].suggested_units * 0.5, 3)
    assert "no demonstrated CLV" in sized[0].stake_reason


CARD = """Selections changed.

# NHL gameday card

- Generated: {stamp}

## Best bets

| Game | Starts | Market | Selection | Model | Edge | Price | Bet down to | Book | Units |
|:-----|:-------|:-------|:----------|------:|-----:|------:|------------:|:-----|------:|
{rows}

## Leans

_None._
"""

ROW_A = "| Florida Panthers @ Boston Bruins | x | `shots_on_goal` | Sam Reinhart under 3.5 | 60% | +13% | -110 | -116 | A | 0.25 |"
ROW_B = "| Florida Panthers @ Boston Bruins | x | `puck_line` | home -1.5 | 44% | +10% | +188 | +182 | B | 0.25 |"


def test_a_pick_belongs_to_the_first_run_that_listed_it() -> None:
    cards = [
        CARD.format(stamp="2026-11-08T13:50:00+00:00", rows=ROW_A),
        CARD.format(stamp="2026-11-08T20:45:00+00:00", rows=ROW_A + "\n" + ROW_B),
        CARD.format(stamp="2026-11-08T22:40:00+00:00", rows=ROW_B),
    ]
    listings = pick_timing.first_listings_from_cards(cards)
    runs = {(item["market"], item["run"]) for item in listings}
    assert runs == {("shots_on_goal", "morning"), ("puck_line", "afternoon")}
    pl = [i for i in listings if i["market"] == "puck_line"][0]
    assert (pl["player"], pl["selection"], pl["line"], pl["price"]) == ("", "home", -1.5, 188.0)


def test_scoring_reads_the_ledger_and_reports_no_price() -> None:
    cards = [
        CARD.format(stamp="2026-11-08T13:50:00+00:00", rows=ROW_A),
        CARD.format(stamp="2026-11-08T20:45:00+00:00", rows=ROW_B),
    ]
    listings = pick_timing.first_listings_from_cards(cards)
    ledger = pd.DataFrame([
        {"snapshot_date": "2026-11-08", "home_team": "Boston Bruins", "away_team": "Florida Panthers",
         "market": "shots_on_goal", "player": "Sam Reinhart", "selection": "under", "line": 3.5,
         "outcome": "won"},
        {"snapshot_date": "2026-11-08", "home_team": "Boston Bruins", "away_team": "Florida Panthers",
         "market": "puck_line", "player": float("nan"), "selection": "home", "line": -1.5,
         "outcome": "lost"},
    ])
    scored = pick_timing.score(listings, ledger=ledger)
    by_run = {r["run"]: r for r in scored}
    assert by_run["morning"]["profit"] == 1 / 1.1 * 1.0 or abs(by_run["morning"]["profit"] - 100 / 110) < 1e-9
    assert by_run["afternoon"]["profit"] == -1.0
    summary = pick_timing.summarise(scored)
    text = pick_timing.render(summary, generated="now", has_closes=False)
    assert "Reinhart" not in text and "-110" not in text and "+188" not in text
    assert summary["late_trails"] is False


def test_late_picks_trail_only_on_a_clear_interval_with_enough_picks() -> None:
    def rows(run, value, n, offset):
        return [{"run": run, "market": "m", "game": (offset + i,), "outcome": "won",
                 "profit": value + (0.01 if i % 2 else -0.01), "clv": value} for i in range(n)]

    few = pick_timing.summarise(rows("morning", 0.05, 100, 0) + rows("afternoon", -0.05, 10, 1000))
    assert few["late_trails"] is False
    many = pick_timing.summarise(rows("morning", 0.05, 100, 0) + rows("afternoon", -0.05, 80, 1000))
    assert many["late_trails"] is True and "roi" in many["trails_on"]
