"""Paths, season arithmetic, and the betting-discipline constants.

Season codes are derived from the date rather than written down. A hardcoded
list does not fail when it goes stale — it silently keeps fitting the model on
seasons that ended before the games it is pricing, and nothing in the output
says so.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MANUAL_DIR = DATA_DIR / "manual"
STAGING_DIR = DATA_DIR / "staging"
OUTPUTS_DIR = DATA_DIR / "outputs"

STAGING_PROVIDER_POLICY_PATH = MANUAL_DIR / "staging_provider_policy.json"
STAGING_PROVENANCE_PATH = STAGING_DIR / "staging_provenance.json"

#: How many seasons the models are fitted on, including the one being played.
SEASON_HISTORY_COUNT = 4

#: The month an NHL season starts counting from. Seasons run October to June,
#: so August is a safe boundary: no season is in progress, and the schedule for
#: the coming one is published.
SEASON_ROLLOVER_MONTH = 8

#: NHL API game types. 2 is the regular season; 3 is the playoffs. The models
#: are fitted on regular-season games only — playoff usage, deployment and
#: goaltending are a different distribution, and mixing them in would quietly
#: bias every per-player rate.
REGULAR_SEASON_GAME_TYPE = 2
PLAYOFF_GAME_TYPE = 3


def current_season_id(today: date | None = None) -> int:
    """The NHL's id for the season being played, e.g. 20262027."""
    moment = today or date.today()
    start_year = (
        moment.year if moment.month >= SEASON_ROLLOVER_MONTH else moment.year - 1
    )
    return start_year * 10000 + (start_year + 1)


def recent_season_ids(
    count: int = SEASON_HISTORY_COUNT, today: date | None = None
) -> list[int]:
    """The `count` most recent season ids, oldest first, ending with the
    season being played."""
    if count < 1:
        raise ValueError("A season history needs at least one season.")
    moment = today or date.today()
    start_year = (
        moment.year if moment.month >= SEASON_ROLLOVER_MONTH else moment.year - 1
    )
    first_year = start_year - (count - 1)
    return [
        year * 10000 + (year + 1) for year in range(first_year, start_year + 1)
    ]


def season_label(season_id: int) -> str:
    """`20262027` -> `2026-27`, for prose and report headings."""
    text = str(int(season_id))
    if len(text) != 8:
        raise ValueError(f"{season_id!r} is not an eight-digit NHL season id.")
    return f"{text[:4]}-{text[6:]}"


DEFAULT_SEASONS = recent_season_ids()
CURRENT_SEASON = DEFAULT_SEASONS[-1]

#: The Odds API sport key for the NHL.
ODDS_API_SPORT_KEY = "icehockey_nhl"

# Betting discipline, carried over from the EPL lab and confirmed for this one.

#: Cooper does not lay heavy juice. A price worse than this needs an explicit
#: human decision; the card will not select one on its own.
MAX_DEFAULT_JUICE = -160

#: Longest price the models are trusted to judge. Independent-Poisson tails
#: overstate rare counts, and the market's favourite-longshot bias prices them
#: short on top of that, so the two errors compound in the same direction.
MAX_DEFAULT_PRICE = 600

#: Minimum modelled edge for a team-market selection.
MIN_EDGE = 0.035

#: Minimum modelled edge for a player prop. Higher than the team bar on
#: purpose: the card is built hours before the lineup, the scratch list, and
#: the confirmed starting goalie are known, and books reprice on all three.
#: A prop edge must clear a higher bar, never a lower one.
MIN_PROP_EDGE = 0.06

BANKROLL_UNIT_DOLLARS = 25.0
