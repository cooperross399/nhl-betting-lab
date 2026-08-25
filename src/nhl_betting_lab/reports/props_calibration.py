"""`data/outputs/props_calibration.md` — does the props model mean what it says?

This report answers one question: when the model says 62%, does it happen 62%
of the time? It does **not** answer whether the model beats a price, and it
says so in its own text, because those two questions get confused constantly
and the confusion always runs in the flattering direction.

The house rule, from `CLAUDE.md`:

    Calibration is a precondition, not a goal. It can rule a model out; it can
    never rule one in. Where historical prices exist, a price-based backtest
    decides.

Three things this report does that a naive calibration report does not:

**It reports counts beside every rate.** A bucket holding nine outcomes says
nothing, and a table that hides that invites exactly the over-reading this
project exists to avoid.

**It splits by volume bucket, not only by probability.** The defect a
per-player count model actually has lives in workload: a fourth-liner priced
off ten minutes and a first-line centre priced off twenty-two are two
different models wearing one name. A correction that straightens the headline
curve while leaving the low-minutes bucket bent has not fixed anything.

**It is walk-forward, and the correction is too.** The correction applied to
any sample is fitted only on samples from strictly earlier game-days. The
report states how many samples were dropped as warm-up rather than quietly
scoring them uncorrected.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.markets import MARKETS_BY_KEY
from nhl_betting_lab.models.calibration import (
    PlattCalibration,
    WalkForwardResult,
    brier_score,
    calibration_verdict,
    log_loss,
    reliability_table,
    walk_forward_calibrate,
)
from nhl_betting_lab.stats import wilson_interval


CALIBRATION_MARKDOWN_FILENAME = "props_calibration.md"
CALIBRATION_JSON_FILENAME = "props_calibration.json"

#: Ice-time buckets for skaters, in minutes. A prop's dominant input is
#: workload, so this is where a per-player count model's real defects show up.
SKATER_TOI_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("under 12 min", 0.0, 12.0),
    ("12-16 min", 12.0, 16.0),
    ("16-20 min", 16.0, 20.0),
    ("20 min and up", 20.0, 1e9),
)

#: Goalies get their own scale. Sharing the skater buckets put every goalie in
#: "20 min and up" — or, worse, labelled a 41-minute start "under 12 min",
#: which is how 330 samples came to sit in a bucket whose name said the
#: opposite of what they were. A goalie who was pulled and one who went the
#: distance face very different shot counts and belong apart.
GOALIE_TOI_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("goalie, pulled or partial (under 50 min)", 0.0, 50.0),
    ("goalie, full game (50 min+)", 50.0, 1e9),
)

TOI_BUCKETS: tuple[tuple[str, float, float], ...] = (
    SKATER_TOI_BUCKETS + GOALIE_TOI_BUCKETS
)

#: Below this many samples a bucket is reported with its count and no verdict.
BUCKET_FLOOR = 100


@dataclass
class MarketCalibration:
    """One market's walk-forward calibration result."""

    market: str
    samples: int
    warmup_skipped: int
    raw_brier: float | None
    corrected_brier: float | None
    raw_log_loss: float | None
    corrected_log_loss: float | None
    correction: PlattCalibration
    raw_table: list[Any] = field(default_factory=list)
    corrected_table: list[Any] = field(default_factory=list)
    volume_rows: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = ""
    #: The ice-time-conditional variant, measured the same way. See
    #: `docs/why_ice_time_gets_its_own_correction.md` for the mechanism.
    grouped_brier: float | None = None
    grouped_volume_rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def improved(self) -> bool:
        if self.raw_brier is None or self.corrected_brier is None:
            return False
        return self.corrected_brier < self.raw_brier

    @property
    def grouped_beats_pooled(self) -> bool:
        if self.grouped_brier is None or self.corrected_brier is None:
            return False
        return self.grouped_brier < self.corrected_brier


@dataclass
class CalibrationReport:
    generated_at: str
    total_samples: int = 0
    markets: list[MarketCalibration] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        if not self.total_samples:
            return (
                "No samples. Nothing about this model's calibration is known, "
                "and the honest statement is that it has not been measured."
            )
        measured = [item for item in self.markets if item.samples >= BUCKET_FLOOR]
        return (
            f"{self.total_samples:,} walk-forward samples across "
            f"{len(self.markets)} market(s); {len(measured)} have enough "
            "samples to say anything about."
        )


def _bucket_for(toi_seconds: float, is_goalie: bool) -> str:
    minutes = float(toi_seconds) / 60.0
    buckets = GOALIE_TOI_BUCKETS if is_goalie else SKATER_TOI_BUCKETS
    for label, low, high in buckets:
        if low <= minutes < high:
            return label
    return buckets[-1][0]


def _volume_rows(
    scored: Sequence[tuple[str, float, float, bool]],
    toi: Sequence[float],
    *,
    is_goalie: bool,
) -> list[dict[str, Any]]:
    """Predicted vs observed per ice-time bucket, raw and corrected."""
    buckets: dict[str, list[tuple[float, float, bool]]] = {}
    for (_, raw, corrected, won), seconds in zip(scored, toi):
        buckets.setdefault(_bucket_for(seconds, is_goalie), []).append(
            (raw, corrected, won)
        )
    rows: list[dict[str, Any]] = []
    for label, _, _ in TOI_BUCKETS:
        entries = buckets.get(label)
        if not entries:
            continue
        count = len(entries)
        hits = sum(1 for _, _, won in entries if won)
        low, high = wilson_interval(hits, count)
        rows.append(
            {
                "bucket": label,
                "samples": count,
                "raw_predicted": sum(raw for raw, _, _ in entries) / count,
                "corrected_predicted": sum(c for _, c, _ in entries) / count,
                "observed": hits / count,
                "observed_low": low,
                "observed_high": high,
                "enough": count >= BUCKET_FLOOR,
            }
        )
    return rows


def measure_market(
    samples: pd.DataFrame,
    *,
    market: str,
    minimum_fit_samples: int = PlattCalibration.MINIMUM_SAMPLES,
    refit_every: int = 5,
) -> MarketCalibration:
    """Walk-forward calibrate one market's samples."""
    subset = samples[samples["market"].astype(str) == market]
    if subset.empty:
        return MarketCalibration(
            market=market,
            samples=0,
            warmup_skipped=0,
            raw_brier=None,
            corrected_brier=None,
            raw_log_loss=None,
            corrected_log_loss=None,
            correction=PlattCalibration.identity(),
            verdict="No samples for this market.",
        )
    ordered = subset.sort_values(["date", "game_id", "player_id", "line"])
    is_goalie = market == "goalie_saves"
    rows = [
        (
            str(row.date),
            float(row.model_probability),
            bool(row.outcome),
            _bucket_for(float(row.toi_seconds), is_goalie),
        )
        for row in ordered.itertuples()
    ]
    result: WalkForwardResult = walk_forward_calibrate(
        rows, minimum_fit_samples=minimum_fit_samples, refit_every=refit_every
    )
    # The same samples, corrected per ice-time bucket instead of pooled. Both
    # are reported: a variant that is only ever shown when it wins is not a
    # measurement, it is a selection.
    grouped: WalkForwardResult = walk_forward_calibrate(
        rows,
        minimum_fit_samples=minimum_fit_samples,
        refit_every=refit_every,
        grouped=True,
    )
    # The correction reported is the last one fitted, i.e. the one a card
    # generated today would use. Reporting an average of corrections would
    # describe a model that never existed.
    correction = (
        result.corrections[-1][1]
        if result.corrections
        else PlattCalibration.identity()
    )
    # Align ice time with the scored samples: the warm-up was dropped from the
    # front of the date-sorted series, so the tail matches.
    toi = ordered["toi_seconds"].tolist()[result.warmup_skipped :]
    return MarketCalibration(
        market=market,
        samples=len(result.scored),
        warmup_skipped=result.warmup_skipped,
        raw_brier=brier_score(result.raw),
        corrected_brier=brier_score(result.corrected),
        raw_log_loss=log_loss(result.raw),
        corrected_log_loss=log_loss(result.corrected),
        correction=correction,
        raw_table=reliability_table(result.raw),
        corrected_table=reliability_table(result.corrected),
        volume_rows=_volume_rows(result.scored, toi, is_goalie=is_goalie),
        verdict=calibration_verdict(result),
        grouped_brier=brier_score(grouped.corrected),
        grouped_volume_rows=_volume_rows(
            grouped.scored,
            ordered["toi_seconds"].tolist()[grouped.warmup_skipped :],
            is_goalie=is_goalie,
        ),
    )


def build_calibration_report(
    samples: pd.DataFrame,
    *,
    now: datetime | None = None,
    minimum_fit_samples: int = PlattCalibration.MINIMUM_SAMPLES,
) -> CalibrationReport:
    moment = now or datetime.now(timezone.utc)
    report = CalibrationReport(
        generated_at=moment.isoformat(timespec="seconds"),
        total_samples=len(samples),
    )
    markets = (
        sorted(set(samples["market"].astype(str)))
        if not samples.empty
        else []
    )
    for market in markets:
        report.markets.append(
            measure_market(
                samples,
                market=market,
                minimum_fit_samples=minimum_fit_samples,
            )
        )
    report.notes = [
        "Calibration can rule a model out. It cannot rule one in. Nothing in "
        "this report says the model beats a price; that question is answered "
        "only by `data/outputs/player_props_backtest.md`.",
        "Every correction applied here was fitted only on samples from "
        "strictly earlier game-days. Warm-up samples are dropped rather than "
        "scored uncorrected, and the count is stated per market.",
        "Ice time is the dominant input to a skater prop, so a correction "
        "that straightens the headline curve while leaving a volume bucket "
        "bent has not fixed the model.",
        "These samples are priced at standard lines, not at prices that were "
        "actually for sale. A well-calibrated model with no price advantage "
        "is a normal and unprofitable thing to have.",
        "Goalie relief appearances produce no sample: a book posts a total "
        "saves line for the expected starter, and nobody can bet a saves prop "
        "on a goalie who enters cold in the second period. See "
        "`docs/goalie_props_need_a_confirmed_starter.md` — the model still "
        "has no way to know who starts, which is a card-level gate rather "
        "than something this measurement fixes.",
        "Both a pooled correction and an ice-time-conditional one are shown "
        "for every market, whether or not the conditional one wins. A variant "
        "reported only when it wins is a selection, not a measurement.",
        "**Neither correction is in force on the card.** The card prices "
        "props with the raw model. Calibration cannot rule a model in, so a "
        "correction ships only when the price-based backtest in "
        "`data/outputs/player_props_backtest.md` says it should — and that "
        "report currently measures nothing, because no historical prices have "
        "been bought.",
    ]
    return report


def _fmt(value: float | None, spec: str = ".4f") -> str:
    return format(value, spec) if isinstance(value, (int, float)) else "-"


def render_calibration(report: CalibrationReport) -> str:
    lines = [
        "# Player props calibration",
        "",
        (
            "When the model says 62%, does it happen 62% of the time? That is "
            "the only question this report answers. Whether the model beats a "
            "price is a different question, answered in "
            "`data/outputs/player_props_backtest.md`."
        ),
        "",
        f"- Generated: {report.generated_at}",
        f"- {report.summary_line()}",
        "",
    ]

    if not report.total_samples:
        lines.extend(
            [
                "## Not measured",
                "",
                (
                    "There are no samples, so nothing about this model's "
                    "calibration is known. The honest statement is that it "
                    "has not been measured — not that it is uncalibrated, and "
                    "certainly not that it is fine."
                ),
                "",
            ]
        )
        lines.extend(["## Standing notes", "", *[f"- {note}" for note in report.notes], ""])
        return "\n".join(lines)

    lines.extend(
        [
            "## Headline, per market",
            "",
            (
                "| Market | Samples | Warm-up dropped | Brier raw | Brier "
                "pooled | Brier by ice time | Correction |"
            ),
            (
                "|:-------|--------:|----------------:|----------:|"
                "-------------:|------------------:|:-----------|"
            ),
        ]
    )
    for item in report.markets:
        label = MARKETS_BY_KEY[item.market].label if item.market in MARKETS_BY_KEY else item.market
        lines.append(
            f"| `{item.market}` ({label}) | {item.samples:,} "
            f"| {item.warmup_skipped:,} | {_fmt(item.raw_brier)} "
            f"| {_fmt(item.corrected_brier)} | {_fmt(item.grouped_brier)} "
            f"| {item.correction.describe()} |"
        )
    lines.append("")

    for item in report.markets:
        lines.extend([f"## `{item.market}`", "", f"- {item.verdict}", ""])
        if item.samples < BUCKET_FLOOR:
            lines.extend(
                [
                    (
                        f"Only {item.samples} samples. That is too few for a "
                        "reliability table to mean anything, so none is shown."
                    ),
                    "",
                ]
            )
            continue

        lines.extend(
            [
                "### Reliability, before and after the correction",
                "",
                "| Bucket | Samples | Predicted (raw) | Predicted (corrected) | Observed |",
                "|:-------|--------:|----------------:|----------------------:|---------:|",
            ]
        )
        corrected_by_label = {row.label: row for row in item.corrected_table}
        for row in item.raw_table:
            fixed = corrected_by_label.get(row.label)
            # The corrected series can land in a different bucket than the raw
            # one — that is what a correction does — so a raw bucket with no
            # corrected counterpart shows a dash rather than a borrowed number.
            corrected = f"{fixed.predicted:.1%}" if fixed is not None else "-"
            lines.append(
                f"| {row.label} | {row.count:,} | {row.predicted:.1%} "
                f"| {corrected} | {row.observed:.1%} |"
            )
        lines.append("")

        if item.volume_rows:
            lines.extend(
                [
                    "### By ice time — where a count model's defects actually live",
                    "",
                    (
                        "| Ice time | Samples | Predicted (raw) | Predicted "
                        "(corrected) | Observed | 95% on observed |"
                    ),
                    "|:---------|--------:|----------------:|----------------------:|---------:|:----------------|",
                ]
            )
            for row in item.volume_rows:
                note = "" if row["enough"] else " ⚠"
                lines.append(
                    f"| {row['bucket']}{note} | {row['samples']:,} "
                    f"| {row['raw_predicted']:.1%} "
                    f"| {row['corrected_predicted']:.1%} "
                    f"| {row['observed']:.1%} "
                    f"| {row['observed_low']:.1%} .. {row['observed_high']:.1%} |"
                )
            lines.extend(
                [
                    "",
                    (
                        "⚠ marks a bucket below "
                        f"{BUCKET_FLOOR} samples. Its numbers are printed with "
                        "their count and should be read as noise, not as a "
                        "finding."
                    ),
                    "",
                ]
            )

        if item.grouped_volume_rows:
            verdict = (
                "beats the pooled curve"
                if item.grouped_beats_pooled
                else "does **not** beat the pooled curve"
            )
            lines.extend(
                [
                    "### The same buckets, corrected per ice-time bucket",
                    "",
                    (
                        f"Brier {_fmt(item.grouped_brier)} against "
                        f"{_fmt(item.corrected_brier)} pooled, so the "
                        f"ice-time-conditional correction {verdict} here. "
                        "The mechanism is in "
                        "`docs/why_ice_time_gets_its_own_correction.md`; the "
                        "decision to use it belongs to the price-based "
                        "backtest, not to this table."
                    ),
                    "",
                    "| Ice time | Samples | Predicted | Observed |",
                    "|:---------|--------:|----------:|---------:|",
                ]
            )
            for row in item.grouped_volume_rows:
                note = "" if row["enough"] else " ⚠"
                lines.append(
                    f"| {row['bucket']}{note} | {row['samples']:,} "
                    f"| {row['corrected_predicted']:.1%} "
                    f"| {row['observed']:.1%} |"
                )
            lines.append("")

    lines.extend(["## Standing notes", "", *[f"- {note}" for note in report.notes], ""])
    return "\n".join(lines)


def save_calibration_report(
    report: CalibrationReport, *, output_dir: Path | None = None
) -> dict[str, str]:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / CALIBRATION_MARKDOWN_FILENAME
    markdown.write_text(render_calibration(report), encoding="utf-8")
    payload = {
        "generated_at": report.generated_at,
        "total_samples": report.total_samples,
        "notes": report.notes,
        "markets": [
            {
                "market": item.market,
                "samples": item.samples,
                "warmup_skipped": item.warmup_skipped,
                "raw_brier": item.raw_brier,
                "corrected_brier": item.corrected_brier,
                "raw_log_loss": item.raw_log_loss,
                "corrected_log_loss": item.corrected_log_loss,
                "correction": {
                    "intercept": item.correction.intercept,
                    "slope": item.correction.slope,
                    "fitted_on": item.correction.fitted_on,
                    "is_identity": item.correction.is_identity,
                },
                "improved": item.improved,
                "grouped_brier": item.grouped_brier,
                "grouped_beats_pooled": item.grouped_beats_pooled,
                "grouped_volume_rows": item.grouped_volume_rows,
                "verdict": item.verdict,
                "volume_rows": item.volume_rows,
            }
            for item in report.markets
        ],
    }
    json_path = directory / CALIBRATION_JSON_FILENAME
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return {"markdown": str(markdown), "json": str(json_path)}
