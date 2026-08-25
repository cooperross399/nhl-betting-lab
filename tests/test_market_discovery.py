from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.reports import market_discovery as discovery


def _row(market: str, book: str, line: float | None, home: str, away: str = "BOS") -> dict:
    return {
        "date": "2026-10-08",
        "home_team": home,
        "away_team": away,
        "market": market,
        "book": book,
        "line": line,
        "selection": "over",
        "american_odds": -110,
    }


def test_an_absent_market_is_not_declared_unavailable() -> None:
    """The EPL `total_2_5` lesson, written into the verdict text."""
    frame = pd.DataFrame([_row("moneyline", "DraftKings", None, "TOR")])

    report = discovery.discover_coverage(frame, markets=["moneyline", "blocked_shots"])
    blocked = next(item for item in report.markets if item.market == "blocked_shots")

    assert blocked.offered is False
    assert "alternate ladders" in blocked.verdict()
    assert "EPL lab skipped" in blocked.verdict()


def test_a_book_covering_the_whole_slate_on_one_line_is_complete() -> None:
    frame = pd.DataFrame(
        [
            _row("total_goals", "DraftKings", 5.5, "TOR"),
            _row("total_goals", "DraftKings", 5.5, "EDM"),
        ]
    )

    report = discovery.discover_coverage(frame, markets=["total_goals"])

    assert report.markets[0].has_a_complete_line is True
    assert "cover the whole slate" in report.markets[0].verdict()


def test_a_market_split_across_books_is_incomplete_not_unavailable() -> None:
    """One book on each half of the slate is not one book on the slate."""
    frame = pd.DataFrame(
        [
            _row("total_goals", "DraftKings", 5.5, "TOR"),
            _row("total_goals", "FanDuel", 5.5, "EDM"),
        ]
    )

    report = discovery.discover_coverage(frame, markets=["total_goals"])

    assert report.markets[0].offered is True
    assert report.markets[0].has_a_complete_line is False
    assert "incomplete rather than unavailable" in report.markets[0].verdict()


def test_the_alternate_ladder_can_supply_a_complete_line_the_bulk_one_lacks() -> None:
    """Exactly the EPL failure, reproduced so the report catches it."""
    frame = pd.DataFrame(
        [
            # Bulk line: only one book, only one game.
            _row("total_goals", "WilliamHill", 5.5, "TOR"),
            # Alternate ladder: a book that covers everything at 6.5.
            _row("total_goals", "BetRivers", 6.5, "TOR"),
            _row("total_goals", "BetRivers", 6.5, "EDM"),
        ]
    )

    report = discovery.discover_coverage(frame, markets=["total_goals"])
    coverage = report.markets[0]

    assert coverage.has_a_complete_line is True
    assert any(item.book == "BetRivers" for item in coverage.complete_book_lines)


def test_the_widest_partial_line_is_named_so_the_gap_is_diagnosable() -> None:
    frame = pd.DataFrame(
        [
            _row("points", "DraftKings", 0.5, "TOR"),
            _row("points", "DraftKings", 0.5, "EDM"),
            _row("points", "FanDuel", 0.5, "TOR"),
            _row("moneyline", "DraftKings", None, "CGY"),
        ]
    )

    report = discovery.discover_coverage(frame, markets=["points"])

    assert "DraftKings" in report.markets[0].verdict()
    assert "2 of 3 games" in report.markets[0].verdict()


def test_lines_seen_are_reported_so_a_missing_line_is_visible() -> None:
    frame = pd.DataFrame(
        [
            _row("shots_on_goal", "DraftKings", line, "TOR")
            for line in (1.5, 2.5, 3.5, 4.5)
        ]
    )

    report = discovery.discover_coverage(frame, markets=["shots_on_goal"])

    assert report.markets[0].lines == (1.5, 2.5, 3.5, 4.5)


def test_an_empty_frame_reports_every_market_as_unoffered() -> None:
    report = discovery.discover_coverage(
        pd.DataFrame(columns=["market"]), markets=["moneyline", "points"]
    )

    assert report.slate_games == 0
    assert all(item.offered is False for item in report.markets)


def test_unmapped_provider_markets_are_listed_rather_than_discarded() -> None:
    report = discovery.discover_coverage(
        pd.DataFrame(columns=["market"]),
        markets=["moneyline"],
        unmapped_provider_markets=["team_totals", "player_power_play_points"],
    )

    rendered = discovery.render_discovery(report)

    assert "team_totals" in rendered
    assert "player_power_play_points" in rendered
    assert "worth adding is visible" in rendered


def test_the_report_says_it_decides_nothing() -> None:
    report = discovery.discover_coverage(pd.DataFrame(columns=["market"]))

    rendered = discovery.render_discovery(report)

    assert "decides nothing" in rendered
    assert "evidence for a human decision" in rendered


def test_the_report_carries_the_before_writing_a_market_off_warning() -> None:
    report = discovery.discover_coverage(pd.DataFrame(columns=["market"]))

    rendered = discovery.render_discovery(report)

    assert "Before writing a market off" in rendered
    assert "not** established as unavailable" in rendered


def test_the_share_is_a_fraction_of_the_slate() -> None:
    entry = discovery.LineCoverage(
        market="points", line=0.5, book="DK", games_priced=3, games_in_slate=4
    )

    assert entry.share == pytest.approx(0.75)
    assert entry.complete is False


def test_a_slate_of_zero_games_is_never_complete() -> None:
    entry = discovery.LineCoverage(
        market="points", line=0.5, book="DK", games_priced=0, games_in_slate=0
    )

    assert entry.complete is False
    assert entry.share == 0.0
