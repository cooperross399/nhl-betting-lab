"""Shooter and goalie talent, updated shot by shot, as PostHockey estimates it.

PostHockey's glossary (posthockey.com/glossary, section 4) keeps every
shooter's finishing and every goalie's stopping as a posterior on the logit
scale of an expected-goals model, updated after each unblocked attempt:

    prior   mu ~ Normal(prior_mean, prior_sd^2)
    walk    each shot adds walk variance, so old shots fade
    update  p  = sigmoid(base_logit + mu_shooter - mu_goalie)
            w  = p (1 - p)
            v' = 1 / (1/v + w)
            mu' = mu + v' (y - p)       (the goalie moves the other way)

with variance capped, and talent re-centred on the league at each season
boundary. Shrinkage falls out of the arithmetic: a shooter with forty shots
has barely moved off the prior, one with four hundred has.

What this module does differently, stated so nobody assumes otherwise:

* The base logit is the lab's own context xG (`xg.context_design_matrix`),
  fitted on earlier seasons only, not PostHockey's 93-feature model.
* No league scoring-environment term `E`: each season's base model already
  carries its own intercept, and estimating `E` from the season being scored
  would leak it. Re-centring subtracts the mean talent of players who shot
  (or faced shots) that season, which keeps a season's sum of probabilities
  where the base model put it, as PostHockey's re-centring does.
* No age drift: the lab has no birth dates on the shot table.
* The random-walk variances are this lab's choice (PostHockey does not
  publish them), `SHOOTER_WALK` and `GOALIE_WALK` below.

Every attempt carries the talent *before* it was taken (`mu_shooter`,
`mu_goalie`), so a figure built from these columns for a game uses nothing
from that game's later shots, and nothing at all from later games.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SHOOTER_PRIOR_MEAN = 0.0
SHOOTER_PRIOR_SD = 0.20
GOALIE_PRIOR_MEAN = 0.0
GOALIE_PRIOR_SD = 0.05
VARIANCE_CAP = 0.5
#: Added to a shooter's variance before each of his attempts. A forward
#: takes about 150 unblocked attempts a season, so his talent can wander
#: about 0.04 on the logit scale over a season, and his posterior settles near
#: an SD of 0.10 (a memory of roughly a thousand attempts) instead of
#: collapsing onto his career average.
SHOOTER_WALK = 1e-5
#: A starter faces about 1,500 unblocked attempts a season: a wander of about
#: 0.009 a season, settling near an SD of 0.03 under a prior of 0.05.
GOALIE_WALK = 5e-8


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class Posterior:
    mean: float
    variance: float
    shots: int = 0


def add_talent(
    shots: pd.DataFrame, *, base: str = "xg_ctx", order: str = "date"
) -> tuple[pd.DataFrame, dict[object, Posterior], dict[object, Posterior]]:
    """`shots` with pre-shot talent and the three adjusted xG columns.

    Adds `mu_shooter` and `mu_goalie` (before the shot), `xg_sh`
    (shooter-adjusted), `xg_sv` (goalie-adjusted) and `xg_full` (both), plus
    `mu_shooter_after`, the shooter's talent once the shot is counted, which is
    what a later game reads. Also returns every shooter's and goalie's
    posterior after the last shot, for the report. Blocked attempts and shots at an empty net take
    no part and carry the unadjusted base in every column. Shots are taken in
    `order` (a sortable date column), then game, then game clock.
    """
    frame = shots.copy()
    n = len(frame)
    for column in ("mu_shooter", "mu_goalie", "mu_shooter_after"):
        frame[column] = 0.0
    for column in ("xg_sh", "xg_sv", "xg_full"):
        frame[column] = frame[base].astype(float) if n else 0.0
    if not n:
        return frame, {}, {}
    keys = [c for c in (order, "game_id", "game_seconds") if c in frame]
    ordered = frame.sort_values(keys, kind="stable").index
    eligible = (
        frame["unblocked"].astype(bool) & ~frame["empty_net"].astype(bool)
    ).to_numpy()
    base_p = frame[base].astype(float).to_numpy()
    base_logit = _logit(base_p)
    goal = frame["goal"].astype(bool).to_numpy().astype(float)
    shooter = frame["shooter_id"].to_numpy()
    goalie = frame["goalie_id"].to_numpy() if "goalie_id" in frame else np.full(n, None)
    season = frame["season"].to_numpy() if "season" in frame else np.zeros(n)
    position = {index: i for i, index in enumerate(frame.index)}

    shooters: dict[object, Posterior] = {}
    goalies: dict[object, Posterior] = {}
    mu_s = np.zeros(n)
    mu_g = np.zeros(n)
    mu_after = np.zeros(n)
    current_season = None
    for index in ordered:
        i = position[index]
        if season[i] != current_season:
            if current_season is not None:
                _recentre(shooters)
                _recentre(goalies)
            current_season = season[i]
        s_key = shooter[i] if shooter[i] == shooter[i] and shooter[i] is not None else None
        g_key = goalie[i] if goalie[i] == goalie[i] and goalie[i] is not None else None
        s = shooters.get(s_key) if s_key is not None else None
        if s_key is not None and s is None:
            s = shooters[s_key] = Posterior(SHOOTER_PRIOR_MEAN, SHOOTER_PRIOR_SD**2)
        g = goalies.get(g_key) if g_key is not None else None
        if g_key is not None and g is None:
            g = goalies[g_key] = Posterior(GOALIE_PRIOR_MEAN, GOALIE_PRIOR_SD**2)
        mu_s[i] = s.mean if s is not None else 0.0
        mu_g[i] = g.mean if g is not None else 0.0
        if eligible[i]:
            p = float(_sigmoid(base_logit[i] + mu_s[i] - mu_g[i]))
            w = p * (1 - p)
            if s is not None:
                v = min(s.variance + SHOOTER_WALK, VARIANCE_CAP)
                s.variance = 1.0 / (1.0 / v + w)
                s.mean += s.variance * (goal[i] - p)
                s.shots += 1
            if g is not None:
                v = min(g.variance + GOALIE_WALK, VARIANCE_CAP)
                g.variance = 1.0 / (1.0 / v + w)
                g.mean -= g.variance * (goal[i] - p)
                g.shots += 1
        mu_after[i] = s.mean if s is not None else 0.0

    frame["mu_shooter"] = mu_s
    frame["mu_goalie"] = mu_g
    frame["mu_shooter_after"] = mu_after
    adjusted = {
        "xg_sh": base_logit + mu_s,
        "xg_sv": base_logit - mu_g,
        "xg_full": base_logit + mu_s - mu_g,
    }
    for column, logit in adjusted.items():
        frame[column] = np.where(
            eligible, _sigmoid(logit), np.where(frame["unblocked"].astype(bool), base_p, 0.0)
        )
    return frame, shooters, goalies


def _recentre(players: dict[object, Posterior]) -> None:
    """Subtract the mean talent of everyone who took part last season."""
    active = [p for p in players.values() if p.shots]
    if not active:
        return
    offset = float(np.mean([p.mean for p in active]))
    for p in players.values():
        p.mean -= offset
        p.shots = 0


def goalie_tier(mean: float, sd: float) -> str:
    """PostHockey's A-F: where the posterior's one-sigma band sits.

    A: the whole band above average. F: the whole band below. B and D: the
    mean above or below and the band overlapping average by less than half
    its width; C: otherwise. A letter carries confidence as well as ability.
    """
    low, high = mean - sd, mean + sd
    if low > 0:
        return "A"
    if high < 0:
        return "F"
    if mean > 0 and mean > sd / 2:
        return "B"
    if mean < 0 and -mean > sd / 2:
        return "D"
    return "C"


def gsax_plus(gsax: pd.Series) -> pd.Series:
    """GSAx rescaled to mean 100, SD 15 across the goalies given."""
    sd = float(gsax.std(ddof=0))
    if not sd or sd != sd:
        return pd.Series(100.0, index=gsax.index)
    return 100 + 15 * (gsax - gsax.mean()) / sd
