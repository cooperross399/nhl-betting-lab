"""Count distributions for prop pricing, and the choice between them.

A prop is a question about a count: how many shots, how many points, how many
saves. Pricing one needs a distribution over counts, and the usual reflex is
Poisson because it has one parameter and closed-form tails.

Poisson also asserts that variance equals mean. For some of these counts that
is roughly true and for others it is badly false, so this module measures the
dispersion instead of assuming it, and uses a negative binomial where the data
says Poisson would be lying.

Which is which, from the NHL boxscore data:

* **Shots on goal** are close to Poisson. A shot is a repeated, weakly
  dependent event within a game.
* **Points and assists** are overdispersed. They arrive in clusters — a
  three-point night and a five-game blank are the same player — because points
  depend on linemates and on the team scoring at all.
* **Goalie saves** are strongly overdispersed. The count is driven by shots
  against, which varies enormously game to game; the save itself is almost
  incidental. Pricing saves as Poisson would understate both tails badly, and
  the tails are where the alternate lines live.
* **Blocked shots** are mildly overdispersed and depend on game script: a team
  defending a lead blocks far more.

Overdispersion always widens the distribution, so pricing an overdispersed
count as Poisson **understates the Over on a high line and overstates it on a
low one**. That is not a small effect at the alternate lines this lab prefers.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


#: A variance-to-mean ratio at or below this is treated as Poisson. Above it,
#: a negative binomial is fitted. 1.15 rather than 1.0 because a sample ratio
#: wobbles above one by chance, and swapping distributions on noise would make
#: the model's shape depend on which games happened to be in the file.
DISPERSION_THRESHOLD = 1.15

#: An `r` above this is numerically indistinguishable from Poisson and starts
#: costing precision in the gamma functions, so it collapses to Poisson.
MAX_DISPERSION_R = 500.0


class CountDistribution:
    """A distribution over non-negative integer counts."""

    mean: float

    def pmf(self, k: int) -> float:
        raise NotImplementedError

    def cdf(self, k: int) -> float:
        """P(X <= k)."""
        if k < 0:
            return 0.0
        return min(1.0, sum(self.pmf(i) for i in range(int(k) + 1)))

    def sf(self, k: int) -> float:
        """P(X > k). This is what an Over bet at line k + 0.5 pays on."""
        return max(0.0, 1.0 - self.cdf(k))

    def over_probability(self, line: float) -> float:
        """P(count beats `line`).

        A half-point line has no push. A whole-number line does: a book
        settling "over 2.0" refunds a 2, so the bet is P(X > 2) conditioned on
        no push. That distinction is priced here rather than being rounded
        away, because whole-number alternate lines are common on shots and
        saves and quietly treating one as a half-point line misprices it.
        """
        value = float(line)
        floor = math.floor(value)
        if math.isclose(value, floor):
            push = self.pmf(int(floor))
            remaining = 1.0 - push
            if remaining <= 0.0:
                return 0.0
            return self.sf(int(floor)) / remaining
        return self.sf(int(floor))

    def push_probability(self, line: float) -> float:
        """P(the bet is refunded). Zero on any half-point line."""
        value = float(line)
        floor = math.floor(value)
        if math.isclose(value, floor):
            return self.pmf(int(floor))
        return 0.0


@dataclass(frozen=True)
class Poisson(CountDistribution):
    mean: float

    def pmf(self, k: int) -> float:
        if k < 0:
            return 0.0
        lam = max(float(self.mean), 1e-9)
        return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


@dataclass(frozen=True)
class NegativeBinomial(CountDistribution):
    """Mean/dispersion parameterisation: variance = mean + mean^2 / r.

    `r` is the dispersion. As r grows the distribution converges on Poisson,
    which is why a large r collapses to Poisson at construction.
    """

    mean: float
    r: float

    def pmf(self, k: int) -> float:
        if k < 0:
            return 0.0
        mean = max(float(self.mean), 1e-9)
        r = max(float(self.r), 1e-6)
        p = r / (r + mean)
        return math.exp(
            math.lgamma(k + r)
            - math.lgamma(r)
            - math.lgamma(k + 1)
            + r * math.log(p)
            + k * math.log(1.0 - p)
        )


@dataclass(frozen=True)
class Dispersion:
    """A measured variance-to-mean ratio and what it implies."""

    mean: float
    variance: float
    samples: int

    @property
    def ratio(self) -> float:
        return self.variance / self.mean if self.mean > 0 else 1.0

    @property
    def overdispersed(self) -> bool:
        return self.samples >= 30 and self.ratio > DISPERSION_THRESHOLD

    @property
    def r(self) -> float | None:
        """The negative binomial dispersion this ratio implies, if any."""
        if not self.overdispersed:
            return None
        excess = self.variance - self.mean
        if excess <= 0:
            return None
        return (self.mean * self.mean) / excess

    def describe(self) -> str:
        if self.samples < 30:
            return (
                f"{self.samples} samples: too few to measure dispersion, "
                "so Poisson is used by default."
            )
        shape = "negative binomial" if self.overdispersed else "Poisson"
        return (
            f"variance/mean = {self.ratio:.2f} over {self.samples} samples "
            f"-> {shape}"
        )


def measure_dispersion(values: Iterable[float]) -> Dispersion:
    """Sample mean and variance of a count column."""
    rows = [float(value) for value in values]
    count = len(rows)
    if count == 0:
        return Dispersion(mean=0.0, variance=0.0, samples=0)
    mean = sum(rows) / count
    if count < 2:
        return Dispersion(mean=mean, variance=0.0, samples=count)
    variance = sum((value - mean) ** 2 for value in rows) / (count - 1)
    return Dispersion(mean=mean, variance=variance, samples=count)


def distribution_for(mean: float, dispersion: Dispersion | None) -> CountDistribution:
    """Poisson, or negative binomial where the measured data demands it.

    The dispersion is measured once at fit time on the whole stat column and
    then reused for every player, rather than fitted per player. A per-player
    dispersion from twenty games is noise, and it would give the busiest
    players the tightest distributions purely because they have more games.
    """
    average = max(float(mean), 1e-9)
    if dispersion is None:
        return Poisson(mean=average)
    r = dispersion.r
    if r is None or r >= MAX_DISPERSION_R:
        return Poisson(mean=average)
    return NegativeBinomial(mean=average, r=r)


def poisson_over_probability(mean: float, line: float) -> float:
    """Convenience for the common case; identical to `Poisson(...).over_probability`."""
    return Poisson(mean=mean).over_probability(line)


def tail_sum(distribution: CountDistribution, values: Sequence[int]) -> float:
    """Total probability mass on a set of counts. Used in tests and reports."""
    return sum(distribution.pmf(int(value)) for value in values)
