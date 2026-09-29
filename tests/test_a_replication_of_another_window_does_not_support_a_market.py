"""A replication verdict is about the windows it compared, not about any figure.

#254 made `run_replication.py` refuse to compare windows of different phases
("a wager priced at two distances from face-off is two different questions")
and wrote `discovery_phase` and `test_phase` into `replication.json`. Its two
readers never read them. `allowlist_evidence.assess_markets` and
`what_we_can_claim.build_claims_report` keyed the verdict by market alone. The
contract `player_props_backtest.json` is the `late` window (Gameday Refresh
runs `--phase late`), so a replication of two `card` seasons marked
`replicated` was read as held-out confirmation of the `late` figure: the
bundle called the market supported, and the claims document printed
"**Replicated** on the 2025-26-card window" beside it.

Now a record applies to a figure only when both windows it compared are the
figure's own phase. A record of another window, a record that names no window
(written before #254), or a figure that names none, is no replication record
for that figure, and the line says why. This can only take support away.
Found by sweep 5 (replication-phase-not-checked-by-consumers, 2 of 2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhl_betting_lab.reports import replication as rep
from nhl_betting_lab.reports.allowlist_evidence import assess_markets
from nhl_betting_lab.reports.what_we_can_claim import build_claims_report


def _entry(roi: float, bets: int = 4000) -> dict:
    return {
        "bets": bets, "roi": roi, "low": roi - 0.03, "high": roi + 0.03,
        "includes_zero": False, "looks": 7, "family": "",
        "adjusted_low": roi - 0.04, "adjusted_high": roi + 0.04,
        "survives_correction": True,
    }


def _plant(directory: Path, *, contract_phase: str | None,
           discovery: str | None, test: str | None,
           state: str = "replicated", market: str = "blocked_shots",
           roi: float = 0.05, card_file: dict | None = None) -> None:
    backtest: dict = {
        "generated_at": "2026-09-29T00:00:00+00:00", "bets": 4000,
        "by_market": {market: _entry(roi)} if card_file is None else {},
    }
    if contract_phase is not None:
        backtest["phase"] = contract_phase
    (directory / "player_props_backtest.json").write_text(json.dumps(backtest))
    if card_file is not None:
        (directory / "player_props_backtest_card.json").write_text(
            json.dumps(card_file)
        )
    record: dict = {
        "discovery_label": "2024-25", "test_label": "2025-26",
        "markets": [{"market": market, "state": state, "reason": "held"}],
    }
    if discovery is not None:
        record["discovery_phase"] = discovery
    if test is not None:
        record["test_phase"] = test
    (directory / "replication.json").write_text(json.dumps(record))


def _verdict(directory: Path, market: str = "blocked_shots"):
    return {v.market: v for v in assess_markets(output_dir=directory)}[market]


def _claim(directory: Path, market: str = "blocked_shots"):
    report = build_claims_report(output_dir=directory)
    return report, next(c for c in report.claims if c.market == market)


# --- the reported case ----------------------------------------------------


def test_a_card_replication_does_not_support_the_late_figure(tmp_path: Path) -> None:
    _plant(tmp_path, contract_phase="late", discovery="card", test="card")
    verdict = _verdict(tmp_path)
    assert verdict.supported is False
    assert verdict.replicated is False
    assert verdict.conclusive == "candidate"
    assert "no replication record for this window" in verdict.reason
    assert "`card`" in verdict.reason and "`late`" in verdict.reason


def test_the_claims_document_does_not_print_it_as_replicated(tmp_path: Path) -> None:
    _plant(tmp_path, contract_phase="late", discovery="card", test="card")
    report, claim = _claim(tmp_path)
    assert claim.replication == ""
    assert report.anything_demonstrated is False
    sentence = claim.sentence()
    assert "Replicated" not in sentence
    assert "no replication record for this window" in sentence
    # The single-window sentence still governs.
    assert "until it replicates on a window it was not found on" in sentence


# --- a record that cannot be matched -------------------------------------


@pytest.mark.parametrize(
    "contract, discovery, test",
    [
        ("late", None, None),       # written before #254
        ("late", "late", None),     # half a record
        (None, "late", "late"),     # the figure names no window
        ("late", "card", "late"),   # never written by the runner; still no
    ],
)
def test_an_unmatched_record_supports_nothing(
    tmp_path: Path, contract, discovery, test
) -> None:
    _plant(tmp_path, contract_phase=contract, discovery=discovery, test=test)
    verdict = _verdict(tmp_path)
    assert verdict.supported is False
    assert verdict.replicated is False
    assert "no replication record for this window" in verdict.reason
    report, claim = _claim(tmp_path)
    assert claim.replication == ""
    assert report.anything_demonstrated is False


# --- the same window still counts ----------------------------------------


def test_a_replication_of_the_figure_s_own_window_still_counts(
    tmp_path: Path,
) -> None:
    _plant(tmp_path, contract_phase="late", discovery="late", test="late")
    verdict = _verdict(tmp_path)
    assert verdict.supported is True
    assert verdict.replicated is True
    report, claim = _claim(tmp_path)
    assert claim.replication.startswith("**Replicated")
    assert report.anything_demonstrated is True


def test_a_market_read_from_the_card_window_matches_a_card_record(
    tmp_path: Path,
) -> None:
    """`by_market_with_other_windows` fills it from the card file: its window."""
    card = {"phase": "card", "phase_hours": 9.5, "bets": 4000,
            "by_market": {"blocked_shots": _entry(0.05)}}
    _plant(tmp_path, contract_phase="late", discovery="card", test="card",
           card_file=card)
    assert _verdict(tmp_path).supported is True
    _plant(tmp_path, contract_phase="late", discovery="late", test="late",
           card_file=card)
    verdict = _verdict(tmp_path)
    assert verdict.supported is False
    assert "`late`" in verdict.reason and "`card` window" in verdict.reason


def test_a_failed_replication_of_another_window_is_not_attached_either(
    tmp_path: Path,
) -> None:
    """Contradicted on two `card` seasons says nothing of the `late` figure."""
    _plant(tmp_path, contract_phase="late", discovery="card", test="card",
           state=rep.CONTRADICTED)
    _, claim = _claim(tmp_path)
    assert claim.replication == ""
    assert "no replication record for this window" in claim.sentence()
    assert _verdict(tmp_path).supported is False


def test_the_matching_rule_itself() -> None:
    same = {"discovery_phase": "late", "test_phase": "late"}
    assert rep.window_mismatch(same, "late") == ""
    assert rep.window_mismatch(same, "card")
    assert rep.window_mismatch(same, "")
    assert "written before" in rep.window_mismatch({}, "late")
    assert "written before" in rep.window_mismatch({"discovery_phase": "late"}, "late")
    assert "written before" in rep.window_mismatch({"test_phase": "late"}, "late")
    assert "this figure names no snapshot window" in rep.window_mismatch(same, "")
    assert rep.window_mismatch({"discovery_phase": "card", "test_phase": "late"}, "late")
    assert rep.window_mismatch({"discovery_phase": "late", "test_phase": "card"}, "late")
