"""Assemble the evidence a human needs to decide whether to allowlist a market.

Step 4 of `docs/provider_allowlist_approval.md`. It gathers every measurement
that exists, checksums each one, and states what they support — in one place,
so a reviewer is not asked to hold six reports in their head.

## What this deliberately does not do

**It does not write a receipt, and it does not draft one.** Not a template
with blanks, not a file with `reviewer_name: ""`. A receipt Claude wrote is
not evidence that a human reviewed anything, and a directory where some
receipts are real and some are drafts is worse than an empty one. What it
produces instead is a list of the exact values a receipt must contain, as
instructions in a report, for Cooper to write himself.

**It does not recommend enabling anything by default.** The recommendation is
computed from the evidence, and the honest output for a market with no
price-based measurement is "not supported" — which is what every market in
this repository currently is. A bundle that concluded "looks good" from
calibration alone would be exactly the confusion this project exists to avoid.

**It does not read the policy as permission.** A market already allowlisted
still gets assessed on its evidence, because the question a bundle answers is
"does the evidence support this", not "is it already on".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nhl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from nhl_betting_lab.markets import ALL_MARKETS
from nhl_betting_lab.reports.player_props_backtest import by_market_with_other_windows
from nhl_betting_lab.reports.what_we_can_claim import unread_reason
from nhl_betting_lab.staging_provider_policy import file_sha256
from nhl_betting_lab.stats import (
    NO_DEMONSTRATED_EDGE,
    bets_needed_to_detect,
    correction_family,
)


BUNDLE_MARKDOWN_FILENAME = "allowlist_evidence_bundle.md"
BUNDLE_JSON_FILENAME = "allowlist_evidence_bundle.json"

#: The reports a reviewer should have in front of them. Missing ones are
#: listed as missing rather than quietly omitted — a bundle that hides a gap
#: is worse than one that shows it.
EVIDENCE_FILENAMES: tuple[str, ...] = (
    "player_props_backtest.md",
    "props_calibration.md",
    "team_markets_measurement.md",
    "what_we_can_claim.md",
    "provider_shadow_verification.md",
    "provider_market_discovery.md",
    "historical_props_retention.json",
    # Required, not optional. A market that cleared its first window and was
    # then not confirmed on a held-out one is the exact shape this lab keeps
    # retracting, and a bundle that cannot see the replication record cannot
    # see that shape. `blocked_shots` was reported "supported" here while
    # replication.json recorded it "not confirmed".
    "replication.md",
)

#: The files every verdict below is READ from, each beside the report above
#: that a reviewer checksums. They are gitignored, so a fresh checkout has the
#: reports and none of these, and CI never builds `replication.json` at all.
#: This bundle used to read an absent one as an empty one: with only the
#: tracked reports present, all 12 markets read "no price-based measurement
#: exists" beside a checksummed `player_props_backtest.md` recording 9,379
#: `shots_on_goal` bets, and the Gameday Refresh bundle said `points` and
#: `blocked_shots` had "no replication record" beside a checksummed
#: `replication.md`. An input that could not be read is now named as missing
#: evidence, per market and in the recommendation.
VERDICT_INPUTS: dict[str, str] = {
    "player_props_backtest.json": "player_props_backtest.md",
    "team_markets_measurement.json": "team_markets_measurement.md",
    "replication.json": "replication.md",
}

#: Replication verdicts that permit a market to be called supported. Only
#: one does. "not confirmed" is not a neutral absence -- the second window
#: was run and it declined to confirm -- and "untestable" means there was
#: never a first-window result to replicate.
REPLICATED = "replicated"

#: A market needs at least this many measured bets before the bundle will
#: describe its evidence as anything other than "too thin to read". Set from
#: the project's own arithmetic: separating a +10% edge from zero takes about
#: 385 bets, and anything under a few hundred cannot distinguish a real edge
#: from a good run.
MINIMUM_BETS_TO_READ = 200


@dataclass
class EvidenceFile:
    """One report, and proof of exactly which version was reviewed."""

    name: str
    present: bool
    relative_path: str = ""
    checksum_sha256: str = ""
    bytes: int = 0

    def as_row(self) -> str:
        if not self.present:
            return f"| `{self.name}` | **missing** | — |"
        return (
            f"| `{self.relative_path}` | {self.bytes:,} bytes "
            f"| `{self.checksum_sha256}` |"
        )


@dataclass
class MarketVerdict:
    """What the evidence supports for one market, and why."""

    market: str
    bets: int = 0
    roi: float | None = None
    includes_zero: bool = True
    calibration_samples: int = 0
    supported: bool = False
    reason: str = ""

    def sentence(self) -> str:
        return f"`{self.market}`: **{'supported' if self.supported else 'not supported'}** — {self.reason}"


@dataclass
class EvidenceBundle:
    generated_at: str
    provider_name: str
    files: list[EvidenceFile] = field(default_factory=list)
    verdicts: list[MarketVerdict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: Each entry of `VERDICT_INPUTS` that could not be read, with why.
    unread: dict[str, str] = field(default_factory=dict)

    @property
    def supported_markets(self) -> tuple[str, ...]:
        return tuple(item.market for item in self.verdicts if item.supported)

    @property
    def missing_files(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.files if not item.present)

    @property
    def unread_inputs(self) -> tuple[str, ...]:
        return tuple(name for name in VERDICT_INPUTS if name in self.unread)

    def recommendation(self) -> str:
        unread = ", ".join(self.unread_inputs)
        if self.missing_files:
            return (
                "**Enable nothing yet.** "
                f"{len(self.missing_files)} evidence file(s) are missing, so "
                "the picture is incomplete: "
                f"{', '.join(self.missing_files)}."
                + (
                    " The verdicts are read from files that could not be "
                    f"read either: {unread}."
                    if unread
                    else ""
                )
            )
        if unread and not self.supported_markets:
            # Absence fails closed here — nothing unread can be supported —
            # but "the evidence supports enabling nothing" is a statement
            # about evidence this bundle never read.
            return (
                "**Enable nothing yet.** The verdicts below are read from "
                f"measurement outputs this bundle could not read: {unread}. "
                "A verdict that could not be read is missing evidence, not a "
                "finding, so the picture is incomplete."
            )
        if not self.supported_markets:
            return (
                "**The evidence supports enabling nothing.** Every market is "
                "either unmeasured against real prices or measured with an "
                f"interval that includes zero, which means {NO_DEMONSTRATED_EDGE}."
            )
        return (
            "The evidence is consistent with enabling "
            f"{', '.join(f'`{m}`' for m in self.supported_markets)}. That is "
            "not a recommendation to do so — it is a statement that the "
            "measurement does not rule them out.\n\n"
            "**Each listed market cleared a held-out window as well as the "
            "one it was found on**, which is the bar a market must now pass "
            "to appear here at all — a positive result on one window is a "
            "candidate and this sentence used to be printed about markets "
            "that had never faced a second. Two windows agreeing is worth "
            "considerably more than one measured precisely, and it is still "
            "two windows, scored by a model that has never been tested on a "
            "season it did not help fit. The decision is yours either way."
            + (
                f"\n\nSome verdicts could not be read ({unread}), so the "
                "markets read from them are not assessed here at all."
                if unread
                else ""
            )
        )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def collect_files(
    *, output_dir: Path, repository_root: Path
) -> list[EvidenceFile]:
    files: list[EvidenceFile] = []
    for name in EVIDENCE_FILENAMES:
        path = output_dir / name
        if not path.is_file():
            files.append(EvidenceFile(name=name, present=False))
            continue
        try:
            relative = path.resolve().relative_to(repository_root).as_posix()
        except ValueError:
            relative = str(path)
        files.append(
            EvidenceFile(
                name=name,
                present=True,
                relative_path=relative,
                checksum_sha256=file_sha256(path),
                bytes=path.stat().st_size,
            )
        )
    return files


def unread_verdict_inputs(output_dir: Path) -> dict[str, str]:
    """Each of `VERDICT_INPUTS` that is absent or unreadable, with why."""
    problems = {
        name: unread_reason(Path(output_dir) / name) for name in VERDICT_INPUTS
    }
    return {name: problem for name, problem in problems.items() if problem}


def assess_markets(*, output_dir: Path) -> list[MarketVerdict]:
    """What the measurements support, market by market."""
    props = _read_json(output_dir / "player_props_backtest.json")
    team = _read_json(output_dir / "team_markets_measurement.json")
    calibration = _read_json(output_dir / "props_calibration.json")
    # `_read_json` gives `{}` for an absent file and an empty one alike; these
    # say which, so an absent input is never reported as a finding.
    unread = unread_verdict_inputs(output_dir)
    replication_unread = unread.get("replication.json", "")

    calibration_samples = {
        str(item.get("market")): int(item.get("samples", 0) or 0)
        for item in calibration.get("markets", [])
        if isinstance(item, dict)
    }
    # The held-out window's verdict, keyed by market. A market absent from
    # this record has no replication result at all, which is not the same as
    # passing one -- `.get` therefore yields None and the market cannot be
    # supported.
    replication = {
        str(item.get("market")): str(item.get("state", "")).strip()
        for item in (_read_json(output_dir / "replication.json").get("markets") or [])
        if isinstance(item, dict)
    }

    # A prop market the contract window has no bets for is read from another
    # window, labelled; one it measured keeps that measurement.
    prop_results = by_market_with_other_windows(output_dir, props)
    team_results = {
        str(item.get("market")): item
        for item in (team.get("markets") or [])
        if isinstance(item, dict)
    }

    verdicts: list[MarketVerdict] = []
    for market in ALL_MARKETS:
        entry = (
            prop_results.get(market.key)
            if market.is_prop
            else team_results.get(market.key)
        )
        samples = calibration_samples.get(market.key, 0)
        bets = int((entry or {}).get("bets", 0) or 0)

        if not entry or bets == 0:
            source = (
                "player_props_backtest.json"
                if market.is_prop
                else "team_markets_measurement.json"
            )
            problem = unread.get(source, "")
            if problem:
                # Missing evidence, not a finding. This read "no price-based
                # measurement exists" whenever the JSON was absent, beside the
                # checksummed report recording the measurement.
                report_name = VERDICT_INPUTS[source]
                beside = (
                    f", while the checksummed `{report_name}` is present"
                    if (output_dir / report_name).is_file()
                    else ""
                )
                opening = (
                    f"its verdict could not be read: {problem}{beside}. A "
                    "verdict that could not be read is missing evidence, not "
                    "an absence of measurement"
                )
            else:
                opening = "no price-based measurement exists"
            verdicts.append(
                MarketVerdict(
                    market=market.key,
                    calibration_samples=samples,
                    supported=False,
                    reason=(
                        opening
                        + (
                            f"; it has been calibration-checked on {samples:,} "
                            "walk-forward samples, which can rule the model "
                            "out and can never rule it in"
                            if samples
                            else ""
                        )
                        + "."
                    ),
                )
            )
            continue

        includes_zero = bool(entry.get("includes_zero", True))
        # The corrected interval is the one that counts. Several markets are
        # measured on one body of data, so the uncorrected number for whichever
        # cleared 95% describes a search rather than a finding.
        survives = bool(entry.get("survives_correction", not includes_zero))
        # An interval that excludes zero is conclusive. It is not therefore
        # FAVOURABLE, and this bundle exists to inform a decision about
        # enabling a market, so the two must never be conflated.
        #
        # `points` measures -4.4% over 6,202 bets with a corrected interval
        # excluding zero. Before this line existed it was labelled
        # "supported", and once the two missing evidence files were produced
        # `recommendation()` would have read "the evidence is consistent with
        # enabling `points`" -- about a market demonstrated to lose money.
        # A demonstrated deficit is the strongest possible argument AGAINST
        # enabling, and it was being rendered as the argument for.
        looks = int(entry.get("looks", 1) or 1)
        # The family as the measuring report counted it. The props backtest
        # corrects over its markets and the overall figure, and five lines of
        # this bundle called that "the 7 markets measured on the same data"
        # for six markets (8 on `hits`, whose card window measured seven).
        family = correction_family(looks, str(entry.get("family", "") or ""))
        adjusted_low = entry.get("adjusted_low")
        adjusted_high = entry.get("adjusted_high")
        roi = entry.get("roi")
        roi_value = float(roi) if isinstance(roi, (int, float)) else None
        # An ROI that cannot be read is not a positive one. A market whose
        # interval excludes zero but whose sign is unknown falls to the
        # deficit branch, which states the uncertainty rather than assuming
        # the favourable reading.
        conclusive_and_positive = survives and roi_value is not None and roi_value > 0
        # A positive result on one window is a candidate, not a finding. The
        # held-out window is the whole point of the replication step, so a
        # market it did not confirm cannot be reported as supported however
        # well it did the first time.
        replication_state = replication.get(market.key)
        replicated = replication_state == REPLICATED
        # "No replication record" is true only of a record that was read and
        # does not list this market. Gameday Refresh never builds
        # `replication.json`, so the bundle it uploads said that of `points`
        # and `blocked_shots` while checksumming the `replication.md` that
        # records them as untestable. An unread record is said to be unread.
        held_out = (
            f"The held-out verdict could not be read ({replication_unread})"
            if replication_unread
            else "The held-out window did not confirm it "
            f"({replication_state or 'no replication record'})"
        )

        if bets < MINIMUM_BETS_TO_READ:
            reason = (
                f"only {bets} measured bet(s), below the "
                f"{MINIMUM_BETS_TO_READ} needed before a result is worth "
                f"reading. Separating a +10% edge from zero takes about "
                f"{bets_needed_to_detect(0.10):,} bets."
            )
            supported = False
        elif not conclusive_and_positive and survives:
            # Conclusive, and conclusively bad.
            reason = (
                (
                    f"**{roi_value:+.1%} over {bets:,} bets, and the "
                    "corrected interval excludes zero on the LOSING side.**"
                    if roi_value is not None
                    else (
                        f"**{bets:,} bets, and the corrected interval "
                        "excludes zero, but the return could not be read, so "
                        "the sign is unknown.**"
                    )
                )
                + (
                    " This is a demonstrated deficit, not an unproven edge: the"
                    " measurement does not fail to support enabling this market,"
                    " it argues against it."
                    # "Demonstrated" takes the same two windows a positive
                    # needs. `points` was called one here on a replication
                    # record built by counting every book's quote as a bet; at
                    # one bet per wager neither season carries it alone.
                    if replicated
                    else f" {held_out}, so it"
                    " is not a demonstrated deficit. A loss that survives the"
                    " correction still argues against enabling this market,"
                    " not for it."
                )
            )
            supported = False
        elif not survives:
            corrected = (
                f" Corrected for the {family} "
                f"it runs {float(adjusted_low):+.1%} to "
                f"{float(adjusted_high):+.1%}, which includes zero."
                if isinstance(adjusted_low, (int, float))
                and isinstance(adjusted_high, (int, float))
                and looks > 1
                else ""
            )
            reason = (
                f"{roi_value:+.1%} over {bets:,} bets."
                if roi_value is not None
                else f"{bets:,} bets."
            ) + corrected + f" {NO_DEMONSTRATED_EDGE.capitalize()}."
            supported = False
        else:
            reason = (
                f"{roi_value:+.1%} over {bets:,} bets, and the interval "
                f"excludes zero even after correcting for the {family}. "
                "That is the strongest thing this "
                "repository can currently say, and it rests on one snapshot "
                "window."
                if roi_value is not None
                else f"{bets:,} bets, and the corrected interval excludes zero."
            )
            supported = replicated
            if replicated:
                reason += (
                    " **A held-out window confirmed it.** Two windows "
                    "agreeing is worth considerably more than one measured "
                    "precisely, and it is still two windows."
                )
            else:
                reason += (
                    f" **{held_out}.** "
                    "One window is a candidate; two agreeing is a finding. "
                    "This is the first."
                )

        window = str((entry or {}).get("_window", "") or "")
        if window:
            reason += f" Measured only in the {window}."

        verdicts.append(
            MarketVerdict(
                market=market.key,
                bets=bets,
                roi=roi_value,
                includes_zero=includes_zero,
                calibration_samples=samples,
                supported=supported,
                reason=reason,
            )
        )
    return verdicts


def build_bundle(
    *,
    provider_name: str,
    output_dir: Path | None = None,
    repository_root: Path | None = None,
    now: datetime | None = None,
) -> EvidenceBundle:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    root = (repository_root or PROJECT_ROOT).resolve()
    bundle = EvidenceBundle(
        generated_at=(now or datetime.now(timezone.utc)).isoformat(
            timespec="seconds"
        ),
        provider_name=provider_name,
        files=collect_files(output_dir=directory, repository_root=root),
        verdicts=assess_markets(output_dir=directory),
        unread=unread_verdict_inputs(directory),
    )
    bundle.notes = [
        "Claude assembled this bundle and stops here. Claude never writes a "
        "human acceptance receipt, never adds a name to "
        "`allowed_provider_names`, and never adds a market to "
        "`required_markets`.",
        "The checksums above are what makes an approval current. The PR gate "
        "recomputes them, so a receipt citing a report that has since changed "
        "fails rather than passing quietly.",
        # Until 2026-09-25 this named "Staging validation" first. No such
        # gate exists: the card skips a staged file it cannot parse, and its
        # markets then read as unavailable. The committed bundle, pinned by
        # the receipt's checksum, still carries the old sentence.
        "Allowlisting a market does not skip any other gate. Completeness, "
        "freshness and the puck-drop guard all still run on every card. "
        "Nothing validates the staged files beyond that: a file the card "
        "cannot parse is skipped and its markets read as unavailable.",
        "An approval made against this evidence's recommendation is a "
        "legitimate decision, and it stays on the record as one. The EPL lab "
        "has exactly that on file.",
        "Where several markets are measured on one body of data, the interval "
        "that counts is the one corrected for how many were tested. The "
        "uncorrected number for whichever market cleared 95% describes a "
        "search.",
    ]
    return bundle


def render_bundle(bundle: EvidenceBundle) -> str:
    lines = [
        "# Allowlist evidence bundle",
        "",
        (
            f"Everything needed to decide whether to trust "
            f"`{bundle.provider_name}` for a market, in one place."
        ),
        "",
        f"- Generated: {bundle.generated_at}",
        "",
        "## Recommendation",
        "",
        bundle.recommendation(),
        "",
        "## What the evidence supports, market by market",
        "",
    ]
    lines.extend(f"- {item.sentence()}" for item in bundle.verdicts)
    lines.extend(
        [
            "",
            "## The evidence, and exactly which version of it",
            "",
            "| File | Size | SHA-256 |",
            "|:-----|-----:|:--------|",
        ]
    )
    lines.extend(item.as_row() for item in bundle.files)
    lines.append("")
    lines.extend(
        [
            "### Where the verdicts were read from",
            "",
            (
                "Not the reports above: each verdict is read from the "
                "measurement output beside its report. One that could not be "
                "read is missing evidence, and the verdicts that need it say "
                "so rather than reporting an absence."
            ),
            "",
            *[
                f"- `{name}`: "
                + (
                    f"**not read** — {bundle.unread[name]}."
                    if name in bundle.unread
                    else "read."
                )
                for name in VERDICT_INPUTS
            ],
            "",
        ]
    )

    if bundle.missing_files:
        lines.extend(
            [
                (
                    "A missing file is listed rather than omitted. It means "
                    "that part of the picture has not been produced yet, not "
                    "that it was reviewed and found unremarkable."
                ),
                "",
            ]
        )

    present = [item for item in bundle.files if item.present]
    lines.extend(
        [
            "## If you decide to approve",
            "",
            (
                "Write the receipt yourself, into "
                "`data/manual/human_acceptance_receipts/<receipt_id>.json`. "
                "Claude does not write one, and does not leave a draft — a "
                "receipt Claude wrote is not evidence that a human reviewed "
                "anything. `data/manual/human_acceptance_receipts/README.md` "
                "has the full shape; these are the values from this bundle:"
            ),
            "",
            "```json",
            json.dumps(
                {
                    "provider_name": bundle.provider_name,
                    "approved_markets": ["<the markets you are approving>"],
                    "evidence": [
                        {
                            "path": item.relative_path,
                            "checksum_sha256": item.checksum_sha256,
                        }
                        for item in present
                    ],
                },
                indent=2,
            ),
            "```",
            "",
            (
                "Then add the same markets to `required_markets` in "
                "`data/manual/staging_provider_policy.json`, and the provider "
                "name to `allowed_provider_names`. The Provider Policy PR "
                "Gate checks that the paperwork matches and that every "
                "checksum above still holds."
            ),
            "",
            "## Standing notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in bundle.notes)
    lines.append("")
    return "\n".join(lines)


def save_bundle(
    bundle: EvidenceBundle, *, output_dir: Path | None = None
) -> dict[str, str]:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / BUNDLE_MARKDOWN_FILENAME
    markdown.write_text(render_bundle(bundle), encoding="utf-8")
    json_path = directory / BUNDLE_JSON_FILENAME
    json_path.write_text(
        json.dumps(
            {
                "generated_at": bundle.generated_at,
                "provider_name": bundle.provider_name,
                "recommendation": bundle.recommendation(),
                "supported_markets": list(bundle.supported_markets),
                "missing_files": list(bundle.missing_files),
                "unread_inputs": list(bundle.unread_inputs),
                "unread": dict(bundle.unread),
                "files": [item.__dict__ for item in bundle.files],
                "verdicts": [item.__dict__ for item in bundle.verdicts],
                "notes": bundle.notes,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"markdown": str(markdown), "json": str(json_path)}
