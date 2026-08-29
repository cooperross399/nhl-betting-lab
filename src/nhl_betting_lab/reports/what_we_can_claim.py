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
    #: Whether it still excludes zero once the number of markets measured on
    #: the same data is counted. This is the one that governs.
    survives_correction: bool = False
    looks: int = 1
    replication: str = ""
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
        base = (
            f"`{self.market}`: {self.roi:+.1%} over {self.bets:,} bets, 95% "
            f"interval {self.low:+.1%} to {self.high:+.1%}."
        )
        if self.replication:
            return f"{base} {self.replication}"
        if not self.survives_correction:
            correction = (
                f" Correcting for the {self.looks} markets measured on the "
                "same data, it does not exclude zero."
                if self.looks > 1 and not self.includes_zero
                else ""
            )
            return (
                f"{base}{correction} **{NO_DEMONSTRATED_EDGE.capitalize()}**."
            )
        return (
            f"{base} The interval excludes zero even after correcting for the "
            f"{self.looks} markets measured on the same data — which is not "
            "the same as an edge that will persist, and means nothing until "
            "it replicates on a window it was not found on."
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

    def _replicated(self, *, positive: bool) -> list["MarketClaim"]:
        """Claims that survived the search, replicated, and point the way asked.

        The sign is not a detail. A market the model reliably *loses* on
        satisfies "measured, survives correction, replicated" exactly as well
        as one it wins on — and this document once announced that as
        "at least one survived the correction and then replicated", which
        reads as good news and was a loss of 6.6% over nine thousand bets.
        The one document whose job is to stop a number being misread must not
        be the thing misreading it.
        """
        return [
            claim
            for claim in self.claims
            if claim.measured
            and claim.survives_correction
            and claim.replication.lstrip("*").startswith("Replicated")
            and claim.roi is not None
            and ((claim.roi > 0) if positive else (claim.roi < 0))
        ]

    @property
    def demonstrated_edges(self) -> list["MarketClaim"]:
        return self._replicated(positive=True)

    @property
    def demonstrated_deficits(self) -> list["MarketClaim"]:
        return self._replicated(positive=False)

    @property
    def anything_demonstrated(self) -> bool:
        """An *edge*. A replicated loss is demonstrated too, and is not this."""
        return bool(self.demonstrated_edges)

    def headline(self) -> str:
        measured = [claim for claim in self.claims if claim.measured]
        if not measured:
            return (
                "**Nothing in this repository has a demonstrated edge, "
                "because nothing has been measured against real prices yet.** "
                "That is a statement about the evidence, not about the models."
            )
        if not self.anything_demonstrated:
            base = (
                f"**{NO_DEMONSTRATED_EDGE.capitalize()} in any market.** "
                f"{len(measured)} market(s) have been measured against real "
                "prices. Nothing survives correcting for the number of "
                "markets tested and then holds on a window it was not found "
                "on."
            )
            deficits = self.demonstrated_deficits
            if deficits:
                names = ", ".join(f"`{claim.market}`" for claim in deficits)
                base += (
                    f" What *has* survived both tests is a loss: {names}. "
                    "A replicated deficit is a finding, not a null result, "
                    "and it is the finding the model has."
                )
            return base
        return (
            f"{len(measured)} market(s) measured against real prices, and at "
            "least one **profitable** result survived the correction and then "
            "replicated on an "
            "unseen window. Read the per-market lines and the sample sizes "
            "before doing anything with that."
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
    replication = _read_json(directory / "replication.json")
    team = _read_json(directory / "team_markets_measurement.json")

    # A replication verdict outranks any single-window number, so it is
    # attached to the market and printed instead of the interval prose.
    replication_states: dict[str, str] = {}
    for item in replication.get("markets", []) or []:
        if not isinstance(item, dict):
            continue
        state = str(item.get("state", ""))
        if state in {"", "untestable"}:
            continue
        market_key = str(item.get("market", ""))
        if state == "replicated":
            replication_states[market_key] = (
                f"**Replicated** on the "
                f"{replication.get('test_label', 'test')} window."
            )
        else:
            replication_states[market_key] = (
                f"Measured again on the "
                f"{replication.get('test_label', 'test')} window and "
                f"**{state}** there, so **{NO_DEMONSTRATED_EDGE}**."
            )

    calibration_samples = {
        str(item.get("market")): int(item.get("samples", 0) or 0)
        for item in calibration.get("markets", [])
        if isinstance(item, dict)
    }
    by_market = dict(backtest.get("by_market", {}) or {})
    # Team markets are measured in their own report; the claims document
    # covers everything or it is not the claims document.
    for entry in team.get("markets", []) or []:
        if not isinstance(entry, dict):
            continue
        if int(entry.get("bets", 0) or 0) > 0:
            by_market.setdefault(str(entry.get("market")), entry)
    unmeasurable = dict(backtest.get("unmeasurable_markets", {}) or {})
    unmeasurable.setdefault(
        "regulation_3_way",
        "the provider serves it per-event only, with no bulk history; its "
        "evidence accumulates forward once the season starts",
    )

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
                    roi=float(entry.get("roi", 0.0) or 0.0),
                    low=float(entry.get("low", 0.0) or 0.0),
                    high=float(entry.get("high", 0.0) or 0.0),
                    includes_zero=bool(entry.get("includes_zero", True)),
                    survives_correction=bool(
                        entry.get("survives_correction", False)
                    ),
                    looks=int(entry.get("looks", 1) or 1),
                    replication=replication_states.get(market.key, ""),
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
        "A result has to clear three things before it counts: enough bets, an "
        "interval that survives correcting for how many markets were tested, "
        "and then holding on a window it was not found on. Clearing the first "
        "two and failing the third is the ordinary outcome, not a surprise.",
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
