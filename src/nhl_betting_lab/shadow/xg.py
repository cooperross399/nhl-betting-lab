"""The lab's own expected-goals model, fitted on earlier seasons only.

MoneyPuck's xG would be better and is licensed (`docs/nhl_data_sources.md`),
so this is a plain logistic regression of goal on unblocked-attempt features:
distance, angle, shot type, rebound, strength and an empty net. The public
models (Evolving-Hockey, MoneyPuck, HockeyViz) use the same core features and
agree that distance and angle carry most of the signal.

**A season's xG comes from a model fitted on the seasons before it.** The
earliest season has no earlier season, so it is fitted on itself and every
figure built on it is marked in-sample and kept out of the walk-forward
comparison.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

SHOT_TYPES: tuple[str, ...] = (
    "wrist",
    "snap",
    "slap",
    "backhand",
    "tip-in",
    "deflected",
    "wrap-around",
)

#: Strength states with their own coefficient; 5v5 is the reference.
STRENGTH_TERMS: tuple[str, ...] = ("PP", "SH", "EV", "EA")

#: Small ridge on the coefficients, so a rare shot type in a thin season
#: cannot run its coefficient off to infinity.
RIDGE = 1.0


def season_of(game_id: object) -> int:
    """`2025020123` -> 20252026."""
    start = int(str(int(game_id))[:4])
    return start * 10000 + start + 1


def design_matrix(shots: pd.DataFrame) -> np.ndarray:
    distance = pd.to_numeric(shots["distance"], errors="coerce").fillna(35.0).clip(1.0, 200.0)
    angle = pd.to_numeric(shots["angle"], errors="coerce").fillna(30.0).clip(0.0, 180.0)
    columns = [
        np.ones(len(shots)),
        distance / 10.0,
        np.log(distance),
        angle / 45.0,
        (angle / 45.0) ** 2,
        shots["rebound"].astype(float),
        shots["empty_net"].astype(float),
    ]
    kinds = shots["shot_type"].astype(str)
    columns += [(kinds == kind).astype(float) for kind in SHOT_TYPES]
    strengths = shots["strength"].astype(str)
    columns += [(strengths == term).astype(float) for term in STRENGTH_TERMS]
    return np.column_stack([np.asarray(c, dtype=float) for c in columns])


@dataclass
class XgModel:
    coefficients: np.ndarray
    attempts: int
    goals: int

    @classmethod
    def fit(cls, shots: pd.DataFrame, *, iterations: int = 50) -> "XgModel":
        """Logistic regression by Newton's method on unblocked attempts."""
        unblocked = shots[shots["unblocked"].astype(bool)]
        if unblocked.empty:
            raise ValueError("No unblocked attempts to fit expected goals on.")
        x = design_matrix(unblocked)
        y = unblocked["goal"].astype(float).to_numpy()
        beta = np.zeros(x.shape[1])
        rate = min(max(y.mean(), 1e-4), 1 - 1e-4)
        beta[0] = np.log(rate / (1 - rate))
        penalty = np.eye(x.shape[1]) * RIDGE
        penalty[0, 0] = 0.0
        for _ in range(iterations):
            p = 1.0 / (1.0 + np.exp(-(x @ beta)))
            w = p * (1 - p)
            gradient = x.T @ (y - p) - penalty @ beta
            hessian = (x * w[:, None]).T @ x + penalty
            step = np.linalg.solve(hessian, gradient)
            beta = beta + step
            if np.max(np.abs(step)) < 1e-8:
                break
        return cls(coefficients=beta, attempts=len(unblocked), goals=int(y.sum()))

    def predict(self, shots: pd.DataFrame) -> np.ndarray:
        """Goal probability per attempt; zero for a blocked one."""
        if shots.empty:
            return np.zeros(0)
        p = 1.0 / (1.0 + np.exp(-(design_matrix(shots) @ self.coefficients)))
        return np.where(shots["unblocked"].astype(bool).to_numpy(), p, 0.0)


@dataclass
class SeasonXg:
    season: int
    fitted_on: tuple[int, ...]
    in_sample: bool
    attempts: int
    goals: int
    expected: float


def add_expected_goals(shots: pd.DataFrame) -> tuple[pd.DataFrame, list[SeasonXg]]:
    """`shots` with `xg` and `season` columns, each season scored out of sample."""
    frame = shots.copy()
    frame["season"] = frame["game_id"].map(season_of)
    frame["xg"] = 0.0
    record: list[SeasonXg] = []
    seasons: Sequence[int] = sorted(frame["season"].unique())
    for season in seasons:
        earlier = [s for s in seasons if s < season]
        in_sample = not earlier
        training = frame[frame["season"].isin(earlier or [season])]
        model = XgModel.fit(training)
        mask = frame["season"] == season
        frame.loc[mask, "xg"] = model.predict(frame[mask])
        rows = frame[mask & frame["unblocked"].astype(bool)]
        record.append(
            SeasonXg(
                season=int(season),
                fitted_on=tuple(int(s) for s in (earlier or [season])),
                in_sample=in_sample,
                attempts=len(rows),
                goals=int(rows["goal"].sum()),
                expected=float(rows["xg"].sum()),
            )
        )
    return frame, record
