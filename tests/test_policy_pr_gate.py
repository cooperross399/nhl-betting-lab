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


def test_the_shipped_policy_passes_because_it_allows_nothing() -> None:
    result = gate.run_gate()

    assert result.passed is True
    assert result.checked_providers == []
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


def test_the_receipts_directory_is_documented_and_empty_of_receipts() -> None:
    """Claude never writes one, so the directory holds only its README."""
    from nhl_betting_lab.config import MANUAL_DIR

    directory = MANUAL_DIR / gate.RECEIPTS_DIRNAME
    receipts = list(directory.glob("*.json"))

    assert (directory / "README.md").is_file()
    assert receipts == []
