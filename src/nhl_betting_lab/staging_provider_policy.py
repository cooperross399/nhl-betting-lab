"""The fail-closed provider policy.

`data/manual/staging_provider_policy.json` decides which provider and which
markets the card may use. It ships allowlisting **nothing**, and every failure
mode here resolves to "not allowed":

* file missing -> not allowed
* file unreadable -> not allowed
* file malformed -> not allowed
* market absent from `required_markets` -> not allowed
* allowlist entry without a human acceptance receipt -> not allowed

That is the whole design. A policy loader that returns a permissive default on
an unreadable file is a policy loader that stops existing the moment something
goes wrong, which is exactly when it matters.

Claude may prepare a policy change and open a pull request for it. Claude may
never write a receipt, add a name to `allowed_provider_names`, or add a market
to `required_markets`. Those are Cooper's.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.markets import MARKETS_BY_KEY


POLICY_FILENAME = "staging_provider_policy.json"

PROVIDER_TYPES = ("odds_api", "manual_upload", "fixture_provider", "unknown")

SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

#: The one provider this lab is built around. Naming it here does not allow
#: it; the policy file does that, and it does not.
ODDS_API_PROVIDER_NAME = "the_odds_api"


class PolicyError(RuntimeError):
    """The policy could not be read. Always resolves to 'not allowed'."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class AllowlistEntry:
    """One provider's reviewed approval, and what it covers."""

    provider_name: str
    provider_type: str
    status: str
    approved_at: str
    reviewer_name: str
    evidence_receipt_id: str
    required_markets: tuple[str, ...]
    known_limitations: tuple[str, ...] = ()
    max_provider_run_age_hours: float | None = None

    @property
    def is_allowed(self) -> bool:
        return (
            self.status == "allowed"
            and bool(self.reviewer_name)
            and bool(self.evidence_receipt_id)
        )


@dataclass
class StagingProviderPolicy:
    """The loaded policy, or an explanation of why nothing is allowed."""

    path: str
    checksum_sha256: str = ""
    valid: bool = False
    allowed_provider_names: tuple[str, ...] = ()
    allowed_provider_types: tuple[str, ...] = ()
    entries: dict[str, AllowlistEntry] = field(default_factory=dict)
    max_provider_run_age_hours: float | None = None
    blockers: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.blockers:
            return "Policy refuses"
        if not self.allowed_provider_names:
            return "Nothing allowlisted"
        return "Allowlisted"

    def provider_allowed(self, provider_name: str) -> bool:
        name = str(provider_name or "").strip()
        if not self.valid or name not in self.allowed_provider_names:
            return False
        entry = self.entries.get(name)
        return bool(entry and entry.is_allowed)

    def market_allowed(self, provider_name: str, market_key: str) -> bool:
        """Whether this exact market is covered by a reviewed approval.

        Provider-level approval is not market-level approval. A provider can
        be trustworthy for moneylines and untested on blocked shots, and the
        card must not read the first as permission for the second.
        """
        if not self.provider_allowed(provider_name):
            return False
        entry = self.entries.get(str(provider_name).strip())
        return bool(entry) and str(market_key).strip() in entry.required_markets

    def allowed_markets(self, provider_name: str) -> tuple[str, ...]:
        if not self.provider_allowed(provider_name):
            return ()
        entry = self.entries.get(str(provider_name).strip())
        return entry.required_markets if entry else ()

    def refusal_reason(self, provider_name: str, market_key: str) -> str:
        """Why this market is not allowed, in words a report can print."""
        name = str(provider_name or "").strip()
        market = str(market_key or "").strip()
        if self.blockers:
            return f"Provider policy could not be read: {self.blockers[0]}"
        if not self.valid:
            return "Provider policy is not valid, so nothing is allowlisted."
        if name not in self.allowed_provider_names:
            return (
                f"`{name}` is not in `allowed_provider_names`. Allowlisting is "
                "a reviewed human decision; see "
                "docs/provider_allowlist_approval.md"
            )
        entry = self.entries.get(name)
        if entry is None:
            return (
                f"`{name}` is named in `allowed_provider_names` but has no "
                "allowlist entry, so no approval exists to rely on."
            )
        if not entry.is_allowed:
            return (
                f"`{name}`'s allowlist entry is `{entry.status}` and carries no "
                "complete human acceptance receipt."
            )
        return (
            f"`{market}` is not in `{name}`'s reviewed `required_markets`. "
            "Provider approval is not market approval."
        )


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(value, dict):
        return None, "the JSON root must be an object"
    return value, ""


def _parse_entry(name: str, payload: Any, blockers: list[str]) -> AllowlistEntry | None:
    if not isinstance(payload, dict):
        blockers.append(f"Allowlist entry for `{name}` is not a JSON object.")
        return None
    status = str(payload.get("allowlist_status", "")).strip().lower()
    provider_type = str(payload.get("provider_type", "")).strip().lower()
    if provider_type not in PROVIDER_TYPES:
        blockers.append(
            f"Allowlist entry for `{name}` has provider_type "
            f"{provider_type!r}; expected one of {list(PROVIDER_TYPES)}."
        )
        return None
    markets_value = payload.get("required_markets")
    if not isinstance(markets_value, list) or not all(
        isinstance(item, str) for item in markets_value
    ):
        blockers.append(
            f"Allowlist entry for `{name}` needs `required_markets` as a list "
            "of market keys."
        )
        return None
    markets = tuple(
        dict.fromkeys(item.strip() for item in markets_value if item.strip())
    )
    unknown = [item for item in markets if item not in MARKETS_BY_KEY]
    if unknown:
        # A market key that does not exist cannot be approved. Silently
        # ignoring it would let a typo read as an approval that covers nothing
        # while looking like it covers something.
        blockers.append(
            f"Allowlist entry for `{name}` names unknown markets {unknown}."
        )
        return None
    receipt = str(payload.get("evidence_receipt_id", "")).strip()
    reviewer = str(payload.get("reviewer_name", "")).strip()
    if status == "allowed" and not (receipt and reviewer):
        blockers.append(
            f"Allowlist entry for `{name}` claims `allowed` without both a "
            "reviewer name and an evidence receipt id. An approval nobody "
            "signed is not an approval."
        )
        return None
    age = payload.get("max_provider_run_age_hours")
    try:
        max_age = float(age) if age is not None else None
    except (TypeError, ValueError):
        blockers.append(
            f"Allowlist entry for `{name}` has a non-numeric "
            "max_provider_run_age_hours."
        )
        return None
    return AllowlistEntry(
        provider_name=name,
        provider_type=provider_type,
        status=status,
        approved_at=str(payload.get("approved_at", "")).strip(),
        reviewer_name=reviewer,
        evidence_receipt_id=receipt,
        required_markets=markets,
        known_limitations=tuple(
            str(item) for item in payload.get("known_limitations", []) or []
        ),
        max_provider_run_age_hours=max_age,
    )


def load_policy(
    policy_path: Path | None = None, *, repository_root: Path | None = None
) -> StagingProviderPolicy:
    """Load the policy. Every failure resolves to 'nothing is allowed'."""
    root = (repository_root or PROJECT_ROOT).resolve()
    # The default is relative to the given root, not to the real repository.
    # Defaulting to the real path while honouring a different root would make
    # a test — or a dry run against a checkout — silently read the live
    # policy, which is the one file that must never be read by accident.
    requested = (
        Path(policy_path)
        if policy_path
        else (root / "data" / "manual" / POLICY_FILENAME)
    )
    resolved = (requested if requested.is_absolute() else root / requested).resolve()
    display = (
        resolved.relative_to(root).as_posix()
        if resolved.is_relative_to(root)
        else str(resolved)
    )
    policy = StagingProviderPolicy(path=display)

    if not resolved.is_relative_to(root):
        policy.blockers.append(
            "The provider policy must stay inside the repository."
        )
        return policy
    if resolved.suffix.lower() != ".json":
        policy.blockers.append("The provider policy must be a `.json` file.")
        return policy
    if not resolved.is_file():
        policy.blockers.append(f"Provider policy is missing: `{display}`.")
        return policy

    payload, error = _read_json_object(resolved)
    if payload is None:
        policy.blockers.append(f"Provider policy could not be read: {error}")
        return policy
    try:
        policy.checksum_sha256 = file_sha256(resolved)
    except OSError as exc:
        policy.blockers.append(f"Provider policy could not be hashed: {exc}")
        return policy

    names_value = payload.get("allowed_provider_names")
    if not isinstance(names_value, list) or not all(
        isinstance(item, str) for item in names_value
    ):
        policy.blockers.append(
            "`allowed_provider_names` must be a JSON list of names."
        )
        return policy
    types_value = payload.get("allowed_provider_types")
    if not isinstance(types_value, list) or not all(
        isinstance(item, str) and item.strip() in PROVIDER_TYPES
        for item in types_value
    ):
        policy.blockers.append(
            "`allowed_provider_types` must be a JSON list drawn from "
            f"{list(PROVIDER_TYPES)}."
        )
        return policy

    entries_value = payload.get("provider_allowlist_entries", {})
    if not isinstance(entries_value, dict):
        policy.blockers.append(
            "`provider_allowlist_entries` must be a JSON object."
        )
        return policy

    entries: dict[str, AllowlistEntry] = {}
    for name, raw in entries_value.items():
        entry = _parse_entry(str(name), raw, policy.blockers)
        if entry is not None:
            entries[str(name)] = entry

    allowed_names = tuple(
        dict.fromkeys(item.strip() for item in names_value if item.strip())
    )
    for name in allowed_names:
        if name not in entries:
            policy.blockers.append(
                f"`{name}` is in `allowed_provider_names` with no allowlist "
                "entry. A name without a reviewed entry allows nothing."
            )

    age = payload.get("max_provider_run_age_hours")
    try:
        policy.max_provider_run_age_hours = float(age) if age is not None else None
    except (TypeError, ValueError):
        policy.blockers.append("`max_provider_run_age_hours` must be a number.")
        return policy

    policy.allowed_provider_names = allowed_names
    policy.allowed_provider_types = tuple(item.strip() for item in types_value)
    policy.entries = entries
    policy.valid = not policy.blockers
    if not policy.valid:
        # A partially-valid policy is not a policy. Refuse everything.
        policy.allowed_provider_names = ()
    return policy


def run_is_fresh(
    generated_at: str, *, max_age_hours: float | None, now: datetime | None = None
) -> tuple[bool, str]:
    """Whether a provider run is recent enough to build a card from.

    An unparseable or missing timestamp is stale, not fresh. A run that cannot
    say when it happened is exactly the run not to trust.
    """
    if max_age_hours is None:
        return True, "No freshness limit is configured."
    text = str(generated_at or "").strip()
    if not text:
        return False, "The provider run has no timestamp, so it is treated as stale."
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return False, f"The provider run timestamp {text!r} could not be read."
    if stamp.tzinfo is None:
        return False, (
            "The provider run timestamp carries no timezone, so its age "
            "cannot be established."
        )
    moment = now or datetime.now(timezone.utc)
    age_hours = (moment - stamp).total_seconds() / 3600.0
    if age_hours < 0:
        return False, "The provider run is timestamped in the future."
    if age_hours > float(max_age_hours):
        return False, (
            f"The provider run is {age_hours:.1f} hours old, past the "
            f"{max_age_hours:g}-hour limit."
        )
    return True, f"The provider run is {age_hours:.1f} hours old."
