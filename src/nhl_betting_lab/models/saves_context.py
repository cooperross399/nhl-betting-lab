"""Game context for goalie saves: the favourite, home ice, and both teams.

Cooper asked on 2026-10-20 for the saves projection to "factor in the team
that is favored to win and home ice advantage". The props model prices saves
as the goalie's own shots against per sixty, times the opponent's shot
factor, times his save rate (`PlayerPropsModel.expected_saves`). Three things
a game carries are invisible to that:

* **Who is favoured.** The better team spends more of the night with the
  puck, so its goalie faces fewer shots. Score effects pull the other way
  late (a trailing team shoots more), which is why this is measured rather
  than assumed. The market's de-vigged moneyline is the input: it is known
  before the card, it carries the lineup news the model lacks, and the card
  stages it every day.
* **Home ice and the rink.** Home teams outshoot visitors slightly, and the
  shot counts themselves are recorded by the home building's scorers, some
  of whom count more generously than others. Both are read from the
  completed-games table: a home flag, and each arena's total shots against
  the same clubs' totals elsewhere.
* **Tonight's two teams, not the goalie's career.** The goalie's shots
  against per sixty is his own history, which follows him across clubs and
  is never shrunk. The current club's shots allowed and the opponent's shots
  generated, recency-weighted, describe tonight.

`fit_poisson` recalibrates the props model's own mean on these features
(log-linear, so each enters as a multiplier). The coefficients the card uses
are fitted by `scripts/run_saves_model_study.py` on two seasons of starts and
written into `SHIPPED`; nothing here is fitted on the card's own night.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from nhl_betting_lab.models.value import american_to_implied
from nhl_betting_lab.season import game_date


#: Recency for the team shot rates: a game's weight halves every this many of
#: the club's games. Fixed before the study, not tuned on it.
TEAM_HALF_LIFE_GAMES = 20

#: Games of league-average evidence each team rate is shrunk toward.
TEAM_PRIOR_GAMES = 10

#: Rink factor: games' weight halves every this many of the arena's games,
#: and the factor is shrunk with this many games of "no bias".
ARENA_HALF_LIFE_GAMES = 82
ARENA_PRIOR_GAMES = 30

#: Every feature a context model may use, in a fixed order.
FEATURES: tuple[str, ...] = (
    "log_base",
    "home",
    "logit_win",
    "log_team_sa",
    "log_opp_sf",
    "log_arena",
    "log_toi_ratio",
)


@dataclass(frozen=True)
class TeamShotRates:
    """Each club's recent shots for and against, relative to the league."""

    shots_for: dict[str, float]
    shots_against: dict[str, float]
    arena: dict[str, float]
    league_per_team_game: float

    def team_sa(self, team: str) -> float:
        return self.shots_against.get(str(team), 1.0)

    def opp_sf(self, team: str) -> float:
        return self.shots_for.get(str(team), 1.0)

    def arena_factor(self, home: str) -> float:
        return self.arena.get(str(home), 1.0)


def _weighted_mean(values: list[float], half_life: float, prior: float, centre: float) -> float:
    if not values:
        return centre
    n = len(values)
    weights = [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]
    total = sum(w * v for w, v in zip(weights, values))
    return (total + prior * centre) / (sum(weights) + prior)


def team_shot_rates(games: pd.DataFrame) -> TeamShotRates:
    """Recent shots for/against per club, and each arena's counting bias.

    Reads `home_team`, `away_team`, `home_shots`, `away_shots` and `date`
    from the completed-games table. A caller passes only games that finished
    before the night being priced.
    """
    empty = TeamShotRates({}, {}, {}, 30.0)
    needed = {"date", "home_team", "away_team", "home_shots", "away_shots"}
    if games is None or games.empty or not needed <= set(games.columns):
        return empty
    frame = games.copy()
    frame["home_shots"] = pd.to_numeric(frame["home_shots"], errors="coerce")
    frame["away_shots"] = pd.to_numeric(frame["away_shots"], errors="coerce")
    frame = frame.dropna(subset=["home_shots", "away_shots"])
    frame = frame[(frame["home_shots"] > 0) & (frame["away_shots"] > 0)]
    if frame.empty:
        return empty
    frame = frame.sort_values([c for c in ("date", "game_id") if c in frame.columns])
    league = float((frame["home_shots"].sum() + frame["away_shots"].sum()) / (2 * len(frame)))

    sf: dict[str, list[float]] = {}
    sa: dict[str, list[float]] = {}
    at_home: dict[str, list[float]] = {}
    on_road: dict[str, list[float]] = {}
    for home, away, hs, aws in zip(
        frame["home_team"].astype(str),
        frame["away_team"].astype(str),
        frame["home_shots"].astype(float),
        frame["away_shots"].astype(float),
    ):
        sf.setdefault(home, []).append(hs)
        sa.setdefault(home, []).append(aws)
        sf.setdefault(away, []).append(aws)
        sa.setdefault(away, []).append(hs)
        at_home.setdefault(home, []).append(hs + aws)
        on_road.setdefault(away, []).append(hs + aws)

    shots_for = {
        t: _weighted_mean(v, TEAM_HALF_LIFE_GAMES, TEAM_PRIOR_GAMES, league) / league
        for t, v in sf.items()
    }
    shots_against = {
        t: _weighted_mean(v, TEAM_HALF_LIFE_GAMES, TEAM_PRIOR_GAMES, league) / league
        for t, v in sa.items()
    }
    arena: dict[str, float] = {}
    for team, totals in at_home.items():
        road = on_road.get(team, [])
        if not road:
            continue
        home_mean = _weighted_mean(totals, ARENA_HALF_LIFE_GAMES, 0.0, 2 * league)
        road_mean = _weighted_mean(road, ARENA_HALF_LIFE_GAMES, 0.0, 2 * league)
        raw = home_mean / road_mean if road_mean > 0 else 1.0
        weight = len(totals) / (len(totals) + ARENA_PRIOR_GAMES)
        arena[team] = 1.0 + weight * (raw - 1.0)
    return TeamShotRates(shots_for, shots_against, arena, league)


def home_win_probabilities(
    prices: pd.DataFrame,
    resolve: Mapping[str, str] | None = None,
) -> dict[tuple[str, str, str], float]:
    """(league date, home, away) -> the market's de-vigged home win chance.

    Each book's two moneyline prices at one moment are de-vigged in
    proportion, and the game's figure is the median across every such pair.
    A row priced at or after face-off is ignored when the frame says when it
    was priced (`snapshot`, else `fetched_at`). Teams are mapped through
    `resolve` (provider name -> abbreviation) when it is given; a name that
    does not map drops the game rather than guessing.
    """
    if prices is None or prices.empty or "market" not in prices.columns:
        return {}
    rows = prices[prices["market"].astype(str) == "moneyline"].copy()
    if rows.empty:
        return {}
    rows["selection"] = rows["selection"].astype(str).str.strip().str.lower()
    rows = rows[rows["selection"].isin(["home", "away"])]
    moment_col = next((c for c in ("snapshot", "fetched_at") if c in rows.columns), None)
    if moment_col and "commence_time" in rows.columns:
        at = pd.to_datetime(rows[moment_col], errors="coerce", utc=True)
        start = pd.to_datetime(rows["commence_time"], errors="coerce", utc=True)
        rows = rows[(at < start) | at.isna() | start.isna()]
    if rows.empty:
        return {}
    rows["implied"] = [american_to_implied(v) for v in rows["american_odds"]]
    rows = rows[rows["implied"] > 0]
    when = rows["commence_time"] if "commence_time" in rows.columns else rows.get("date")
    rows["_day"] = [game_date(v) for v in when]
    rows["_moment"] = rows[moment_col].astype(str) if moment_col else ""
    rows["_book"] = rows["book"].astype(str) if "book" in rows.columns else ""
    wide = rows.pivot_table(
        index=["_day", "home_team", "away_team", "_book", "_moment"],
        columns="selection",
        values="implied",
        aggfunc="max",
    ).dropna()
    if wide.empty or not {"home", "away"} <= set(wide.columns):
        return {}
    wide["p"] = wide["home"] / (wide["home"] + wide["away"])
    medians = wide["p"].groupby(level=[0, 1, 2]).median()
    out: dict[tuple[str, str, str], float] = {}
    for (day, home, away), p in medians.items():
        if resolve is not None:
            h = resolve.get(str(home))
            a = resolve.get(str(away))
            if h is None or a is None:
                continue
        else:
            h, a = str(home), str(away)
        out[(str(day), h, a)] = float(p)
    return out


def logit(p: float | None) -> float:
    """log(p / (1 - p)), clipped; an unknown chance is an even one (0.0)."""
    if p is None or not math.isfinite(float(p)):
        return 0.0
    value = min(max(float(p), 0.02), 0.98)
    return math.log(value / (1.0 - value))


def feature_row(
    *,
    base_mean: float,
    venue: str,
    win_probability: float | None,
    team: str,
    opponent: str,
    rates: TeamShotRates | None,
    toi_ratio: float = 1.0,
) -> dict[str, float]:
    """Every feature for one goalie start, as `FEATURES` names them."""
    home_team = team if venue == "home" else opponent
    if rates is None:
        team_sa = opp_sf = arena = 1.0
    else:
        team_sa = rates.team_sa(team)
        opp_sf = rates.opp_sf(opponent)
        arena = rates.arena_factor(home_team)
    return {
        "log_base": math.log(max(float(base_mean), 1e-6)),
        "home": 1.0 if venue == "home" else 0.0,
        "logit_win": logit(win_probability),
        "log_team_sa": math.log(max(team_sa, 1e-6)),
        "log_opp_sf": math.log(max(opp_sf, 1e-6)),
        "log_arena": math.log(max(arena, 1e-6)),
        "log_toi_ratio": math.log(max(float(toi_ratio), 1e-6)),
    }


def fit_poisson(X: np.ndarray, y: np.ndarray, *, iterations: int = 60, ridge: float = 1e-6) -> np.ndarray:
    """Poisson regression by iteratively reweighted least squares.

    The first column must be the intercept. Starts from the identity on
    `log_base` when that is the second column, which is where a
    recalibration of an already-sensible mean begins.
    """
    beta = np.zeros(X.shape[1])
    beta[0] = 0.0
    if X.shape[1] > 1:
        beta[1] = 1.0
    for _ in range(iterations):
        eta = np.clip(X @ beta, -10, 10)
        mu = np.exp(eta)
        z = eta + (y - mu) / mu
        weighted = X * mu[:, None]
        gram = X.T @ weighted + ridge * np.eye(X.shape[1])
        new = np.linalg.solve(gram, weighted.T @ z)
        if np.max(np.abs(new - beta)) < 1e-9:
            beta = new
            break
        beta = new
    return beta


def residual_dispersion(y: Iterable[float], mu: Iterable[float]) -> float | None:
    """Negative-binomial r from residuals: 1/r = sum((y-mu)^2 - mu) / sum(mu^2).

    None when the residuals are no more spread than a Poisson's.
    """
    ys = np.asarray(list(y), dtype=float)
    ms = np.asarray(list(mu), dtype=float)
    if len(ys) < 30:
        return None
    excess = float(np.sum((ys - ms) ** 2 - ms))
    scale = float(np.sum(ms**2))
    if excess <= 0 or scale <= 0:
        return None
    return scale / excess


@dataclass(frozen=True)
class SavesContext:
    """A fitted recalibration: log mean = intercept + sum(coef x feature)."""

    intercept: float
    coefficients: dict[str, float]
    dispersion_r: float | None

    def mean(self, features: Mapping[str, float]) -> float:
        eta = self.intercept + sum(
            float(coef) * float(features.get(name, 0.0))
            for name, coef in self.coefficients.items()
        )
        return math.exp(eta)
