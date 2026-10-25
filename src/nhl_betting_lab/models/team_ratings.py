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

Since 2026-10-21 (Cooper: "i want it to affect the model") the file is built
on PostHockey's shooter-adjusted xG with GSAx(sh) (`xg_shooter_gsax`) and
carries each team's own home ice (`home_ice`, a log deviation from the
league's), which this module sets as `TeamModel.home_ice`. Priced on the
bought team markets the same day it did not pass the switch rule written
before the test (docs/team_variants_decision_rule.md); it ships on his word.
From the same date each team's attack and defence also carry its last-five
form (Cooper, 2026-10-21: factored in, not relied on), already multiplied in
by the builder and published beside them as `form`.
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

#: The first league day whose frozen team-market opinions were priced on
#: PostHockey's shooter-adjusted xG with GSAx(sh) and each team's own home ice
#: (Cooper, 2026-10-21: "i want it to affect the model"). The 2027-04-25
#: verdict on team markets covers these games only; rows frozen earlier are
#: set aside, as the xG switch set aside the goals rows.
TEAM_RATINGS_FROM = "2026-10-22"


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
    try:
        home_ice = {str(t): float(v) for t, v in (ratings.get("home_ice") or {}).items()}
    except (AttributeError, TypeError, ValueError) as exc:
        return "goals", f"{RATINGS_FILE} carries an unreadable home_ice ({exc})"
    for team, rate in teams.items():
        current = model.teams.get(team)
        model.teams[team] = TeamRates(
            team=team,
            games=current.games if current else 0,
            attack=float(rate["attack"]),
            defence=float(rate["defence"]),
        )
    model.home_ice = home_ice
    variant = str(ratings.get("variant", ""))
    stat = (
        "shooter-adjusted expected goals plus goaltending"
        if variant == "xg_shooter_gsax"
        else "expected goals plus goaltending and finishing"
    )
    home = f", each team's own home ice ({len(home_ice)} teams)" if home_ice else ""
    form = ratings.get("form")
    if isinstance(form, dict) and form:
        home += f", last-{ratings.get('form_games', 5)} form ({len(form)} teams)"
    return "xg", f"{stat}{home}, {len(teams)} teams, through {through}"


#: A starter's goaltending factor is read inside this range, so one hot or
#: cold record cannot dominate a team's defence.
STARTER_FACTOR_RANGE = (0.85, 1.15)


def apply_starters(
    model: TeamModel, processed: Path, starters: dict[str, int | None]
) -> list[str]:
    """Swap each team's goaltending for tonight's starter's, in place.

    Cooper, 2026-10-25 (PostHockey prices the listed goalie, not the
    team's goalies together). `starters` maps a club to its listed starter's
    NHL id, or None for a listed goalie this lab has no id for. The ratings
    file's `team_goalie` is the goaltending inside each team's defence; it is
    divided out and the starter's own factor (`goalies`, his GSAx(sh) record
    regressed toward `unseen_goalie`) multiplied in. A goalie with no record
    gets `unseen_goalie`, a little below average. A club with no listing, or a
    file without the goalie tables, is left as it was. Returns one line per
    club moved.
    """
    try:
        ratings = json.loads((Path(processed) / RATINGS_FILE).read_text(encoding="utf-8"))
        team_goalie = {str(k): float(v) for k, v in (ratings.get("team_goalie") or {}).items()}
        goalies = {str(k): float(v) for k, v in (ratings.get("goalies") or {}).items()}
        unseen = float(ratings.get("unseen_goalie", 1.0))
    except (OSError, ValueError, TypeError, AttributeError):
        return []
    if not team_goalie or not goalies:
        return []
    low, high = STARTER_FACTOR_RANGE
    moved = []
    for club, goalie in sorted(starters.items()):
        rate = model.teams.get(club)
        inside = team_goalie.get(club)
        if rate is None or not inside or inside <= 0:
            continue
        own = goalies.get(str(goalie), unseen) if goalie is not None else unseen
        own = min(high, max(low, own))
        model.teams[club] = TeamRates(
            team=rate.team, games=rate.games, attack=rate.attack,
            defence=rate.defence / inside * own,
        )
        moved.append(f"{club}: goaltending x{own / inside:.3f} for tonight's starter")
    return moved
