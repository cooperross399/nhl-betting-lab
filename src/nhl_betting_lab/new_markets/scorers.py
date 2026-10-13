"""First and last goal scorer: settlement, a shadow model, and its measurement.

The provider lists `player_goal_scorer_first` and `player_goal_scorer_last`.
`docs/periphery_markets_decision.md` deferred both because settlement needs
the order of goals, which the boxscore does not carry. The NHL's free
play-by-play does: every goal is an event with its period, its clock, its
scorer, the scoring side and the `situationCode` that says whether the net
was empty. This module reads that order, settles both markets on it, prices
them, and measures the prices walk-forward on outcomes.

**This is a shadow model.** Nothing on the card's path may import it
(`tests/test_the_shadow_model_cannot_reach_the_card.py`). Outcome
measurement can rule it out and never in; reaching the card needs a price
backtest and Cooper's sign-off.

## Settlement, as assumed

These are the usual US-book rules. They are this lab's assumptions, not any
one book's published terms; a book that differs settles differently.

* **First scorer:** the first goal of the game, overtime included. Shootout
  goals never count (a shootout "goal" is not a goal scored in play).
* **Last scorer:** the last goal of the game, overtime included, shootout
  excluded. **Empty-net goals count**, for both markets.
* **A player who does not dress is void** (stake returned). A player who
  dresses is action, whether or not he is on the ice for the goal. Some books
  also void a player who enters after the first goal; in the NHL every
  dressed player is available from the opening faceoff, so that rule is not
  modelled.
* **No goal in regulation or overtime** (a 0-0 game decided in the
  shootout): every player selection loses, and the "no goalscorer"
  selection (`NO_SCORER`) wins.
* A goal is credited to `scoringPlayerId` as the NHL records it; the NHL has
  no own goals, so the scorer is always on the scoring side.

## The model, in five lines

1. Each side's regulation expected goals come from the card's goals
   `TeamModel`, fitted walk-forward, scaled so the league total matches
   regulation goals in the play-by-play history.
2. Goals are a Poisson race: P(home scores first) = lh / (lh + la) x
   P(at least one goal), and P(no scorer) = P(0-0 after sixty) x
   P(a tied game reaches the shootout without an overtime goal), fitted on
   earlier games (every playoff overtime ends on a goal).
3. Last scorer is the same race, except that a fitted share of last goals
   are empty-netters, and those go to the side that leads after regulation
   (its regulation-win share from the same Poisson scorelines).
4. Inside a team, P(player) is proportional to his expected goals tonight
   from the card's `PlayerPropsModel` (shrunk per-60 goal rate x trailing-10
   ice time x opponent, venue and power-play factors). A skater the props
   model does not price takes his position's league per-60 rate x his own
   trailing ice time.
5. The candidates are the skaters who dressed, which is what settlement voids
   on. Empty-netters take the same within-team split as any goal (the late
   lineup on the ice is not modelled).

## What the measurement says, and cannot

`measure` scores each game's realised first and last scorer (or "no
scorer") by log-likelihood against three baselines on the same games: the
same team shares with every dressed skater equal (`uniform`), the same team
shares split by position-group league rates (`position`), and a coin-flip
team share with equal skaters (`naive`). It also buckets the per-player
probabilities for calibration. It cannot say anything about prices: that is
the price backtest this module does not run.

Normalising over the skaters who dressed uses the lineup, which is known at
warm-ups, not when a morning card is built. A book voids a player who does
not dress, so the market is priced over the same set, but a card built
before lineups would carry a little more uncertainty than this measurement.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

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
from nhl_betting_lab.models.player_props import PlayerPropsModel, position_group
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.stats import clustered_mean_interval, clustered_wilson_interval

#: The provider's market keys, and this module's names for them.
PROVIDER_KEYS: dict[str, str] = {
    "player_goal_scorer_first": "first",
    "player_goal_scorer_last": "last",
}
MARKETS = ("first", "last")

#: The selection that wins when no goal is scored in regulation or overtime.
NO_SCORER = "no_scorer"

REGULAR_SEASON = 2
PLAYOFFS = 3

#: Walk-forward cadence and the history a window needs before it is scored.
REFIT_DAYS = 14
MINIMUM_HISTORY_GAMES = 200

#: Probability floor in log-likelihoods, so one impossible outcome under a
#: baseline cannot dominate a mean.
PROBABILITY_FLOOR = 1e-6

#: Calibration buckets on a player's probability of scoring first (or last).
CALIBRATION_EDGES = (0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 1.0)

#: Used only before any history exists (never in a scored window, which
#: needs `MINIMUM_HISTORY_GAMES` of history): roughly the league's recent
#: shares, stated so a reader can see they are defaults and not fits.
DEFAULT_OT_GOAL_SHARE = 0.6
DEFAULT_EMPTY_NET_LAST_SHARE = 0.15


# -- the feed ------------------------------------------------------------


def fetch_play_by_play(
    game_id: int,
    *,
    requester: Requester | None = None,
    raw_dir: Path | None = None,
) -> CacheEntry:
    """One game's play-by-play, from cache once the game is final.

    The same cache file the shadow stats read (`data/raw/nhl/play_by_play`),
    so a game either runner fetched is never fetched again. Free and keyless;
    never an odds request.
    """
    identifier = int(game_id)
    if identifier <= 0:
        raise NhlApiError(f"{game_id!r} is not a usable NHL game id.")
    path = play_by_play_path(identifier, raw_dir)
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


def play_by_play_path(game_id: int, raw_dir: Path | None = None) -> Path:
    return _cache_root(raw_dir) / "play_by_play" / f"{int(game_id)}.json"


def read_cached_play_by_play(game_id: int, raw_dir: Path | None = None) -> Any | None:
    """The cached payload, or None. Never touches the network."""
    return _read_cache(play_by_play_path(game_id, raw_dir))


# -- goal order ----------------------------------------------------------


@dataclass(frozen=True)
class Goal:
    """One goal scored in play (never a shootout attempt)."""

    period: int
    period_type: str
    #: Seconds since the opening faceoff.
    game_seconds: int
    team: str
    scorer_id: int | None
    empty_net: bool


@dataclass(frozen=True)
class GoalOrder:
    """Every goal of one game in the order scored, and who dressed."""

    game_id: int
    game_type: int
    final: bool
    home: str
    away: str
    goals: tuple[Goal, ...]
    shootout: bool
    #: Every player on the game's roster (`rosterSpots`), team abbreviation
    #: by player id. Settlement voids anyone not here.
    dressed: Mapping[int, str] = field(default_factory=dict)

    @property
    def first(self) -> Goal | None:
        return self.goals[0] if self.goals else None

    @property
    def last(self) -> Goal | None:
        return self.goals[-1] if self.goals else None

    def regulation_goals(self) -> tuple[int, int]:
        home = sum(1 for g in self.goals if g.period <= 3 and g.team == self.home)
        away = sum(1 for g in self.goals if g.period <= 3 and g.team == self.away)
        return home, away

    def scorer(self, market: str) -> int | str | None:
        """The winning selection: a player id, `NO_SCORER`, or None (unknown scorer)."""
        goal = self.first if market == "first" else self.last if market == "last" else _bad(market)
        if goal is None:
            return NO_SCORER
        return goal.scorer_id


def _bad(market: str):
    raise KeyError(f"Unknown scorer market {market!r}; known: {MARKETS}")


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _clock_seconds(value: object) -> int | None:
    text = str(value or "").strip()
    minutes, _, seconds = text.partition(":")
    if not minutes.isdigit() or not seconds.isdigit():
        return None
    return int(minutes) * 60 + int(seconds)


def _period(play: Mapping[str, Any], game_type: int) -> tuple[int, str]:
    descriptor = play.get("periodDescriptor") or {}
    number = _int_or_none(descriptor.get("number")) or _int_or_none(play.get("period")) or 0
    kind = str(descriptor.get("periodType") or "").strip().upper()
    if not kind:
        if number <= 3:
            kind = "REG"
        elif number >= 5 and game_type == REGULAR_SEASON:
            kind = "SO"
        else:
            kind = "OT"
    return number, kind


def parse_goal_order(payload: Mapping[str, Any]) -> GoalOrder:
    """Every goal scored in play, in order, from one game's play-by-play.

    Order is period, then clock, then the feed's own `sortOrder` (its
    position in the list when absent). Shootout plays are dropped and only
    flag `shootout`. A goal is empty-net when the conceding side's goalie
    digit in `situationCode` is 0.
    """
    teams: dict[int, str] = {}
    for key in ("homeTeam", "awayTeam"):
        block = payload.get(key) or {}
        identifier = _int_or_none(block.get("id"))
        if identifier is not None:
            teams[identifier] = str(block.get("abbrev") or "").strip()
    home = teams.get(_int_or_none((payload.get("homeTeam") or {}).get("id")) or -1, "")
    away = teams.get(_int_or_none((payload.get("awayTeam") or {}).get("id")) or -1, "")
    game_type = _int_or_none(payload.get("gameType")) or 0
    dressed: dict[int, str] = {}
    for spot in payload.get("rosterSpots") or []:
        if not isinstance(spot, Mapping):
            continue
        pid = _int_or_none(spot.get("playerId"))
        tid = _int_or_none(spot.get("teamId"))
        if pid is not None and tid in teams:
            dressed[pid] = teams[tid]

    keyed: list[tuple[tuple[int, int, float], Goal]] = []
    shootout = False
    for index, play in enumerate(payload.get("plays") or []):
        if not isinstance(play, Mapping):
            continue
        number, kind = _period(play, game_type)
        if kind == "SO":
            shootout = True
            continue
        if str(play.get("typeDescKey") or "") != "goal":
            continue
        details = play.get("details") or {}
        scorer = _int_or_none(details.get("scoringPlayerId"))
        owner = _int_or_none(details.get("eventOwnerTeamId"))
        team = teams.get(owner) if owner is not None else None
        if team is None and scorer is not None:
            team = dressed.get(scorer)
        if team not in {home, away} or not team:
            team = ""
        clock = _clock_seconds(play.get("timeInPeriod"))
        code = str(play.get("situationCode") or "").strip()
        empty = False
        if len(code) == 4 and code.isdigit() and team:
            # (away goalie, away skaters, home skaters, home goalie)
            conceding_goalie = code[0] if team == home else code[3]
            empty = conceding_goalie == "0"
        sort = _int_or_none(play.get("sortOrder"))
        keyed.append(
            (
                (number, clock if clock is not None else 0, float(sort if sort is not None else index)),
                Goal(
                    period=number,
                    period_type=kind,
                    game_seconds=(number - 1) * 1200 + (clock or 0),
                    team=team,
                    scorer_id=scorer,
                    empty_net=empty,
                ),
            )
        )
    keyed.sort(key=lambda item: item[0])
    return GoalOrder(
        game_id=_int_or_none(payload.get("id")) or 0,
        game_type=game_type,
        final=game_is_final(payload),
        home=home,
        away=away,
        goals=tuple(goal for _, goal in keyed),
        shootout=shootout,
        dressed=dressed,
    )


# -- settlement ----------------------------------------------------------


def settle(order: GoalOrder, market: str, selection: int | str) -> str:
    """"win", "loss" or "void" for one selection, by the rules in the docstring.

    Refuses a game that is not final: a first goal can be settled early but a
    last goal cannot, and one rule for both is the safer one.
    """
    if market not in MARKETS:
        _bad(market)
    if not order.final:
        raise ValueError(f"Game {order.game_id} is not final; nothing settles on it yet.")
    winner = order.scorer(market)
    if selection == NO_SCORER:
        return "win" if winner == NO_SCORER else "loss"
    pid = _int_or_none(selection)
    if pid is None:
        raise ValueError(f"{selection!r} is neither a player id nor {NO_SCORER!r}.")
    if pid not in order.dressed:
        return "void"
    return "win" if winner == pid else "loss"


# -- league facts the model needs, fitted on earlier games ----------------


@dataclass(frozen=True)
class ScorerContext:
    """Shares the model reads, measured only on games before the window."""

    #: Of regular-season games tied after regulation, the share decided by an
    #: overtime goal rather than the shootout.
    ot_goal_share: float = DEFAULT_OT_GOAL_SHARE
    #: Of games with a goal, the share whose last goal went into an empty net.
    empty_net_last_share: float = DEFAULT_EMPTY_NET_LAST_SHARE
    #: Mean regulation goals per game in the history.
    regulation_goals_per_game: float | None = None
    games: int = 0


def fit_context(orders: Iterable[GoalOrder]) -> ScorerContext:
    tied = decided_in_ot = with_goal = empty_last = 0
    regulation_total = 0
    games = 0
    for order in orders:
        if not order.final or not order.home or not order.away:
            continue
        games += 1
        home, away = order.regulation_goals()
        regulation_total += home + away
        if order.game_type == REGULAR_SEASON and home == away:
            tied += 1
            if any(goal.period > 3 for goal in order.goals):
                decided_in_ot += 1
        if order.goals:
            with_goal += 1
            empty_last += int(order.goals[-1].empty_net)
    if games == 0:
        return ScorerContext()
    return ScorerContext(
        ot_goal_share=decided_in_ot / tied if tied else DEFAULT_OT_GOAL_SHARE,
        empty_net_last_share=empty_last / with_goal if with_goal else DEFAULT_EMPTY_NET_LAST_SHARE,
        regulation_goals_per_game=regulation_total / games,
        games=games,
    )


# -- the model -----------------------------------------------------------


def _poisson_pmf(mean: float, k: int) -> float:
    return math.exp(-mean + k * math.log(mean) - math.lgamma(k + 1)) if mean > 0 else float(k == 0)


def regulation_lead_share(home_mean: float, away_mean: float, max_goals: int = 20) -> float:
    """P(home leads after sixty | someone leads), independent Poisson scorelines."""
    home_pmf = [_poisson_pmf(home_mean, k) for k in range(max_goals + 1)]
    away_pmf = [_poisson_pmf(away_mean, k) for k in range(max_goals + 1)]
    home = away = 0.0
    for i, ph in enumerate(home_pmf):
        for j, pa in enumerate(away_pmf):
            if i > j:
                home += ph * pa
            elif j > i:
                away += ph * pa
    return home / (home + away) if home + away > 0 else 0.5


def team_probabilities(
    home_mean: float,
    away_mean: float,
    context: ScorerContext,
    *,
    game_type: int = REGULAR_SEASON,
) -> dict[str, dict[str, float]]:
    """{"first": {home, away, none}, "last": {home, away, none}}.

    `home_mean` / `away_mean` are regulation expected goals. A playoff game
    cannot end without a goal, so its "none" is zero.
    """
    home_mean = max(float(home_mean), 1e-9)
    away_mean = max(float(away_mean), 1e-9)
    total = home_mean + away_mean
    scoreless = math.exp(-total)
    no_ot_goal = 0.0 if game_type == PLAYOFFS else 1.0 - context.ot_goal_share
    none = scoreless * no_ot_goal
    share = home_mean / total
    first_home = (1.0 - none) * share
    lead = regulation_lead_share(home_mean, away_mean)
    f = context.empty_net_last_share
    last_share = (1.0 - f) * share + f * lead
    last_home = (1.0 - none) * last_share
    return {
        "first": {"home": first_home, "away": 1.0 - none - first_home, "none": none},
        "last": {"home": last_home, "away": 1.0 - none - last_home, "none": none},
    }


def player_probabilities(
    sides: Mapping[str, float],
    weights: Mapping[int, tuple[str, float]],
) -> dict[int | str, float]:
    """Spread each side's probability over its skaters by weight.

    `sides` is {"home", "away", "none"} from `team_probabilities`; `weights`
    maps player id to ("home" | "away", weight). A side whose weights sum to
    zero is split equally; a side with no skater listed keeps its mass off
    the board (the caller sees it as the probabilities summing short).
    """
    out: dict[int | str, float] = {NO_SCORER: float(sides.get("none", 0.0))}
    for side in ("home", "away"):
        members = [(pid, max(float(w), 0.0)) for pid, (s, w) in weights.items() if s == side]
        if not members:
            continue
        total = sum(w for _, w in members)
        for pid, w in members:
            out[pid] = sides[side] * (w / total if total > 0 else 1.0 / len(members))
    return out


# -- walk-forward measurement --------------------------------------------


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@dataclass
class Window:
    """What one refit knows: the two fitted models and the league shares."""

    team_model: TeamModel
    props_model: PlayerPropsModel | None
    context: ScorerContext
    #: League goals per 60 by position group ("F", "D").
    group_per60: dict[str, float]
    #: League goals per appearance by position group, for the position baseline.
    group_per_game: dict[str, float]
    #: Mean trailing ice time by group, for a skater with no history.
    group_toi: dict[str, float]
    #: Each skater's trailing-10 mean ice time before the window.
    trailing_toi: dict[int, float]


def _fit_window(
    team_history: pd.DataFrame,
    log_history: pd.DataFrame,
    order_history: list[GoalOrder],
) -> Window:
    team_model = TeamModel().fit(team_history)
    props: PlayerPropsModel | None
    try:
        props = PlayerPropsModel().fit(log_history)
    except (KeyError, ValueError):
        props = None
    skaters = log_history[log_history["role"].astype(str) == "skater"].copy()
    skaters["toi_seconds"] = pd.to_numeric(skaters["toi_seconds"], errors="coerce").fillna(0.0)
    skaters["goals"] = pd.to_numeric(skaters["goals"], errors="coerce").fillna(0.0)
    skaters = skaters[skaters["toi_seconds"] > 0]
    skaters["group"] = skaters["position"].map(position_group)
    per60: dict[str, float] = {}
    per_game: dict[str, float] = {}
    group_toi: dict[str, float] = {}
    for group, rows in skaters.groupby("group"):
        seconds = float(rows["toi_seconds"].sum())
        if seconds > 0:
            per60[str(group)] = float(rows["goals"].sum()) / seconds * 3600.0
            per_game[str(group)] = float(rows["goals"].mean())
            group_toi[str(group)] = float(rows["toi_seconds"].mean())
    ordered = skaters.sort_values(["date", "game_id"])
    trailing = (
        ordered.groupby("player_id")["toi_seconds"]
        .apply(lambda s: float(s.tail(PlayerPropsModel.RECENT_GAMES).mean()))
        .to_dict()
    )
    return Window(
        team_model=team_model,
        props_model=props,
        context=fit_context(order_history),
        group_per60=per60,
        group_per_game=per_game,
        group_toi=group_toi,
        trailing_toi={int(k): v for k, v in trailing.items()},
    )


def _skater_weight(window: Window, row: Any) -> tuple[float, bool]:
    """(expected goals tonight, whether the props model priced him)."""
    pid = int(row.player_id)
    if window.props_model is not None:
        try:
            value = window.props_model.expected_count(
                pid, "goals", opponent=str(row.opponent), venue=str(row.venue)
            )
        except KeyError:
            value = None
        if value is not None and value > 0 and math.isfinite(value):
            return float(value), True
    group = position_group(row.position)
    group = group if group in {"F", "D"} else "F"
    rate = window.group_per60.get(group, 0.0)
    toi = window.trailing_toi.get(pid) or window.group_toi.get(group, 0.0)
    return rate * toi / 3600.0, False


@dataclass
class Measurement:
    """Per game-market log-likelihoods and per player-market probabilities."""

    games: pd.DataFrame
    players: pd.DataFrame
    skipped: dict[str, int]
    windows: int = 0
    fallback_weights: int = 0
    weights: int = 0
    #: Only with `measure(selections=True)`: one row per (game, market,
    #: selection) the model prices, every dressed skater and `NO_SCORER`,
    #: with its probability and whether it won. Unlike `players`, a game is
    #: kept whoever scored (a goalie's goal, a scorer the logs miss), so the
    #: price backtest never chooses its games by their outcome.
    selections: pd.DataFrame = field(default_factory=pd.DataFrame)


BASELINES = ("uniform", "position", "naive")


def measure(
    team_games: pd.DataFrame,
    logs: pd.DataFrame,
    orders: Mapping[int, GoalOrder],
    *,
    refit_days: int = REFIT_DAYS,
    minimum_history: int = MINIMUM_HISTORY_GAMES,
    selections: bool = False,
) -> Measurement:
    """Score every regular-season game walk-forward, refitting every `refit_days`.

    A game is scored only when its play-by-play is cached and final, at
    least `minimum_history` earlier games with play-by-play exist, the logs
    list its dressed skaters, and its realised scorer is one of them (a
    goalie's goal, or a scorer missing from the logs, is counted and
    skipped).
    """
    skipped = {"no_play_by_play": 0, "scorer_not_a_listed_skater": 0, "no_skaters_listed": 0,
               "before_minimum_history": 0}
    games = team_games.copy()
    games["game_id"] = pd.to_numeric(games["game_id"], errors="coerce")
    games["_date"] = games["date"].map(_as_date)
    games = games.dropna(subset=["game_id", "_date", "home_goals", "away_goals"])
    games["game_id"] = games["game_id"].astype(int)
    games = games.sort_values(["_date", "game_id"])
    regular = games[pd.to_numeric(games["game_type"], errors="coerce") == REGULAR_SEASON]
    log_frame = logs.copy()
    log_frame["game_id"] = pd.to_numeric(log_frame["game_id"], errors="coerce")
    log_frame = log_frame.dropna(subset=["game_id"])
    log_frame["game_id"] = log_frame["game_id"].astype(int)
    log_frame["_date"] = log_frame["date"].map(_as_date)
    log_frame = log_frame.dropna(subset=["_date"])
    skaters_by_game = {
        gid: rows
        for gid, rows in log_frame[
            (log_frame["role"].astype(str) == "skater")
            & (pd.to_numeric(log_frame["toi_seconds"], errors="coerce").fillna(0) > 0)
        ].groupby("game_id")
    }
    date_of = dict(zip(games["game_id"], games["_date"]))

    game_rows: list[dict[str, Any]] = []
    player_rows: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    out = Measurement(games=pd.DataFrame(), players=pd.DataFrame(), skipped=skipped)
    if regular.empty:
        out.games, out.players = pd.DataFrame(game_rows), pd.DataFrame(player_rows)
        return out
    start = regular["_date"].iloc[0]
    end = regular["_date"].iloc[-1]
    window_start = start
    while window_start <= end:
        window_end = window_start + timedelta(days=refit_days)
        todo = regular[(regular["_date"] >= window_start) & (regular["_date"] < window_end)]
        window_start = window_end
        if todo.empty:
            continue
        cutoff = todo["_date"].iloc[0]
        history_orders = [
            o for gid, o in orders.items()
            if o.final and date_of.get(gid) is not None and date_of[gid] < cutoff
        ]
        if len(history_orders) < minimum_history:
            skipped["before_minimum_history"] += int(todo["game_id"].isin(list(orders)).sum())
            continue
        window = _fit_window(
            games[games["_date"] < cutoff],
            log_frame[log_frame["_date"] < cutoff].drop(columns=["_date"]),
            history_orders,
        )
        out.windows += 1
        context = window.context
        scale = (
            context.regulation_goals_per_game / window.team_model.league_goals_per_game
            if context.regulation_goals_per_game and window.team_model.league_goals_per_game
            else 1.0
        )
        naive_lam = (context.regulation_goals_per_game or window.team_model.league_goals_per_game) / 2.0
        naive_sides = team_probabilities(naive_lam, naive_lam, context)
        for game in todo.to_dict("records"):
            gid = int(game["game_id"])
            order = orders.get(gid)
            if order is None or not order.final:
                skipped["no_play_by_play"] += 1
                continue
            listed = skaters_by_game.get(gid)
            if listed is None or listed.empty:
                skipped["no_skaters_listed"] += 1
                continue
            home, away = str(game["home_team"]), str(game["away_team"])
            lh, la = window.team_model.expected_goals(home, away)
            sides = team_probabilities(lh * scale, la * scale, context)
            model_w: dict[int, tuple[str, float]] = {}
            uniform_w: dict[int, tuple[str, float]] = {}
            position_w: dict[int, tuple[str, float]] = {}
            for row in listed.itertuples():
                team = str(row.team)
                side = "home" if team == home else "away" if team == away else None
                if side is None:
                    continue
                pid = int(row.player_id)
                weight, modelled = _skater_weight(window, row)
                out.weights += 1
                out.fallback_weights += int(not modelled)
                model_w[pid] = (side, weight)
                uniform_w[pid] = (side, 1.0)
                group = position_group(row.position)
                position_w[pid] = (side, window.group_per_game.get(group if group in {"F", "D"} else "F", 0.0))
            for market in MARKETS:
                winner = order.scorer(market)
                if selections and winner is not None:
                    for selection, p in player_probabilities(sides[market], model_w).items():
                        selection_rows.append(
                            {
                                "game_id": gid,
                                "date": game["_date"].isoformat(),
                                "market": market,
                                "selection": str(selection),
                                "p": float(p),
                                "won": winner == selection,
                            }
                        )
                if winner != NO_SCORER and winner not in model_w:
                    skipped["scorer_not_a_listed_skater"] += 1
                    continue
                probs = {
                    "model": player_probabilities(sides[market], model_w),
                    "uniform": player_probabilities(sides[market], uniform_w),
                    "position": player_probabilities(sides[market], position_w),
                    "naive": player_probabilities(naive_sides[market], uniform_w),
                }
                row_out: dict[str, Any] = {
                    "game_id": gid,
                    "date": game["_date"].isoformat(),
                    "market": market,
                    "winner": str(winner),
                    "no_scorer": winner == NO_SCORER,
                    "home_mean": lh * scale,
                    "away_mean": la * scale,
                }
                for name, p in probs.items():
                    row_out[f"ll_{name}"] = math.log(max(p.get(winner, 0.0), PROBABILITY_FLOOR))
                team_outcome = (
                    "none" if winner == NO_SCORER
                    else "home" if model_w[int(winner)][0] == "home" else "away"
                )
                row_out["ll_team_model"] = math.log(max(sides[market][team_outcome], PROBABILITY_FLOOR))
                row_out["ll_team_naive"] = math.log(max(naive_sides[market][team_outcome], PROBABILITY_FLOOR))
                row_out["p_none"] = sides[market]["none"]
                game_rows.append(row_out)
                model_p = probs["model"]
                for pid in model_w:
                    player_rows.append(
                        {
                            "game_id": gid,
                            "market": market,
                            "player_id": pid,
                            "p": model_p.get(pid, 0.0),
                            "hit": int(winner == pid),
                        }
                    )
    out.games = pd.DataFrame(game_rows)
    out.players = pd.DataFrame(player_rows)
    if selections:
        out.selections = pd.DataFrame(
            selection_rows, columns=["game_id", "date", "market", "selection", "p", "won"]
        )
    return out


def summarise(result: Measurement) -> dict[str, Any]:
    """Log-likelihood differences with date-clustered intervals, and calibration."""
    summary: dict[str, Any] = {
        "windows": result.windows,
        "skipped": dict(result.skipped),
        "skater_weights": result.weights,
        "fallback_weights": result.fallback_weights,
        "markets": {},
    }
    if result.games.empty:
        return summary
    for market in MARKETS:
        frame = result.games[result.games["market"] == market]
        if frame.empty:
            continue
        entry: dict[str, Any] = {
            "games": int(len(frame)),
            "dates": int(frame["date"].nunique()),
            "no_scorer_games": int(frame["no_scorer"].sum()),
            "predicted_no_scorer": float(frame["p_none"].sum()),
            "log_loss": {name: float(-frame[f"ll_{name}"].mean()) for name in ("model", *BASELINES)},
            "against": {},
        }
        for name in BASELINES:
            entry["against"][name] = _difference(
                frame["ll_model"] - frame[f"ll_{name}"], frame["date"]
            )
        entry["team"] = {
            "log_loss_model": float(-frame["ll_team_model"].mean()),
            "log_loss_naive": float(-frame["ll_team_naive"].mean()),
            "difference": _difference(frame["ll_team_model"] - frame["ll_team_naive"], frame["date"]),
        }
        players = result.players[result.players["market"] == market]
        entry["calibration"] = calibration(players)
        summary["markets"][market] = entry
    return summary


def _difference(values: pd.Series, dates: pd.Series) -> dict[str, Any]:
    """Mean per game, x1000, with a 95% interval clustered on the date."""
    interval = clustered_mean_interval(list(values.astype(float)), list(dates))
    verdict = (
        "better" if interval.low > 0 else "worse" if interval.high < 0
        else "no demonstrated difference"
    )
    return {
        "per_1000": 1000 * interval.roi,
        "low": 1000 * interval.low,
        "high": 1000 * interval.high,
        "games": interval.bets,
        "verdict": verdict,
    }


def calibration(players: pd.DataFrame) -> list[dict[str, Any]]:
    """Predicted against observed, per bucket, with a game-clustered interval."""
    rows: list[dict[str, Any]] = []
    if players.empty:
        return rows
    edges = CALIBRATION_EDGES
    for low, high in zip(edges[:-1], edges[1:]):
        bucket = players[(players["p"] >= low) & (players["p"] < high)]
        if bucket.empty:
            continue
        clusters = bucket.groupby("game_id")["hit"].agg(["sum", "count"])
        lo, hi = clustered_wilson_interval(
            (int(s), int(c)) for s, c in zip(clusters["sum"], clusters["count"])
        )
        rows.append(
            {
                "bucket": f"{100 * low:.0f}-{100 * high:.0f}%",
                "player_games": int(len(bucket)),
                "games": int(bucket["game_id"].nunique()),
                "predicted": float(bucket["p"].mean()),
                "observed": float(bucket["hit"].mean()),
                "low": lo,
                "high": hi,
                "inside": bool(lo <= float(bucket["p"].mean()) <= hi),
            }
        )
    return rows


def validate_against_boxscores(
    team_games: pd.DataFrame, orders: Mapping[int, GoalOrder]
) -> dict[str, Any]:
    """Share of games whose parsed goals match the boxscore score per side.

    The boxscore credits the shootout winner one goal, which the play-by-play
    does not list as a goal in play; a game that went to a shootout matches
    when one side is exactly one short and that side won.
    """
    checked = matched = 0
    for row in team_games.itertuples():
        gid = _int_or_none(row.game_id)
        order = orders.get(gid) if gid is not None else None
        if order is None or not order.final:
            continue
        try:
            home_box, away_box = int(row.home_goals), int(row.away_goals)
        except (TypeError, ValueError):
            continue
        checked += 1
        home = sum(1 for g in order.goals if g.team == order.home)
        away = sum(1 for g in order.goals if g.team == order.away)
        if order.shootout:
            ok = (home + 1, away) == (home_box, away_box) or (home, away + 1) == (home_box, away_box)
        else:
            ok = (home, away) == (home_box, away_box)
        matched += int(ok)
    return {"games": checked, "match": matched / checked if checked else 1.0}
