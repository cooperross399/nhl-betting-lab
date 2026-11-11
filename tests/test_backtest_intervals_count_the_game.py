"""The props backtest and the team measurement count the game, not the wager.

The forward report moved to game-clustered intervals on 2026-09-29 (#258);
the props backtest and the team measurement kept `stats.roi_interval`, which
counts every wager after the best-price collapse as an independent draw. But
every rung, side and player of one game settle on one boxscore. In a null
where the bets of a game move together, the per-bet interval "excludes zero"
far more often than one time in twenty; the game-clustered one does not.

These reproduce the defect through the real `run_backtest` and
`measure_prices`, and pin the two conventions the switch relies on: the
interval is the old one exactly when every game holds one bet, and never
narrower; and the point estimate, the bets and the family do not move.
"""

from __future__ import annotations

import random

import pandas as pd
import pytest

from nhl_betting_lab.reports import player_props_backtest as bt
from nhl_betting_lab.reports import team_markets_measurement as tmm
from nhl_betting_lab.stats import roi_interval
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at

TEAMS = ["TOR", "BOS", "MTL", "OTT", "DET", "BUF", "TBL", "FLA"]
TEAM_NAMES = {team.lower(): team for team in TEAMS}


@pytest.fixture(autouse=True)
def no_checkout_data(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    point_default_data_dirs_at(
        monkeypatch, tmp_path_factory.mktemp("checkout_defaults")
    )


def _null_slate(rng: random.Random, games: int, players: int):
    """`games` games of `players` skaters each, every one bet over 2.5 shots
    at even money (fair: each game is a coin flip), and every player in a
    game landing on the same side of the line: a shared game shock."""
    samples, prices = [], []
    for game in range(games):
        day = f"2025-{1 + game // 28:02d}-{1 + game % 28:02d}"
        home, away = TEAMS[(2 * game) % 8], TEAMS[(2 * game + 1) % 8]
        actual = 5.0 if rng.random() < 0.5 else 0.0
        for index in range(players):
            player = f"Player {game}-{index}"
            samples.append(
                {
                    "date": day,
                    "game_id": game,
                    "player_id": 1000 * game + index,
                    "team": home if index % 2 == 0 else away,
                    "market": "shots_on_goal",
                    "player": player,
                    "mean": 4.6,  # P(over 2.5) ~ 0.84 against 0.50 implied
                    "dispersion_r": float("nan"),
                    "actual": actual,
                    "toi_seconds": 1200,
                }
            )
            prices.append(
                {
                    "date": day,
                    "commence_time": f"{day}T23:00:00Z",
                    "snapshot": f"{day}T13:30:00Z",
                    "home_team": home,
                    "away_team": away,
                    "market": "shots_on_goal",
                    "player": player,
                    "selection": "over",
                    "line": 2.5,
                    "american_odds": 100,
                    "book": "DraftKings",
                }
            )
    return pd.DataFrame(samples), pd.DataFrame(prices)


def _run(samples: pd.DataFrame, prices: pd.DataFrame) -> bt.BacktestReport:
    return bt.run_backtest(
        prices, samples, edge_threshold=0.06, team_names=TEAM_NAMES
    )


def test_a_null_with_a_game_shock_no_longer_reads_as_an_edge() -> None:
    rng = random.Random(20261110)
    runs, plain_hits, clustered_hits = 60, 0, 0
    for _ in range(runs):
        samples, prices = _null_slate(rng, games=40, players=6)
        report = _run(samples, prices)
        assert report.overall is not None and report.overall.bets == 240
        plain = roi_interval([bet.profit for bet in report.bets])
        plain_hits += not plain.includes_zero
        clustered_hits += not report.overall.includes_zero
        # Same point estimate, same bets: only the width moves.
        assert report.overall.roi == pytest.approx(plain.roi)
        assert report.overall.high - report.overall.low >= plain.high - plain.low
    # Six bets a game, perfectly correlated: the per-bet interval excludes
    # zero about half the time (P(|Z| > 1.96 / sqrt 6) ~ 0.42); the game's
    # about one time in twenty.
    assert plain_hits / runs > 0.25
    assert clustered_hits / runs < 0.15


def test_one_bet_a_game_is_the_old_interval_bit_for_bit() -> None:
    samples, prices = _null_slate(random.Random(7), games=50, players=1)
    report = _run(samples, prices)
    plain = roi_interval(
        [bet.profit for bet in report.bets],
        looks=report.looks,
        family=report.family,
    )
    assert report.overall.bets == 50
    assert (report.overall.low, report.overall.high) == (plain.low, plain.high)
    assert report.overall.adjusted_low == plain.adjusted_low
    assert report.overall.wins == sum(bet.won for bet in report.bets)


def test_every_bet_carries_the_game_it_settles_on() -> None:
    samples, prices = _null_slate(random.Random(3), games=3, players=4)
    report = _run(samples, prices)
    assert len({bet.game for bet in report.bets}) == 3
    assert all(len(bet.game) == 3 and bet.game[2] for bet in report.bets)


def test_the_family_correction_is_unchanged() -> None:
    samples, prices = _null_slate(random.Random(11), games=30, players=3)
    report = _run(samples, prices)
    assert report.looks == 2  # one market plus the overall figure
    assert report.overall.looks == report.looks
    assert all(item.looks == report.looks for item in report.by_market.values())


def _totals(games: int, lines: list[float], rng: random.Random):
    """Every game priced at each of `lines`, the model over on all of them,
    and one game's final score settling every line together."""
    samples, prices = [], []
    for game in range(games):
        day = f"2025-{1 + game // 28:02d}-{1 + game % 28:02d}"
        home, away = TEAMS[(2 * game) % 8], TEAMS[(2 * game + 1) % 8]
        over = rng.random() < 0.5
        for line in lines:
            samples.append(
                {
                    "date": day,
                    "game_id": game,
                    "home_team": home,
                    "away_team": away,
                    "market": "total_goals",
                    "selection": "over",
                    "line": line,
                    "model_probability": 0.6,
                    "outcome": over,
                    "push": False,
                    "home_goals": 5 if over else 1,
                    "away_goals": 4 if over else 1,
                    "regulation": True,
                }
            )
            prices.append(
                {
                    "date": day,
                    "home_team": home,
                    "away_team": away,
                    "market": "total_goals",
                    "selection": "over",
                    "line": line,
                    "american_odds": 100,
                }
            )
    return pd.DataFrame(samples), pd.DataFrame(prices)


def _team_interval(samples, prices):
    return tmm.measure_prices(
        prices,
        samples,
        market="total_goals",
        edge_threshold=0.035,
        team_names=TEAM_NAMES,
        looks=4,
    )


def test_team_lines_of_one_game_are_one_draw() -> None:
    samples, prices = _totals(40, [5.5, 6.5, 7.5], random.Random(5))
    interval = _team_interval(samples, prices)
    assert interval is not None and interval.bets == 120
    returns = [1.0 if o else -1.0 for o in samples["outcome"]]
    plain = roi_interval(returns, looks=4)
    assert interval.roi == pytest.approx(plain.roi)
    assert interval.looks == 4
    # Three perfectly correlated lines a game: the error is sqrt(3) wider.
    assert (interval.high - interval.low) == pytest.approx(
        (plain.high - plain.low) * (3 * 40 / 39) ** 0.5 * (119 / 120) ** 0.5,
        rel=0.05,
    )


def test_team_one_line_a_game_is_the_old_interval() -> None:
    samples, prices = _totals(40, [6.5], random.Random(5))
    interval = _team_interval(samples, prices)
    returns = [1.0 if o else -1.0 for o in samples["outcome"]]
    plain = roi_interval(returns, looks=4)
    assert (interval.low, interval.high) == (plain.low, plain.high)


def test_the_comparison_sets_the_per_bet_interval_beside_the_games() -> None:
    """`interval_comparison` (the 2026-11-11 rerun) reads the same bets two
    ways: per bet as before 2026-11-10, per game as the report prints. The
    per-game half is the report's own figure, the per-bet half is
    `roi_interval`, and nothing but bounds and counts is written."""
    samples, prices = _null_slate(random.Random(11), games=30, players=4)
    report = _run(samples, prices)
    comparison = bt.interval_comparison(report)
    overall = comparison["overall"]
    plain = roi_interval(
        [bet.profit for bet in report.bets],
        wins=sum(1 for bet in report.bets if bet.won),
        looks=report.looks,
        family=report.family,
    )
    assert overall["bets"] == 120 and overall["games"] == 30
    assert overall["roi"] == pytest.approx(report.overall.roi)
    assert (overall["per_bet"]["low"], overall["per_bet"]["high"]) == (
        plain.low,
        plain.high,
    )
    assert (overall["per_game"]["low"], overall["per_game"]["high"]) == (
        report.overall.low,
        report.overall.high,
    )
    market = comparison["by_market"]["shots_on_goal"]
    assert market["per_game"]["survives_correction"] == (
        report.by_market["shots_on_goal"].survives_correction
    )
    assert "player" not in str(comparison).lower()
    assert "american_odds" not in str(comparison)
