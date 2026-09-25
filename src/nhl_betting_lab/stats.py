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
from collections.abc import Iterable, Sequence
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


def correction_family(looks: int, family: str = "") -> str:
    """The family a correction counted, in words that are true of it.

    `family` says what the looks are when they are not simply markets. The
    props backtest corrects over its markets AND the overall figure, and
    every sentence that stated the count used to call all of it markets: the
    `late` window measures 6 markets and printed "correcting for the 7
    markets tested", the card window measures 7 and printed 8, and the claims
    document and the allowlist bundle repeated it beside a table of six
    market rows. The count was right and the unit was not. A family of
    markets alone — team markets, the forward ledger, whose correction
    `docs/when_this_ends.md` registers as "across the markets measured" —
    keeps that unit. One phrase for every document, so they cannot drift.
    """
    if family:
        return f"{looks} figures measured on the same data ({family})"
    return f"{looks} markets measured on the same data"


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
    #: How many figures were tested in the same family. One means the naive
    #: interval is the honest one; more means it is not.
    looks: int = 1
    standard_error: float = 0.0
    #: What those looks are, when they are not simply markets — the props
    #: backtest's "6 markets and the overall figure". Empty means each look
    #: is one market. See `correction_family`.
    family: str = ""

    @property
    def includes_zero(self) -> bool:
        return self.low <= 0.0 <= self.high

    @property
    def adjusted_low(self) -> float:
        """The interval after correcting for how many figures were tested."""
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
        # What the correction counted, never "markets" for a family that is
        # more than markets. See `correction_family`.
        family = correction_family(self.looks, self.family)
        if self.survives_correction:
            return naive + (
                f" It also survives correcting for the {family}, at "
                f"{self.adjusted_low:+.1%} to {self.adjusted_high:+.1%}, "
                "which is worth more than the uncorrected number."
            )
        return naive + (
            f" But correcting for the {family} widens it to "
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
    family: str = "",
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
            family=family,
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
            family=family,
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
        family=family,
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


def wilson_interval(
    successes: int, trials: int, *, z: float = Z95
) -> tuple[float, float]:
    """Wilson interval on a hit rate. Correct at small n, unlike normal.

    95% unless `z` says otherwise. A rate that is one row of a family (one
    market among several in the same table) passes `bonferroni_z(looks)`,
    the same correction `RoiInterval.adjusted_low` applies to a mean.

    It assumes every trial is independent. Where trials arrive in clusters
    that share an outcome — the lines of one player-game, the selections of
    one game — use `clustered_wilson_interval`.
    """
    if trials <= 0:
        return 0.0, 1.0
    hits = max(0, min(int(successes), int(trials)))
    n = float(trials)
    return wilson_interval_on_rate(hits / n, n, z=z)


def wilson_interval_on_rate(
    rate: float, trials: float, *, z: float = Z95
) -> tuple[float, float]:
    """The Wilson arithmetic at a rate and a possibly fractional trial count.

    `wilson_interval` is this at a whole number, bit for bit. The fractional
    form exists for an effective sample size, which is rarely a whole number.
    """
    n = float(trials)
    if n <= 0:
        return 0.0, 1.0
    p = min(max(float(rate), 0.0), 1.0)
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = (
        z * math.sqrt(p * (1.0 - p) / n + z * z / (4 * n * n))
    ) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def clustered_wilson_interval(
    clusters: Iterable[tuple[int, int]],
) -> tuple[float, float]:
    """95% Wilson interval on a hit rate whose trials arrive in clusters.

    `clusters` is `(hits, trials)` per cluster: per game, when every
    selection at every line of one game shares its scoreline, or when every
    line of a player-game and every player in one game share its events.
    Rows inside a cluster are not independent trials, and a Wilson interval
    on the rows pretends they are.

    The rate is the pooled one. Its variance is measured across clusters —
    the ratio estimator's cluster-robust variance — and turned into a design
    effect, `deff = sum((hits_g - rate * trials_g) ** 2) / (N * rate * (1 -
    rate))`, and an effective sample size `N / deff` that the Wilson
    arithmetic is then run at. Three conventions, each so that the interval
    is never narrower than one on the rows:

    * clusters of one are independent trials, and the result is exactly
      `wilson_interval(hits, trials)`;
    * a design effect below one — rows inside a cluster that move in
      opposite directions, like an over and an under of one game in one
      bucket — is held at one, as survey practice does (Korn and Graubard),
      so the interval is the Wilson interval on the rows, never narrower;
    * where no design effect can be measured — a single cluster, or a rate
      of exactly 0 or 1 — each cluster counts as one trial rather than
      assuming the rows inside it are independent.

    Identical rows inside equal clusters therefore give exactly the Wilson
    interval on the clusters: repeating every row k times moves nothing.
    """
    pairs: list[tuple[int, int]] = []
    for hits, trials in clusters:
        size = int(trials)
        won = int(hits)
        if size <= 0:
            continue
        if not 0 <= won <= size:
            raise ValueError(f"A cluster cannot hold {won} hits in {size} trials.")
        pairs.append((won, size))
    trials_total = sum(size for _, size in pairs)
    hits_total = sum(won for won, _ in pairs)
    if trials_total <= 0:
        return 0.0, 1.0
    if len(pairs) == trials_total:
        return wilson_interval(hits_total, trials_total)
    rate = hits_total / trials_total
    if len(pairs) < 2 or hits_total in (0, trials_total):
        return wilson_interval_on_rate(rate, float(len(pairs)))
    spread = sum((won - rate * size) ** 2 for won, size in pairs)
    design_effect = max(1.0, spread / (trials_total * rate * (1.0 - rate)))
    return wilson_interval_on_rate(rate, trials_total / design_effect)


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
