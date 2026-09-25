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

And one it enforces about itself: it says only what the measurement outputs
it read support. A measurement output it could not find is named as missing,
never read as "nothing was bought" — see `_unmeasured_reason`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nhl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from nhl_betting_lab.markets import ALL_MARKETS, Market
from nhl_betting_lab.reports.player_props_backtest import (
    BACKTEST_JSON_FILENAME,
    by_market_with_other_windows,
    window_phrase,
)
from nhl_betting_lab.reports.team_markets_measurement import (
    MEASUREMENT_JSON_FILENAME,
)
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
    #: Set only when the figure comes from a window other than the one the
    #: rest of its report describes.
    window: str = ""

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
        where = f", measured only in the {self.window}" if self.window else ""
        base = (
            f"`{self.market}`: {self.roi:+.1%} over {self.bets:,} bets, 95% "
            f"interval {self.low:+.1%} to {self.high:+.1%}{where}."
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
        # The sign again. This branch was written for a positive result and
        # was first reached by `points` at -4.5%, which it called an edge.
        outcome = "an edge" if self.roi > 0 else "a loss"
        return (
            f"{base} The interval excludes zero even after correcting for the "
            f"{self.looks} markets measured on the same data — which is not "
            f"the same as {outcome} that will persist, and means nothing until "
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
    #: Which snapshot window the figures describe, derived from the reports.
    window_note: str = ""
    #: The window the across-market prop figure describes.
    overall_window: str = ""
    #: Measurement outputs this document looked for and could not read, each
    #: as a sentence fragment naming the file and the directory. Empty when
    #: both the props and the team measurement were read.
    unread_sources: list[str] = field(default_factory=list)

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
        if not measured and self.unread_sources:
            # A fresh checkout holds none of the gitignored measurement JSONs,
            # and this headline used to read "nothing has been measured
            # against real prices yet" there — over a tracked contract file
            # recording ten measured markets.
            return (
                "**Nothing here shows a demonstrated edge, and this document "
                "cannot say whether anything would:** "
                + "; ".join(self.unread_sources)
                + ". That is a statement about which measurement outputs it "
                "found, not about the evidence or the models."
            )
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


def _shown(directory: Path) -> str:
    """A directory as a reader should see it: repository-relative when inside."""
    try:
        return directory.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return str(directory)


def unread_reason(path: Path) -> str:
    """Why a measurement output could not be read, or "" when it was.

    `_read_json` returns `{}` for a file that is absent, truncated, or not an
    object, which is right for reading and wrong for reporting: `{}` is also
    what a measurement with nothing in it looks like.
    """
    where = _shown(path.parent)
    if not path.is_file():
        return f"`{path.name}` was not found in `{where}`"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = None
    if not isinstance(payload, dict):
        return f"`{path.name}` in `{where}` could not be read"
    return ""


def _unmeasured_reason(
    market: Market,
    *,
    unmeasurable: dict[str, Any],
    backtest: dict[str, Any],
    props_unread: str,
    team: dict[str, Any],
    team_unread: str,
) -> str:
    """Why `market` has no price-based measurement, in words its inputs support.

    ## What this replaced

    Every market this document found no bets for used to get "no historical
    prices have been bought for it yet" — a statement about purchases that
    nothing here ever checked, since this module reads measurement outputs
    and never the price store. Measured, it was false three ways:

    * A Historical Props Purchase run in mode `buy` or `probe` does not
      rebuild the team measurement, and `team_markets_measurement.json` is
      gitignored and in no artifact it restores; its claims step still runs.
      With 308,944 bought team price rows on disk, the document it uploaded
      said moneyline, puck line and totals had never been bought.
    * A team measurement that scored prices and placed no bet (seen 48,000,
      unmatched 48,000, bets 0) printed the same sentence.
    * In a fresh checkout, where every measurement JSON is gitignored, the
      regenerated contract file listed eleven price-measured markets as never
      bought.

    Now: a measurement output that could not be read is named; a team
    measurement that saw prices says where they went; and "holds no price
    for it" is said only from the team measurement's own count of the store
    it read (`stored_by_market`, recorded since 2026-09-25).
    """
    explicit = str(unmeasurable.get(market.key, "") or "").strip()
    if explicit:
        return explicit
    if market.is_prop:
        if props_unread:
            return (
                f"{props_unread}, so this document has no props measurement "
                "to read, which says nothing about whether its prices were "
                "bought"
            )
        window = window_phrase(backtest)
        return "the props backtest placed no bet on it" + (
            f" in the {window}" if window else ""
        )
    if team_unread:
        return (
            f"{team_unread}, so this document has no team measurement to "
            "read, which says nothing about whether its prices were bought"
        )
    window = window_phrase(team)
    where = f" in the {window}" if window else ""
    entry = next(
        (
            item
            for item in team.get("markets", []) or []
            if isinstance(item, dict) and str(item.get("market")) == market.key
        ),
        None,
    )
    accounting = (entry or {}).get("accounting")
    counts = accounting if isinstance(accounting, dict) else {}
    seen = int(counts.get("seen", 0) or 0)
    if seen:
        return (
            f"{seen:,} price(s){where} were scored against the model, one "
            "per wager, and none became a bet: "
            f"{int(counts.get('unresolved', 0) or 0):,} named a team the "
            "team-name map could not resolve, "
            f"{int(counts.get('unmatched', 0) or 0):,} were unmatched, "
            f"{int(counts.get('unparseable', 0) or 0):,} could not be parsed "
            f"and {int(counts.get('below_threshold', 0) or 0):,} fell below "
            "the edge threshold"
        )
    stored_by_market = team.get("stored_by_market")
    if isinstance(stored_by_market, dict):
        stored = int(stored_by_market.get(market.key, 0) or 0)
        if not stored:
            return (
                "the historical team price store the team measurement read "
                "holds no price for it"
            )
        if entry is None:
            return (
                f"{stored:,} historical price row(s) for it are stored, and "
                "the team measurement has no model samples for it, so none "
                "was scored"
            )
        if window:
            return (
                f"{stored:,} historical price row(s) for it are stored, and "
                f"none was captured in the {window} before face-off, which is "
                "the window the team measurement read"
            )
        return (
            f"{stored:,} historical price row(s) for it are stored, and none "
            "was scored"
        )
    # A team measurement written before it recorded the store says only
    # what it scored.
    return f"the team measurement scored no price for it{where}"


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
    backtest = _read_json(directory / BACKTEST_JSON_FILENAME)
    calibration = _read_json(directory / "props_calibration.json")
    replication = _read_json(directory / "replication.json")
    team = _read_json(directory / MEASUREMENT_JSON_FILENAME)
    # Read apart from the payloads, because `{}` means "absent" and "empty"
    # alike, and this document must never say the second about the first.
    props_unread = unread_reason(directory / BACKTEST_JSON_FILENAME)
    team_unread = unread_reason(directory / MEASUREMENT_JSON_FILENAME)

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
    # A prop market the contract window has no bets for is read from another
    # window and says which; one it measured keeps that measurement.
    by_market = by_market_with_other_windows(directory, backtest)
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
        unread_sources=[
            problem for problem in (props_unread, team_unread) if problem
        ],
    )
    windows = [
        f"{kind} figures come from the {phrase}"
        for kind, phrase in (
            ("prop", window_phrase(backtest)),
            ("team", window_phrase(team)),
        )
        if phrase
    ]
    if windows:
        report.window_note = (
            "Unless a line names another window, " + ", and ".join(windows) + "."
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
                    window=str(entry.get("_window", "") or ""),
                )
            )
            continue
        report.claims.append(
            MarketClaim(
                market=market.key,
                measured=False,
                calibration_samples=calibration_samples.get(market.key, 0),
                allowlisted=market.key in allowlisted_markets,
                reason_unmeasured=_unmeasured_reason(
                    market,
                    unmeasurable=unmeasurable,
                    backtest=backtest,
                    props_unread=props_unread,
                    team=team,
                    team_unread=team_unread,
                ),
            )
        )

    overall = backtest.get("overall")
    if isinstance(overall, dict) and int(overall.get("bets", 0) or 0) > 0:
        report.overall_bets = int(overall["bets"])
        report.overall_roi = float(overall.get("roi", 0.0))
        report.overall_includes_zero = bool(overall.get("includes_zero", True))
        report.overall_window = window_phrase(backtest)

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
    if report.unread_sources and any(claim.measured for claim in report.claims):
        # Where a reader starts, not only in the per-market lines. The
        # purchase workflow's document read "no historical prices have been
        # bought" for three team markets whose measurement it never had.
        lines.extend(
            [
                (
                    "**This document is incomplete.** "
                    + "; ".join(report.unread_sources)
                    + ". The markets measured there are listed under \"Not "
                    "measured against real prices\" with that reason, which "
                    "is not the same as having no price."
                ),
                "",
            ]
        )

    if report.overall_bets:
        lines.extend(
            [
                "## Across every measured prop market",
                "",
                (
                    f"{report.overall_roi:+.1%} over {report.overall_bets:,} "
                    + (
                        f"bets in the {report.overall_window}. "
                        if report.overall_window
                        else "bets. "
                    )
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
        if report.window_note:
            lines.extend([report.window_note, ""])
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
