"""`data/outputs/what_we_can_claim.md` — the generated version of the honesty doc.

`docs/what_we_can_and_cannot_claim.md` is written by hand and states the
rules. This is its machine-generated counterpart: it reads whatever
measurement outputs exist and writes down what they actually support, in the
fixed vocabulary this repository uses.

It exists so that "what does the evidence say" has an answer that cannot drift
from the evidence. A hand-written summary goes stale the moment a measurement
is re-run; this one is re-run with it.

Three rules it enforces mechanically:

* Every measured number is printed with its sample size.
* An interval that includes zero is reported with the exact phrase
  "no demonstrated edge", never a softer one.
* A market with no price-based measurement is listed under "not measured",
  never under "no value" and never with a calibration number standing in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.markets import ALL_MARKETS
from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE, detection_table


CLAIMS_MARKDOWN_FILENAME = "what_we_can_claim.md"

#: Phrases that must never appear in this document. A generated summary that
#: reaches for one of these has stopped reporting and started selling.
FORBIDDEN_PHRASES = (
    "guaranteed",
    "sure thing",
    "can't lose",
    "proven edge",
    "beats the market",
)


@dataclass
class MarketClaim:
    market: str
    measured: bool
    bets: int = 0
    roi: float | None = None
    low: float | None = None
    high: float | None = None
    includes_zero: bool = True
    calibration_samples: int = 0
    allowlisted: bool = False
    reason_unmeasured: str = ""

    def sentence(self) -> str:
        if not self.measured:
            reason = self.reason_unmeasured.strip().rstrip(".")
            base = (
                f"`{self.market}` has **no price-based measurement**"
                + (f": {reason}." if reason else ".")
            )
            if self.calibration_samples:
                base += (
                    f" It has been calibration-checked on "
                    f"{self.calibration_samples:,} walk-forward samples, which "
                    "can rule the model out and can never rule it in. That is "
                    "not evidence of an edge and is not offered as any."
                )
            return base
        assert self.roi is not None
        if self.includes_zero:
            return (
                f"`{self.market}`: {self.roi:+.1%} over {self.bets:,} bets, "
                f"95% interval {self.low:+.1%} to {self.high:+.1%}. The "
                f"interval includes zero, which means **{NO_DEMONSTRATED_EDGE}**."
            )
        return (
            f"`{self.market}`: {self.roi:+.1%} over {self.bets:,} bets, 95% "
            f"interval {self.low:+.1%} to {self.high:+.1%}. The interval "
            "excludes zero on this sample and this data, which is not the "
            "same as an edge that will persist."
        )


@dataclass
class ClaimsReport:
    generated_at: str
    claims: list[MarketClaim] = field(default_factory=list)
    overall_bets: int = 0
    overall_roi: float | None = None
    overall_includes_zero: bool = True
    policy_status: str = ""
    allowlisted_markets: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)

    @property
    def anything_demonstrated(self) -> bool:
        return any(
            claim.measured and not claim.includes_zero for claim in self.claims
        )

    def headline(self) -> str:
        measured = [claim for claim in self.claims if claim.measured]
        if not measured:
            return (
                "**Nothing in this repository has a demonstrated edge, "
                "because nothing has been measured against real prices yet.** "
                "That is a statement about the evidence, not about the models."
            )
        if not self.anything_demonstrated:
            return (
                f"**{NO_DEMONSTRATED_EDGE.capitalize()} in any market.** "
                f"{len(measured)} market(s) have been measured against real "
                "prices and every interval includes zero."
            )
        return (
            f"{len(measured)} market(s) measured against real prices; at least "
            "one interval excludes zero on this sample. Read the per-market "
            "lines and the sample sizes before doing anything with that."
        )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_claims_report(
    *,
    output_dir: Path | None = None,
    policy_status: str = "",
    allowlisted_markets: tuple[str, ...] = (),
    now: datetime | None = None,
) -> ClaimsReport:
    """Read whatever measurements exist and state what they support."""
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    moment = now or datetime.now(timezone.utc)
    backtest = _read_json(directory / "player_props_backtest.json")
    calibration = _read_json(directory / "props_calibration.json")

    calibration_samples = {
        str(item.get("market")): int(item.get("samples", 0) or 0)
        for item in calibration.get("markets", [])
        if isinstance(item, dict)
    }
    by_market = backtest.get("by_market", {})
    unmeasurable = backtest.get("unmeasurable_markets", {}) or {}

    report = ClaimsReport(
        generated_at=moment.isoformat(timespec="seconds"),
        policy_status=policy_status,
        allowlisted_markets=tuple(allowlisted_markets),
    )

    for market in ALL_MARKETS:
        entry = by_market.get(market.key) if isinstance(by_market, dict) else None
        if isinstance(entry, dict) and int(entry.get("bets", 0) or 0) > 0:
            report.claims.append(
                MarketClaim(
                    market=market.key,
                    measured=True,
                    bets=int(entry["bets"]),
                    roi=float(entry.get("roi", 0.0)),
                    low=float(entry.get("low", 0.0)),
                    high=float(entry.get("high", 0.0)),
                    includes_zero=bool(entry.get("includes_zero", True)),
                    calibration_samples=calibration_samples.get(market.key, 0),
                    allowlisted=market.key in allowlisted_markets,
                )
            )
            continue
        report.claims.append(
            MarketClaim(
                market=market.key,
                measured=False,
                calibration_samples=calibration_samples.get(market.key, 0),
                allowlisted=market.key in allowlisted_markets,
                reason_unmeasured=str(
                    unmeasurable.get(market.key, "")
                    or "no historical prices have been bought for it yet"
                ),
            )
        )

    overall = backtest.get("overall")
    if isinstance(overall, dict) and int(overall.get("bets", 0) or 0) > 0:
        report.overall_bets = int(overall["bets"])
        report.overall_roi = float(overall.get("roi", 0.0))
        report.overall_includes_zero = bool(overall.get("includes_zero", True))

    report.notes = [
        "An interval that includes zero means "
        f"**{NO_DEMONSTRATED_EDGE}**. Not 'promising', not 'trending "
        "positive', not 'small but positive'.",
        "Calibration can rule a model out. It can never rule one in. A market "
        "with only a calibration number has no price-based evidence, and this "
        "document will not present one as though it did.",
        "Prop prices are one-sided at most books, so every measured prop edge "
        "here is understated rather than overstated.",
        "The first genuinely out-of-sample evidence this project will ever "
        "have is the season being played, one game-day at a time. That is "
        "worth more than any further slicing of the seasons already in the "
        "file.",
        "No market reaches the card without a reviewed human approval, "
        "whatever the numbers above say.",
    ]
    return report


def render_claims(report: ClaimsReport) -> str:
    lines = [
        "# What the evidence actually supports",
        "",
        (
            "Generated from the measurement outputs, so it cannot drift from "
            "them. The hand-written rules live in "
            "`docs/what_we_can_and_cannot_claim.md`."
        ),
        "",
        f"- Generated: {report.generated_at}",
        "",
        report.headline(),
        "",
    ]

    if report.overall_bets:
        lines.extend(
            [
                "## Across every measured market",
                "",
                (
                    f"{report.overall_roi:+.1%} over {report.overall_bets:,} "
                    "bets. "
                    + (
                        f"The interval includes zero: **{NO_DEMONSTRATED_EDGE}**."
                        if report.overall_includes_zero
                        else "The interval excludes zero on this sample."
                    )
                ),
                "",
            ]
        )

    measured = [claim for claim in report.claims if claim.measured]
    unmeasured = [claim for claim in report.claims if not claim.measured]

    if measured:
        lines.extend(["## Measured against real prices", ""])
        lines.extend([f"- {claim.sentence()}" for claim in measured])
        lines.append("")

    lines.extend(["## Not measured against real prices", ""])
    if unmeasured:
        lines.extend([f"- {claim.sentence()}" for claim in unmeasured])
    else:
        lines.append("- Every market this lab prices has been measured.")
    lines.extend(
        [
            "",
            (
                "A market in this list is **not** a market judged to have no "
                "value. It is a market with no price-based evidence either "
                "way, and nothing in this repository will present the two as "
                "the same thing."
            ),
            "",
        ]
    )

    lines.extend(
        [
            "## How much data would settle it",
            "",
            detection_table(),
            "",
            (
                "The NHL's advantage over a smaller league is volume: about "
                "1,312 regular-season games a season with many prop markets "
                "per game. That is the reason props are the centre of this "
                "lab — not because prop edges are believed to be larger, but "
                "because props are the only part of the system that can "
                "accumulate enough bets to ever be measured."
            ),
            "",
        ]
    )

    if report.policy_status:
        lines.extend(
            [
                "## What the card is actually allowed to use",
                "",
                f"- Provider policy: **{report.policy_status}**",
                (
                    "- Allowlisted markets: **"
                    + (", ".join(report.allowlisted_markets) or "none")
                    + "**"
                ),
                "",
            ]
        )

    lines.extend(["## Standing notes", "", *[f"- {note}" for note in report.notes], ""])
    return "\n".join(lines)


def save_claims(
    report: ClaimsReport, *, output_dir: Path | None = None
) -> str:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CLAIMS_MARKDOWN_FILENAME
    rendered = render_claims(report)
    lowered = rendered.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            raise ValueError(
                f"The claims document contains the phrase {phrase!r}, which "
                "this repository does not use about its own results."
            )
    path.write_text(rendered, encoding="utf-8")
    return str(path)
