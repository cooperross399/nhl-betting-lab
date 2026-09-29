"""The replication headline names survivors that failed beside those that held.

`ReplicationReport.headline` returned the replicated sentence alone as soon as
any market replicated. With `points` replicated and `blocked_shots`, a
discovery survivor at +5%, contradicted on the test window at -3%, the
headline written to `replication.md`, to `replication.json`'s `headline` and
to the runner's log read only "`points` held on **T** as well as **D**". The
contradicted survivor, the shape this lab keeps retracting, appeared only in
the table. Found by sweep 5 (replication-headline-omits-failed-survivors).
"""

from __future__ import annotations

from nhl_betting_lab.reports import replication as rep
from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE


def _market(name: str, state: str, *, test_bets: int = 3000,
            test_roi: float = 0.04) -> rep.MarketReplication:
    return rep.MarketReplication(
        market=name, discovery_bets=4000, discovery_roi=0.05,
        discovery_survived=True, test_bets=test_bets, test_roi=test_roi,
        test_survived=state == rep.REPLICATED, state=state, reason="",
    )


def _report(*markets: rep.MarketReplication) -> rep.ReplicationReport:
    return rep.ReplicationReport(
        generated_at="2026-09-29T00:00:00+00:00", discovery_label="D",
        test_label="T", markets=list(markets),
    )


def test_a_contradicted_survivor_is_headlined_beside_a_replicated_one() -> None:
    headline = _report(
        _market("points", rep.REPLICATED),
        _market("blocked_shots", rep.CONTRADICTED, test_roi=-0.03),
    ).headline()
    assert "`points` held on **T** as well as **D**" in headline
    assert "`blocked_shots` survived on **D** and did **not** replicate" in headline
    assert NO_DEMONSTRATED_EDGE in headline


def test_an_untested_survivor_is_headlined_beside_a_replicated_one() -> None:
    headline = _report(
        _market("points", rep.REPLICATED),
        _market("blocked_shots", rep.UNTESTABLE, test_bets=12),
    ).headline()
    assert "`points` held" in headline
    assert "`blocked_shots` survived on **D** and was not tested" in headline


def test_a_not_confirmed_survivor_is_headlined_too() -> None:
    headline = _report(
        _market("points", rep.REPLICATED),
        _market("hits", rep.NOT_CONFIRMED),
    ).headline()
    assert "`hits` survived on **D** and did **not** replicate" in headline


def test_when_every_survivor_held_the_headline_is_unchanged() -> None:
    assert _report(_market("points", rep.REPLICATED)).headline() == (
        "`points` held on **T** as well as **D**. Two windows agreeing is "
        "worth considerably more than one window measured precisely, and it "
        "is still two windows."
    )
