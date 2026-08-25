"""Calibration: measuring whether a model's probabilities mean anything, and
correcting them when they do not.

The house rule this module exists to enforce is written in `CLAUDE.md`:

    **Calibration is a precondition, not a goal.** It can rule a model out; it
    can never rule one in. Where historical prices exist, a price-based
    backtest decides.

A correction fitted and evaluated on the same window is not evidence, it is
arithmetic. Everything here is built so that fitting and evaluating on the
same data is *awkward to do by accident*: `WalkForwardCalibration` takes dated
samples and refuses to score a sample with any correction that could have seen
it.

The correction itself is Platt scaling:

    corrected = sigmoid(intercept + slope * logit(raw))

Two parameters. That is deliberately not many. The defect a per-player Poisson
model actually has is a systematic one — it runs hot in the middle of the range
and collapses at the top, which is the signature of a slope below one — and a
richer correction would start fitting the sample instead of the defect.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np


#: Probabilities are clamped away from 0 and 1 before a logit. Without this a
#: single certain-looking prediction produces an infinite value and takes the
#: whole fit with it.
_EPSILON = 1e-4


def logit(probability: float) -> float:
    p = min(max(float(probability), _EPSILON), 1.0 - _EPSILON)
    return math.log(p / (1.0 - p))


def sigmoid(value: float) -> float:
    # Split on the sign so neither branch overflows.
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


@dataclass(frozen=True)
class PlattCalibration:
    """A fitted correction for a model's measured miscalibration.

    `fitted_on` records the sample count, so a correction fitted on too little
    announces itself in every report that prints it. The honesty rule lives at
    the call site, not here: fit on one window, apply on another, never both
    on the same data.
    """

    intercept: float
    slope: float
    fitted_on: int

    #: Below this many settled outcomes a fitted curve is noise, and the
    #: identity correction is the honest fallback. A correction that quietly
    #: fitted itself to forty bets would be worse than none, because it would
    #: carry the authority of having been "calibrated".
    MINIMUM_SAMPLES = 200

    @property
    def is_identity(self) -> bool:
        return self.intercept == 0.0 and self.slope == 1.0

    @classmethod
    def identity(cls, fitted_on: int = 0) -> "PlattCalibration":
        return cls(intercept=0.0, slope=1.0, fitted_on=fitted_on)

    @classmethod
    def fit(
        cls, samples: Sequence[tuple[float, bool]], *, minimum: int | None = None
    ) -> "PlattCalibration":
        """Newton-fitted logistic regression of outcome on logit(probability)."""
        threshold = cls.MINIMUM_SAMPLES if minimum is None else int(minimum)
        rows = list(samples)
        if len(rows) < threshold:
            return cls.identity(fitted_on=len(rows))
        outcomes = {bool(won) for _, won in rows}
        if len(outcomes) < 2:
            # Every sample won, or every sample lost. A logistic fit on that
            # runs its coefficients to infinity and reports a perfect
            # correction, which is the opposite of what the data shows.
            return cls.identity(fitted_on=len(rows))

        # Vectorised Newton. The scalar loop was correct and unusably slow:
        # a real walk-forward pass refits a few hundred times over a history
        # that grows into the hundreds of thousands, and at sixty iterations
        # apiece that is billions of Python-level operations. The arithmetic
        # below is the same arithmetic.
        xs = np.fromiter(
            (logit(p) for p, _ in rows), dtype=float, count=len(rows)
        )
        ys = np.fromiter(
            (1.0 if won else 0.0 for _, won in rows), dtype=float, count=len(rows)
        )
        a, b = 0.0, 1.0
        for _ in range(60):
            z = a + b * xs
            # Stable sigmoid: exp overflows on the negative branch otherwise.
            p = np.where(
                z >= 0,
                1.0 / (1.0 + np.exp(-np.clip(z, 0, 700))),
                np.exp(np.clip(z, -700, 0)) / (1.0 + np.exp(np.clip(z, -700, 0))),
            )
            residual = p - ys
            w = np.maximum(p * (1.0 - p), 1e-9)
            g0 = float(residual.sum())
            g1 = float((residual * xs).sum())
            h00 = float(w.sum())
            h01 = float((w * xs).sum())
            h11 = float((w * xs * xs).sum())
            determinant = h00 * h11 - h01 * h01
            if abs(determinant) < 1e-12:
                break
            da = (h11 * g0 - h01 * g1) / determinant
            db = (h00 * g1 - h01 * g0) / determinant
            a -= da
            b -= db
            if abs(da) < 1e-10 and abs(db) < 1e-10:
                break
        if not (math.isfinite(a) and math.isfinite(b)):
            return cls.identity(fitted_on=len(rows))
        return cls(intercept=a, slope=b, fitted_on=len(rows))

    def apply(self, probability: float) -> float:
        corrected = sigmoid(self.intercept + self.slope * logit(probability))
        return max(0.0, min(1.0, corrected))

    def describe(self) -> str:
        if self.is_identity:
            return (
                f"identity (no correction; {self.fitted_on} samples, below the "
                f"{self.MINIMUM_SAMPLES} needed)"
            )
        return (
            f"intercept {self.intercept:+.3f}, slope {self.slope:.3f} "
            f"(fitted on {self.fitted_on} samples)"
        )


@dataclass(frozen=True)
class ReliabilityBucket:
    """One row of a reliability table: what was promised and what happened."""

    label: str
    count: int
    predicted: float
    observed: float

    @property
    def gap(self) -> float:
        """Positive means the model promised more than happened."""
        return self.predicted - self.observed


def reliability_table(
    samples: Iterable[tuple[float, bool]],
    *,
    edges: Sequence[float] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
) -> list[ReliabilityBucket]:
    """Predicted vs observed rate per probability bucket, with counts.

    The count is not decoration. A bucket holding nine outcomes says nothing
    about calibration, and a table that hides that invites exactly the
    over-reading this project is built to avoid.
    """
    bounds = list(edges)
    if len(bounds) < 2 or any(b <= a for a, b in zip(bounds, bounds[1:])):
        raise ValueError("Bucket edges must be increasing and at least two.")
    totals = [0] * (len(bounds) - 1)
    predicted = [0.0] * (len(bounds) - 1)
    observed = [0] * (len(bounds) - 1)

    for probability, won in samples:
        p = min(max(float(probability), 0.0), 1.0)
        index = bisect_left(bounds, p) - 1
        index = min(max(index, 0), len(totals) - 1)
        totals[index] += 1
        predicted[index] += p
        observed[index] += 1 if won else 0

    table: list[ReliabilityBucket] = []
    for index, count in enumerate(totals):
        if not count:
            continue
        table.append(
            ReliabilityBucket(
                label=f"{bounds[index]:.0%}-{bounds[index + 1]:.0%}",
                count=count,
                predicted=predicted[index] / count,
                observed=observed[index] / count,
            )
        )
    return table


def brier_score(samples: Iterable[tuple[float, bool]]) -> float | None:
    """Mean squared error of the probabilities. Lower is better; None if empty."""
    total = 0.0
    count = 0
    for probability, won in samples:
        outcome = 1.0 if won else 0.0
        total += (float(probability) - outcome) ** 2
        count += 1
    return total / count if count else None


def log_loss(samples: Iterable[tuple[float, bool]]) -> float | None:
    """Mean negative log likelihood. Lower is better; None if empty."""
    total = 0.0
    count = 0
    for probability, won in samples:
        p = min(max(float(probability), _EPSILON), 1.0 - _EPSILON)
        total += -math.log(p if won else 1.0 - p)
        count += 1
    return total / count if count else None


@dataclass(frozen=True)
class WalkForwardResult:
    """Scored samples, each corrected by data that could not have seen it."""

    #: (date, raw probability, corrected probability, outcome)
    scored: list[tuple[str, float, float, bool]]
    #: The correction in force at each step, for the report.
    corrections: list[tuple[str, PlattCalibration]]
    #: Samples that came before enough history existed to correct them.
    warmup_skipped: int

    @property
    def raw(self) -> list[tuple[float, bool]]:
        return [(raw, won) for _, raw, _, won in self.scored]

    @property
    def corrected(self) -> list[tuple[float, bool]]:
        return [(fixed, won) for _, _, fixed, won in self.scored]


def walk_forward_calibrate(
    samples: Sequence[tuple[str, float, bool] | tuple[str, float, bool, str]],
    *,
    minimum_fit_samples: int = PlattCalibration.MINIMUM_SAMPLES,
    refit_every: int = 1,
    grouped: bool = False,
) -> WalkForwardResult:
    """Correct each sample using only samples dated strictly before it.

    `samples` is `(date, raw probability, outcome)`, optionally with a fourth
    element naming a group. Dates are compared as strings, which is correct
    for ISO dates and wrong for anything else — so anything else is refused
    rather than silently mis-ordered.

    The strictness is the point. A same-day sample is excluded from its own
    correction: on a single game-day a model prices a dozen props off the same
    lineup assumptions, and letting one of them inform another's correction
    would leak within the day even though the dates look ordered.

    Samples before `minimum_fit_samples` of history exist are **dropped**, not
    scored with the identity. Scoring them with the identity and reporting them
    alongside corrected ones would mix two different measurements into one
    average and flatter whichever is worse.

    With `grouped=True` a separate correction is fitted per group, falling back
    to the pooled correction when a group has too little history of its own.
    That is only worth doing where the miscalibration is genuinely
    group-dependent and there is a mechanism for why — see
    `docs/why_ice_time_gets_its_own_correction.md`. A per-group correction
    without a mechanism is curve-fitting with extra steps.
    """
    rows: list[tuple[str, float, bool, str]] = []
    for entry in samples:
        date_text, probability, won = entry[0], entry[1], entry[2]
        group = str(entry[3]) if grouped and len(entry) > 3 else ""
        text = str(date_text)
        if len(text) < 10 or text[4] != "-" or text[7] != "-":
            raise ValueError(
                f"Walk-forward calibration needs ISO dates; got {date_text!r}."
            )
        if not 0.0 <= float(probability) <= 1.0:
            raise ValueError("A raw probability must lie in [0, 1].")
        rows.append((text, float(probability), bool(won), group))
    rows.sort(key=lambda row: row[0])

    scored: list[tuple[str, float, float, bool]] = []
    corrections: list[tuple[str, PlattCalibration]] = []
    history: list[tuple[float, bool]] = []
    grouped_history: dict[str, list[tuple[float, bool]]] = {}
    pooled = PlattCalibration.identity()
    by_group: dict[str, PlattCalibration] = {}
    warmup = 0
    index = 0
    steps_since_refit = 0

    while index < len(rows):
        day = rows[index][0]
        # Everything on this date is scored by a correction fitted on strictly
        # earlier dates only.
        same_day: list[tuple[str, float, bool, str]] = []
        while index < len(rows) and rows[index][0] == day:
            same_day.append(rows[index])
            index += 1

        if len(history) >= minimum_fit_samples:
            if steps_since_refit <= 0:
                pooled = PlattCalibration.fit(history, minimum=minimum_fit_samples)
                corrections.append((day, pooled))
                if grouped:
                    by_group = {
                        name: PlattCalibration.fit(
                            entries, minimum=minimum_fit_samples
                        )
                        for name, entries in grouped_history.items()
                    }
                steps_since_refit = max(1, int(refit_every))
            steps_since_refit -= 1
            for date_text, probability, won, group in same_day:
                # A group whose own correction fell back to the identity has
                # too little history to have one, so it uses the pooled curve
                # rather than no curve at all.
                correction = by_group.get(group) if grouped else None
                if correction is None or correction.is_identity:
                    correction = pooled
                scored.append(
                    (date_text, probability, correction.apply(probability), won)
                )
        else:
            warmup += len(same_day)

        for _, probability, won, group in same_day:
            history.append((probability, won))
            if grouped:
                grouped_history.setdefault(group, []).append((probability, won))

    return WalkForwardResult(
        scored=scored, corrections=corrections, warmup_skipped=warmup
    )


def calibration_verdict(
    result: WalkForwardResult,
    *,
    minimum_samples: int = 200,
    material_improvement: float = 0.0005,
) -> str:
    """One sentence a report can print without overclaiming.

    Deliberately never says a model is good. The strongest thing calibration
    evidence can support is "not ruled out", and saying more than that is the
    exact failure mode this project exists to avoid.

    `material_improvement` exists because the first version of this function
    reported "the correction improves the Brier score (0.1053 raw, 0.1053
    corrected)". Both numbers were the same to four places and the sentence
    still said "improves", which is technically true and reads as a finding. A
    change below the threshold is now reported as *no material change*, with
    the delta shown so the reader can judge it.
    """
    count = len(result.scored)
    if count < minimum_samples:
        return (
            f"Not measurable: {count} scored samples, below the "
            f"{minimum_samples} needed to say anything. No verdict."
        )
    raw_brier = brier_score(result.raw)
    corrected_brier = brier_score(result.corrected)
    if raw_brier is None or corrected_brier is None:
        return "Not measurable: no scored samples. No verdict."
    delta = raw_brier - corrected_brier
    if abs(delta) < material_improvement:
        direction = (
            f"makes no material difference to the Brier score "
            f"({raw_brier:.4f} raw, {corrected_brier:.4f} corrected, delta "
            f"{delta:+.5f})"
        )
    elif delta > 0:
        direction = (
            f"improves the Brier score from {raw_brier:.4f} to "
            f"{corrected_brier:.4f} (delta {delta:+.5f})"
        )
    else:
        direction = (
            f"makes the Brier score worse, from {raw_brier:.4f} to "
            f"{corrected_brier:.4f} (delta {delta:+.5f})"
        )
    return (
        f"Over {count:,} held-out samples the correction {direction}. "
        "Calibration can rule this model out; it cannot rule it in. Whether "
        "the market disagrees with it profitably is a separate question, "
        "answered only by prices."
    )
