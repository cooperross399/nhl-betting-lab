"""The arithmetic that keeps a measured number honest.

Every result this repository publishes is a point estimate from a finite
sample. This module produces the interval around it, the sample size that
would be needed to separate it from zero, and the exact sentence to use when
the interval includes zero.

That sentence is fixed on purpose. "No demonstrated edge" is not a synonym for
"promising", "trending positive", or "small but positive", and a report that
reaches for one of those has stopped reporting and started selling.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


#: 95% two-sided normal critical value.
Z95 = 1.959963984540054

#: The exact words for an interval that includes zero. Used verbatim.
NO_DEMONSTRATED_EDGE = "no demonstrated edge"


def bonferroni_z(looks: int) -> float:
    """The critical value for `looks` simultaneous 95% comparisons.

    Testing seven markets and reporting the one that cleared 95% is not a
    finding, it is a search. With seven looks the chance of at least one 95%
    result under the null is about 30%, so the threshold has to move.

    Bonferroni is conservative and crude, and that is the right trade here:
    the alternative is a sharper correction that needs assumptions about how
    the markets covary, and nothing in this repository has measured that.
    """
    count = max(1, int(looks))
    if count == 1:
        return Z95
    from statistics import NormalDist

    return NormalDist().inv_cdf(1.0 - 0.05 / (2 * count))


@dataclass(frozen=True)
class RoiInterval:
    """Flat-stake ROI with its interval and the sample behind it."""

    bets: int
    staked: float
    profit: float
    roi: float
    low: float
    high: float
    wins: int = 0
    pushes: int = 0
    #: How many markets were tested in the same family. One means the naive
    #: interval is the honest one; more means it is not.
    looks: int = 1
    standard_error: float = 0.0

    @property
    def includes_zero(self) -> bool:
        return self.low <= 0.0 <= self.high

    @property
    def adjusted_low(self) -> float:
        """The interval after correcting for how many markets were tested."""
        if self.looks <= 1 or not self.standard_error:
            return self.low
        return self.roi - bonferroni_z(self.looks) * self.standard_error

    @property
    def adjusted_high(self) -> float:
        if self.looks <= 1 or not self.standard_error:
            return self.high
        return self.roi + bonferroni_z(self.looks) * self.standard_error

    @property
    def survives_correction(self) -> bool:
        """Whether the result still excludes zero once the search is counted."""
        if self.bets < 30:
            return False
        return not (self.adjusted_low <= 0.0 <= self.adjusted_high)

    @property
    def win_rate(self) -> float | None:
        settled = self.bets - self.pushes
        return self.wins / settled if settled > 0 else None

    def verdict(self) -> str:
        """One sentence, with the sample size, that never overclaims."""
        if self.bets == 0:
            return "No bets were placed, so there is nothing to measure."
        if self.bets < 30:
            return (
                f"{self.bets} bets is far too few to measure anything. The "
                f"point estimate is {self.roi:+.1%} and it means nothing yet: "
                f"{NO_DEMONSTRATED_EDGE}."
            )
        if self.includes_zero:
            return (
                f"{self.roi:+.1%} over {self.bets} bets, 95% interval "
                f"{self.low:+.1%} to {self.high:+.1%}. The interval includes "
                f"zero, which means **{NO_DEMONSTRATED_EDGE}**."
            )
        direction = "profitable" if self.roi > 0 else "losing"
        naive = (
            f"{self.roi:+.1%} over {self.bets} bets, 95% interval "
            f"{self.low:+.1%} to {self.high:+.1%}. The interval excludes zero, "
            f"so this sample is {direction} beyond chance — at this sample "
            "size and on this data, which is not the same as an edge that "
            "will persist."
        )
        if self.looks <= 1:
            return naive
        if self.survives_correction:
            return naive + (
                f" It also survives correcting for the {self.looks} markets "
                f"tested ({self.adjusted_low:+.1%} to "
                f"{self.adjusted_high:+.1%}), which is worth more than the "
                "uncorrected number."
            )
        return naive + (
            f" But correcting for the {self.looks} markets tested widens it to "
            f"{self.adjusted_low:+.1%} to {self.adjusted_high:+.1%}, which "
            f"includes zero — so on the family of tests actually run, "
            f"**{NO_DEMONSTRATED_EDGE}**."
        )

    def as_row(self, label: str) -> str:
        """One markdown table row, sample size always beside the number."""
        corrected = (
            f"{self.adjusted_low:+.1%} .. {self.adjusted_high:+.1%}"
            if self.looks > 1
            else "n/a (one test)"
        )
        return (
            f"| {label} | {self.bets} | {self.profit:+.1f}u | "
            f"{self.roi:+.1%} | {self.low:+.1%} .. {self.high:+.1%} | "
            f"{corrected} | {'yes' if self.survives_correction else 'no'} |"
        )


ROI_TABLE_HEADER = (
    "| Market | Bets | Profit | ROI | 95% interval | Corrected for the search "
    "| Survives |\n"
    "|:-------|-----:|-------:|----:|:-------------|:-------------------------"
    "|:---------|"
)


def roi_interval(
    returns: Sequence[float],
    *,
    wins: int = 0,
    pushes: int = 0,
    looks: int = 1,
) -> RoiInterval:
    """ROI and its 95% interval from per-bet profit in units.

    `returns` is profit per bet: +0.91 for a winning -110, -1.0 for a loss,
    0.0 for a push. The interval is the normal interval on the mean return,
    which is the right shape here because a flat-stake series is a mean of
    bounded, independent-ish draws.

    It is *not* exact, and the docs say so: bets on the same game-day share
    lineup and game-script dependence, which makes the true interval slightly
    wider than this one. Reporting a slightly-too-narrow interval that
    includes zero is safe; the error would only matter for a result that
    barely excludes zero, and this project treats such a result as noise
    anyway.
    """
    rows = [float(value) for value in returns]
    bets = len(rows)
    if bets == 0:
        return RoiInterval(
            bets=0,
            staked=0.0,
            profit=0.0,
            roi=0.0,
            low=0.0,
            high=0.0,
            looks=looks,
        )
    profit = sum(rows)
    staked = float(bets)
    roi = profit / staked
    if bets < 2:
        return RoiInterval(
            bets=bets,
            staked=staked,
            profit=profit,
            roi=roi,
            low=float("-inf"),
            high=float("inf"),
            wins=wins,
            pushes=pushes,
            looks=looks,
        )
    mean = roi
    variance = sum((value - mean) ** 2 for value in rows) / (bets - 1)
    standard_error = math.sqrt(variance / bets)
    return RoiInterval(
        bets=bets,
        staked=staked,
        profit=profit,
        roi=roi,
        low=mean - Z95 * standard_error,
        high=mean + Z95 * standard_error,
        wins=wins,
        pushes=pushes,
        looks=looks,
        standard_error=standard_error,
    )


def bets_needed_to_detect(edge: float, *, spread: float = 1.0) -> int:
    """Roughly how many flat bets separate a true edge from zero at 95%.

    `spread` is the standard deviation of per-bet return; 1.0 is about right
    for near-even-money flat staking. The number is an order-of-magnitude
    guide, not a precise power calculation, and every report that prints it
    says so — its job is to make "we cannot know this yet" concrete.
    """
    size = abs(float(edge))
    if size <= 0:
        return 0
    return int(math.ceil((Z95 * float(spread) / size) ** 2))


def detection_table(edges: Sequence[float] = (0.05, 0.08, 0.10, 0.15)) -> str:
    lines = [
        "| If the true edge were | Bets needed to separate it from zero |",
        "|----------------------:|-------------------------------------:|",
    ]
    for edge in edges:
        lines.append(f"| {edge:+.0%} | ~{bets_needed_to_detect(edge):,} |")
    return "\n".join(lines)


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """95% Wilson interval on a hit rate. Correct at small n, unlike normal."""
    if trials <= 0:
        return 0.0, 1.0
    hits = max(0, min(int(successes), int(trials)))
    n = float(trials)
    p = hits / n
    denominator = 1.0 + Z95 * Z95 / n
    centre = (p + Z95 * Z95 / (2 * n)) / denominator
    margin = (
        Z95 * math.sqrt(p * (1.0 - p) / n + Z95 * Z95 / (4 * n * n))
    ) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def looks_significant_but_is_a_multiple_comparison(
    significant: int, looks: int
) -> str:
    """The sentence to print when one slice of many clears 95%.

    With twenty-five looks at one dataset, the probability of at least one 95%
    result is about 72%. A report that shows the winning slice without this
    sentence is showing chance and calling it a finding.
    """
    if looks <= 1 or significant <= 0:
        return ""
    chance = 1.0 - (0.95**looks)
    return (
        f"{significant} of {looks} slices cleared 95%. With {looks} looks at "
        f"one dataset the probability of at least one is about {chance:.0%}, "
        "so this is what chance looks like. A threshold moved to sit on it "
        "would be fitted to this sample and to nothing else."
    )
