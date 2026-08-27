"""Walk-forward correction timelines, so a backtest can apply a correction
that could not have seen the bet it corrects.

The calibration report fits Platt corrections and shows they straighten every
reliability bucket. The house rule says that is not enough: **a change that
improves calibration but loses the price backtest does not ship.** Running
that comparison needs corrections *as they would have existed on each bet's
date* — a single correction fitted on everything would leak the season into
its own bets and flatter whichever variant is worse.

So this builds a timeline: refits on a cadence, each fit using only grid
samples from strictly earlier dates, looked up by "the latest fit strictly
before this bet's game date". The same leak rule as everywhere else, in the
same words.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from nhl_betting_lab.models.calibration import PlattCalibration
from nhl_betting_lab.reports.props_calibration import _bucket_for


#: Refit cadence in days, matching the sample generator's own.
REFIT_DAYS = 14


@dataclass
class CorrectionTimeline:
    """Per-market (and optionally per-bucket) corrections through time."""

    #: market -> sorted list of (from_date_iso, correction)
    pooled: dict[str, list[tuple[str, PlattCalibration]]] = field(
        default_factory=dict
    )
    #: (market, bucket) -> sorted list of (from_date_iso, correction)
    bucketed: dict[tuple[str, str], list[tuple[str, PlattCalibration]]] = field(
        default_factory=dict
    )

    def _lookup(
        self, series: list[tuple[str, PlattCalibration]] | None, day: str
    ) -> PlattCalibration | None:
        if not series:
            return None
        dates = [entry[0] for entry in series]
        # The correction in force on `day` is the latest one whose from-date
        # is <= day; each from-date's fit saw only strictly earlier samples.
        index = bisect_left(dates, day)
        if index < len(dates) and dates[index] == day:
            index += 1
        if index == 0:
            return None
        return series[index - 1][1]

    def correct_pooled(self, market: str, day: str, p_over: float) -> float:
        correction = self._lookup(self.pooled.get(market), day)
        return correction.apply(p_over) if correction else p_over

    def correct_bucketed(
        self, market: str, day: str, toi_seconds: float, p_over: float
    ) -> float:
        bucket = _bucket_for(toi_seconds, market == "goalie_saves")
        correction = self._lookup(self.bucketed.get((market, bucket)), day)
        if correction is None or correction.is_identity:
            # A bucket with too little history falls back to the pooled curve,
            # exactly as the calibration report's grouped variant does.
            return self.correct_pooled(market, day, p_over)
        return correction.apply(p_over)


def build_timeline(
    grid_samples: pd.DataFrame,
    *,
    refit_days: int = REFIT_DAYS,
    minimum_fit_samples: int = PlattCalibration.MINIMUM_SAMPLES,
) -> CorrectionTimeline:
    """Fit the timeline from grid-expanded samples (probability + outcome).

    `grid_samples` needs `date`, `market`, `model_probability`, `outcome`,
    and an ice-time column. Buckets use **expected** ice time where the column
    exists, because expected TOI is the only TOI a live card can know — a
    correction fitted on the actual would be tested on information deployment
    cannot have. Every fit dated D uses only rows with date strictly before D.
    """
    timeline = CorrectionTimeline()
    if grid_samples.empty:
        return timeline
    frame = grid_samples.copy()
    frame["date"] = frame["date"].astype(str).str.slice(0, 10)
    frame = frame.sort_values("date")

    first = date.fromisoformat(str(frame["date"].min()))
    last = date.fromisoformat(str(frame["date"].max()))

    for market, rows in frame.groupby("market"):
        market_key = str(market)
        is_goalie = market_key == "goalie_saves"
        rows = rows.reset_index(drop=True)
        dates = rows["date"].tolist()
        probabilities = rows["model_probability"].astype(float).tolist()
        outcomes = rows["outcome"].astype(bool).tolist()
        toi_column = (
            "expected_toi_seconds"
            if "expected_toi_seconds" in rows.columns
            else "toi_seconds"
        )
        buckets = [
            _bucket_for(float(toi), is_goalie)
            for toi in rows[toi_column].tolist()
        ]

        cursor = first + timedelta(days=refit_days)
        while cursor <= last + timedelta(days=refit_days):
            cutoff = cursor.isoformat()
            end = bisect_left(dates, cutoff)
            history = list(zip(probabilities[:end], outcomes[:end]))
            if len(history) >= minimum_fit_samples:
                fitted = PlattCalibration.fit(
                    history, minimum=minimum_fit_samples
                )
                timeline.pooled.setdefault(market_key, []).append(
                    (cutoff, fitted)
                )
                by_bucket: dict[str, list[tuple[float, bool]]] = {}
                for probability, outcome, bucket in zip(
                    probabilities[:end], outcomes[:end], buckets[:end]
                ):
                    by_bucket.setdefault(bucket, []).append(
                        (probability, outcome)
                    )
                for bucket, entries in by_bucket.items():
                    timeline.bucketed.setdefault(
                        (market_key, bucket), []
                    ).append(
                        (cutoff, PlattCalibration.fit(entries, minimum=minimum_fit_samples))
                    )
            cursor += timedelta(days=refit_days)
    return timeline
