from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nhl_betting_lab.reports import policy_pr_gate as gate


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence(root: Path, relative: str = "data/outputs/player_props_backtest.md") -> dict:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "# measurement\n\nNo demonstrated edge over 41 bets.\n"
    path.write_text(body, encoding="utf-8")
    return {"path": relative, "checksum_sha256": _sha256(body)}


def _receipt(root: Path, **overrides) -> str:
    payload = {
        "receipt_id": "odds_api-20261001T090000-0400-abc12345",
        "provider_name": "the_odds_api",
        "reviewer_name": "cooperross399",
        "reviewed_at": "2026-10-01T09:00:00-04:00",
        "approved_markets": ["moneyline"],
        "evidence": [_evidence(root)],
        "reviewer_statement": "I read the evidence and approve these markets.",
    }
    payload.update(overrides)
    directory = root / "data" / "manual" / gate.RECEIPTS_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{payload['receipt_id']}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return str(payload["receipt_id"])


def _policy(root: Path, *, receipt_id: str, markets: list[str]) -> None:
    path = root / "data" / "manual" / "staging_provider_policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "allowed_provider_names": ["the_odds_api"],
                "allowed_provider_types": ["odds_api"],
                "provider_allowlist_entries": {
                    "the_odds_api": {
                        "allowlist_status": "allowed",
                        "provider_type": "odds_api",
                        "approved_at": "2026-10-01T09:00:00-04:00",
                        "reviewer_name": "cooperross399",
                        "evidence_receipt_id": receipt_id,
                        "required_markets": markets,
                    }
                },
                "max_provider_run_age_hours": 12,
            }
        ),
        encoding="utf-8",
    )


def test_the_shipped_policy_passes_the_gate() -> None:
    """The paperwork must hold in whatever state the repository ships:
    allowlisting nothing passes as the default and correct state, and an
    allowlisting policy passes only because its receipt and evidence
    checksums verify. Either way, a shipped policy that fails its own gate
    is a broken repository."""
    result = gate.run_gate()

    assert result.passed is True, result.failures
    if not result.checked_providers:
        assert "default and correct state" in result.summary_line()


def test_a_complete_approval_passes(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is True, result.failures
    assert result.checked_providers == ["the_odds_api"]


def test_a_missing_receipt_fails_the_gate(tmp_path: Path) -> None:
    _policy(tmp_path, receipt_id="never-written", markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("no receipt file" in item for item in result.failures)


def test_a_receipt_for_one_market_does_not_approve_another(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path, approved_markets=["moneyline"])
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline", "blocked_shots"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("does not approve" in item for item in result.failures)


def test_evidence_that_changed_since_it_was_read_fails(tmp_path: Path) -> None:
    """An approval must not rest on a report that has since moved."""
    receipt = _receipt(tmp_path)
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])
    (tmp_path / "data" / "outputs" / "player_props_backtest.md").write_text(
        "# measurement\n\nDifferent numbers now.\n", encoding="utf-8"
    )

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("changed since it was read" in item for item in result.failures)


def test_missing_evidence_fails(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])
    (tmp_path / "data" / "outputs" / "player_props_backtest.md").unlink()

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("missing evidence" in item for item in result.failures)


def test_a_receipt_citing_no_evidence_fails(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path, evidence=[])
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("cites no evidence" in item for item in result.failures)


def test_a_receipt_with_no_reviewer_statement_fails(tmp_path: Path) -> None:
    """An approval with nothing said about the evidence is a blank signature."""
    receipt = _receipt(tmp_path, reviewer_statement="  ")
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("blank page" in item for item in result.failures)


def test_a_receipt_for_another_provider_fails(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path, provider_name="some_other_api")
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("is for provider" in item for item in result.failures)


def test_a_receipt_missing_a_required_field_fails(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    path = (
        tmp_path / "data" / "manual" / gate.RECEIPTS_DIRNAME / f"{receipt}.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["reviewed_at"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("missing `reviewed_at`" in item for item in result.failures)


def test_a_receipt_id_cannot_escape_the_receipts_directory(tmp_path: Path) -> None:
    payload, error = gate.load_receipt(
        "../../../etc/passwd", repository_root=tmp_path
    )

    assert payload is None
    assert "unsafe characters" in error


def test_evidence_outside_the_repository_is_refused(tmp_path: Path) -> None:
    receipt = _receipt(
        tmp_path,
        evidence=[{"path": "../outside.md", "checksum_sha256": "a" * 64}],
    )
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("outside the repository" in item for item in result.failures)


def test_an_invalid_policy_fails_the_gate(tmp_path: Path) -> None:
    path = tmp_path / "data" / "manual" / "staging_provider_policy.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ broken", encoding="utf-8")

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("not valid" in item for item in result.failures)


def test_the_gate_states_what_it_cannot_prove(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    rendered = gate.render_gate(gate.run_gate(repository_root=tmp_path))

    assert "cannot verify that a human wrote it" in rendered
    assert "Branch protection" in rendered
    assert "Claude never writes a human acceptance receipt" in rendered


def test_the_gate_never_claims_a_pass_proves_a_human_signed(
    tmp_path: Path,
) -> None:
    receipt = _receipt(tmp_path)
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert "does not prove a human signed" in result.summary_line()


def test_the_receipts_directory_is_documented_and_holds_no_orphan() -> None:
    """Claude never writes a receipt, so the directory holds its README and,
    at most, receipts a human wrote that the shipped policy actually cites.
    A receipt nothing cites is paperwork nothing verifies."""
    from nhl_betting_lab.config import MANUAL_DIR
    from nhl_betting_lab.staging_provider_policy import load_policy

    directory = MANUAL_DIR / gate.RECEIPTS_DIRNAME
    on_disk = {path.stem for path in directory.glob("*.json")}
    cited = {
        entry.evidence_receipt_id for entry in load_policy().entries.values()
    }

    assert (directory / "README.md").is_file()
    assert on_disk <= cited, f"orphan receipt(s): {sorted(on_disk - cited)}"


# -- every malformed receipt shape, each of which must fail the gate ----


def test_an_entry_naming_no_receipt_id_is_caught_before_the_gate(
    tmp_path: Path,
) -> None:
    """The policy loader refuses an `allowed` entry with no receipt id, so the
    gate never sees it. Both layers refuse; asserting the outer one is the
    honest test, because that is what actually happens."""
    _policy(tmp_path, receipt_id="", markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("not valid" in item for item in result.failures)


def test_an_unreadable_receipt_fails(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    path = tmp_path / "data" / "manual" / gate.RECEIPTS_DIRNAME / f"{receipt}.json"
    path.write_text("{ not json", encoding="utf-8")
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("could not be read" in item for item in result.failures)


def test_a_receipt_whose_root_is_not_an_object_fails(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    path = tmp_path / "data" / "manual" / gate.RECEIPTS_DIRNAME / f"{receipt}.json"
    path.write_text('["approved"]', encoding="utf-8")
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("not a JSON object" in item for item in result.failures)


def test_a_receipt_naming_no_reviewer_fails(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path, reviewer_name="   ")
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("names no reviewer" in item for item in result.failures)


def test_approved_markets_that_is_not_a_list_fails(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path, approved_markets="moneyline")
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("as a list of keys" in item for item in result.failures)


def test_a_receipt_approving_a_market_that_does_not_exist_fails(
    tmp_path: Path,
) -> None:
    """A typo must not read as an approval that covers something."""
    receipt = _receipt(
        tmp_path, approved_markets=["moneyline", "shots_on_target"]
    )
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("approves unknown markets" in item for item in result.failures)


def test_an_evidence_entry_that_is_not_an_object_fails(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path, evidence=["data/outputs/whatever.md"])
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("is not an object" in item for item in result.failures)


def test_evidence_without_a_valid_checksum_fails(tmp_path: Path) -> None:
    receipt = _receipt(
        tmp_path,
        evidence=[{"path": "data/outputs/x.md", "checksum_sha256": "abc"}],
    )
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False
    assert any("64-character SHA-256" in item for item in result.failures)


def test_evidence_with_no_path_fails(tmp_path: Path) -> None:
    receipt = _receipt(
        tmp_path, evidence=[{"path": "", "checksum_sha256": "a" * 64}]
    )
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    result = gate.run_gate(repository_root=tmp_path)

    assert result.passed is False


def test_a_receipt_id_that_is_only_whitespace_fails(tmp_path: Path) -> None:
    payload, error = gate.load_receipt("   ", repository_root=tmp_path)

    assert payload is None
    assert "names no receipt id" in error


# -- the rendered report -----------------------------------------------


def test_the_rendered_report_lists_every_failure(tmp_path: Path) -> None:
    _policy(tmp_path, receipt_id="missing", markets=["moneyline"])

    rendered = gate.render_gate(gate.run_gate(repository_root=tmp_path))

    assert "FAIL" in rendered
    assert "## Failures" in rendered
    assert "no receipt file" in rendered


def test_the_rendered_report_lists_what_was_checked(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    _policy(tmp_path, receipt_id=receipt, markets=["moneyline"])

    rendered = gate.render_gate(gate.run_gate(repository_root=tmp_path))

    assert "PASS" in rendered
    assert "Provider `the_odds_api`" in rendered
    assert "Market `moneyline`" in rendered


def test_the_summary_counts_the_problems(tmp_path: Path) -> None:
    _policy(tmp_path, receipt_id="missing", markets=["moneyline"])

    summary = gate.run_gate(repository_root=tmp_path).summary_line()

    assert "problem(s) with the approval paperwork" in summary
    assert "not supported by the evidence it cites" in summary


def test_a_hand_built_policy_allowlisting_a_name_with_no_entry_fails(
    tmp_path: Path,
) -> None:
    """Defence in depth: `load_policy` blocks this shape, so the gate's own
    check only fires on a policy object built some other way. A gate should
    not depend on every caller having gone through one door."""
    from nhl_betting_lab.staging_provider_policy import StagingProviderPolicy

    policy = StagingProviderPolicy(
        path="in-memory",
        valid=True,
        allowed_provider_names=("the_odds_api",),
        entries={},
    )

    result = gate.run_gate(policy=policy, repository_root=tmp_path)

    assert result.passed is False
    assert any(
        "allowlisted with no allowlist entry" in item for item in result.failures
    )
