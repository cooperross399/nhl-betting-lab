"""The props best-price collapse merged the two games of a back-to-back.

`run_backtest` collapsed book quotes to one bet per wager with the key
`[date, market, player, line, selection]`, and `date` is the UTC commence date.
A 7pm ET face-off (00:00Z) and the next afternoon's game share one, so each
player's wager on a back-to-back collapsed to whichever game paid more, and
the other game's wager vanished before `priced_outcomes` counted it — the
reconciliation still printed "Accounted for: all of them". On the bought store
that is 4,196 late-window and 5,337 card-window wager keys spanning two
games. It also keyed the raw player string, so one player spelled two ways by
two books was two wagers. Found by the failure-shape audit (3/3 refuters).

What these tests hold: one player's line on two games sharing a UTC date is
two wagers, settled against their own games at their own best prices — with
the provider's event id, and without it — and one game quoted under two
spellings of one player is one wager.
"""

from __future__ import annotations

import pandas as pd

from nhl_betting_lab.reports.player_props_backtest import run_backtest


TEAM_MAP = {
    "carolina hurricanes": "CAR",
    "ottawa senators": "OTT",
    "st louis blues": "STL",
}

#: 7pm ET on 2024-11-16 is 00:00Z on the 17th; the next game is that afternoon.
EVENING = ("2024-11-17T00:00:00Z", "Ottawa Senators", "evt-ott")
AFTERNOON = ("2024-11-17T22:00:00Z", "St. Louis Blues", "evt-stl")


def _quote(game: tuple[str, str, str], book: str, odds: int,
           player: str = "Andrei Svechnikov") -> dict:
    commence, away, event = game
    return {
        "date": commence[:10], "commence_time": commence,
        "provider_event_id": event, "home_team": "Carolina Hurricanes",
        "away_team": away, "market": "shots_on_goal", "player": player,
        "selection": "over", "line": 3.5, "american_odds": odds, "book": book,
    }


def _samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": day, "market": "shots_on_goal", "player": "Andrei Svechnikov",
             "player_id": 8480830, "team": "CAR", "line": 3.5, "mean": 3.4,
             "dispersion_r": None, "actual": actual}
            for day, actual in (("2024-11-16", 2.0), ("2024-11-17", 5.0))
        ]
    )


def _measure(quotes: list[dict]):
    return run_backtest(pd.DataFrame(quotes), _samples(), edge_threshold=-1.0,
                        phase="", team_names=TEAM_MAP)


def test_two_games_on_one_utc_date_are_two_wagers() -> None:
    report = _measure([
        _quote(EVENING, "DraftKings", 140), _quote(EVENING, "FanDuel", 120),
        _quote(AFTERNOON, "DraftKings", 128), _quote(AFTERNOON, "FanDuel", 110),
    ])

    assert report.quotes_seen == 4 and report.wagers == 2
    assert sorted((bet.date, bet.american_odds) for bet in report.bets) == [
        ("2024-11-16", 140.0), ("2024-11-17", 128.0),
    ]


def test_without_an_event_id_the_game_is_its_date_and_teams() -> None:
    quotes = [
        _quote(EVENING, "DraftKings", 140), _quote(AFTERNOON, "DraftKings", 128),
    ]
    for quote in quotes:
        del quote["provider_event_id"]

    report = _measure(quotes)

    assert report.wagers == 2 and len(report.bets) == 2


def test_one_player_spelled_two_ways_is_one_wager() -> None:
    report = _measure([
        _quote(AFTERNOON, "ReBet", 110, player="Andrei Svechnikov"),
        _quote(AFTERNOON, "FanDuel", 128, player="Andrei Svéchnikov"),
    ])

    assert report.wagers == 1
    assert [bet.american_odds for bet in report.bets] == [128.0]


def test_the_same_matchup_on_consecutive_league_dates_is_two_wagers() -> None:
    """Two games between the same clubs in the same building, 7pm ET and the
    next afternoon: only the LEAGUE date separates them, so a key built on
    the UTC date and the teams would still merge them."""
    quotes = [
        _quote(("2024-11-17T00:00:00Z", "Ottawa Senators", ""), "DraftKings", 140),
        _quote(("2024-11-17T22:00:00Z", "Ottawa Senators", ""), "DraftKings", 128),
    ]
    for quote in quotes:
        del quote["provider_event_id"]

    report = _measure(quotes)

    assert report.wagers == 2
