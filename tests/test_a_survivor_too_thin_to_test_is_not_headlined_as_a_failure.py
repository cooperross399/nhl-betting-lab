"""The headline called a survivor "did **not** replicate" on a window too thin to test it.

A market that survives correction on the discovery window and has fewer than
`MINIMUM_TEST_BETS` bets on the test window is `untestable`, and its own
reason says "Calling this a failure would be the same over-reading in the
other direction". `ReplicationReport.headline()` skipped its "measured no
bets" branch whenever any market had test bets, found nothing replicated, and
fell through to "`<market>` survived on **D** and did **not** replicate on
**T**" for every survivor, untestable ones included. That headline is written
to `replication.md` and `replication.json`. Found by sweep 4
(replication-headline-untestable-as-not-replicated, 2 of 2 verifiers).

What these tests hold: a survivor too thin to test is headlined "not tested
on **T** (too few bets)"; "did **not** replicate" is kept for a survivor that
was tested and came back not confirmed or contradicted, and each is named in
its own sentence when both happen at once.
"""

from __future__ import annotations

from nhl_betting_lab.reports import replication as rep
from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE


def _result(bets: int, roi: float, survives: bool) -> dict:
    return {"bets": bets, "roi": roi, "survives_correction": survives}


def _compare(discovery: dict, test: dict) -> rep.ReplicationReport:
    return rep.compare(
        {"by_market": discovery}, {"by_market": test},
        discovery_label="D", test_label="T",
    )


def test_a_survivor_the_test_window_was_too_thin_for_is_not_a_failure() -> None:
    """The sweep's repro: `points` gives the test window bets, so the
    "measured no bets" branch is skipped."""
    report = _compare(
        {"blocked_shots": _result(2700, 0.046, True),
         "points": _result(3400, -0.03, False)},
        {"blocked_shots": _result(12, 0.05, False),
         "points": _result(3400, -0.05, True)},
    )
    blocked = next(i for i in report.markets if i.market == "blocked_shots")
    headline = report.headline()

    assert blocked.state == rep.UNTESTABLE
    assert "did **not** replicate" not in headline, headline
    assert "`blocked_shots`" in headline
    assert "not tested on **T** (too few bets)" in headline
    assert NO_DEMONSTRATED_EDGE in headline, "still no demonstrated edge"


def test_just_under_the_minimum_is_untested_and_at_it_is_tested() -> None:
    under = _compare(
        {"goals": _result(500, 0.1, True)},
        {"goals": _result(rep.MINIMUM_TEST_BETS - 1, 0.02, False)},
    )
    at = _compare(
        {"goals": _result(500, 0.1, True)},
        {"goals": _result(rep.MINIMUM_TEST_BETS, 0.02, False)},
    )

    assert "not tested on **T** (too few bets)" in under.headline()
    assert "did **not** replicate" not in under.headline()
    assert at.markets[0].state == rep.NOT_CONFIRMED
    assert "did **not** replicate on **T**" in at.headline()
    assert "not tested" not in at.headline()


def test_a_contradicted_survivor_still_did_not_replicate() -> None:
    report = _compare(
        {"goals": _result(500, 0.1, True)},
        {"goals": _result(400, -0.08, False)},
    )

    assert report.markets[0].state == rep.CONTRADICTED
    assert "`goals` survived on **D** and did **not** replicate on **T**" in (
        report.headline()
    )


def test_a_failed_and_an_untested_survivor_are_named_apart() -> None:
    report = _compare(
        {"goals": _result(500, 0.1, True),
         "assists": _result(800, 0.07, True)},
        {"goals": _result(400, 0.02, False),
         "assists": _result(30, 0.03, False)},
    )
    headline = report.headline()
    failed, _, rest = headline.partition("did **not** replicate")

    assert "`goals`" in failed and "`assists`" not in failed, headline
    assert "`assists`" in rest and "not tested on **T** (too few bets)" in rest
    assert "`goals`" not in rest, headline
