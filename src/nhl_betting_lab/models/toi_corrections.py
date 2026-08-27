"""The ice-time-conditional correction, as the card applies it live.

The experiment that put this on the card is `scripts/run_correction_experiment.py`
and its recorded verdict in `data/outputs/correction_experiment.json`. The
pooled Platt correction improved calibration and lost the price backtest —
the EPL lesson, replicated to the letter — while the by-TOI correction beat
the raw model on both measured windows. Under the house rule, the backtest
decides; this module is the deciding side of that decision.

Two properties matter for live use:

**It buckets on expected ice time**, because that is the only ice time a card
can know before puck drop. The experiment was re-run bucketed the same way,
so the thing tested is the thing shipped.

**The curves are fitted on everything before today**, which for live pricing
is exactly walk-forward: today's games are not in the fit. The fit is
refreshed whenever the calibration runs, and the file records when and on how
many samples, so a stale correction announces its age instead of hiding it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.models.calibration import PlattCalibration
from nhl_betting_lab.reports.props_calibration import _bucket_for


CORRECTIONS_FILENAME = "current_corrections.json"


@dataclass
class CurrentCorrections:
    """Per-market, per-bucket Platt curves with a pooled fallback."""

    fitted_at: str = ""
    pooled: dict[str, PlattCalibration] = field(default_factory=dict)
    bucketed: dict[tuple[str, str], PlattCalibration] = field(
        default_factory=dict
    )

    def apply(
        self, market: str, expected_toi_seconds: float, p_over: float
    ) -> float:
        """Correct a stated P(over), by bucket where a curve exists."""
        bucket = _bucket_for(
            float(expected_toi_seconds), market == "goalie_saves"
        )
        correction = self.bucketed.get((market, bucket))
        if correction is None or correction.is_identity:
            correction = self.pooled.get(market)
        if correction is None:
            return p_over
        return correction.apply(p_over)

    def describe(self) -> str:
        if not self.pooled and not self.bucketed:
            return "no correction on file"
        return (
            f"by-TOI correction fitted {self.fitted_at or 'at an unrecorded time'}: "
            f"{len(self.pooled)} pooled curve(s), {len(self.bucketed)} bucket "
            "curve(s)"
        )


def fit_current_corrections(
    grid_samples: pd.DataFrame,
    *,
    fitted_at: str,
    minimum_fit_samples: int = PlattCalibration.MINIMUM_SAMPLES,
) -> CurrentCorrections:
    """Fit today's curves on every grid sample to date."""
    current = CurrentCorrections(fitted_at=fitted_at)
    if grid_samples.empty:
        return current
    toi_column = (
        "expected_toi_seconds"
        if "expected_toi_seconds" in grid_samples.columns
        else "toi_seconds"
    )
    for market, rows in grid_samples.groupby("market"):
        market_key = str(market)
        samples = list(
            zip(
                rows["model_probability"].astype(float),
                rows["outcome"].astype(bool),
            )
        )
        current.pooled[market_key] = PlattCalibration.fit(
            samples, minimum=minimum_fit_samples
        )
        is_goalie = market_key == "goalie_saves"
        buckets: dict[str, list[tuple[float, bool]]] = {}
        for (probability, outcome), toi in zip(
            samples, rows[toi_column].astype(float)
        ):
            buckets.setdefault(_bucket_for(toi, is_goalie), []).append(
                (probability, outcome)
            )
        for bucket, entries in buckets.items():
            current.bucketed[(market_key, bucket)] = PlattCalibration.fit(
                entries, minimum=minimum_fit_samples
            )
    return current


def save_current_corrections(
    current: CurrentCorrections, *, processed_dir: Path | None = None
) -> Path:
    directory = Path(processed_dir) if processed_dir else Path(PROCESSED_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CORRECTIONS_FILENAME
    payload = {
        "fitted_at": current.fitted_at,
        "pooled": {
            market: {
                "intercept": c.intercept,
                "slope": c.slope,
                "fitted_on": c.fitted_on,
            }
            for market, c in current.pooled.items()
        },
        "bucketed": {
            f"{market}|{bucket}": {
                "intercept": c.intercept,
                "slope": c.slope,
                "fitted_on": c.fitted_on,
            }
            for (market, bucket), c in current.bucketed.items()
        },
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def load_current_corrections(
    *, processed_dir: Path | None = None
) -> CurrentCorrections:
    """Load today's curves; absent or unreadable means no correction.

    Failing open to *no correction* is right here: the raw model was the
    card's behaviour before the experiment, and a missing file must degrade
    to that rather than to a crash or a stale guess.
    """
    directory = Path(processed_dir) if processed_dir else Path(PROCESSED_DIR)
    path = directory / CORRECTIONS_FILENAME
    current = CurrentCorrections()
    if not path.is_file():
        return current
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return current
    if not isinstance(payload, dict):
        return current
    current.fitted_at = str(payload.get("fitted_at", ""))

    def _curve(entry: object) -> PlattCalibration | None:
        if not isinstance(entry, dict):
            return None
        try:
            return PlattCalibration(
                intercept=float(entry["intercept"]),
                slope=float(entry["slope"]),
                fitted_on=int(entry.get("fitted_on", 0)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    for market, entry in (payload.get("pooled") or {}).items():
        curve = _curve(entry)
        if curve is not None:
            current.pooled[str(market)] = curve
    for key, entry in (payload.get("bucketed") or {}).items():
        market, _, bucket = str(key).partition("|")
        curve = _curve(entry)
        if curve is not None and bucket:
            current.bucketed[(market, bucket)] = curve
    return current
