"""An untestable replication is not a failed one.

The evidence bundle said of `points` "The held-out window did not confirm it
(untestable)". `replication.md` records the opposite of a failure: the
held-out 2025-26 window excludes zero after correction on its own (-5.4% over
3,468 bets). The verdict is untestable only because the 2024-25 discovery
window did not survive correction alone, so there was no first result for the
second window to confirm. "Did not confirm" reads as a replication that was
run and failed; nothing was run.

"Untestable" has three causes in `reports/replication.py` (no first-window
bets, no first-window survivor, too few test-window bets), and the bundle
names the one the record gives rather than assuming the first.
"""
from __future__ import annotations

import json
from pathlib import Path

from nhl_betting_lab.reports import allowlist_evidence as ev


def _write(directory: Path, name: str, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def _setup(directory: Path, *, roi: float, record: dict) -> ev.MarketVerdict:
    directory.mkdir(parents=True, exist_ok=True)
    for name in ev.EVIDENCE_FILENAMES:
        (directory / name).write_text(f"# {name}\n", encoding="utf-8")
    _write(
        directory,
        "player_props_backtest.json",
        {
            "by_market": {
                "points": {
                    "bets": 6202, "roi": roi, "includes_zero": False,
                    "survives_correction": True, "looks": 7,
                    "adjusted_low": roi - 0.03, "adjusted_high": roi + 0.03,
                }
            }
        },
    )
    _write(directory, "replication.json", {"markets": [{"market": "points", **record}]})
    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=directory, repository_root=directory
    )
    return next(v for v in bundle.verdicts if v.market == "points")


# The `points` row of the committed replication record, as its JSON carries it.
POINTS_AS_RECORDED = {
    "state": "untestable",
    "discovery_bets": 2726, "discovery_roi": -0.033, "discovery_survived": False,
    "test_bets": 3468, "test_roi": -0.054, "test_survived": True,
    "reason": "Nothing survived correction on the first window, so there is "
    "no result here to replicate.",
}


def test_points_is_not_said_to_have_failed_a_replication_it_never_had(
    tmp_path: Path,
) -> None:
    verdict = _setup(tmp_path, roi=-0.044, record=POINTS_AS_RECORDED)

    assert "did not confirm" not in verdict.reason
    assert "discovery window did not carry it alone" in verdict.reason
    assert "Nothing was tested on the held-out window" in verdict.reason
    # Still not a demonstrated deficit, still the argument against enabling.
    assert "This is a demonstrated deficit" not in verdict.reason
    assert "argues against enabling" in verdict.reason
    assert verdict.supported is False


def test_a_positive_market_is_not_said_to_have_failed_one_either(
    tmp_path: Path,
) -> None:
    verdict = _setup(tmp_path, roi=0.05, record=POINTS_AS_RECORDED)

    assert "did not confirm" not in verdict.reason
    assert "discovery window did not carry it alone" in verdict.reason
    assert verdict.supported is False


def test_a_thin_test_window_is_named_as_the_cause(tmp_path: Path) -> None:
    """The discovery window carried it; the held-out one was too small."""
    verdict = _setup(
        tmp_path,
        roi=-0.044,
        record={
            "state": "untestable",
            "discovery_bets": 2726, "discovery_survived": True,
            "test_bets": 40, "test_survived": False,
        },
    )

    assert "did not confirm" not in verdict.reason
    assert "discovery window did not carry it alone" not in verdict.reason
    assert "40 bet(s)" in verdict.reason
    assert "Nothing was tested on the held-out window" in verdict.reason


def test_an_unmeasured_discovery_window_is_named_as_the_cause(
    tmp_path: Path,
) -> None:
    verdict = _setup(
        tmp_path,
        roi=-0.044,
        record={
            "state": "untestable",
            "discovery_bets": 0, "discovery_survived": False,
            "test_bets": 3468, "test_survived": True,
        },
    )

    assert "did not confirm" not in verdict.reason
    assert "did not measure it" in verdict.reason
    assert "discovery window did not carry it alone" not in verdict.reason


def test_an_untestable_state_with_no_cause_recorded_still_is_not_a_failure(
    tmp_path: Path,
) -> None:
    verdict = _setup(tmp_path, roi=-0.044, record={"state": "untestable"})

    assert "did not confirm" not in verdict.reason
    assert "Nothing was tested on the held-out window" in verdict.reason
    assert "(untestable)" in verdict.reason


def test_a_replication_that_ran_and_declined_keeps_its_wording(
    tmp_path: Path,
) -> None:
    verdict = _setup(
        tmp_path,
        roi=0.05,
        record={
            "state": "not confirmed",
            "discovery_bets": 2726, "discovery_survived": True,
            "test_bets": 3468, "test_survived": False,
        },
    )

    assert "The held-out window did not confirm it (not confirmed)" in verdict.reason
    assert verdict.supported is False
