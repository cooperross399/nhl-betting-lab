"""What day an NHL game belongs to.

The provider timestamps a game by when the puck drops, in UTC. The NHL
timestamps it by the day it is played. For a North American evening those are
different days — a 19:10 Eastern face-off is 00:10 UTC the following morning —
and roughly three quarters of the schedule is an evening game.

Joining prices to results on the raw UTC date therefore drops most of the
season, and what survives is not a random sample: it is the afternoon games.
Weekend matinees, holiday specials and national-TV windows are a
systematically different set of fixtures from a Tuesday night in Winnipeg.

This module exists so that rule lives in one place. It was fixed once in the
slate sampler and not here, and the second copy quietly discarded 69% of every
price bought.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


#: The NHL's own calendar runs on Eastern time: a game's `gameDate` is the
#: date in America/New_York at face-off, whatever the venue's own timezone.
#: A 22:00 Pacific start in Vancouver is 01:00 Eastern the next day and the
#: NHL still calls it the previous day's game — which is why this is the
#: league's rule rather than the venue's.
LEAGUE_TIMEZONE = ZoneInfo("America/New_York")


def game_date(commence_time: object) -> str:
    """The NHL game date for a provider timestamp, as `YYYY-MM-DD`.

    An unparseable value falls back to its leading ten characters, which is
    the best available guess and is never silently better than the input.
    """
    text = str(commence_time or "").strip()
    if not text:
        return ""
    candidate = text.replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(candidate)
    except ValueError:
        return text[:10]
    if moment.tzinfo is None:
        # No timezone means no conversion is possible, and inventing one would
        # move a third of the schedule by a day.
        return text[:10]
    return moment.astimezone(LEAGUE_TIMEZONE).date().isoformat()
