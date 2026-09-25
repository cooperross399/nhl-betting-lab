"""The props family correction printed its size as a count of markets.

`run_backtest` corrects over every market it measured PLUS the overall
figure (`looks = len(markets) + 1`, deliberately: seven figures are computed
from one body of data), and every sentence that printed that number called it
markets. The `late` window measures 6 markets, so each verdict read
"correcting for the 7 markets tested", and `what_we_can_claim.md` and the
allowlist bundle repeated "the 7 markets measured on the same data" (five
lines of the bundle) — beside a table of 6 market rows, a section saying "7
figures were computed", and a CLAUDE.md recording 6 markets. The card window
measures 7 and printed 8, which reached the bundle's `hits` line. The team
family counts markets only, so one claims document used one phrase for two
units. Found by the failure-shape audit (confirmed 3/3, low severity: the
correction itself is intended and no verdict moves; the stated count is
false).

What these tests hold, on a real backtest saved to disk and read back by the
claims document and the bundle: the family keeps its size (the markets and
the overall figure, Bonferroni over both), and every sentence that states it
says what it counted — "3 figures measured on the same data (2 markets and
the overall figure)" — while a family of markets alone is still called
markets.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import stats
from nhl_betting_lab.reports import allowlist_evidence as ev
from nhl_betting_lab.reports import what_we_can_claim as claims
from nhl_betting_lab.reports.player_props_backtest import (
    run_backtest,
    save_backtest,
)


TEAM_MAP = {"carolina hurricanes": "CAR", "ottawa senators": "OTT"}

#: 7:10pm ET on 2025-01-05 is 00:10Z on the 6th.
COMMENCE = "2025-01-06T00:10:00Z"

#: What the two-market fixture's family must be called wherever it is stated.
FAMILY = "3 figures measured on the same data (2 markets and the overall figure)"


def _name(index: int) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    return "Skater " + "".join(
        letters[(index // 26**power) % 26] for power in (2, 1, 0)
    ).capitalize()


def _wagers(market: str, wins: int, losses: int, *, first: int) -> tuple[list, list]:
    """`wins + losses` wagers on distinct players, over 0.5 at +100, one book."""
    prices, samples = [], []
    for index in range(first, first + wins + losses):
        player = _name(index)
        prices.append(
            {
                "date": "2025-01-05", "commence_time": COMMENCE,
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


def _report():
    """Two markets: `points` survives the family, `shots_on_goal` clears 95%
    uncorrected (z about 2.2) and not once the three figures are counted."""
    points = _wagers("points", 280, 120, first=0)
    shots = _wagers("shots_on_goal", 222, 178, first=1_000)
    return run_backtest(
        pd.DataFrame(points[0] + shots[0]),
        pd.DataFrame(points[1] + shots[1]),
        edge_threshold=-1.0, phase="", team_names=TEAM_MAP,
    )


@pytest.fixture()
def saved(tmp_path: Path) -> Path:
    save_backtest(_report(), output_dir=tmp_path)
    return tmp_path


def _markets_counts(text: str) -> list[int]:
    """Every number the text puts in front of "market(s)" in a correction."""
    return [
        int(number)
        for number in re.findall(
            r"(\d+) markets? (?:tested|measured|and the overall)", text
        )
    ]


def test_the_family_is_still_the_markets_and_the_overall_figure() -> None:
    """The count was right and its label was wrong. Dropping the overall
    figure would make the label true by narrowing every corrected interval.

    The fixture reaches both correction sentences, or it would test none."""
    report = _report()
    z = stats.bonferroni_z(len(report.by_market) + 1)
    shots = report.by_market["shots_on_goal"]

    assert set(report.by_market) == {"points", "shots_on_goal"}
    assert report.by_market["points"].survives_correction is True
    assert shots.includes_zero is False and shots.survives_correction is False
    assert report.looks == 3
    for interval in [report.overall, *report.by_market.values()]:
        assert interval.looks == 3
        assert interval.family == "2 markets and the overall figure"
        assert interval.adjusted_low == pytest.approx(
            interval.roi - z * interval.standard_error
        )
        assert interval.adjusted_high == pytest.approx(
            interval.roi + z * interval.standard_error
        )


def test_the_backtest_report_says_what_its_correction_counted(saved: Path) -> None:
    markdown = (saved / "player_props_backtest.md").read_text(encoding="utf-8")
    payload = json.loads(
        (saved / "player_props_backtest.json").read_text(encoding="utf-8")
    )
    verdicts = [entry["verdict"] for entry in payload["by_market"].values()]

    assert (
        f"It also survives correcting for the {FAMILY}, at " in markdown
    )
    assert f"But correcting for the {FAMILY} widens it to " in markdown
    assert (
        "3 figures were computed from one body of data: 2 markets and the "
        "overall figure." in markdown
    )
    assert all(FAMILY in verdict for verdict in verdicts)
    for text in (markdown, *verdicts):
        assert "3 markets" not in text
        assert set(_markets_counts(text)) == {2}


def test_the_family_survives_the_json_boundary(saved: Path) -> None:
    payload = json.loads(
        (saved / "player_props_backtest.json").read_text(encoding="utf-8")
    )

    assert payload["family"] == "2 markets and the overall figure"
    assert payload["overall"]["family"] == "2 markets and the overall figure"
    for entry in payload["by_market"].values():
        assert entry["looks"] == 3
        assert entry["family"] == "2 markets and the overall figure"


def test_the_claims_document_says_what_the_correction_counted(saved: Path) -> None:
    rendered = claims.render_claims(claims.build_claims_report(output_dir=saved))

    assert (
        f"The interval excludes zero even after correcting for the {FAMILY} — "
        in rendered
    )
    assert f"Correcting for the {FAMILY}, it does not exclude zero." in rendered
    assert "3 markets" not in rendered
    assert set(_markets_counts(rendered)) == {2}


def test_the_allowlist_bundle_says_what_the_correction_counted(saved: Path) -> None:
    bundle = ev.build_bundle(
        provider_name="the_odds_api", output_dir=saved, repository_root=saved
    )
    rendered = ev.render_bundle(bundle)

    assert f"Corrected for the {FAMILY} it runs " in rendered
    assert f"excludes zero even after correcting for the {FAMILY}." in rendered
    assert "3 markets" not in rendered
    assert set(_markets_counts(rendered)) == {2}


def test_a_family_of_markets_alone_is_still_called_markets() -> None:
    """Team markets and the forward ledger correct over markets and nothing
    else, and `docs/when_this_ends.md` registers the forward correction as
    "across the markets measured": their sentences keep that unit."""
    surviving = stats.roi_interval([1.0] * 280 + [-1.0] * 120, looks=3)
    fading = stats.roi_interval([1.0] * 222 + [-1.0] * 178, looks=3)

    assert (
        "It also survives correcting for the 3 markets measured on the same "
        "data, at " in surviving.verdict()
    )
    assert (
        "But correcting for the 3 markets measured on the same data widens "
        "it to " in fading.verdict()
    )
    assert "figures" not in surviving.verdict() + fading.verdict()
