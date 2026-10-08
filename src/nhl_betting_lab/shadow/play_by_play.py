"""Fetch and read the NHL play-by-play feed.

`api-web.nhle.com/v1/gamecenter/{id}/play-by-play` is the same free, keyless
API the lab already fits on. It lists every shot attempt with its location,
its type, the shooter and the goalie in net, and every event carries a
`situationCode` giving the skaters and goalies on the ice. That is enough to
compute Corsi, Fenwick, expected goals, high-danger attempts, strength-state
ice time and goals saved above expected without any paid or licensed source.

What it cannot give, stated so nobody infers otherwise:

* **Ice time by strength is approximate.** The situation is only stamped on
  events, so a power play that expires between two events is credited to the
  power play until the next event. Over a season this is small; on one game
  it can be tens of seconds.
* **A blocked shot's coordinates are where it was blocked**, not where it was
  taken. Blocked attempts count toward Corsi and never toward xG or
  high-danger counts.
* **The shootout is excluded** everywhere. It is not hockey played at any
  strength, and every stat here describes play at a strength.

Caching follows `nhl_api.fetch_boxscore`: only a final game is written, and
a final game is never fetched again.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nhl_betting_lab.data.nhl_api import (
    API_BASE_URL,
    CacheEntry,
    NhlApiError,
    Requester,
    _cache_root,
    _default_requester,
    _get_json,
    _read_cache,
    _write_cache,
    game_is_final,
)

#: The play types that are shot attempts, and what each one is.
SHOT_EVENTS: dict[str, str] = {
    "goal": "goal",
    "shot-on-goal": "shot",
    "missed-shot": "miss",
    "blocked-shot": "block",
}

#: The goal line sits 89 feet from centre ice on an NHL rink.
GOAL_LINE_X = 89.0

#: An unblocked attempt within this many seconds of the same team's previous
#: attempt is a rebound. The public xG models use two to three seconds.
REBOUND_SECONDS = 3

#: Inside this distance and angle an attempt counts as high danger. This is
#: an approximation of the inner slot, not Natural Stat Trick's zone map,
#: which is drawn on the rink rather than stated as a rule.
HIGH_DANGER_FEET = 25.0
HIGH_DANGER_DEGREES = 45.0

STRENGTHS = ("5v5", "PP", "SH", "EV", "EA")

#: The previous event before an attempt, as the context expected-goals model
#: reads it (PostHockey's "prior-event context"). Every other play type is
#: "other"; an attempt with nothing earlier in its period reads "none".
PRIOR_EVENTS: dict[str, str] = {
    "faceoff": "faceoff",
    "hit": "hit",
    "giveaway": "giveaway",
    "takeaway": "takeaway",
    "goal": "attempt",
    "shot-on-goal": "attempt",
    "missed-shot": "attempt",
    "blocked-shot": "block",
}

#: An attempt this soon after a play outside the attacking zone is a rush.
RUSH_SECONDS = 4


def fetch_play_by_play(
    game_id: int,
    *,
    requester: Requester | None = None,
    raw_dir: Path | None = None,
) -> CacheEntry:
    """One game's play-by-play, from cache once the game is final."""
    identifier = int(game_id)
    if identifier <= 0:
        raise NhlApiError(f"{game_id!r} is not a usable NHL game id.")
    path = _cache_root(raw_dir) / "play_by_play" / f"{identifier}.json"
    cached = _read_cache(path)
    if cached is not None and game_is_final(cached):
        return CacheEntry(path=path, payload=cached, from_cache=True, complete=True)
    payload = _get_json(
        f"{API_BASE_URL}/v1/gamecenter/{identifier}/play-by-play",
        requester=requester or _default_requester,
    )
    complete = game_is_final(payload)
    if complete:
        _write_cache(path, payload)
    return CacheEntry(path=path, payload=payload, from_cache=False, complete=complete)


def clock_seconds(value: object) -> int | None:
    """`"MM:SS"` as seconds, or None when it is not a clock reading."""
    text = str(value or "").strip()
    minutes, _, seconds = text.partition(":")
    if not minutes.isdigit() or not seconds.isdigit():
        return None
    return int(minutes) * 60 + int(seconds)


def parse_situation(code: object) -> tuple[int, int, int, int] | None:
    """`situationCode` as (away goalie, away skaters, home skaters, home goalie)."""
    text = str(code or "").strip()
    if len(text) != 4 or not text.isdigit():
        return None
    away_goalie, away_skaters, home_skaters, home_goalie = (int(c) for c in text)
    return away_goalie, away_skaters, home_skaters, home_goalie


def strength_for(situation: tuple[int, int, int, int], *, home: bool) -> str:
    """The strength state from one side's point of view.

    `EA` is an extra attacker (own net empty); a shot *into* an empty net is
    flagged separately, since it says nothing about the shooter's strength.
    """
    away_goalie, away_skaters, home_skaters, home_goalie = situation
    own_goalie, own, opp = (
        (home_goalie, home_skaters, away_skaters)
        if home
        else (away_goalie, away_skaters, home_skaters)
    )
    if own_goalie == 0:
        return "EA"
    if own == opp == 5:
        return "5v5"
    if own > opp:
        return "PP"
    if own < opp:
        return "SH"
    return "EV"


def shot_geometry(
    x: float, y: float, *, shooter_home: bool, home_defending: str, zone: str
) -> tuple[float, float]:
    """Distance (feet) and angle (degrees off the centre line) to the net shot at."""
    side = str(home_defending or "").strip().lower()
    if side in {"left", "right"}:
        # The home goalie stands in the net on the side home defends, so home
        # shoots at the other one.
        home_shoots_right = side == "left"
        target = GOAL_LINE_X if home_shoots_right == shooter_home else -GOAL_LINE_X
    else:
        # No side recorded: an offensive-zone attempt was taken at the near
        # net, anything else at the far one.
        sign = 1.0 if x >= 0 else -1.0
        target = sign * GOAL_LINE_X if str(zone).upper() == "O" else -sign * GOAL_LINE_X
    dx = abs(target - x)
    distance = math.hypot(dx, y)
    angle = math.degrees(math.atan2(abs(y), dx)) if distance > 0 else 0.0
    return distance, angle


@dataclass
class GameEvents:
    """One game's shot attempts, strength-state ice time and penalties."""

    game_id: int
    home: str
    away: str
    shots: list[dict[str, Any]] = field(default_factory=list)
    #: (team, strength) -> seconds, both sides' points of view.
    seconds: dict[tuple[str, str], float] = field(default_factory=dict)
    #: team -> penalties taken.
    penalties: dict[str, int] = field(default_factory=dict)
    #: Attempts whose shooting team could not be told.
    unattributed: int = 0


def _team_abbrevs(payload: Mapping[str, Any]) -> dict[int, str]:
    teams: dict[int, str] = {}
    for key in ("homeTeam", "awayTeam"):
        block = payload.get(key) or {}
        try:
            teams[int(block.get("id"))] = str(block.get("abbrev") or "").strip()
        except (TypeError, ValueError):
            continue
    return teams


def _roster_teams(payload: Mapping[str, Any]) -> dict[int, int]:
    roster: dict[int, int] = {}
    for spot in payload.get("rosterSpots") or []:
        try:
            roster[int(spot.get("playerId"))] = int(spot.get("teamId"))
        except (TypeError, ValueError, AttributeError):
            continue
    return roster


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def game_events(payload: Mapping[str, Any]) -> GameEvents:
    """Every shot attempt, with geometry and strength, plus ice time by strength."""
    teams = _team_abbrevs(payload)
    home_id = _int_or_none((payload.get("homeTeam") or {}).get("id"))
    away_id = _int_or_none((payload.get("awayTeam") or {}).get("id"))
    home = teams.get(home_id, "") if home_id is not None else ""
    away = teams.get(away_id, "") if away_id is not None else ""
    result = GameEvents(game_id=int(payload.get("id") or 0), home=home, away=away)
    if not home or not away:
        return result
    roster = _roster_teams(payload)
    plays = [p for p in payload.get("plays") or [] if isinstance(p, Mapping)]

    def period_of(play: Mapping[str, Any]) -> tuple[int, str]:
        descriptor = play.get("periodDescriptor") or {}
        number = _int_or_none(descriptor.get("number")) or 0
        kind = str(descriptor.get("periodType") or "").upper()
        if not kind:
            kind = "SO" if number >= 5 and str(payload.get("gameType")) == "2" else "REG"
        return number, kind

    last_attempt: dict[str, tuple[int, int]] = {}
    score: dict[str, int] = {home: 0, away: 0}
    #: The play before this one in the same period: (period, clock, kind,
    #: owner, x, y, zone). Stamped on every attempt as its context.
    prior: tuple[int, int, str, str | None, float | None, float | None, str] | None = None
    for index, play in enumerate(plays):
        period, kind = period_of(play)
        if kind == "SO":
            continue
        clock = clock_seconds(play.get("timeInPeriod"))
        situation = parse_situation(play.get("situationCode"))
        before = prior if prior is not None and prior[0] == period else None
        if clock is not None:
            prior_details = play.get("details") or {}
            owner_id = _int_or_none(prior_details.get("eventOwnerTeamId"))
            prior = (
                period,
                clock,
                PRIOR_EVENTS.get(str(play.get("typeDescKey") or ""), "other"),
                teams.get(owner_id) if owner_id is not None else None,
                _float_or_none(prior_details.get("xCoord")),
                _float_or_none(prior_details.get("yCoord")),
                str(prior_details.get("zoneCode") or "").upper(),
            )

        # Ice time: the gap to the next event in the same period belongs to
        # this event's situation.
        if clock is not None and situation is not None:
            following = plays[index + 1] if index + 1 < len(plays) else None
            if following is not None and period_of(following)[0] == period:
                later = clock_seconds(following.get("timeInPeriod"))
                if later is not None and later > clock:
                    gap = float(later - clock)
                    for team, is_home in ((home, True), (away, False)):
                        key = (team, strength_for(situation, home=is_home))
                        result.seconds[key] = result.seconds.get(key, 0.0) + gap

        kind_key = str(play.get("typeDescKey") or "")
        details = play.get("details") or {}
        if kind_key == "penalty":
            if (_int_or_none(details.get("duration")) or 0) > 0:
                penalized = roster.get(_int_or_none(details.get("committedByPlayerId")) or -1)
                if penalized is None:
                    penalized = _int_or_none(details.get("eventOwnerTeamId"))
                abbrev = teams.get(penalized) if penalized is not None else None
                if abbrev:
                    result.penalties[abbrev] = result.penalties.get(abbrev, 0) + 1
            continue
        event = SHOT_EVENTS.get(kind_key)
        if event is None or situation is None or clock is None:
            continue

        shooter = _int_or_none(
            details.get("scoringPlayerId") if event == "goal" else details.get("shootingPlayerId")
        )
        team_id = roster.get(shooter) if shooter is not None else None
        if team_id is None and event != "block":
            # The event's owner is the shooting side for every attempt but a
            # block, where it may be the blocking side; never guess that one.
            team_id = _int_or_none(details.get("eventOwnerTeamId"))
        team = teams.get(team_id) if team_id is not None else None
        if team not in {home, away}:
            result.unattributed += 1
            continue
        is_home = team == home
        opponent = away if is_home else home
        x = details.get("xCoord")
        y = details.get("yCoord")
        try:
            distance, angle = shot_geometry(
                float(x),
                float(y),
                shooter_home=is_home,
                home_defending=str(play.get("homeTeamDefendingSide") or ""),
                zone=str(details.get("zoneCode") or ""),
            )
        except (TypeError, ValueError):
            distance, angle = float("nan"), float("nan")
        away_goalie, _, _, home_goalie = situation
        net_empty = (away_goalie if is_home else home_goalie) == 0
        game_seconds = (period - 1) * 1200 + clock
        previous = last_attempt.get(team)
        rebound = (
            event != "block"
            and previous is not None
            and previous[0] == period
            and 0 <= clock - previous[1] <= REBOUND_SECONDS
        )
        if event != "block":
            last_attempt[team] = (period, clock)
        context = prior_context(before, team=team, clock=clock, x=_float_or_none(x), y=_float_or_none(y))
        score_diff = score[team] - score[opponent]
        if event == "goal":
            score[team] += 1
        result.shots.append(
            {
                "game_id": result.game_id,
                "period": period,
                "game_seconds": game_seconds,
                "team": team,
                "opponent": opponent,
                "is_home": is_home,
                "shooter_id": shooter,
                "goalie_id": _int_or_none(details.get("goalieInNetId")),
                "event": event,
                "goal": event == "goal",
                "unblocked": event != "block",
                "on_goal": event in {"goal", "shot"},
                "distance": distance,
                "angle": angle,
                "shot_type": str(details.get("shotType") or "").strip().lower(),
                "strength": strength_for(situation, home=is_home),
                "empty_net": net_empty,
                "rebound": bool(rebound),
                "score_diff": score_diff,
                **context,
            }
        )
    return result


def _float_or_none(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def prior_context(
    before: tuple | None, *, team: str, clock: int, x: float | None, y: float | None
) -> dict[str, Any]:
    """What happened just before an attempt, from the shooting side's view.

    `prior_event` is the previous play in the period ("none" when there is
    none), `prior_same_team` whether the shooting side owned it, and
    `prior_seconds` and `prior_feet` how long ago and how far away it was
    (NaN when a clock or a location is missing). `rush` is an attempt within
    `RUSH_SECONDS` of a play in the neutral zone or the shooting side's own
    end; zone codes are from the owner's point of view, so an opponent's
    offensive-zone play is the shooter's own end.
    """
    if before is None:
        return {"prior_event": "none", "prior_same_team": False,
                "prior_seconds": float("nan"), "prior_feet": float("nan"), "rush": False}
    _, prior_clock, kind, owner, px, py, zone = before
    seconds = float(clock - prior_clock) if clock >= prior_clock else float("nan")
    feet = (
        math.hypot(x - px, y - py)
        if None not in (x, y, px, py)
        else float("nan")
    )
    same = owner == team
    outside = zone == "N" or (same and zone == "D") or (owner is not None and not same and zone == "O")
    rush = bool(outside and seconds == seconds and seconds <= RUSH_SECONDS)
    return {"prior_event": kind, "prior_same_team": bool(same), "prior_seconds": seconds,
            "prior_feet": feet, "rush": rush}


def is_high_danger(distance: float, angle: float) -> bool:
    if distance != distance or angle != angle:  # NaN
        return False
    return distance <= HIGH_DANGER_FEET and angle <= HIGH_DANGER_DEGREES
