"""Team ratings on expected goals and goaltending, read from a file.

Cooper decided on 2026-10-05 that the card's team markets are priced on the
same model as the public site: the fitted goals `TeamModel` keeps its league
rate, home advantage, overtime rate and back-to-back factors, and its attack
and defence become recent xG for and against, times a finishing factor and a
goaltending (GSAx) factor. That is the `xg_luck` stack of the shadow
measurement, which beat the goals ratings on every outcome column of the
first walk-forward run.

The ratings are built by `scripts/run_shadow_stats.py --tables-only` into
`data/processed/shadow_team_ratings.json` (`shadow.measurement.xg_team_ratings`).
This module only reads that file, so nothing on the card's path imports the
shadow package (tests/test_the_shadow_model_cannot_reach_the_card.py). Props
are untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.models.team_model import TeamModel, TeamRates

#: Beside the processed tables.
RATINGS_FILE = "shadow_team_ratings.json"

#: The first league day whose frozen team-market opinions were priced on these
#: ratings. Team-market ledger rows frozen before it were priced on goals, and
#: the forward report sets them aside (Cooper's "full switch", 2026-10-05:
#: the 2027-04-25 verdict on team markets covers xG games only).
XG_RATINGS_FROM = "2026-10-06"


def apply_xg_ratings(model: TeamModel, games: pd.DataFrame, processed: Path) -> tuple[str, str]:
    """Rate `model`'s teams on the xG ratings file, in place.

    Returns ("xg", detail) when applied, or ("goals", reason) when the file
    is missing, unreadable, or was not built through the latest
    regular-season game `games` holds; the model then keeps its goals
    ratings. A team the file does not rate keeps its goals rating.
    """
    path = Path(processed) / RATINGS_FILE
    try:
        ratings = json.loads(path.read_text(encoding="utf-8"))
        teams = ratings["teams"]
        through = str(ratings["last_game_date"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return "goals", f"{RATINGS_FILE} could not be read ({exc})"
    regular = games[pd.to_numeric(games["game_type"], errors="coerce") == 2]
    latest = str(regular["date"].max())[:10] if not regular.empty else ""
    if through != latest:
        return "goals", f"{RATINGS_FILE} runs through {through}, the game history through {latest}"
    for team, rate in teams.items():
        current = model.teams.get(team)
        model.teams[team] = TeamRates(
            team=team,
            games=current.games if current else 0,
            attack=float(rate["attack"]),
            defence=float(rate["defence"]),
        )
    return "xg", f"expected goals plus goaltending and finishing, {len(teams)} teams, through {through}"
