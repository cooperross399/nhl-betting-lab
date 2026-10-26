"""Where tonight's number comes from: each game's win chance, factor by factor.

Cooper, 2026-10-26 (PostHockey's game pages show what moved each line). The
card layers its factors on one `TeamModel` in a fixed order; this rebuilds
the home side's win chance with each layer added in turn, so the public
game page can show a waterfall that ends exactly at the card's own number:

1. **Team strength**: the xG ratings, with last-five form divided back out,
   on the league's home edge alone.
2. **Home ice**: each team's own home edge (`TeamModel.home_ice`).
3. **Last-five form**: the ratings as the card reads them.
4. **Rest and travel**: back-to-backs, long rest and time zones.
5. **Tonight's lineup**: the dressed skaters' attack and defence.
6. **Tonight's goalies**: the listed starters in place of the team's goalies.
7. **Referee crew**: scales both sides' goals, so it moves the total and
   barely the win chance.
8. **PostHockey blend**: half way to PostHockey's pre-game win probability.

Each step is a full repricing of the same model with one more layer on, so
the steps add up to the final number by construction. Line movement, which a
later run applies to each opinion after this, is not a model layer and is
not in it. Reads and computes only: the model it is given is not changed.
"""

from __future__ import annotations

import copy
from typing import Any

from nhl_betting_lab.models.team_model import TeamModel, TeamRates

#: (key, label) in the order the card applies them.
STEPS = (
    ("strength", "Team strength (xG ratings)"),
    ("home_ice", "Home ice"),
    ("form", "Last-five form"),
    ("rest", "Rest and travel"),
    ("lineup", "Tonight's lineup"),
    ("goalies", "Tonight's goalies"),
    ("referees", "Referee crew"),
    ("posthockey", "Second-opinion blend"),
)


def _without_form(teams: dict[str, TeamRates], form: dict[str, dict[str, float]]) -> dict[str, TeamRates]:
    out = {}
    for club, rate in teams.items():
        f = form.get(club) or {}
        attack = float(f.get("attack", 1.0)) or 1.0
        defence = float(f.get("defence", 1.0)) or 1.0
        out[club] = TeamRates(team=rate.team, games=rate.games, attack=rate.attack / attack,
                              defence=rate.defence / defence)
    return out


def breakdown(
    model: TeamModel,
    home: str,
    away: str,
    *,
    rated: dict[str, TeamRates],
    lineup: dict[str, TeamRates],
    goalies: dict[str, TeamRates],
    form: dict[str, dict[str, float]] | None = None,
    home_b2b: bool = False,
    away_b2b: bool = False,
    schedule_state: dict[str, dict[str, bool]] | None = None,
) -> list[dict[str, Any]]:
    """[{key, label, homeWin, homeGoals, awayGoals, delta}] for one game.

    `rated`, `lineup` and `goalies` are the model's team table after the
    ratings were applied, after tonight's lineup, and after tonight's
    starters; `model` holds everything else as the card set it. `delta` is
    the home win chance this step added, in probability (the first step's is
    its distance from a coin flip).
    """
    probe = copy.copy(model)
    probe.home_ice = {}
    probe.schedule_state = {}
    probe.game_factors = {}
    probe.pregame_weight = 0.0
    rest_flags = {"home_b2b": False, "away_b2b": False}
    out: list[dict[str, Any]] = []
    previous = 0.5
    for key, label in STEPS:
        if key == "strength":
            probe.teams = _without_form(rated, form or {})
        elif key == "home_ice":
            probe.home_ice = dict(model.home_ice)
        elif key == "form":
            probe.teams = dict(rated)
        elif key == "rest":
            probe.schedule_state = dict(schedule_state or {})
            rest_flags = {"home_b2b": bool(home_b2b), "away_b2b": bool(away_b2b)}
        elif key == "lineup":
            probe.teams = dict(lineup)
        elif key == "goalies":
            probe.teams = dict(goalies)
        elif key == "referees":
            probe.game_factors = dict(model.game_factors)
        elif key == "posthockey":
            probe.pregame_weight = model.pregame_weight
        eh, ea = probe.expected_goals(home, away, **rest_flags)
        win = probe.moneyline_probabilities(home, away, **rest_flags)["home"]
        out.append({
            "key": key, "label": label, "homeWin": round(float(win), 4),
            "homeGoals": round(float(eh), 3), "awayGoals": round(float(ea), 3),
            "delta": round(float(win) - previous, 4),
        })
        previous = float(win)
    return out


def slate_breakdowns(
    prices,
    model: TeamModel,
    *,
    team_names: dict[str, str],
    rated: dict[str, TeamRates],
    lineup: dict[str, TeamRates],
    goalies: dict[str, TeamRates],
    form: dict[str, dict[str, float]] | None = None,
    history=None,
    schedule_history=None,
) -> list[dict[str, Any]]:
    """One breakdown per game the moneyline was priced for, as the card priced it.

    Back-to-backs read `history` and rest and travel `schedule_history`,
    exactly as `card_pricing.price_team_markets` reads them, so the last step
    is the card's own moneyline.
    """
    from nhl_betting_lab.providers.team_names import resolve_team
    from nhl_betting_lab.rest import (
        last_played_dates,
        last_played_rinks,
        played_previous_day,
        schedule_state,
    )
    from nhl_betting_lab.season import row_game_date

    if prices is None or prices.empty:
        return []
    last = last_played_dates(history) if history is not None else {}
    games = schedule_history if schedule_history is not None else history
    rinks = last_played_rinks(games) if games is not None else {}
    saved = model.schedule_state
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    try:
        for row in prices[prices["market"].astype(str) == "moneyline"].itertuples():
            home_label, away_label = str(row.home_team), str(row.away_team)
            home = resolve_team(home_label, team_names) if team_names else home_label
            away = resolve_team(away_label, team_names) if team_names else away_label
            day = row_game_date(row)
            if home is None or away is None or (home, away, day) in seen:
                continue
            seen.add((home, away, day))
            state = {team: schedule_state(rinks.get(team), day, home) for team in (home, away)}
            model.schedule_state = state
            steps = breakdown(
                model, home, away, rated=rated, lineup=lineup, goalies=goalies, form=form,
                home_b2b=played_previous_day(last, home, day),
                away_b2b=played_previous_day(last, away, day),
                schedule_state=state,
            )
            out.append({"home_team": home_label, "away_team": away_label, "home": home,
                        "away": away, "date": day, "steps": steps})
    finally:
        model.schedule_state = saved
    return out


def ratings_form(processed) -> dict[str, dict[str, float]]:
    """Each team's last-five form from the ratings file; empty without it."""
    import json
    from pathlib import Path

    from nhl_betting_lab.models.team_ratings import RATINGS_FILE

    try:
        ratings = json.loads((Path(processed) / RATINGS_FILE).read_text(encoding="utf-8"))
        return {str(k): dict(v) for k, v in (ratings.get("form") or {}).items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}
