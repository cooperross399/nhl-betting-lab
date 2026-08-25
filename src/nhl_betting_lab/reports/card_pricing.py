"""Turn fitted models into the probability map the card consumes.

Kept separate from `gameday_card.py` on purpose. The card's job is gating and
presentation; this module's job is producing an opinion. Mixing them would
make it possible for a gate to be bypassed by a pricing path, which is exactly
the shape of bug that lets an unapproved market reach a selection.

The map is keyed by `(market, player_casefold, home, away, selection, line)`.
A key that is absent means *no modelled opinion* — which is different from a
probability of zero, and the card treats it as different.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from nhl_betting_lab.markets import MARKETS_BY_KEY
from nhl_betting_lab.models.calibration import PlattCalibration
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel


ProbabilityMap = dict[tuple, float]


def _line(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def price_props(
    prices: pd.DataFrame,
    model: PlayerPropsModel,
    *,
    corrections: Mapping[str, PlattCalibration] | None = None,
    team_of: Mapping[str, str] | None = None,
) -> tuple[ProbabilityMap, list[str]]:
    """Model probabilities for every prop row the model has an opinion on.

    Returns `(map, unresolved_players)`. An unresolved player is reported, not
    guessed at: a fuzzy name match produces a confident price for a bet nobody
    placed, and the row looks exactly like a correct one.
    """
    probabilities: ProbabilityMap = {}
    unresolved: set[str] = set()
    if prices.empty:
        return probabilities, []

    for row in prices.itertuples():
        market_key = str(getattr(row, "market", "")).strip()
        market = MARKETS_BY_KEY.get(market_key)
        if market is None or not market.is_prop:
            continue
        player = str(getattr(row, "player", "") or "").strip()
        line = _line(getattr(row, "line", None))
        if not player or line is None:
            continue
        player_id = model.resolve_player(player)
        if player_id is None:
            unresolved.add(player)
            continue

        home = str(getattr(row, "home_team", ""))
        away = str(getattr(row, "away_team", ""))
        # Which side the player is on decides his opponent and venue, and
        # getting it backwards would apply the wrong concession factor to
        # every prop in the game. The fitted model knows his team.
        rates = model.skaters.get(player_id) or model.goalies.get(player_id)
        team = (team_of or {}).get(player) or (rates.team if rates else "")
        if team and team == home:
            opponent, venue = away, "home"
        elif team and team == away:
            opponent, venue = home, "away"
        else:
            # The provider names teams differently from the boxscore, and a
            # guess here is a wrong opponent factor rather than a missing one.
            opponent, venue = "", "home"

        over = model.over_probability(
            player_id, market_key, line, opponent=opponent, venue=venue
        )
        if over is None:
            continue
        correction = (corrections or {}).get(market_key)
        if correction is not None:
            over = correction.apply(over)

        selection = str(getattr(row, "selection", "")).strip().lower()
        key = (market_key, player.casefold(), home, away, selection, line)
        if selection in {"over", "yes"}:
            probabilities[key] = over
        elif selection in {"under", "no"}:
            probabilities[key] = 1.0 - over

    return probabilities, sorted(unresolved)


def price_team_markets(
    prices: pd.DataFrame,
    model: TeamModel,
    *,
    team_names: Mapping[str, str] | None = None,
) -> ProbabilityMap:
    """Model probabilities for the team markets in a price frame."""
    probabilities: ProbabilityMap = {}
    if prices.empty:
        return probabilities
    lookup = dict(team_names or {})

    for row in prices.itertuples():
        market_key = str(getattr(row, "market", "")).strip()
        market = MARKETS_BY_KEY.get(market_key)
        if market is None or market.is_prop:
            continue
        home_label = str(getattr(row, "home_team", ""))
        away_label = str(getattr(row, "away_team", ""))
        home = lookup.get(home_label, home_label)
        away = lookup.get(away_label, away_label)
        selection = str(getattr(row, "selection", "")).strip().lower()
        line = _line(getattr(row, "line", None))
        key = (market_key, "", home_label, away_label, selection, line)

        if market_key == "moneyline":
            probabilities[key] = model.moneyline_probabilities(home, away).get(
                selection, 0.0
            )
        elif market_key == "puck_line":
            if line is None:
                continue
            sides = model.puck_line_probabilities(home, away, line=abs(line))
            # A negative line is the side laying the goals; a positive one is
            # the side taking them. Reading the sign wrong would flip every
            # puck-line price on the card.
            if selection == "home":
                probabilities[key] = sides["home_minus" if line < 0 else "home_plus"]
            elif selection == "away":
                probabilities[key] = sides["away_minus" if line < 0 else "away_plus"]
        elif market_key == "total_5_5":
            if line is None:
                continue
            totals = model.total_probabilities(home, away, line=line)
            if selection in totals:
                probabilities[key] = totals[selection]

    return probabilities
