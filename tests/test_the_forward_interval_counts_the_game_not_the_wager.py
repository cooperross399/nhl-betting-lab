"""The forward report's intervals count the game, not the wager.

The registered 2027-04-25 statistic (populations A and B) and the per-market
Bets intervals were `stats.roi_interval` over the collapsed wagers, and the
page said so: "each wager an independent draw". They are not independent.
The best-price collapse keys on the selection, line included, so every rung
of one player's alternate ladder is its own wager, and so are both sides of
every line and every player in the game — all settled on one boxscore. The
CLV and calibration reports were moved to game-clustered intervals for
exactly this; the forward report, the one docs/when_this_ends.md decides the
lab on, was not.

Found by sweep 4. A null simulation through the real `build_forward_report`
(90 games x 8 players x a 5-rung shots ladder at exactly fair prices, 3,600
wagers, floor met) read population B's corrected interval "excludes zero" in
18% of runs with independent players, and 59% with a modest shared game-pace
shock — against ~5% for an honest 95% interval.

These tests pin that every forward interval is now
`stats.clustered_mean_interval` on the game — (home, away, league game date),
the key settlement finds the game by — with the same family of looks; that
it is exactly the old interval when every game holds one wager and never
narrower than it otherwise; that the registered description ("excludes
zero") is read off the clustered bounds; and that the page no longer calls
each wager an independent draw.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.stats import clustered_mean_interval, roi_interval

NOW = datetime(2027, 4, 26, tzinfo=timezone.utc)
OPENER = datetime(2026, 10, 8, 23, tzinfo=timezone.utc)
A = "population_every_opinion"
B = "population_clears_edge_bar"
PLAYERS = 6
RUNGS = (0.5, 1.5, 2.5, 3.5, 4.5)


def _row(game: int, player: int, line: float, won: bool, *,
         market: str = "shots_on_goal", selection: str = "over",
         home: str | None = None, day: int | None = None) -> dict:
    """One settled even-money wager with an edge past both bars."""
    day = game if day is None else day
    commence = (OPENER + timedelta(days=day)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "snapshot_date": commence[:10], "commence_time": commence,
        "home_team": home or f"Home {game}", "away_team": f"Away {game}",
        "market": market, "player": f"Player {game}-{player}",
        "selection": selection, "line": line, "american_odds": 100.0,
        "book": "DK", "model_probability": 0.6, "edge": 0.10,
        "verdicts_in_force": "v", "settled_at": "2027-04-26T12:00:00Z",
        "outcome": "won" if won else "lost", "actual": 1.0,
        "profit_units": 1.0 if won else -1.0,
    }


def _ladder(games: int = 100, winners: int = 55) -> pd.DataFrame:
    """`games` games, each 6 players x a 5-rung ladder = 30 wagers that all
    win or all lose together: the game's shared result, at its extreme."""
    rows = [
        _row(game, player, line, game < winners)
        for game in range(games)
        for player in range(PLAYERS)
        for line in RUNGS
    ]
    return pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))


def _games(frame: pd.DataFrame) -> list[tuple]:
    return [
        (str(home), str(away), str(commence)[:10])
        for home, away, commence in zip(
            frame["home_team"], frame["away_team"], frame["commence_time"]
        )
    ]


def test_the_registered_statistic_is_clustered_on_the_game() -> None:
    """3,000 wagers in 100 games at 55-45: row by row +10% reads as
    excluding zero, and on the game it does not."""
    ledger = _ladder()
    payload = fe.build_forward_report(ledger, now=NOW)
    stat = payload["registered_statistic"][B]
    assert stat["settled_opinions"] == 3000 and stat["meets_floor"]

    profits = ledger["profit_units"].astype(float).tolist()
    expected = clustered_mean_interval(profits, _games(ledger), looks=1)
    naive = roi_interval(profits, looks=1)
    # The fixture must be one the old rule got wrong.
    assert naive.survives_correction, "row by row this reads excludes zero"
    assert not expected.survives_correction

    assert stat["low"] == expected.low and stat["high"] == expected.high
    assert stat["adjusted_low"] == expected.adjusted_low
    assert stat["adjusted_high"] == expected.adjusted_high
    assert stat["roi"] == naive.roi, "the point estimate does not move"
    assert stat["low"] < naive.low and stat["high"] > naive.high
    assert stat["survives_correction"] is False
    assert stat["corrected_interval"] == "spans_zero"
    # Population A is the same wagers here, and reads the same way.
    assert payload["registered_statistic"][A]["corrected_interval"] == "spans_zero"


def test_the_per_market_bets_interval_is_clustered_on_the_game() -> None:
    ledger = _ladder()
    entry = fe.build_forward_report(ledger, now=NOW)["markets"]["shots_on_goal"]
    expected = clustered_mean_interval(
        ledger["profit_units"].astype(float).tolist(), _games(ledger), looks=1
    )
    assert entry["bets"] == 3000
    assert (entry["low"], entry["high"]) == (expected.low, expected.high)
    assert entry["adjusted_low"] == expected.adjusted_low
    assert entry["includes_zero"] is True
    assert entry["survives_correction"] is False
    assert "includes zero" in entry["verdict"]


def test_the_family_correction_is_kept_on_the_clustered_error() -> None:
    """Two markets measured: both the registered statistic and each market's
    corrected bounds are the clustered interval corrected for two looks."""
    shots = _ladder(games=40, winners=22)
    goals = shots.assign(market="goals")
    ledger = pd.concat([shots, goals], ignore_index=True)
    payload = fe.build_forward_report(ledger, now=NOW)
    for market, subset in (("shots_on_goal", shots), ("goals", goals)):
        entry = payload["markets"][market]
        expected = clustered_mean_interval(
            subset["profit_units"].astype(float).tolist(), _games(subset),
            looks=2,
        )
        assert entry["looks"] == 2
        assert entry["adjusted_low"] == expected.adjusted_low
        assert entry["adjusted_high"] == expected.adjusted_high
    stat = payload["registered_statistic"][B]
    pooled = clustered_mean_interval(
        ledger["profit_units"].astype(float).tolist(), _games(ledger), looks=2
    )
    assert stat["looks"] == 2
    assert stat["adjusted_low"] == pooled.adjusted_low
    assert stat["adjusted_high"] == pooled.adjusted_high


def test_one_wager_per_game_is_the_old_interval_exactly() -> None:
    """Where no game holds two wagers the clustered interval IS the row
    interval, bit for bit — the change only widens where rows share a game."""
    rows = [_row(game, 0, 2.5, game % 5 < 3) for game in range(200)]
    ledger = pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))
    payload = fe.build_forward_report(ledger, now=NOW)
    naive = roi_interval(ledger["profit_units"].astype(float).tolist())
    stat = payload["registered_statistic"][B]
    entry = payload["markets"]["shots_on_goal"]
    for got in (stat, entry):
        assert (got["low"], got["high"]) == (naive.low, naive.high)
        assert (got["adjusted_low"], got["adjusted_high"]) == (
            naive.adjusted_low, naive.adjusted_high,
        )


def test_two_meetings_of_the_same_clubs_are_two_games() -> None:
    """The game is (home, away, league game date): the same two clubs on
    two nights are two games, not one cluster."""
    rows = [
        _row(game, 0, 2.5, game % 5 < 3, home="Boston Bruins", day=game)
        for game in range(200)
    ]
    for row in rows:
        row["away_team"] = "New York Rangers"
    ledger = pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))
    naive = roi_interval(ledger["profit_units"].astype(float).tolist())
    stat = fe.build_forward_report(ledger, now=NOW)["registered_statistic"][B]
    assert (stat["low"], stat["high"]) == (naive.low, naive.high)


def test_never_narrower_than_the_row_interval() -> None:
    """Both sides of one line move against each other, so the error on the
    game falls below the error on rows. The interval is held at the row one
    (Korn and Graubard), never narrower."""
    rows = []
    for game in range(150):
        over_wins = game % 2 == 0
        rows.append(_row(game, 0, 2.5, over_wins, selection="over"))
        rows.append(_row(game, 0, 2.5, not over_wins, selection="under"))
    ledger = pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))
    payload = fe.build_forward_report(ledger, now=NOW)
    naive = roi_interval(ledger["profit_units"].astype(float).tolist())
    stat = payload["registered_statistic"][B]
    assert stat["settled_opinions"] == 300
    assert (stat["low"], stat["high"]) == (naive.low, naive.high)
    entry = payload["markets"]["shots_on_goal"]
    assert (entry["low"], entry["high"]) == (naive.low, naive.high)


def test_the_page_says_the_game_is_the_draw() -> None:
    rendered = fe.render_forward_report(fe.build_forward_report(_ladder(), now=NOW))
    section = rendered.split("## Registered decision statistic", 1)[1]
    section = section.split("\n## ", 1)[0]
    assert "independent draw" not in rendered
    assert "clustered on the game" in section
    assert "never narrower" in section
    bets = rendered.split("## Accumulated so far", 1)[1].split("\n## ", 1)[0]
    assert "clustered on the game" in bets
