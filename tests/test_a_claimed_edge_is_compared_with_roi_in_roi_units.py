"""The props backtest compared a probability-point edge against an ROI.

`render_backtest`'s "claimed edge against the realised one" paragraph printed
the mean selected edge (`side_probability - implied`, in probability points)
beside the flat-stake ROI (return per unit staked) and called the difference
the shrinkage that selection causes. Those are different units. A bet the
model gives 45% at +200 (implied 33.3%) claims an edge of 11.7 probability
points but an expected return of 0.45 * 3.0 - 1 = +35% per unit: at plus-money
prices a point of probability is worth the decimal price in return, so part of
the printed "gap" was the units, not the selection. (At -200 it goes the other
way: 75% against 66.7% is 8.3 points but +12.5% per unit.)

What these tests hold, on hand-built bets whose two units differ materially:
the number set against the realised ROI is the model's own expected return
per unit staked, mean(p * decimal - 1), computed on the same basis as the ROI;
the probability-point edge, if printed, is labelled as points and is not the
figure the gap is measured from.
"""

from __future__ import annotations

import re

from nhl_betting_lab.reports import player_props_backtest as bt
from nhl_betting_lab.stats import roi_interval


def _bet(
    *, odds: float, p: float, implied: float, won: bool, profit: float
) -> bt.PlacedBet:
    return bt.PlacedBet(
        date="2025-01-01",
        market="shots_on_goal",
        player="X",
        line=2.5,
        selection="over",
        american_odds=odds,
        model_probability=p,
        implied_probability=implied,
        edge=p - implied,
        actual=3.0 if won else 1.0,
        won=won,
        push=False,
        profit=profit,
    )


def _report(bets: list[bt.PlacedBet]) -> bt.BacktestReport:
    report = bt.BacktestReport(generated_at="2025-01-02", edge_threshold=0.05)
    report.bets = bets
    report.overall = roi_interval(
        [bet.profit for bet in bets], wins=sum(1 for bet in bets if bet.won)
    )
    report.by_market["shots_on_goal"] = report.overall
    return report


def _plus_two_hundred() -> bt.BacktestReport:
    # Ten +200 bets the model gives 45% (implied 1/3): 11.7 points of edge,
    # +35.0% expected per unit. Three win: 3 * 2 - 7 = -1u, ROI -10.0%.
    return _report(
        [
            _bet(odds=200, p=0.45, implied=1 / 3, won=True, profit=2.0)
            for _ in range(3)
        ]
        + [
            _bet(odds=200, p=0.45, implied=1 / 3, won=False, profit=-1.0)
            for _ in range(7)
        ]
    )


def _paragraph(rendered: str) -> str:
    section = rendered.split("### The claimed edge against the realised one", 1)[1]
    return section.split("###", 1)[0]


def test_the_claim_set_against_roi_is_expected_return_per_unit() -> None:
    paragraph = _paragraph(bt.render_backtest(_plus_two_hundred()))

    # The model's own expected return per unit staked, on the ROI's basis.
    assert "**+35.0%**" in paragraph
    assert "**-10.0%**" in paragraph
    assert "per unit staked" in paragraph


def test_the_probability_point_edge_is_not_printed_as_a_return() -> None:
    paragraph = _paragraph(bt.render_backtest(_plus_two_hundred()))

    # 11.7 points is the edge in probability; it may appear, but only
    # labelled as points, never in the bolded slot that is set against ROI.
    assert "**+11.7%**" not in paragraph
    for match in re.finditer(r"11\.7", paragraph):
        assert "point" in paragraph[match.end(): match.end() + 30]


def test_the_claim_is_a_mean_over_bets_at_their_own_prices() -> None:
    # One +200 bet at 45% (+35.0%) and one -200 bet at 75% (implied 2/3):
    # 0.75 * 1.5 - 1 = +12.5%. Mean +23.75%, printed +23.8%; the mean
    # probability-point edge is (11.67 + 8.33) / 2 = 10.0 points.
    report = _report(
        [
            _bet(odds=200, p=0.45, implied=1 / 3, won=True, profit=2.0),
            _bet(odds=-200, p=0.75, implied=2 / 3, won=False, profit=-1.0),
        ]
    )

    paragraph = _paragraph(bt.render_backtest(report))

    assert "**+23.8%**" in paragraph
    assert "**+50.0%**" in paragraph  # realised: (2 - 1) / 2
    assert "**+10.0%**" not in paragraph


def test_the_paragraph_states_its_sample_size() -> None:
    paragraph = _paragraph(bt.render_backtest(_plus_two_hundred()))

    assert "10 bets" in paragraph
