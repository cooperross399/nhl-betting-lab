"""`data/outputs/team_markets_measurement.md` — the team model, measured.

Team markets are not the point of this lab. They exist so that an edge
anywhere can be found, and a market nobody prices is a market where nobody
can find one. But "not the point" is not a reason to measure them loosely, so
this report is built to the same rules as the props one:

* every number carries its sample size;
* calibration can rule the model out and never in;
* where historical prices exist the price-based backtest decides, and where
  they do not the report says **no price-based measurement** rather than
  offering a calibration figure in its place.

## What the split by market is for

Moneyline, puck line and totals fail differently, and pooling them would hide
which one is broken. In particular the puck line is the market most likely to
expose a modelling error, because covering -1.5 depends on the overtime rule
rather than on the scoring rate — so a model that has overtime wrong looks
fine on moneylines and totals and wrong only here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.config import MIN_EDGE, OUTPUTS_DIR
from nhl_betting_lab.markets import MARKETS_BY_KEY
from nhl_betting_lab.models.calibration import (
    PlattCalibration,
    brier_score,
    calibration_verdict,
    reliability_table,
    walk_forward_calibrate,
)
from nhl_betting_lab.providers.team_names import load_team_name_map, resolve_team
from nhl_betting_lab.models.value import (
    OddsError,
    american_to_implied,
    profit_on_win,
)
from nhl_betting_lab.season import game_date
from nhl_betting_lab.stats import (
    NO_DEMONSTRATED_EDGE,
    ROI_TABLE_HEADER,
    RoiInterval,
    detection_table,
    roi_interval,
    wilson_interval,
)


MEASUREMENT_MARKDOWN_FILENAME = "team_markets_measurement.md"
MEASUREMENT_JSON_FILENAME = "team_markets_measurement.json"

#: Below this many samples a market gets its count and no verdict.
SAMPLE_FLOOR = 200


@dataclass
class MarketMeasurement:
    market: str
    samples: int = 0
    warmup_skipped: int = 0
    raw_brier: float | None = None
    corrected_brier: float | None = None
    correction: PlattCalibration = field(
        default_factory=PlattCalibration.identity
    )
    reliability: list[Any] = field(default_factory=list)
    verdict: str = ""
    priced: RoiInterval | None = None

    @property
    def has_price_evidence(self) -> bool:
        return self.priced is not None and self.priced.bets > 0


@dataclass
class TeamMeasurementReport:
    generated_at: str
    total_samples: int = 0
    games: int = 0
    markets: list[MarketMeasurement] = field(default_factory=list)
    priced_outcomes: int = 0
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        if not self.total_samples:
            return (
                "No samples. The team model has not been measured, and that "
                "is the honest statement — not that it is fine."
            )
        measured = [item for item in self.markets if item.has_price_evidence]
        return (
            f"{self.total_samples:,} walk-forward samples across "
            f"{len(self.markets)} market(s) and {self.games:,} games; "
            f"{len(measured)} market(s) have any price-based evidence."
        )


def measure_calibration(
    samples: pd.DataFrame,
    *,
    market: str,
    minimum_fit_samples: int = PlattCalibration.MINIMUM_SAMPLES,
    refit_every: int = 5,
) -> MarketMeasurement:
    """Walk-forward calibrate one team market."""
    subset = samples[samples["market"].astype(str) == market]
    # A push is not an outcome the model was asked about, so it is excluded
    # rather than scored as a loss. Scoring pushes as losses would make every
    # whole-number total look worse than it is.
    subset = subset[~subset["push"].astype(bool)]
    if subset.empty:
        return MarketMeasurement(market=market, verdict="No samples.")

    ordered = subset.sort_values(["date", "game_id", "selection", "line"])
    rows = [
        (str(row.date), float(row.model_probability), bool(row.outcome))
        for row in ordered.itertuples()
    ]
    result = walk_forward_calibrate(
        rows, minimum_fit_samples=minimum_fit_samples, refit_every=refit_every
    )
    correction = (
        result.corrections[-1][1]
        if result.corrections
        else PlattCalibration.identity()
    )
    return MarketMeasurement(
        market=market,
        samples=len(result.scored),
        warmup_skipped=result.warmup_skipped,
        raw_brier=brier_score(result.raw),
        corrected_brier=brier_score(result.corrected),
        correction=correction,
        reliability=reliability_table(result.raw),
        verdict=calibration_verdict(result),
    )


def _puck_line_selection(selection: str, line: float | None) -> tuple[str, float | None]:
    """Translate a price row's puck-line naming onto the samples' naming.

    The provider says `home` at line `-1.5`; the samples say `home_minus` at
    `-1.5`. The two describe one bet, and joining them on the raw strings
    silently measured the puck line as having no price evidence at all —
    the third join-vocabulary mismatch this repository has found, after team
    names and game dates.
    """
    side = str(selection).strip().lower()
    if line is None or side not in {"home", "away"}:
        return side, line
    suffix = "minus" if float(line) < 0 else "plus"
    return f"{side}_{suffix}", line


def measure_prices(
    prices: pd.DataFrame,
    samples: pd.DataFrame,
    *,
    market: str,
    edge_threshold: float = MIN_EDGE,
    team_names: Mapping[str, str] | None = None,
    looks: int = 1,
) -> RoiInterval | None:
    """Flat-stake ROI against historical team prices, or None if there are none."""
    if prices.empty or samples.empty:
        return None
    priced = prices[prices["market"].astype(str) == market]
    if priced.empty:
        return None
    # The provider says "Toronto Maple Leafs"; the samples say "TOR".
    names = dict(team_names or load_team_name_map())

    lookup: dict[tuple, tuple[float, bool, bool]] = {}
    for row in samples[samples["market"].astype(str) == market].itertuples():
        line = None if row.line is None or pd.isna(row.line) else float(row.line)
        lookup[
            (
                str(row.date)[:10],
                str(row.home_team),
                str(row.away_team),
                str(row.selection),
                line,
            )
        ] = (float(row.model_probability), bool(row.outcome), bool(row.push))

    returns: list[float] = []
    wins = pushes = 0
    for row in priced.itertuples():
        try:
            line_value = getattr(row, "line", None)
            line = (
                None
                if line_value is None or pd.isna(line_value)
                else float(line_value)
            )
        except (TypeError, ValueError):
            line = None
        # The league game date, not the UTC commence date. An evening face-off
        # is the next day in UTC and joining on that discards most of a season.
        selection = str(getattr(row, "selection", ""))
        if market == "puck_line":
            selection, line = _puck_line_selection(selection, line)
        key = (
            game_date(
                getattr(row, "commence_time", "") or getattr(row, "date", "")
            ),
            resolve_team(getattr(row, "home_team", ""), names)
            or str(getattr(row, "home_team", "")),
            resolve_team(getattr(row, "away_team", ""), names)
            or str(getattr(row, "away_team", "")),
            selection,
            line,
        )
        found = lookup.get(key)
        if found is None:
            continue
        probability, won, push = found
        try:
            implied = american_to_implied(getattr(row, "american_odds"))
            price = float(getattr(row, "american_odds"))
        except (OddsError, TypeError, ValueError):
            continue
        if probability - implied < edge_threshold:
            continue
        if push:
            returns.append(0.0)
            pushes += 1
            continue
        returns.append(profit_on_win(price) if won else -1.0)
        wins += 1 if won else 0
    if not returns:
        return None
    return roi_interval(returns, wins=wins, pushes=pushes, looks=looks)


def build_team_measurement(
    samples: pd.DataFrame,
    prices: pd.DataFrame | None = None,
    *,
    edge_threshold: float = MIN_EDGE,
    now: datetime | None = None,
    minimum_fit_samples: int = PlattCalibration.MINIMUM_SAMPLES,
    team_names: Mapping[str, str] | None = None,
) -> TeamMeasurementReport:
    moment = now or datetime.now(timezone.utc)
    price_frame = (
        prices if prices is not None else pd.DataFrame(columns=["market"])
    )
    report = TeamMeasurementReport(
        generated_at=moment.isoformat(timespec="seconds"),
        total_samples=len(samples),
        games=int(samples["game_id"].nunique()) if not samples.empty else 0,
        priced_outcomes=len(price_frame),
    )
    markets = (
        sorted(set(samples["market"].astype(str))) if not samples.empty else []
    )
    # Every team market measured on the same games is one family of tests,
    # exactly as the props are.
    looks = max(1, len(markets))
    for market in markets:
        measurement = measure_calibration(
            samples, market=market, minimum_fit_samples=minimum_fit_samples
        )
        measurement.priced = measure_prices(
            price_frame,
            samples,
            market=market,
            edge_threshold=edge_threshold,
            team_names=team_names,
            looks=looks,
        )
        report.markets.append(measurement)

    report.notes = [
        "Team markets are not the point of this lab. They are measured to the "
        "same standard anyway, because a market nobody prices is a market "
        "where nobody can find an edge.",
        "The puck line is the market most likely to expose a modelling error: "
        "covering -1.5 depends on the overtime rule rather than on the "
        "scoring rate, so a model that has overtime wrong looks fine on "
        "moneylines and totals and wrong only here.",
        "A push is excluded rather than scored as a loss. Scoring pushes as "
        "losses would make every whole-number total look worse than it is.",
        "Calibration can rule this model out; it cannot rule it in. Where "
        "historical prices exist the backtest decides, and where they do not "
        "this report says so rather than offering a calibration number in "
        "their place.",
    ]
    return report


def _fmt(value: float | None, spec: str = ".4f") -> str:
    return format(value, spec) if isinstance(value, (int, float)) else "-"


def render_team_measurement(report: TeamMeasurementReport) -> str:
    lines = [
        "# Team markets measurement",
        "",
        (
            "Moneyline, puck line and totals — calibrated walk-forward, and "
            "measured against real prices wherever any have been bought."
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
                    "There are no samples, so nothing about the team model is "
                    "known. That is the honest statement — not that it is "
                    "fine."
                ),
                "",
                *["## Standing notes", ""],
                *[f"- {note}" for note in report.notes],
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Calibration",
            "",
            "| Market | Samples | Brier raw | Brier corrected | Correction |",
            "|:-------|--------:|----------:|----------------:|:-----------|",
        ]
    )
    for item in report.markets:
        label = (
            MARKETS_BY_KEY[item.market].label
            if item.market in MARKETS_BY_KEY
            else item.market
        )
        lines.append(
            f"| `{item.market}` ({label}) | {item.samples:,} "
            f"| {_fmt(item.raw_brier)} | {_fmt(item.corrected_brier)} "
            f"| {item.correction.describe()} |"
        )
    lines.append("")

    for item in report.markets:
        lines.extend([f"### `{item.market}`", "", f"- {item.verdict}", ""])
        if item.samples < SAMPLE_FLOOR or not item.reliability:
            lines.extend(
                [
                    f"Only {item.samples} samples; no reliability table is shown.",
                    "",
                ]
            )
            continue
        lines.extend(
            [
                "| Bucket | Samples | Predicted | Observed | 95% on observed |",
                "|:-------|--------:|----------:|---------:|:----------------|",
            ]
        )
        for row in item.reliability:
            low, high = wilson_interval(
                int(round(row.observed * row.count)), row.count
            )
            lines.append(
                f"| {row.label} | {row.count:,} | {row.predicted:.1%} "
                f"| {row.observed:.1%} | {low:.1%} .. {high:.1%} |"
            )
        lines.append("")

    lines.extend(["## Measured against real prices", ""])
    measured = [item for item in report.markets if item.has_price_evidence]
    if measured:
        lines.append(ROI_TABLE_HEADER)
        for item in measured:
            lines.append(item.priced.as_row(f"`{item.market}`"))
        lines.append("")
        for item in measured:
            lines.append(f"- `{item.market}`: {item.priced.verdict()}")
        lines.extend(["", "### How much data would settle it", "", detection_table(), ""])
    else:
        lines.extend(
            [
                (
                    f"**No price-based measurement.** {report.priced_outcomes:,} "
                    "historical team price(s) are on disk, and no market has "
                    "enough matched, above-threshold outcomes to measure. This "
                    f"means **{NO_DEMONSTRATED_EDGE}** — and equally, no "
                    "demonstrated absence of one."
                ),
                "",
                (
                    "The calibration numbers above are **not** a substitute. "
                    "They say the model's probabilities are internally "
                    "sensible; they say nothing about whether the market "
                    "disagrees with them profitably."
                ),
                "",
            ]
        )

    lines.extend(["## Standing notes", "", *[f"- {note}" for note in report.notes], ""])
    return "\n".join(lines)


def save_team_measurement(
    report: TeamMeasurementReport, *, output_dir: Path | None = None
) -> dict[str, str]:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / MEASUREMENT_MARKDOWN_FILENAME
    markdown.write_text(render_team_measurement(report), encoding="utf-8")
    payload = {
        "generated_at": report.generated_at,
        "total_samples": report.total_samples,
        "games": report.games,
        "priced_outcomes": report.priced_outcomes,
        "notes": report.notes,
        "markets": [
            {
                "market": item.market,
                "samples": item.samples,
                "raw_brier": item.raw_brier,
                "corrected_brier": item.corrected_brier,
                "verdict": item.verdict,
                "has_price_evidence": item.has_price_evidence,
                "bets": item.priced.bets if item.priced else 0,
                "roi": item.priced.roi if item.priced else None,
                "low": item.priced.low if item.priced else None,
                "high": item.priced.high if item.priced else None,
                "includes_zero": (
                    item.priced.includes_zero if item.priced else True
                ),
                "looks": item.priced.looks if item.priced else 1,
                "survives_correction": (
                    item.priced.survives_correction if item.priced else False
                ),
            }
            for item in report.markets
        ],
    }
    json_path = directory / MEASUREMENT_JSON_FILENAME
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return {"markdown": str(markdown), "json": str(json_path)}
