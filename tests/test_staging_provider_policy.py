from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


from nhl_betting_lab import staging_provider_policy as policy_module
from nhl_betting_lab.config import MANUAL_DIR
from nhl_betting_lab.staging_provider_policy import load_policy, run_is_fresh


def _write(root: Path, payload: dict) -> Path:
    path = root / "data" / "manual" / "staging_provider_policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _approved_entry(**overrides: object) -> dict:
    entry = {
        "allowlist_status": "allowed",
        "provider_type": "odds_api",
        "approved_at": "2026-10-01T09:00:00-04:00",
        "reviewer_name": "cooperross399",
        "evidence_receipt_id": "odds_api-20261001T090000-0400-abc123",
        "required_markets": ["moneyline", "shots_on_goal"],
    }
    entry.update(overrides)
    return entry


def _policy(root: Path, **overrides: object) -> dict:
    payload = {
        "allowed_provider_names": ["the_odds_api"],
        "allowed_provider_types": ["odds_api"],
        "provider_allowlist_entries": {"the_odds_api": _approved_entry()},
        "max_provider_run_age_hours": 12,
    }
    payload.update(overrides)
    _write(root, payload)
    return payload


# -- the shipped policy ------------------------------------------------


def test_the_repository_ships_allowlisting_nothing() -> None:
    """The correct state until a market is measured and a human signs."""
    loaded = load_policy()

    assert loaded.allowed_provider_names == ()
    assert loaded.provider_allowed("the_odds_api") is False
    assert loaded.status == "Nothing allowlisted"


def test_the_shipped_policy_is_valid_even_though_it_allows_nothing() -> None:
    """Empty is a decision, not a malformed file."""
    loaded = load_policy()

    assert loaded.valid is True
    assert loaded.blockers == []


def test_the_shipped_policy_file_exists_where_the_docs_say() -> None:
    assert (MANUAL_DIR / policy_module.POLICY_FILENAME).is_file()


# -- fail-closed -------------------------------------------------------


def test_a_missing_policy_allows_nothing(tmp_path: Path) -> None:
    loaded = load_policy(
        tmp_path / "data" / "manual" / "staging_provider_policy.json",
        repository_root=tmp_path,
    )

    assert loaded.valid is False
    assert loaded.provider_allowed("the_odds_api") is False
    assert "missing" in loaded.blockers[0]


def test_an_unreadable_policy_allows_nothing(tmp_path: Path) -> None:
    path = tmp_path / "data" / "manual" / "staging_provider_policy.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")

    loaded = load_policy(path, repository_root=tmp_path)

    assert loaded.provider_allowed("the_odds_api") is False
    assert "could not be read" in loaded.blockers[0]


def test_a_policy_outside_the_repository_is_refused(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere.json"

    loaded = load_policy(outside, repository_root=tmp_path)

    assert loaded.valid is False
    assert "inside the repository" in loaded.blockers[0]


def test_a_non_json_policy_path_is_refused(tmp_path: Path) -> None:
    loaded = load_policy(tmp_path / "policy.yaml", repository_root=tmp_path)

    assert "`.json`" in loaded.blockers[0]


def test_a_partially_valid_policy_allows_nothing(tmp_path: Path) -> None:
    """A policy with one bad entry is not a policy with one fewer entry."""
    _policy(
        tmp_path,
        provider_allowlist_entries={
            "the_odds_api": _approved_entry(),
            "broken": {"allowlist_status": "allowed"},
        },
    )

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.valid is False
    assert loaded.allowed_provider_names == ()
    assert loaded.provider_allowed("the_odds_api") is False


# -- approvals ---------------------------------------------------------


def test_a_complete_approval_allows_its_named_markets(tmp_path: Path) -> None:
    _policy(tmp_path)

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.provider_allowed("the_odds_api") is True
    assert loaded.market_allowed("the_odds_api", "moneyline") is True
    assert loaded.market_allowed("the_odds_api", "shots_on_goal") is True


def test_provider_approval_is_not_market_approval(tmp_path: Path) -> None:
    """Trustworthy for moneylines is not permission for blocked shots."""
    _policy(tmp_path)

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.market_allowed("the_odds_api", "blocked_shots") is False
    assert "not market approval" in loaded.refusal_reason(
        "the_odds_api", "blocked_shots"
    )


def test_an_approval_nobody_signed_is_not_an_approval(tmp_path: Path) -> None:
    _policy(
        tmp_path,
        provider_allowlist_entries={
            "the_odds_api": _approved_entry(reviewer_name="")
        },
    )

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.provider_allowed("the_odds_api") is False
    assert any("nobody signed" in blocker for blocker in loaded.blockers)


def test_an_approval_without_an_evidence_receipt_is_refused(tmp_path: Path) -> None:
    _policy(
        tmp_path,
        provider_allowlist_entries={
            "the_odds_api": _approved_entry(evidence_receipt_id="")
        },
    )

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.provider_allowed("the_odds_api") is False


def test_a_name_without_an_entry_allows_nothing(tmp_path: Path) -> None:
    _policy(tmp_path, provider_allowlist_entries={})

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.provider_allowed("the_odds_api") is False
    assert any("no allowlist entry" in blocker for blocker in loaded.blockers)


def test_a_typo_in_a_market_key_is_refused_rather_than_ignored(
    tmp_path: Path,
) -> None:
    """Ignoring it would let an approval look broader than it is."""
    _policy(
        tmp_path,
        provider_allowlist_entries={
            "the_odds_api": _approved_entry(
                required_markets=["moneyline", "shots_on_target"]
            )
        },
    )

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.valid is False
    assert any("unknown markets" in blocker for blocker in loaded.blockers)


def test_a_pending_status_does_not_allow(tmp_path: Path) -> None:
    _policy(
        tmp_path,
        provider_allowlist_entries={
            "the_odds_api": _approved_entry(allowlist_status="pending")
        },
    )

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.provider_allowed("the_odds_api") is False
    assert "pending" in loaded.refusal_reason("the_odds_api", "moneyline")


def test_an_unknown_provider_type_is_refused(tmp_path: Path) -> None:
    _policy(
        tmp_path,
        provider_allowlist_entries={
            "the_odds_api": _approved_entry(provider_type="scraper")
        },
    )

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.valid is False


def test_allowed_markets_is_empty_for_an_unapproved_provider(
    tmp_path: Path,
) -> None:
    _policy(tmp_path)

    loaded = load_policy(repository_root=tmp_path)

    assert loaded.allowed_markets("some_other_provider") == ()


def test_the_refusal_reason_points_at_the_approval_document(
    tmp_path: Path,
) -> None:
    _policy(tmp_path, allowed_provider_names=[])

    loaded = load_policy(repository_root=tmp_path)

    assert "provider_allowlist_approval" in loaded.refusal_reason(
        "the_odds_api", "moneyline"
    )


def test_the_policy_is_checksummed_so_a_change_is_visible(tmp_path: Path) -> None:
    _policy(tmp_path)

    loaded = load_policy(repository_root=tmp_path)

    assert policy_module.SHA256_PATTERN.fullmatch(loaded.checksum_sha256)


# -- freshness ---------------------------------------------------------


def _stamp(hours_ago: float) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    ).isoformat(timespec="seconds")


def test_a_recent_run_is_fresh() -> None:
    fresh, reason = run_is_fresh(_stamp(1), max_age_hours=12)

    assert fresh is True
    assert "hours old" in reason


def test_an_old_run_is_stale() -> None:
    fresh, reason = run_is_fresh(_stamp(20), max_age_hours=12)

    assert fresh is False
    assert "past the" in reason


def test_a_run_with_no_timestamp_is_stale_not_fresh() -> None:
    """A run that cannot say when it happened is the run not to trust."""
    fresh, reason = run_is_fresh("", max_age_hours=12)

    assert fresh is False
    assert "no timestamp" in reason


def test_an_unparseable_timestamp_is_stale() -> None:
    fresh, _ = run_is_fresh("last Tuesday", max_age_hours=12)

    assert fresh is False


def test_a_naive_timestamp_is_stale_because_its_age_is_unknowable() -> None:
    fresh, reason = run_is_fresh("2026-10-08T19:00:00", max_age_hours=12)

    assert fresh is False
    assert "no timezone" in reason


def test_a_future_timestamp_is_refused() -> None:
    fresh, reason = run_is_fresh(_stamp(-5), max_age_hours=12)

    assert fresh is False
    assert "future" in reason


def test_no_configured_limit_means_no_freshness_check() -> None:
    fresh, _ = run_is_fresh(_stamp(500), max_age_hours=None)

    assert fresh is True
