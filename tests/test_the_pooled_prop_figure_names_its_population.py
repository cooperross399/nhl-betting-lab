"""The claims document headed a six-market pool "every measured prop market".

`what_we_can_claim.md` takes its pooled prop figure from the contract
(`late`) window's backtest and its per-market list from both windows: a prop
market the `late` window never priced is read from the `card` window and
labelled. So "## Across every measured prop market: -0.3% over 25,911 bets in
the `late` window" sat above a list of seven measured prop markets, one of
them `hits` — -1.3% over 5,178 bets, measured only in the `card` window and
not in the pool (9,379 + 6,194 + 564 + 3,761 + 1,727 + 4,286 = 25,911). The
heading named a population the figure does not cover, and nothing in the
section said which measured market was left out. Found by the failure-shape
audit (confirmed 2/3; the third refuter read the body's window phrase as
enough). The pool itself is right: pooling across windows would take the
better of two moments, which this lab refuses.

What these tests hold, on the production sequence (the `card` window saved
with its label, then the `late` window over the contract file): the heading
counts the markets the pooled figure covers out of the prop markets measured,
the section names each one left out and its window, the pooled number is the
contract window's own, and with nothing left out the heading still reads
"every measured prop market".
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from nhl_betting_lab.reports import what_we_can_claim as claims
from nhl_betting_lab.reports.player_props_backtest import (
    run_backtest,
    save_backtest,
)


TEAM_MAP = {"carolina hurricanes": "CAR", "ottawa senators": "OTT"}
COMMENCE = pd.Timestamp("2025-01-06T00:10:00Z")


def _name(index: int) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    return "Skater " + "".join(
        letters[(index // 26**power) % 26] for power in (2, 1, 0)
    ).capitalize()


def _wagers(
    market: str, wins: int, losses: int, *, first: int, hours_before: float
) -> tuple[list, list]:
    prices, samples = [], []
    for index in range(first, first + wins + losses):
        player = _name(index)
        prices.append(
            {
                "date": "2025-01-05", "commence_time": COMMENCE.isoformat(),
                "snapshot": (
                    COMMENCE - pd.Timedelta(hours=hours_before)
                ).isoformat(),
                "provider_event_id": "evt-car-ott",
                "home_team": "Carolina Hurricanes", "away_team": "Ottawa Senators",
                "market": market, "player": player, "selection": "over",
                "line": 0.5, "american_odds": 100, "book": "DraftKings",
            }
        )
        samples.append(
            {
                "date": "2025-01-05", "market": market, "player": player,
                "player_id": 8_470_000 + index, "team": "CAR", "mean": 1.2,
                "dispersion_r": None,
                "actual": 1.0 if index - first < wins else 0.0,
            }
        )
    return prices, samples


def _run(directory: Path, phase: str, hours: float, markets: dict, label: str = ""):
    prices, samples = [], []
    for first, (market, (wins, losses)) in enumerate(markets.items()):
        quotes, rows = _wagers(
            market, wins, losses, first=1_000 * first, hours_before=hours
        )
        prices += quotes
        samples += rows
    report = run_backtest(
        pd.DataFrame(prices), pd.DataFrame(samples), edge_threshold=-1.0,
        phase=phase, team_names=TEAM_MAP,
    )
    save_backtest(report, output_dir=directory, label=label)
    return report


def _late(directory: Path):
    """The contract window: two prop markets, 300 bets between them."""
    return _run(
        directory, "late", 4.0,
        {"shots_on_goal": (110, 90), "points": (45, 55)},
    )


def _card(directory: Path):
    """The card window prices `hits`, which the `late` window has none of."""
    return _run(
        directory, "card", 9.5,
        {"hits": (60, 60), "shots_on_goal": (130, 70)}, label="card",
    )


def _team(directory: Path) -> None:
    """A measured team market: in the document, and never in the prop pool."""
    (directory / "team_markets_measurement.json").write_text(
        json.dumps(
            {"phase": "late", "phase_hours": 1.5, "markets": [{
                "market": "moneyline", "bets": 954, "roi": -0.066,
                "low": -0.136, "high": 0.004, "includes_zero": True,
                "looks": 3, "survives_correction": False,
            }]}
        ),
        encoding="utf-8",
    )


def _pooled_section(rendered: str) -> str:
    start = rendered.index("## Across")
    return rendered[start:rendered.index("## Measured against real prices")]


def test_the_heading_counts_the_markets_the_pool_covers(tmp_path: Path) -> None:
    _card(tmp_path)
    late = _late(tmp_path)
    _team(tmp_path)

    report = claims.build_claims_report(output_dir=tmp_path)
    rendered = claims.render_claims(report)
    section = _pooled_section(rendered)
    hits = next(claim for claim in report.claims if claim.market == "hits")

    assert hits.measured and hits.window
    assert "every measured prop market" not in rendered
    assert section.startswith("## Across 2 of the 3 measured prop markets\n")
    assert f"over {late.overall.bets:,} bets in the `late` window, 4.0 hours" in section


def test_the_section_names_what_it_leaves_out(tmp_path: Path) -> None:
    _card(tmp_path)
    _late(tmp_path)
    _team(tmp_path)

    section = _pooled_section(
        claims.render_claims(claims.build_claims_report(output_dir=tmp_path))
    )

    assert (
        "It does not include `hits`, measured only in the `card` window, 9.5 "
        "hours before face-off. Windows are never pooled: a wager priced at "
        "two moments is two questions." in section
    )
    assert "`shots_on_goal`" not in section
    assert "`moneyline`" not in section


def test_the_pooled_figure_is_the_contract_window_alone(tmp_path: Path) -> None:
    """Folding `hits` in would pool two windows — the better of two moments."""
    card = _card(tmp_path)
    late = _late(tmp_path)

    report = claims.build_claims_report(output_dir=tmp_path)

    assert report.overall_bets == late.overall.bets == 300
    assert report.overall_roi == late.overall.roi
    assert card.by_market["hits"].bets == 120


def test_with_nothing_left_out_the_heading_still_says_every(tmp_path: Path) -> None:
    _late(tmp_path)
    _team(tmp_path)

    rendered = claims.render_claims(claims.build_claims_report(output_dir=tmp_path))
    section = _pooled_section(rendered)

    assert section.startswith("## Across every measured prop market\n")
    assert "It does not include" not in section
