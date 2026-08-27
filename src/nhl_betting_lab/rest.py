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
