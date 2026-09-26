"""The bundle's headline must not deny what its own market lines say.

With nothing supported, `recommendation()` printed "Every market is either
unmeasured against real prices or measured with an interval that includes
zero" -- directly above a `points` line saying its corrected interval
excludes zero on the losing side and a `blocked_shots` line saying its
corrected interval excludes zero on one window. That is today's real state
(`points` -4.2% surviving correction as a deficit, `blocked_shots` +7.9%
surviving on one window and not confirmed on a held-out one). The headline
now names each such market for what it is, and keeps the old sentence only
for the markets it is true of. No verdict moves: nothing becomes supported.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhl_betting_lab.reports import allowlist_evidence as ev
from nhl_betting_lab.stats import roi_interval


FAMILY = "6 markets and the overall figure"


def _interval(returns: list[float]) -> dict:
    measured = roi_interval(returns, looks=7, family=FAMILY)
    return {
        "bets": measured.bets,
        "roi": measured.roi,
        "low": measured.low,
        "high": measured.high,
        "includes_zero": measured.includes_zero,
        "looks": 7,
        "family": measured.family,
        "adjusted_low": measured.adjusted_low,
        "adjusted_high": measured.adjusted_high,
        "survives_correction": measured.survives_correction,
        "profit": measured.profit,
    }


# +8% over 3,000 at even money, and -8.7% over 6,140: both survive the
# seven-look correction, one on each side.
BLOCKED = [1.0] * 1620 + [-1.0] * 1380
POINTS = [0.9] * 2950 + [-1.0] * 3190
# +1% over 3,000: spans zero, before and after correction.
SHOTS = [1.0] * 1515 + [-1.0] * 1485


def _plant(directory: Path, by_market: dict, replication: list[dict]) -> ev.EvidenceBundle:
    directory.mkdir(parents=True, exist_ok=True)
    for name in ev.EVIDENCE_FILENAMES:
        (directory / name).write_text(f"# {name}\n", encoding="utf-8")
    everything: list[float] = []
    for returns in by_market.values():
        everything.extend(returns)
    (directory / "player_props_backtest.json").write_text(
        json.dumps(
            {
                "rows_read": 100000,
                "phase": "late",
                "phase_hours": 4.1,
                "by_market": {m: _interval(r) for m, r in by_market.items()},
                "overall": _interval(everything),
            }
        ),
        encoding="utf-8",
    )
    (directory / "team_markets_measurement.json").write_text(
        json.dumps({"stored_rows": 10, "markets": []}), encoding="utf-8"
    )
    (directory / "replication.json").write_text(
        json.dumps({"markets": replication}), encoding="utf-8"
    )
    return ev.build_bundle(
        provider_name="the_odds_api", output_dir=directory, repository_root=directory
    )


def _todays_state(tmp_path: Path) -> ev.EvidenceBundle:
    return _plant(
        tmp_path,
        {"blocked_shots": BLOCKED, "points": POINTS, "shots_on_goal": SHOTS},
        [
            {"market": "blocked_shots", "state": "not confirmed"},
            {"market": "points", "state": "untestable"},
        ],
    )


def test_the_headline_no_longer_says_every_interval_includes_zero(tmp_path: Path) -> None:
    bundle = _todays_state(tmp_path)
    recommendation = bundle.recommendation()
    lines = {v.market: v.reason for v in bundle.verdicts}

    # The lines say it; the headline must not deny it.
    assert "excludes zero" in lines["points"]
    assert "excludes zero" in lines["blocked_shots"]
    assert "Every market is either" not in recommendation
    # The verdict itself is unchanged.
    assert bundle.supported_markets == ()
    assert "supports enabling nothing" in recommendation


def test_the_headline_names_the_one_window_result_as_a_candidate(tmp_path: Path) -> None:
    recommendation = _todays_state(tmp_path).recommendation()
    candidate = recommendation.split("`blocked_shots`", 1)
    assert len(candidate) == 2, recommendation
    after = candidate[1].split("`points`", 1)[0]
    assert "one window" in after
    assert "held-out" in after
    assert "candidate" in after


def test_the_headline_names_the_surviving_loss_as_an_argument_against(tmp_path: Path) -> None:
    recommendation = _todays_state(tmp_path).recommendation()
    assert "`points`" in recommendation
    after = recommendation.split("`points`", 1)[1]
    assert "argues against enabling" in after
    # Not replicated, so not called demonstrated.
    assert "demonstrated deficit" not in recommendation.replace(
        "not a demonstrated deficit", ""
    )


def test_the_markets_that_do_span_zero_keep_the_old_sentence(tmp_path: Path) -> None:
    recommendation = _todays_state(tmp_path).recommendation()
    assert "Every other market is either unmeasured against real prices or" in recommendation
    assert "`shots_on_goal`" not in recommendation


def test_with_nothing_conclusive_the_sentence_is_unchanged(tmp_path: Path) -> None:
    bundle = _plant(tmp_path, {"shots_on_goal": SHOTS}, [])
    assert bundle.recommendation() == (
        "**The evidence supports enabling nothing.** Every market is either "
        "unmeasured against real prices or measured with an interval that "
        "includes zero, which means no demonstrated edge."
    )


def test_a_replicated_loss_is_named_a_demonstrated_deficit(tmp_path: Path) -> None:
    bundle = _plant(
        tmp_path,
        {"points": POINTS},
        [{"market": "points", "state": "replicated"}],
    )
    recommendation = bundle.recommendation()
    assert "`points`" in recommendation
    assert "demonstrated deficit" in recommendation
    assert "argues against enabling" in recommendation
    assert bundle.supported_markets == ()
