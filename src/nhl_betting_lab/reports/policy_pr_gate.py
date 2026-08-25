"""The provider policy PR gate.

A pull request that widens `data/manual/staging_provider_policy.json` must
carry the paperwork that justifies it. This module decides whether it does.

What the gate checks:

* every provider newly named in `allowed_provider_names` has an allowlist
  entry, and that entry names a receipt;
* the receipt file exists, parses, and is well formed;
* the receipt names every market the entry newly allows — a receipt for
  moneylines does not approve blocked shots;
* every evidence file the receipt cites exists and still has the checksum the
  receipt recorded, so an approval cannot rest on a report that has changed
  since it was read.

**What the gate cannot check: that a human wrote the receipt.** Nothing in a
file can prove that. Branch protection and Cooper's review on the pull request
are what actually carry that weight. The gate makes sure the paperwork is real
and current; it does not pretend to prove authorship, and the report it writes
says so.

Read-only. It never edits the policy, never writes a receipt, and never
approves anything.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.markets import MARKETS_BY_KEY
from nhl_betting_lab.staging_provider_policy import (
    StagingProviderPolicy,
    file_sha256,
    load_policy,
)


RECEIPTS_DIRNAME = "human_acceptance_receipts"
GATE_MARKDOWN_FILENAME = "provider_policy_pr_gate.md"

SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

REQUIRED_RECEIPT_FIELDS = (
    "receipt_id",
    "provider_name",
    "reviewer_name",
    "reviewed_at",
    "approved_markets",
    "evidence",
    "reviewer_statement",
)


@dataclass
class GateResult:
    """Whether the paperwork holds up, and exactly where it does not."""

    passed: bool = True
    checked_providers: list[str] = field(default_factory=list)
    approved_markets: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.passed = False
        self.failures.append(reason)

    def summary_line(self) -> str:
        if not self.checked_providers:
            return (
                "The policy allowlists nothing, so there is no approval to "
                "check. That is the repository's default and correct state."
            )
        if self.passed:
            return (
                f"The paperwork holds for {len(self.checked_providers)} "
                f"provider(s) and {len(self.approved_markets)} market(s). "
                "This does not prove a human signed it; see the note below."
            )
        return (
            f"{len(self.failures)} problem(s) with the approval paperwork. "
            "The policy change is not supported by the evidence it cites."
        )


def _receipts_dir(repository_root: Path) -> Path:
    return repository_root / "data" / "manual" / RECEIPTS_DIRNAME


def load_receipt(
    receipt_id: str, *, repository_root: Path | None = None
) -> tuple[dict[str, Any] | None, str]:
    """Read one receipt, or say why it could not be read."""
    root = (repository_root or PROJECT_ROOT).resolve()
    identifier = str(receipt_id or "").strip()
    if not identifier:
        return None, "the allowlist entry names no receipt id"
    if not re.fullmatch(r"[A-Za-z0-9._-]+", identifier):
        # A receipt id becomes a filename. Anything else could escape the
        # directory, and a receipt read from outside it is not a receipt.
        return None, f"receipt id {identifier!r} contains unsafe characters"
    path = _receipts_dir(root) / f"{identifier}.json"
    if not path.is_file():
        return None, f"no receipt file at `data/manual/{RECEIPTS_DIRNAME}/{identifier}.json`"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"receipt `{identifier}` could not be read: {exc}"
    if not isinstance(payload, dict):
        return None, f"receipt `{identifier}` is not a JSON object"
    return payload, ""


def check_receipt(
    payload: dict[str, Any],
    *,
    provider_name: str,
    required_markets: tuple[str, ...],
    repository_root: Path | None = None,
) -> list[str]:
    """Every problem with one receipt, or an empty list."""
    root = (repository_root or PROJECT_ROOT).resolve()
    problems: list[str] = []
    identifier = str(payload.get("receipt_id", "")).strip() or "<unnamed>"

    for name in REQUIRED_RECEIPT_FIELDS:
        if name not in payload:
            problems.append(f"receipt `{identifier}` is missing `{name}`")
    if problems:
        return problems

    if str(payload.get("provider_name", "")).strip() != provider_name:
        problems.append(
            f"receipt `{identifier}` is for provider "
            f"{payload.get('provider_name')!r}, not `{provider_name}`"
        )
    if not str(payload.get("reviewer_name", "")).strip():
        problems.append(f"receipt `{identifier}` names no reviewer")
    if not str(payload.get("reviewer_statement", "")).strip():
        problems.append(
            f"receipt `{identifier}` carries no reviewer statement. An "
            "approval with nothing said about the evidence is a signature on "
            "a blank page."
        )

    approved = payload.get("approved_markets")
    if not isinstance(approved, list) or not all(
        isinstance(item, str) for item in approved
    ):
        problems.append(
            f"receipt `{identifier}` needs `approved_markets` as a list of keys"
        )
    else:
        approved_set = {item.strip() for item in approved}
        unknown = sorted(approved_set - set(MARKETS_BY_KEY))
        if unknown:
            problems.append(
                f"receipt `{identifier}` approves unknown markets {unknown}"
            )
        uncovered = sorted(set(required_markets) - approved_set)
        if uncovered:
            problems.append(
                f"the policy allows {uncovered} for `{provider_name}` but "
                f"receipt `{identifier}` does not approve "
                f"{'them' if len(uncovered) > 1 else 'it'}. A receipt for one "
                "market does not approve another."
            )

    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        problems.append(
            f"receipt `{identifier}` cites no evidence. An approval that "
            "reviewed nothing is not a reviewed approval."
        )
        return problems

    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            problems.append(f"receipt `{identifier}` evidence {index} is not an object")
            continue
        relative = str(item.get("path", "")).strip()
        checksum = str(item.get("checksum_sha256", "")).strip()
        if not relative or not SHA256_PATTERN.fullmatch(checksum):
            problems.append(
                f"receipt `{identifier}` evidence {index} needs a path and a "
                "64-character SHA-256"
            )
            continue
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            problems.append(
                f"receipt `{identifier}` cites evidence outside the repository"
            )
            continue
        if not target.is_file():
            problems.append(
                f"receipt `{identifier}` cites missing evidence `{relative}`"
            )
            continue
        actual = file_sha256(target)
        if actual.lower() != checksum.lower():
            problems.append(
                f"receipt `{identifier}` cites `{relative}` with a checksum "
                "that no longer matches. The approval rests on a report that "
                "has changed since it was read."
            )
    return problems


def run_gate(
    *,
    policy: StagingProviderPolicy | None = None,
    repository_root: Path | None = None,
) -> GateResult:
    """Check every allowlisted provider's paperwork."""
    root = (repository_root or PROJECT_ROOT).resolve()
    loaded = policy or load_policy(repository_root=root)
    result = GateResult()

    for blocker in loaded.blockers:
        result.fail(f"Provider policy is not valid: {blocker}")
    if not loaded.valid:
        return result

    for provider_name in loaded.allowed_provider_names:
        entry = loaded.entries.get(provider_name)
        if entry is None:
            result.fail(
                f"`{provider_name}` is allowlisted with no allowlist entry."
            )
            continue
        result.checked_providers.append(provider_name)
        result.approved_markets.extend(entry.required_markets)
        payload, error = load_receipt(
            entry.evidence_receipt_id, repository_root=root
        )
        if payload is None:
            result.fail(f"`{provider_name}`: {error}")
            continue
        for problem in check_receipt(
            payload,
            provider_name=provider_name,
            required_markets=entry.required_markets,
            repository_root=root,
        ):
            result.fail(f"`{provider_name}`: {problem}")

    result.notes.append(
        "This gate verifies that the approval paperwork is real, complete and "
        "current. It cannot verify that a human wrote it — nothing in a file "
        "can. Branch protection and Cooper's review on the pull request are "
        "what carry that weight."
    )
    result.notes.append(
        "Claude never writes a human acceptance receipt, never adds a name to "
        "`allowed_provider_names`, and never adds a market to "
        "`required_markets`."
    )
    return result


def render_gate(result: GateResult) -> str:
    lines = [
        "# Provider policy PR gate",
        "",
        f"- Result: **{'PASS' if result.passed else 'FAIL'}**",
        f"- {result.summary_line()}",
        "",
    ]
    if result.checked_providers:
        lines.extend(
            [
                "## Checked",
                "",
                *[f"- Provider `{name}`" for name in result.checked_providers],
                *[
                    f"- Market `{market}`"
                    for market in sorted(set(result.approved_markets))
                ],
                "",
            ]
        )
    if result.failures:
        lines.extend(
            ["## Failures", "", *[f"- {item}" for item in result.failures], ""]
        )
    lines.extend(["## What this gate does not prove", ""])
    lines.extend([f"- {item}" for item in result.notes])
    lines.append("")
    return "\n".join(lines)
