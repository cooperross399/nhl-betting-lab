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
from nhl_betting_lab.staging_provider_policy import file_sha256
from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE, bets_needed_to_detect


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
)

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

    @property
    def supported_markets(self) -> tuple[str, ...]:
        return tuple(item.market for item in self.verdicts if item.supported)

    @property
    def missing_files(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.files if not item.present)

    def recommendation(self) -> str:
        if self.missing_files:
            return (
                "**Enable nothing yet.** "
                f"{len(self.missing_files)} evidence file(s) are missing, so "
                "the picture is incomplete: "
                f"{', '.join(self.missing_files)}."
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
            "measurement does not rule them out. The decision is yours."
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


def assess_markets(*, output_dir: Path) -> list[MarketVerdict]:
    """What the measurements support, market by market."""
    props = _read_json(output_dir / "player_props_backtest.json")
    team = _read_json(output_dir / "team_markets_measurement.json")
    calibration = _read_json(output_dir / "props_calibration.json")

    calibration_samples = {
        str(item.get("market")): int(item.get("samples", 0) or 0)
        for item in calibration.get("markets", [])
        if isinstance(item, dict)
    }
    prop_results = props.get("by_market") or {}
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
            verdicts.append(
                MarketVerdict(
                    market=market.key,
                    calibration_samples=samples,
                    supported=False,
                    reason=(
                        "no price-based measurement exists"
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
        roi = entry.get("roi")
        roi_value = float(roi) if isinstance(roi, (int, float)) else None

        if bets < MINIMUM_BETS_TO_READ:
            reason = (
                f"only {bets} measured bet(s), below the "
                f"{MINIMUM_BETS_TO_READ} needed before a result is worth "
                f"reading. Separating a +10% edge from zero takes about "
                f"{bets_needed_to_detect(0.10):,} bets."
            )
            supported = False
        elif includes_zero:
            reason = (
                f"{roi_value:+.1%} over {bets:,} bets, and the 95% interval "
                f"includes zero — {NO_DEMONSTRATED_EDGE}."
                if roi_value is not None
                else f"{bets:,} bets, interval includes zero — {NO_DEMONSTRATED_EDGE}."
            )
            supported = False
        else:
            reason = (
                f"{roi_value:+.1%} over {bets:,} bets, and the 95% interval "
                "excludes zero on this sample. That is the strongest thing "
                "this repository can currently say, and it is still a "
                "statement about one sample rather than about the future."
                if roi_value is not None
                else f"{bets:,} bets, interval excludes zero on this sample."
            )
            supported = True

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
    )
    bundle.notes = [
        "Claude assembled this bundle and stops here. Claude never writes a "
        "human acceptance receipt, never adds a name to "
        "`allowed_provider_names`, and never adds a market to "
        "`required_markets`.",
        "The checksums above are what makes an approval current. The PR gate "
        "recomputes them, so a receipt citing a report that has since changed "
        "fails rather than passing quietly.",
        "Allowlisting a market does not skip any other gate. Staging "
        "validation, completeness, freshness and the puck-drop guard all "
        "still run on every card.",
        "An approval made against this evidence's recommendation is a "
        "legitimate decision, and it stays on the record as one. The EPL lab "
        "has exactly that on file.",
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
