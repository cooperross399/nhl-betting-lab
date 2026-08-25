"""The shadow verification report.

A shadow run fetches real prices, writes them to `data/staging/`, and reports
what it found. That is all it does. It cannot allowlist anything, it cannot
promote staging, and the card cannot read the files it writes.

The report answers three questions and refuses to answer a fourth:

1. Did the adapter parse the provider's real responses?
2. Which markets came back, for how much of the slate, from which books?
3. What did it cost?

The fourth — "so should we use this?" — is a human decision. This report is
evidence for it. Nothing here recommends enabling anything, and
`docs/provider_allowlist_approval.md` describes the six steps that a real
approval takes.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.market_eligibility import (
    EligibilityReport,
    assess_markets,
    slate_games_from,
)
from nhl_betting_lab.providers.env_file import redact
from nhl_betting_lab.reports.market_discovery import (
    DiscoveryReport,
    discover_coverage,
    render_discovery,
)
from nhl_betting_lab.staging_provider_policy import StagingProviderPolicy


SHADOW_JSON_FILENAME = "provider_shadow_verification.json"
SHADOW_MARKDOWN_FILENAME = "provider_shadow_verification.md"
DISCOVERY_MARKDOWN_FILENAME = "provider_market_discovery.md"


@dataclass
class ShadowSummary:
    """One shadow run, in a shape a report and a test can both read."""

    generated_at: str
    provider_name: str
    rows: int
    events_seen: int
    events_priced: int
    credits_spent: int
    quota_remaining: str = ""
    policy_status: str = ""
    policy_checksum: str = ""
    allowlisted_markets: tuple[str, ...] = ()
    eligible_markets: tuple[str, ...] = ()
    excluded_markets: tuple[str, ...] = ()
    exclusion_reasons: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    staging_files: list[str] = field(default_factory=list)
    #: Facts about what this run did NOT do, asserted rather than assumed.
    safety: dict[str, bool] = field(
        default_factory=lambda: {
            "odds_fabricated": False,
            "bets_placed": False,
            "staging_promoted": False,
            "policy_edited": False,
            "provider_allowlisted": False,
            "credential_written": False,
        }
    )


def build_shadow_summary(
    prices: pd.DataFrame,
    *,
    policy: StagingProviderPolicy,
    provider_name: str,
    events_seen: int = 0,
    events_priced: int = 0,
    credits_spent: int = 0,
    quota_remaining: str = "",
    warnings: Sequence[str] = (),
    errors: Sequence[str] = (),
    staging_files: Sequence[Path | str] = (),
    now: datetime | None = None,
) -> tuple[ShadowSummary, EligibilityReport, DiscoveryReport]:
    """Assess a staged price frame without changing anything."""
    moment = now or datetime.now(timezone.utc)
    slate = slate_games_from(prices)
    eligibility = assess_markets(
        prices,
        slate_games=slate,
        policy=policy,
        provider_name=provider_name,
    )
    discovery = discover_coverage(prices)
    summary = ShadowSummary(
        generated_at=moment.isoformat(timespec="seconds"),
        provider_name=provider_name,
        rows=len(prices),
        events_seen=events_seen or len(slate),
        events_priced=events_priced or len(slate),
        credits_spent=credits_spent,
        quota_remaining=quota_remaining,
        policy_status=policy.status,
        policy_checksum=policy.checksum_sha256,
        allowlisted_markets=policy.allowed_markets(provider_name),
        eligible_markets=eligibility.eligible_markets,
        excluded_markets=eligibility.excluded_markets,
        exclusion_reasons=eligibility.exclusion_reasons(),
        warnings=list(warnings),
        errors=list(errors),
        staging_files=[str(Path(item).name) for item in staging_files],
    )
    return summary, eligibility, discovery


def render_shadow(
    summary: ShadowSummary,
    eligibility: EligibilityReport,
    discovery: DiscoveryReport,
) -> str:
    lines = [
        "# Provider shadow verification",
        "",
        (
            "A shadow run fetches real prices into `data/staging/` and reports "
            "what it found. The card cannot read those files. **Nothing in "
            "this report allowlists a provider or a market.**"
        ),
        "",
        "## Run",
        "",
        f"- Generated at: {summary.generated_at}",
        f"- Provider: **{summary.provider_name}**",
        f"- Price rows staged: **{summary.rows}**",
        f"- Events: {summary.events_priced} priced of {summary.events_seen} seen",
        f"- Credits spent: **{summary.credits_spent}**"
        + (
            f" ({summary.quota_remaining} remaining)"
            if summary.quota_remaining
            else ""
        ),
        f"- Staging files: {', '.join(summary.staging_files) or 'none'}",
        "",
        "## Policy",
        "",
        f"- Status: **{summary.policy_status}**",
        f"- Policy checksum: `{summary.policy_checksum or 'not available'}`",
        (
            "- Allowlisted markets for this provider: **"
            + (", ".join(summary.allowlisted_markets) or "none")
            + "**"
        ),
        "",
        "## Market eligibility",
        "",
        f"- {eligibility.summary_line()}",
        "",
        "| Market | State | Priced | Reason |",
        "|:-------|:------|:-------|:-------|",
    ]
    for item in eligibility.markets:
        lines.append(
            f"| `{item.market}` | {item.state} "
            f"| {item.games_priced}/{item.games_in_slate} | {item.reason} |"
        )
    lines.extend(
        [
            "",
            (
                "An excluded market is **not** a pass, an avoid, or a "
                "no-value call. It is a market that was not usable, for the "
                "stated reason, and no price was invented for it."
            ),
            "",
        ]
    )

    if summary.warnings:
        lines.extend(["## Warnings", "", *[f"- {item}" for item in summary.warnings], ""])
    if summary.errors:
        lines.extend(["## Errors", "", *[f"- {item}" for item in summary.errors], ""])

    lines.extend(
        [
            "## Coverage",
            "",
            f"- {discovery.summary_line()}",
            "",
            "Full detail: `data/outputs/provider_market_discovery.md`.",
            "",
            "## What this run did not do",
            "",
            *[
                f"- {label.replace('_', ' ').capitalize()}: "
                f"**{'Yes' if value else 'No'}**"
                for label, value in sorted(summary.safety.items())
            ],
            "",
            "## Next step",
            "",
            (
                "Nothing, automatically. Allowlisting a market takes "
                "measurement against real prices and a reviewed human "
                "approval; see `docs/provider_allowlist_approval.md`. Claude "
                "prepares the evidence and stops."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def save_shadow_reports(
    summary: ShadowSummary,
    eligibility: EligibilityReport,
    discovery: DiscoveryReport,
    *,
    output_dir: Path | None = None,
) -> dict[str, str]:
    """Write both reports. Every string is redacted on the way out."""
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = asdict(summary)
    payload["markets"] = [
        {
            "market": item.market,
            "state": item.state,
            "reason": item.reason,
            "usable_for_picks": item.usable_for_picks,
            "is_no_value_call": item.is_no_value_call,
            "games_priced": item.games_priced,
            "games_in_slate": item.games_in_slate,
        }
        for item in eligibility.markets
    ]
    json_path = directory / SHADOW_JSON_FILENAME
    json_path.write_text(
        redact(json.dumps(payload, indent=2, sort_keys=True, default=str)) + "\n",
        encoding="utf-8",
    )
    markdown_path = directory / SHADOW_MARKDOWN_FILENAME
    markdown_path.write_text(
        redact(render_shadow(summary, eligibility, discovery)), encoding="utf-8"
    )
    discovery_path = directory / DISCOVERY_MARKDOWN_FILENAME
    discovery_path.write_text(redact(render_discovery(discovery)), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "discovery": str(discovery_path),
    }
