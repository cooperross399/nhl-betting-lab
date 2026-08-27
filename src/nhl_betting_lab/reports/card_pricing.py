"""Turn fitted models into the probability map the card consumes.

Kept separate from `gameday_card.py` on purpose. The card's job is gating and
presentation; this module's job is producing an opinion. Mixing them would
make it possible for a gate to be bypassed by a pricing path, which is exactly
the shape of bug that lets an unapproved market reach a selection.

The map is keyed by `(market, player_casefold, home, away, selection, line)`,
using the provider's own team strings so the card can join back to its price
rows. A key that is absent means *no modelled opinion* — which is different
from a probability of zero, and the card treats it as different.

Both entry points take a team-name map, because the provider says
`"Toronto Maple Leafs"` and every model here is keyed by `"TOR"`. Without it
the lookups miss silently and every game is priced league-average versus
league-average — plausible numbers, no error, nothing to notice. Unresolved
names are returned to the caller to report rather than guessed at.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from nhl_betting_lab.markets import MARKETS_BY_KEY
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.toi_corrections import CurrentCorrections
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers.team_names import resolve_team
from nhl_betting_lab.rest import last_played_dates, played_previous_day
from nhl_betting_lab.season import game_date


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
    corrections: CurrentCorrections | None = None,
    team_names: Mapping[str, str] | None = None,
) -> tuple[ProbabilityMap, list[str]]:
    """Model probabilities for every prop row the model has an opinion on.

    Returns `(map, unresolved)`. An unresolved player or team is reported, not
    guessed at: a fuzzy name match produces a confident price for a bet nobody
    placed, and the row looks exactly like a correct one.
    """
    probabilities: ProbabilityMap = {}
    unresolved: set[str] = set()
    lookup = dict(team_names or {})
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
        home_label = str(getattr(row, "home_team", ""))
        away_label = str(getattr(row, "away_team", ""))
        home = resolve_team(home_label, lookup) if lookup else home_label
        away = resolve_team(away_label, lookup) if lookup else away_label
        if home is None or away is None:
            # A game whose teams cannot be mapped produces no opinion at all.
            # Pricing it with a missing opponent factor would look like a
            # modelled row and be a league-average one.
            unresolved.update(
                label
                for label, resolved in (
                    (home_label, home),
                    (away_label, away),
                )
                if resolved is None and label
            )
            continue

        # Resolved against the two teams in this game, which recovers a name
        # two players share when they play for different clubs.
        player_id = model.resolve_player_in_game(player, home=home, away=away)
        if player_id is None:
            unresolved.add(player)
            continue

        # Which side the player is on decides his opponent and venue, and
        # getting it backwards applies the wrong concession factor to every
        # prop in the game. The fitted model knows his team.
        rates = model.skaters.get(player_id) or model.goalies.get(player_id)
        team = rates.team if rates else ""
        if team and team == home:
            opponent, venue = away, "home"
        elif team and team == away:
            opponent, venue = home, "away"
        else:
            # The player is priced, both teams mapped, and he is on neither.
            # That is a stale roster rather than a name problem, so it is
            # reported rather than priced against a guessed opponent.
            unresolved.add(player)
            continue

        over = model.over_probability(
            player_id, market_key, line, opponent=opponent, venue=venue
        )
        if over is None:
            continue
        if corrections is not None:
            # Bucketed on the player's *expected* ice time — the only ice
            # time a card can know — exactly as the winning experiment
            # variant was measured.
            over = corrections.apply(
                market_key,
                rates.expected_toi_seconds if rates else 0.0,
                over,
            )

        selection = str(getattr(row, "selection", "")).strip().lower()
        # Keyed on the provider's own labels, because that is what the card
        # will look the row up by.
        key = (
            market_key,
            player.casefold(),
            home_label,
            away_label,
            selection,
            line,
        )
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
    history: pd.DataFrame | None = None,
) -> tuple[ProbabilityMap, list[str]]:
    """Model probabilities for the team markets, and the names that did not map.

    `history` is the completed-games table, used for one thing: whether each
    side played yesterday. The back-to-back adjustment shipped because it won
    the price backtest *with rest included*, so a card pricing without it
    would be shipping an unmeasured policy under a measured one's name.
    Without history every side prices as rested, which is the conservative
    direction — the adjustment only moves a price when the schedule
    affirmatively says a side is tired.
    """
    probabilities: ProbabilityMap = {}
    unresolved: set[str] = set()
    if prices.empty:
        return probabilities, []
    lookup = dict(team_names or {})
    last_played = (
        last_played_dates(history) if history is not None else {}
    )

    for row in prices.itertuples():
        market_key = str(getattr(row, "market", "")).strip()
        market = MARKETS_BY_KEY.get(market_key)
        if market is None or market.is_prop:
            continue
        home_label = str(getattr(row, "home_team", ""))
        away_label = str(getattr(row, "away_team", ""))
        home = resolve_team(home_label, lookup) if lookup else home_label
        away = resolve_team(away_label, lookup) if lookup else away_label
        if home is None or away is None:
            unresolved.update(
                label
                for label, resolved in ((home_label, home), (away_label, away))
                if resolved is None and label
            )
            continue
        selection = str(getattr(row, "selection", "")).strip().lower()
        line = _line(getattr(row, "line", None))
        key = (market_key, "", home_label, away_label, selection, line)

        day = game_date(getattr(row, "commence_time", "") or getattr(row, "date", ""))
        rest = {
            "home_b2b": played_previous_day(last_played, home, day),
            "away_b2b": played_previous_day(last_played, away, day),
        }

        if market_key == "moneyline":
            probabilities[key] = model.moneyline_probabilities(
                home, away, **rest
            ).get(selection, 0.0)
        elif market_key == "puck_line":
            if line is None:
                continue
            sides = model.puck_line_probabilities(
                home, away, line=abs(line), **rest
            )
            # A negative line is the side laying the goals; a positive one is
            # the side taking them. Reading the sign wrong would flip every
            # puck-line price on the card.
            if selection == "home":
                probabilities[key] = sides["home_minus" if line < 0 else "home_plus"]
            elif selection == "away":
                probabilities[key] = sides["away_minus" if line < 0 else "away_plus"]
        elif market_key == "regulation_3_way":
            probabilities[key] = model.regulation_3_way_probabilities(
                home, away, **rest
            ).get(selection, 0.0)
        elif market_key == "total_goals":
            if line is None:
                continue
            totals = model.total_probabilities(home, away, line=line, **rest)
            if selection in totals:
                probabilities[key] = totals[selection]

    return probabilities, sorted(unresolved)
