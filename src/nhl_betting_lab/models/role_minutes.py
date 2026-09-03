"""Turning a line label into a distribution over minutes, and saying how well it works.

Daily Faceoff reports a *label* -- `f1`, `d2`, `pp1`. The prop model consumes
*minutes*. This module is the translator between the two, and it is
deliberately wired into nothing: `docs/where_the_remaining_error_lives.md`
measures the stale-minutes cell at -6.44% over 5,661 bets, and the only
honest way to find out whether a line feed closes it is to collect the feed
forward and measure it later. A translator built today can be tested for
*accuracy* today; it cannot be tested for *money* until there are labels.

**The historical mapping comes from a proxy, and the proxy is not the label.**
The game logs carry no line assignments, so a player's role on a night is
approximated by his usage RANK inside his own team and position group that
night: the top three forwards by ice time stand in for a first line, the next
three for a second, the top two defencemen for a first pair. That is a rank
*realised after the fact*, which is why:

* it is only ever fitted on games strictly earlier than the game being
  described (`fit_role_minutes(..., before=...)`), and
* using a game's own realised rank to describe that same game is an ORACLE.
  `oracle=True` exists for exactly one purpose -- bounding what a perfect
  label could buy -- and every number produced that way must be labelled one.

**Power-play units are the weakest link here and are marked as such.** The
logs record no power-play membership, so `pp1`/`pp2` are matched to the
team's top five and next five skaters by total ice time. A real first unit is
five specific players, not the five who happened to play the most, so a
`pp1` distribution from this module is a proxy of a proxy. It carries
`is_proxy=True` and its accuracy against real unit membership is UNMEASURED.

**It returns a distribution, not a number, and the distribution is worth
less than it sounds.** The prop model plugs a scalar ice time into a count
mean; by the law of total variance that discards `Var(E[N|TOI])`, which is
real and is largest in the widest bands. `MinutesDistribution.expectation`
and `.total_variance` are the calls that let a caller integrate over minutes
instead of guessing one. But measured on 6,000 of the card's own 2025-26
bets, integrating over the band instead of plugging in its centre moves
P(over) by a mean of **0.11 probability points** and moves the side actually
bet by **+0.066 points** -- against a 2.70-point toll and a 6-point bar. The
interface is the right one; it is not a fix for the cell, and quoting it as
one would be the fourth retraction.

**What it is worth, measured before anyone spends a season collecting.**
Walk-forward over 123,724 skater-games (2023-24 to 2025-26), predicting a
player's next-game ice time, where the incumbent is the model's own
trailing-ten estimate (reproduced here to the last bit on all 123,724):

* trailing-ten: MAE 1.984 min, RMSE 2.622, R-squared 0.667
* rank-band prior from the last known band: MAE 2.551, R-squared 0.468
* the shrunk blend of the two: MAE 1.968, R-squared 0.673 -- better than the
  incumbent by 0.016 min, which is one second
* a PERFECT label (the game's own realised band, an ORACLE): MAE 1.535,
  R-squared 0.808

So a label feed is worth something only if its label is close to the rank the
player actually ends up occupying. On the event that costs money -- ice time
about to rise by more than two minutes, base rate 20.5% -- the last-known
band scores ROC-AUC 0.568 against 0.560 for a purely trailing-ten read of the
same history, a difference of +0.008 [+0.004, +0.014] under a date-clustered
bootstrap: real, and useless. A perfect label scores 0.839. Re-pricing the
card's own bets at each input, a perfect label is worth **+3.20 ROI points
[+2.37, +3.97]** over the incumbent and **+2.42 [+1.32, +3.46]** over a
placebo that shuffles the same labels between players on the same night,
while the feasible last-known band is worth **-0.02 [-0.84, +0.81]** --
**no demonstrated edge**. That +2.42 is the ceiling on the whole collection
effort, and it is an optimistic ceiling: realised rank knows how the game
went, and a line posted the morning of does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd


#: Forwards ride in threes, defencemen in pairs. Ranks past the last band
#: fall into it rather than inventing an `f5` nobody dresses.
FORWARD_BAND_SIZE = 3
DEFENCE_BAND_SIZE = 2
BAND_COUNT = 4

EV_BANDS = ("f1", "f2", "f3", "f4", "d1", "d2", "d3", "d4")
PP_BANDS = ("pp1", "pp2")
KNOWN_LABELS = EV_BANDS + PP_BANDS

#: Power-play units hold five skaters. With no membership in the logs, the
#: team's top five by ice time stand in for the first unit and the next five
#: for the second. A proxy, and flagged as one everywhere it surfaces.
PP_UNIT_SIZE = 5

#: The quantile grid every fitted cell is stored on. Fine enough to
#: interpolate and to integrate over, small enough to hold per cell.
PROBS: tuple[float, ...] = tuple(i / 100.0 for i in range(101))

#: A cell thinner than this is not a distribution, it is a handful of games.
#: Cells below it fall back to a wider one and say so in `basis`.
MINIMUM_CELL = 200


def position_band_group(position: str) -> str:
    """`F` or `D`. Goalies belong to neither and are never ranked here."""
    code = str(position or "").strip().upper()
    if code.startswith("D"):
        return "D"
    if code.startswith("G"):
        return "G"
    return "F"


def band_for_rank(group: str, rank: int) -> str:
    """The band a usage rank lands in, e.g. (`F`, 4) -> `f2`.

    Ranks are 1-based. Anything past the fourth band is folded into it: a
    team dressing a thirteenth forward has not invented a fifth line.
    """
    if rank < 1:
        raise ValueError(f"Usage ranks are 1-based; got {rank!r}.")
    letter = position_band_group(group)
    if letter == "G":
        raise ValueError("Goalies have no line band.")
    size = FORWARD_BAND_SIZE if letter == "F" else DEFENCE_BAND_SIZE
    index = min(BAND_COUNT, (int(rank) - 1) // size + 1)
    return f"{letter.lower()}{index}"


def with_usage_bands(logs: pd.DataFrame) -> pd.DataFrame:
    """Add `band_group`, `usage_rank`, `ev_band` and `pp_band` to skater rows.

    The rank is within (game, team, position group) on realised ice time,
    descending, so rank 1 is that night's most-used forward or defenceman.
    Ties break by player id, which is arbitrary but stable -- an unstable
    ordering would make the same game fit differently on two runs.
    """
    required = {"game_id", "team", "position", "toi_seconds", "player_id"}
    missing = required - set(logs.columns)
    if missing:
        raise KeyError(
            f"Cannot rank usage without {sorted(missing)}; refusing to guess "
            "at a player's role from a partial frame."
        )
    frame = logs.copy()
    if "role" in frame.columns:
        frame = frame[frame["role"].astype(str) == "skater"]
    frame["toi_seconds"] = pd.to_numeric(
        frame["toi_seconds"], errors="coerce"
    ).fillna(0.0)
    frame = frame[frame["toi_seconds"] > 0]
    frame["band_group"] = frame["position"].map(position_band_group)
    frame = frame[frame["band_group"].isin(("F", "D"))]
    if frame.empty:
        frame["usage_rank"] = pd.Series(dtype="int64")
        frame["ev_band"] = pd.Series(dtype="object")
        frame["pp_band"] = pd.Series(dtype="object")
        return frame

    ordered = frame.sort_values(
        ["game_id", "team", "band_group", "toi_seconds", "player_id"],
        ascending=[True, True, True, False, True],
    )
    ordered["usage_rank"] = (
        ordered.groupby(["game_id", "team", "band_group"]).cumcount() + 1
    )
    ordered["ev_band"] = [
        band_for_rank(group, rank)
        for group, rank in zip(ordered["band_group"], ordered["usage_rank"])
    ]

    # The power-play proxy ignores position: a unit is five skaters, so the
    # ranking that stands in for it has to be team-wide.
    team_ordered = ordered.sort_values(
        ["game_id", "team", "toi_seconds", "player_id"],
        ascending=[True, True, False, True],
    )
    team_rank = (
        team_ordered.groupby(["game_id", "team"]).cumcount() + 1
    )
    pp_band = np.where(
        team_rank <= PP_UNIT_SIZE,
        "pp1",
        np.where(team_rank <= 2 * PP_UNIT_SIZE, "pp2", ""),
    )
    team_ordered["team_usage_rank"] = team_rank
    team_ordered["pp_band"] = pp_band
    return team_ordered.sort_index()


@dataclass(frozen=True)
class MinutesDistribution:
    """A predictive distribution over one player's ice time, in seconds.

    Empirical: the quantile grid is the band's own realised ice times from
    games before the one being described. Nothing here assumes a shape, and
    nothing here is a point estimate -- `mean_seconds` is reported because a
    caller will want it, not because it is what the caller should plug in.
    """

    label: str
    basis: str
    n: int
    quantiles: tuple[float, ...]
    mean_seconds: float
    sd_seconds: float
    is_proxy: bool = False
    is_oracle: bool = False

    @property
    def median_seconds(self) -> float:
        return self.quantile(0.5)

    def quantile(self, p: float) -> float:
        """Linear interpolation on the stored grid."""
        if not 0.0 <= float(p) <= 1.0:
            raise ValueError(f"A quantile needs a probability; got {p!r}.")
        return float(np.interp(float(p), PROBS, self.quantiles))

    def spread_seconds(self, lower: float = 0.1, upper: float = 0.9) -> float:
        """Width of the central band, the number that says how much a label
        actually pins down."""
        return self.quantile(upper) - self.quantile(lower)

    def nodes(self, count: int = 25) -> tuple[tuple[float, float], ...]:
        """Equal-probability integration nodes: `(seconds, weight)` pairs.

        Midpoint nodes on the empirical quantile function, so a caller
        integrates over the band's real shape -- including its left tail,
        which is where a fourth-liner's scratch-adjacent nights live.
        """
        if count < 1:
            raise ValueError("An integration needs at least one node.")
        weight = 1.0 / count
        return tuple(
            (self.quantile((i + 0.5) * weight), weight) for i in range(count)
        )

    def expectation(
        self, fn: Callable[[float], float], *, count: int = 25
    ) -> float:
        """E[fn(TOI)] over this distribution, not fn(E[TOI])."""
        return float(
            sum(weight * float(fn(seconds)) for seconds, weight in self.nodes(count))
        )

    def total_variance(
        self,
        mean_fn: Callable[[float], float],
        var_fn: Callable[[float], float],
        *,
        count: int = 25,
    ) -> float:
        """Var[count stat] by the law of total variance.

        `E[Var(N|TOI)] + Var(E[N|TOI])`. The second term is exactly what a
        scalar ice time throws away, and it is largest in the widest bands.
        """
        nodes = self.nodes(count)
        inner = sum(w * float(var_fn(s)) for s, w in nodes)
        mean = sum(w * float(mean_fn(s)) for s, w in nodes)
        spread = sum(w * (float(mean_fn(s)) - mean) ** 2 for s, w in nodes)
        return float(inner + spread)

    def sample(self, size: int, rng: np.random.Generator) -> np.ndarray:
        """Inverse-transform draws, for a caller that would rather simulate."""
        draws = rng.random(int(size))
        return np.interp(draws, PROBS, self.quantiles)

    def describe(self) -> str:
        note = ""
        if self.is_oracle:
            note = " ORACLE"
        elif self.is_proxy:
            note = " proxy"
        return (
            f"{self.label}: mean {self.mean_seconds / 60.0:.1f}m, "
            f"median {self.median_seconds / 60.0:.1f}m, "
            f"p10-p90 {self.spread_seconds() / 60.0:.1f}m, n={self.n}{note}"
        )


@dataclass(frozen=True)
class RoleMinutes:
    """Fitted band distributions, and the blend weight that beats both parts.

    `fitted_before` is the date every game in the fit is strictly earlier
    than. It is carried so a caller cannot apply a table to a game it has
    already seen without the frame saying so.
    """

    fitted_before: str
    n_games: int
    cells: dict[tuple[str, ...], MinutesDistribution]
    league: MinutesDistribution
    blend_weight: float = 1.0
    blend_n: int = 0

    def labels(self) -> tuple[str, ...]:
        return tuple(sorted(key[0] for key in self.cells if len(key) == 1))

    def distribution(self, *labels: str) -> MinutesDistribution:
        """The predictive distribution for a set of Daily Faceoff labels.

        `distribution("f1")` is a first-line forward; `distribution("f1",
        "pp1")` is a first-line forward who is also on the top unit, if
        enough games support that cell -- otherwise it falls back to the
        widest single label available and says which in `basis`.
        """
        wanted = tuple(sorted(_normalise(label) for label in labels))
        if not wanted:
            raise ValueError("Name at least one line label.")
        exact = self.cells.get(wanted)
        if exact is not None and exact.n >= MINIMUM_CELL:
            return exact
        for label in wanted:
            single = self.cells.get((label,))
            if single is not None and single.n >= MINIMUM_CELL:
                return _relabel(single, "+".join(wanted))
        return _relabel(self.league, "+".join(wanted))

    def blend(
        self,
        *labels: str,
        trailing_toi_seconds: float | None,
    ) -> MinutesDistribution:
        """The band prior shrunk toward the player's own trailing ice time.

        The weight is fitted on games before `fitted_before` -- it is not a
        judgement call -- and the returned distribution is the band's shape
        recentred on the blended location. Recentring keeps the spread of the
        band, which is the honest statement: blending moves where a player
        sits, it does not make his minutes more certain.
        """
        prior = self.distribution(*labels)
        if trailing_toi_seconds is None or not np.isfinite(
            float(trailing_toi_seconds)
        ):
            return prior
        weight = float(self.blend_weight)
        centre = weight * float(trailing_toi_seconds) + (1.0 - weight) * prior.mean_seconds
        shift = centre - prior.mean_seconds
        return MinutesDistribution(
            label=f"{prior.label}|trailing",
            basis=f"{prior.basis}+trailing({weight:.2f})",
            n=prior.n,
            quantiles=tuple(q + shift for q in prior.quantiles),
            mean_seconds=centre,
            sd_seconds=prior.sd_seconds,
            is_proxy=prior.is_proxy,
            is_oracle=prior.is_oracle,
        )

    def table(self) -> str:
        """One line per single label, for a report or a sanity check."""
        rows = [self.league.describe()]
        rows.extend(
            self.cells[(label,)].describe()
            for label in KNOWN_LABELS
            if (label,) in self.cells
        )
        return "\n".join(rows)


def _normalise(label: str) -> str:
    text = str(label or "").strip().lower().replace("-", "").replace("_", "")
    if text not in KNOWN_LABELS:
        raise ValueError(
            f"{label!r} is not a line label this lab knows. Expected one of "
            f"{', '.join(KNOWN_LABELS)}."
        )
    return text


def _relabel(source: MinutesDistribution, label: str) -> MinutesDistribution:
    if source.label == label:
        return source
    return MinutesDistribution(
        label=label,
        basis=source.basis,
        n=source.n,
        quantiles=source.quantiles,
        mean_seconds=source.mean_seconds,
        sd_seconds=source.sd_seconds,
        is_proxy=source.is_proxy,
        is_oracle=source.is_oracle,
    )


def _distribution(
    values: np.ndarray, *, label: str, basis: str, is_proxy: bool
) -> MinutesDistribution:
    quantiles = tuple(float(v) for v in np.quantile(values, PROBS))
    return MinutesDistribution(
        label=label,
        basis=basis,
        n=int(values.size),
        quantiles=quantiles,
        mean_seconds=float(values.mean()),
        sd_seconds=float(values.std(ddof=1)) if values.size > 1 else 0.0,
        is_proxy=is_proxy,
    )


def fit_role_minutes(
    logs: pd.DataFrame,
    *,
    before: str,
    trailing_column: str | None = None,
    ranked: pd.DataFrame | None = None,
) -> RoleMinutes:
    """Fit band distributions on games strictly before `before`.

    Walk-forward is the whole point: a band table fitted on a season and
    applied to that season's October is an oracle, and this lab has retracted
    four findings for less. Pass `ranked` when the caller has already banded
    the frame once (refitting per date otherwise re-ranks the whole history
    on every call); it is filtered by date here regardless.

    `trailing_column`, when present, is a strictly-backward-looking ice-time
    mean per row and is used to fit the shrinkage weight between the band
    prior and the player's own recent minutes.
    """
    cutoff = pd.to_datetime(before, errors="coerce")
    if pd.isna(cutoff):
        raise ValueError(f"Not a usable cutoff date: {before!r}")

    frame = with_usage_bands(logs) if ranked is None else ranked
    dates = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame[dates.notna() & (dates < cutoff)]
    if frame.empty:
        raise ValueError(
            f"No games before {before}; a band table needs history and will "
            "not be fitted from nothing."
        )

    toi = frame["toi_seconds"].to_numpy(dtype=float)
    league = _distribution(toi, label="league", basis="league", is_proxy=False)

    cells: dict[tuple[str, ...], MinutesDistribution] = {}
    ev = frame["ev_band"].to_numpy()
    pp = frame["pp_band"].to_numpy()
    for label in EV_BANDS:
        values = toi[ev == label]
        if values.size:
            cells[(label,)] = _distribution(
                values, label=label, basis=label, is_proxy=False
            )
    for label in PP_BANDS:
        values = toi[pp == label]
        if values.size:
            cells[(label,)] = _distribution(
                values, label=label, basis=label, is_proxy=True
            )
    for ev_label in EV_BANDS:
        for pp_label in PP_BANDS:
            values = toi[(ev == ev_label) & (pp == pp_label)]
            if values.size:
                key = tuple(sorted((ev_label, pp_label)))
                cells[key] = _distribution(
                    values, label="+".join(key), basis="+".join(key), is_proxy=True
                )

    weight, blend_n = _fit_blend_weight(frame, trailing_column, cells)
    return RoleMinutes(
        fitted_before=str(pd.Timestamp(cutoff).date()),
        n_games=int(frame.shape[0]),
        cells=cells,
        league=league,
        blend_weight=weight,
        blend_n=blend_n,
    )


def _fit_blend_weight(
    frame: pd.DataFrame,
    trailing_column: str | None,
    cells: dict[tuple[str, ...], MinutesDistribution],
) -> tuple[float, int]:
    """Least-squares weight on the player's own trailing mean, band as the
    other end. Returns 1.0 (all trailing) when there is nothing to fit on."""
    if not trailing_column or trailing_column not in frame.columns:
        return 1.0, 0
    trailing = pd.to_numeric(frame[trailing_column], errors="coerce").to_numpy(
        dtype=float
    )
    band_mean = np.array(
        [
            cells[(label,)].mean_seconds if (label,) in cells else np.nan
            for label in frame["ev_band"].to_numpy()
        ],
        dtype=float,
    )
    actual = frame["toi_seconds"].to_numpy(dtype=float)
    usable = np.isfinite(trailing) & np.isfinite(band_mean) & np.isfinite(actual)
    if usable.sum() < MINIMUM_CELL:
        return 1.0, int(usable.sum())
    gap = trailing[usable] - band_mean[usable]
    denominator = float(np.dot(gap, gap))
    if denominator <= 0:
        return 1.0, int(usable.sum())
    weight = float(np.dot(actual[usable] - band_mean[usable], gap) / denominator)
    return float(min(1.0, max(0.0, weight))), int(usable.sum())


def realised_band(
    logs: pd.DataFrame, *, oracle: bool = False
) -> pd.DataFrame:
    """The band each player actually occupied in each game -- AN ORACLE.

    This is the perfect line label: what the coach's deployment turned out to
    be, read off the game that has already been played. It exists to bound
    what any label feed could ever be worth, and it must never be used to
    describe a game the caller is pricing. The `oracle` flag has to be passed
    explicitly so that no call site can claim it happened by accident.
    """
    if not oracle:
        raise ValueError(
            "realised_band reads a game's own outcome. Pass oracle=True to "
            "say so out loud, and label every number it produces an oracle."
        )
    return with_usage_bands(logs)[
        ["game_id", "player_id", "date", "team", "band_group", "usage_rank",
         "ev_band", "pp_band", "toi_seconds"]
    ]


def distributions_for_labels(
    table: RoleMinutes, labels: Iterable[Sequence[str]]
) -> list[MinutesDistribution]:
    """Convenience for a caller holding a night's worth of Daily Faceoff rows."""
    return [table.distribution(*group) for group in labels]
