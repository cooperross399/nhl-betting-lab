"""Which teams played yesterday — the schedule fact the rest adjustment reads.

One definition, used by both the walk-forward sampler and the live card. The
back-to-back adjustment shipped because it won the price backtest, and "ship
exactly what was tested" cuts both ways: a card that priced rest differently
from the experiment that approved it — or, as it briefly did, not at all —
would be shipping an unmeasured policy under a measured one's name.

Rest derives from the schedule. A team's previous game is completed and dated
before the next one is priced, whichever window is being priced, so nothing
here can leak. Dates are league game dates (`season.game_date`), not UTC
calendar days: a 19:10 Eastern game and the next night's 22:00 Pacific game
are consecutive league days even when UTC says otherwise, and the UTC version
of this rule is the third join-vocabulary bug this repository fixed.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def last_played_dates(games: pd.DataFrame) -> dict[str, str]:
    """Each team's most recent completed game date, from the results table.

    The input is `team_games.csv` or any frame with `date`, `home_team`,
    `away_team`. Rows with unparseable dates are skipped rather than guessed.
    """
    latest: dict[str, str] = {}
    if games.empty:
        return latest
    ordered = games.sort_values("date")
    for row in ordered.itertuples():
        day = str(getattr(row, "date", ""))[:10]
        if len(day) != 10:
            continue
        for team in (str(row.home_team), str(row.away_team)):
            latest[team] = day
    return latest


def played_previous_day(
    last_played: Mapping[str, str], team: str, game_date: str
) -> bool:
    """Whether `team`'s most recent game was the league day before `game_date`.

    False when the team is unknown or either date is unusable — a missing
    schedule fact prices as rested, which is the common case and the
    conservative direction: the adjustment only ever *moves* a price when the
    schedule affirmatively says the side is tired.
    """
    previous = last_played.get(str(team))
    if not previous:
        return False
    try:
        gap = (pd.Timestamp(str(game_date)[:10]) - pd.Timestamp(previous)).days
    except (ValueError, TypeError):
        return False
    return gap == 1


#: Each club's home rink's standard-time offset from UTC, in hours. Only the
#: difference between two rinks is ever read, so daylight saving cancels.
RINK_UTC_OFFSET: dict[str, int] = {
    "BOS": -5, "BUF": -5, "CAR": -5, "CBJ": -5, "DET": -5, "FLA": -5,
    "MTL": -5, "NJD": -5, "NYI": -5, "NYR": -5, "OTT": -5, "PHI": -5,
    "PIT": -5, "TBL": -5, "TOR": -5, "WSH": -5,
    "CHI": -6, "DAL": -6, "MIN": -6, "NSH": -6, "STL": -6, "WPG": -6,
    "CGY": -7, "COL": -7, "EDM": -7, "UTA": -7, "ARI": -7,
    "ANA": -8, "LAK": -8, "SJS": -8, "SEA": -8, "VAN": -8, "VGK": -8,
}

#: Days since a club's last game at or above which it counts as rested, and
#: above which the gap is a season break rather than rest (Cooper,
#: 2026-10-21: rest days, travel and time zones).
LONG_REST_DAYS = 3
SEASON_BREAK_DAYS = 10
#: Time zones crossed since the last game's rink at or above which a club
#: counts as having travelled.
TRAVEL_ZONES = 2


def last_played_rinks(games: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """Each team's most recent completed game: (league date, home club)."""
    latest: dict[str, tuple[str, str]] = {}
    if games.empty:
        return latest
    for row in games.sort_values("date").itertuples():
        day = str(getattr(row, "date", ""))[:10]
        if len(day) != 10:
            continue
        for team in (str(row.home_team), str(row.away_team)):
            latest[team] = (day, str(row.home_team))
    return latest


def schedule_state(
    previous: tuple[str, str] | None, game_date: str, rink: str
) -> dict[str, bool]:
    """Whether a club is rested (`LONG_REST_DAYS`+, under a season break) and
    whether it crossed `TRAVEL_ZONES`+ time zones from its last game's rink
    to tonight's. Unknown facts read as neither, the direction that never
    moves a price."""
    state = {"long_rest": False, "travelled": False}
    if not previous:
        return state
    day, last_rink = previous
    try:
        gap = (pd.Timestamp(str(game_date)[:10]) - pd.Timestamp(day)).days
    except (ValueError, TypeError):
        return state
    state["long_rest"] = LONG_REST_DAYS <= gap <= SEASON_BREAK_DAYS
    here, there = RINK_UTC_OFFSET.get(str(rink)), RINK_UTC_OFFSET.get(str(last_rink))
    if here is not None and there is not None and gap <= SEASON_BREAK_DAYS:
        state["travelled"] = abs(here - there) >= TRAVEL_ZONES
    return state
