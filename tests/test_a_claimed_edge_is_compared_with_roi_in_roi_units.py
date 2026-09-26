"""The props backtest compared a probability-point edge against an ROI.

`render_backtest`'s "claimed edge against the realised one" paragraph printed
the mean selected edge (`side_probability - implied`, in probability points)
beside the flat-stake ROI (return per unit staked) and called the difference
the shrinkage that selection causes. Those are different units. A point of
probability is worth the decimal price in return, at every price (expected
return = edge x decimal, and the decimal is always above one): a bet the model
gives 45% at +200 (implied 33.3%) claims an edge of 11.7 probability points
but an expected return of 0.45 * 3.0 - 1 = +35% per unit, and 75% at -200
(implied 66.7%) is 8.3 points and +12.5% per unit. So part of the printed
"gap" was the units, not the selection.

And the model's probability on a whole-number line is conditional on no push
(`CountDistribution.over_probability`), while the ROI keeps a push in its
denominator at zero profit. So a bet's claim on the ROI's basis is
(1 - P(push)) * (p * decimal - 1): over 2.0 with P(X=2) = 0.3 and p = 0.6 at
+100 claims +14% per unit staked, not +20%.

What these tests hold, on hand-built bets whose units differ materially: the
number set against the realised ROI is the model's own expected return per
unit staked, averaged over every bet (pushes included) at each bet's own price
and push chance; the probability-point edge, if printed, is labelled as points
and is not the figure the gap is measured from; the run carries each bet's
push chance from its distribution, and the bets CSV keeps its columns.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from nhl_betting_lab.models.counts import Poisson
from nhl_betting_lab.reports import player_props_backtest as bt
from nhl_betting_lab.stats import roi_interval


def _bet(
    *,
    odds: float,
    p: float,
    implied: float,
    won: bool,
    profit: float,
    selection: str = "over",
    line: float = 2.5,
    push: bool = False,
    push_probability: float = 0.0,
) -> bt.PlacedBet:
    return bt.PlacedBet(
        date="2025-01-01",
        market="shots_on_goal",
        player="X",
        line=line,
        selection=selection,
        american_odds=odds,
        model_probability=p,
        implied_probability=implied,
        edge=p - implied,
        actual=line if push else (3.0 if won else 1.0),
        won=won,
        push=push,
        profit=profit,
        push_probability=push_probability,
    )


def _report(bets: list[bt.PlacedBet]) -> bt.BacktestReport:
    report = bt.BacktestReport(generated_at="2025-01-02", edge_threshold=0.05)
    report.bets = bets
    report.overall = roi_interval(
        [bet.profit for bet in bets],
        wins=sum(1 for bet in bets if bet.won),
        pushes=sum(1 for bet in bets if bet.push),
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


def test_the_paragraph_does_not_say_the_units_differ_only_at_plus_money() -> None:
    paragraph = _paragraph(bt.render_backtest(_plus_two_hundred()))

    assert "plus-money" not in paragraph
    assert "at any price" in paragraph


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


def test_an_under_is_claimed_at_its_own_side_probability() -> None:
    # `model_probability` is already the side's probability: an under the
    # model gives 60% at +100 claims 0.6 * 2 - 1 = +20%, not the -20% its
    # complement would.
    report = _report(
        [
            _bet(
                odds=100, p=0.6, implied=0.5, won=True, profit=1.0,
                selection="under",
            )
        ]
    )

    paragraph = _paragraph(bt.render_backtest(report))

    assert "**+20.0%**" in paragraph
    assert "**-20.0%**" not in paragraph


def test_a_push_possible_line_is_claimed_on_the_rois_basis() -> None:
    # Over 2.0 with P(X=2) = 0.3 and a no-push P(over) of 0.6 at +100:
    # (1 - 0.3) * (0.6 * 2 - 1) = +14.0%. It pushed (profit 0). Beside it a
    # half-point bet at 60%, +100, that won: +20.0%. The claim is the mean
    # over BOTH bets, pushes included as the ROI includes them:
    # (14 + 20) / 2 = +17.0%, against a realised (0 + 1) / 2 = +50.0%.
    # Ignoring the push chance would print +20.0%; dividing by the one bet
    # that did not push would print +34.0%.
    report = _report(
        [
            _bet(
                odds=100, p=0.6, implied=0.5, won=False, profit=0.0,
                line=2.0, push=True, push_probability=0.3,
            ),
            _bet(odds=100, p=0.6, implied=0.5, won=True, profit=1.0),
        ]
    )

    paragraph = _paragraph(bt.render_backtest(report))

    assert "**+17.0%**" in paragraph
    assert "**+50.0%**" in paragraph
    assert "**+20.0%**" not in paragraph
    assert "**+34.0%**" not in paragraph


def _whole_line_run() -> bt.BacktestReport:
    # Poisson(3.4) over 3.0 at +150: P(X=3) ~ 0.223, no-push P(over) ~ 0.569
    # against 0.40 implied, so every row is bet.
    samples = pd.DataFrame(
        [
            {
                "date": f"2025-01-{1 + index % 28:02d}",
                "game_id": 1000 + index,
                "player_id": 2000 + index,
                "market": "shots_on_goal",
                "player": f"Player {index}",
                "mean": 3.4,
                "dispersion_r": float("nan"),
                "actual": 5.0,
                "toi_seconds": 1200,
            }
            for index in range(20)
        ]
    )
    prices = pd.DataFrame(
        [
            {
                "date": row.date,
                "commence_time": f"{row.date}T18:00:00Z",
                "market": row.market,
                "player": row.player,
                "selection": "over",
                "line": 3.0,
                "american_odds": 150,
            }
            for row in samples.itertuples()
        ]
    )
    return bt.run_backtest(prices, samples, edge_threshold=0.05)


def test_the_run_carries_each_bets_push_chance_from_its_distribution() -> None:
    report = _whole_line_run()

    expected = Poisson(mean=3.4).push_probability(3.0)
    assert report.bets
    assert expected > 0.2
    for bet in report.bets:
        assert abs(bet.push_probability - expected) < 1e-12


def test_the_bets_csv_keeps_its_columns(tmp_path: Path) -> None:
    report = _whole_line_run()

    paths = bt.save_backtest(report, output_dir=tmp_path)

    columns = list(pd.read_csv(paths["csv"]).columns)
    assert "push_probability" not in columns
    assert columns == [
        "date", "market", "player", "line", "selection", "american_odds",
        "model_probability", "implied_probability", "edge", "actual", "won",
        "push", "profit", "book",
    ]


def test_the_paragraph_states_its_sample_size() -> None:
    paragraph = _paragraph(bt.render_backtest(_plus_two_hundred()))

    assert "10 bets" in paragraph
