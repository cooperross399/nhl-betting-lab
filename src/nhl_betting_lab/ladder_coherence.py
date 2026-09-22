"""Where a book contradicts its own ladder, and by how much.

The model has no demonstrated edge (`docs/why_the_model_has_no_edge.md`): its
disagreement with the price carries a coefficient of 0.032 where the market
carries 0.97. So this module holds no opinion about hockey at all. It compares
a book **against itself**, and the only arithmetic it uses is the fact that a
harder threshold cannot be more likely than an easier one.

## The one fact everything here rests on

For a stat `S` and lines `i < j`, the event `S > j` is contained in `S > i`.
So:

    P(S > i)  >=  P(S > j)      always, for every player, every night.

A book that quotes `over j` at a higher probability than `over i` has
contradicted itself. No model is needed to know one of those two quotes is
wrong, and no view about the player is needed to act on it.

## Which side is wrong, and what the edge is

The violation does not say *which* rung is mispriced. It does not have to.
Take the de-vigged probability of the higher rung, `p_j`. Because the higher
rung is contained in the lower one:

    P(S > i)  >=  P(S > j)  =  p_j

and the book is selling `over i` at a vig-inclusive implied price `q_i`. So

    edge  =  p_j  -  q_i

is a **lower bound** on the true edge, and it is conservative twice over: it
compares a de-vigged probability against a price that still carries the vig,
and it assumes the higher rung is exactly fair when the violation means at
least one of the two is not.

`p_j` needs both sides of rung `j` quoted, because a one-sided quote cannot be
de-vigged and pretending otherwise manufactures a probability out of nothing
— the same rule `models.value.no_vig_available` enforces everywhere else.
`q_i` needs only the over side, because it is used as a price, not as a
probability.

## Why the comparison never crosses a book or a moment

Two rungs from different books is the line-shopping hypothesis, and that one
is already dead: of 161,891 quotes only 1,557 — under one percent — were
positive-EV against the other books' de-vigged consensus. Two rungs from
different moments is not a contradiction at all; it is a book changing its
mind, which it is entitled to do. Only *one book, one moment, two rungs* is a
contradiction, so that is the only comparison `find_violations` makes.

## What this is not

It is not a card, not a selection, and not a permission. Nothing here consults
the allowlist because nothing here may produce a pick: a violation is evidence
for a measurement, and a measurement is evidence for a receipt only Cooper can
sign. The forward test is registered in
`docs/pre_registered_ladder_coherence.md` and decided on one pooled number.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pandas as pd

from nhl_betting_lab.models.value import (
    OddsError,
    american_to_implied,
    devig_two_way,
)


#: One book, one moment, one player's market. The comparison happens only
#: inside a group with all five equal; see the module docstring for why each
#: component is load-bearing rather than merely convenient.
LADDER_KEY: tuple[str, ...] = (
    "provider_event_id",
    "market",
    "player",
    "book",
    "snapshot",
)

VIOLATION_COLUMNS: tuple[str, ...] = (
    *LADDER_KEY,
    "low_line",
    "high_line",
    "low_over_odds",
    "p_high_devigged",
    "q_low_implied",
    "edge",
    "ladder_class",
)


@dataclass(frozen=True)
class Rung:
    """One line at one book at one moment."""

    line: float
    over_odds: float | None = None
    under_odds: float | None = None

    @property
    def implied_over(self) -> float | None:
        """The vig-inclusive price of the over, usable as a price only."""
        if self.over_odds is None:
            return None
        try:
            return american_to_implied(self.over_odds)
        except (OddsError, TypeError, ValueError):
            return None

    @property
    def fair_over(self) -> float | None:
        """The de-vigged probability, or None when only one side is quoted.

        A one-sided rung has no honest de-vig. Returning None here is what
        keeps a manufactured probability out of the edge arithmetic.
        """
        if self.over_odds is None or self.under_odds is None:
            return None
        try:
            return devig_two_way(self.over_odds, self.under_odds)[0]
        except (OddsError, TypeError, ValueError):
            return None


#: Bands in probability points, **fixed before any forward rung existed** and
#: anchored to a mechanism rather than to a return.
#:
#: They are deliberately NOT called tiers and deliberately not A/B/C.
#: `reports.gameday_card` already has `_tier_for` returning A/B/C and a
#: `TIER_UNITS = {"A": 0.5, "B": 0.25, "C": 0.1}` — measuring edge against
#: the best-bet bar, which is a different scale from the absolute points
#: below. Two A/B/C ladders under one word in one repository is how "home"
#: came to mean the provider in one table and ESPN in another, and 36% of
#: November's neutral-site bets graded for the opponent.
#:
#: The mechanism is the vig. A two-way prop carries roughly four to eight per
#: cent of margin, so two to four points sit on each side, and two rungs can
#: differ by that much through nothing more interesting than one of them
#: being priced with a wider margin than the other. So:
#:
#: * ``C`` at 2 points is the **detection floor** — the smallest gap that is
#:   not comfortably explained by a vig asymmetry between the two rungs.
#: * ``B`` at 4 points clears a typical one-sided vig share outright.
#: * ``A`` at 8 points is larger than any plausible margin artifact, so the
#:   contradiction has to be real even if both rungs are priced badly.
#:
#: Nothing below ``C`` is flagged. These numbers were not chosen by looking at
#: what any of them returned, because at the moment they were written down no
#: forward rung had been captured and there was nothing to look at. Revising
#: them after the season starts would convert a registration into a fit, which
#: is the move `docs/no_edge_out_of_sample.md` records the EPL lab making.
LADDER_CLASSES: tuple[tuple[str, float], ...] = (
    ("wide", 0.08),
    ("clear", 0.04),
    ("marginal", 0.02),
)

#: The smallest gap that is flagged at all: the last band's threshold, read
#: from the table rather than repeated, so the two can never disagree.
DETECTION_FLOOR: float = LADDER_CLASSES[-1][1]

#: What the card would stake, if a card were ever licensed to stake anything.
#: It is not: nothing is allowlisted and only Cooper may change that. These
#: exist so a band means something concrete rather than being a label.
#:
#: **The registered test does not use them.** It is flat-staked, one bet per
#: wager, which is the convention every other measurement in this repository
#: uses (`best_price_per_wager`). Weighting a return by a stake this lab
#: invented would measure the staking rule and the violation together, and
#: only one of those is the hypothesis.
LADDER_CLASS_UNITS: dict[str, float] = {
    "wide": 0.5,
    "clear": 0.25,
    "marginal": 0.1,
}


def class_for(edge: float) -> str | None:
    """The band an edge falls in, or None when it is below the floor."""
    for name, threshold in LADDER_CLASSES:
        if edge >= threshold:
            return name
    return None


def _rungs_from(frame: pd.DataFrame) -> tuple[list[Rung], int]:
    """One `Rung` per distinct line, plus the count of rows that collapsed.

    `find_violations` counts duplicates across the whole table instead of
    summing this, because it does not visit every ladder. This count stays
    because it is the per-ladder reference the whole-table count must agree
    with, and `test_the_two_duplicate_counts_agree` holds them together.

    Two rows for the same line inside one group are not a ladder with a
    zero-width step — they are a duplicate, and in the historical store they
    are the single largest source of apparent violations. They are collapsed
    here and **counted**, because a loader that drops rows without saying how
    many is how this repository lost 67% of an archive to a missing hyphen.
    """
    rungs: dict[float, dict[str, float]] = {}
    collapsed = 0
    for row in frame.itertuples():
        try:
            line = float(getattr(row, "line"))
        except (TypeError, ValueError):
            continue
        if line != line:  # NaN
            continue
        side = str(getattr(row, "selection", "")).strip().lower()
        if side not in {"over", "under"}:
            continue
        try:
            odds = float(getattr(row, "american_odds"))
        except (TypeError, ValueError):
            continue
        slot = rungs.setdefault(line, {})
        if side in slot:
            collapsed += 1
            continue
        slot[side] = odds
    built = [
        Rung(line=line, over_odds=sides.get("over"), under_odds=sides.get("under"))
        for line, sides in sorted(rungs.items())
    ]
    return built, collapsed


def violations_in_ladder(rungs: Sequence[Rung]) -> list[dict[str, float]]:
    """Every self-contradicting pair in one book's ladder at one moment.

    Every pair is compared, not only adjacent ones: a ladder can be coherent
    step by step and still contradict itself end to end, and the largest edge
    is usually the widest pair rather than a neighbouring one.
    """
    ordered = sorted(rungs, key=lambda rung: rung.line)
    found: list[dict[str, float]] = []
    for index, low in enumerate(ordered):
        q_low = low.implied_over
        if q_low is None:
            continue
        for high in ordered[index + 1 :]:
            if high.line <= low.line:
                continue
            p_high = high.fair_over
            if p_high is None:
                continue
            edge = p_high - q_low
            if edge < DETECTION_FLOOR:
                continue
            found.append(
                {
                    "low_line": low.line,
                    "high_line": high.line,
                    "low_over_odds": low.over_odds,
                    "p_high_devigged": p_high,
                    "q_low_implied": q_low,
                    "edge": edge,
                    "ladder_class": class_for(edge),
                }
            )
    return found


@dataclass
class LadderScan:
    """What a scan looked at, so a count of violations has a denominator."""

    ladders: int = 0
    ladders_with_two_rungs: int = 0
    comparable_pairs: int = 0
    duplicate_rows_collapsed: int = 0
    violations: int = 0

    def summary_line(self) -> str:
        if not self.ladders:
            return (
                "No ladder was scanned. That is an absence, not a coherent "
                "market: nothing has been shown about anything."
            )
        rate = (
            100.0 * self.violations / self.comparable_pairs
            if self.comparable_pairs
            else 0.0
        )
        return (
            f"{self.violations} violation(s) at or above "
            f"{DETECTION_FLOOR * 100:.0f} points, across {self.comparable_pairs} "
            f"comparable rung pair(s) in {self.ladders_with_two_rungs} of "
            f"{self.ladders} ladder(s) — {rate:.3f}%. "
            f"{self.duplicate_rows_collapsed} duplicate row(s) collapsed."
        )


def find_violations(
    prices: pd.DataFrame,
    *,
    key: Iterable[str] = LADDER_KEY,
) -> tuple[pd.DataFrame, LadderScan]:
    """Scan a price table for books contradicting their own ladders.

    Returns one row per **wager** — the over at the lower line, at that book —
    keeping the largest edge when several higher rungs bound the same one, so
    a single bet is never counted twice. That is the same one-bet-per-wager
    convention every other measurement here uses; counting per quote is how
    this lab once reported -1.6% for a population that was really -0.29%.

    The scan report is returned beside the rows because a violation count
    without its denominator is not a result.
    """
    columns = list(key)
    scan = LadderScan()
    missing = [name for name in (*columns, "line", "selection", "american_odds")
               if name not in prices.columns]
    if missing:
        raise ValueError(
            "find_violations needs every ladder-identity column and is "
            f"missing {missing}. A scan that silently groups on whatever "
            "happens to be present would compare two books, or two moments, "
            "and call the difference a contradiction."
        )
    if prices.empty:
        return pd.DataFrame(columns=list(VIOLATION_COLUMNS)), scan

    # A ladder with one line cannot contradict itself, and on the two-season
    # store 1.72M of 2.0M groups are exactly that. They are counted into the
    # denominator and then skipped without being built, because building them
    # turned a scan into an hour.
    grouped = prices.groupby(columns, dropna=False)
    scan.ladders = int(grouped.ngroups)
    # Counted across the whole table, not inside the loop below, because the
    # loop does not visit every ladder — and a duplicate that goes unreported
    # because its ladder was skipped is exactly the kind of silent skip that
    # once cost this repository 67% of an archive.
    scan.duplicate_rows_collapsed = int(
        prices.duplicated(subset=[*columns, "line", "selection"]).sum()
    )
    candidates = prices[grouped["line"].transform("nunique") >= 2]
    if candidates.empty:
        return pd.DataFrame(columns=list(VIOLATION_COLUMNS)), scan

    rows: list[dict[str, object]] = []
    for group_key, frame in candidates.groupby(columns, dropna=False):
        rungs, _ = _rungs_from(frame)
        if len(rungs) < 2:
            continue
        scan.ladders_with_two_rungs += 1
        priced = [rung for rung in rungs if rung.implied_over is not None]
        deviggable = [rung for rung in rungs if rung.fair_over is not None]
        scan.comparable_pairs += sum(
            1
            for low in priced
            for high in deviggable
            if high.line > low.line
        )
        identity = dict(zip(columns, group_key if isinstance(group_key, tuple)
                            else (group_key,)))
        for hit in violations_in_ladder(rungs):
            rows.append({**identity, **hit})

    if not rows:
        return pd.DataFrame(columns=list(VIOLATION_COLUMNS)), scan

    found = pd.DataFrame(rows)
    # One bet per wager: the wager is the over at the lower line at that book,
    # however many higher rungs happen to contradict it.
    wager = columns + ["low_line"]
    found = (
        found.sort_values("edge", ascending=False)
        .drop_duplicates(subset=wager, keep="first")
        .reset_index(drop=True)
    )
    scan.violations = len(found)
    return found[list(VIOLATION_COLUMNS)], scan
