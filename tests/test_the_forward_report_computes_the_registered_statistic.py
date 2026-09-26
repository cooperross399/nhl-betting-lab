"""The forward report never computed the statistic the lab is decided on.

`docs/when_this_ends.md` registers the 2027-04-25 stop/continue decision on
one number: "the forward ledger's pooled return on frozen opinions, one bet
per wager at the best price the card could have taken, corrected across the
markets measured. Opinions, not bets", with a floor of 3,000 settled
opinions ("Below that ... the pipeline failed rather than the model") and a
table of exactly one of four outcomes. `build_forward_report` produced only
per-market figures, and per market only for the rows clearing the shipped
edge bar — so on 2027-04-25 there would have been no pooled number, no
floor check, and nothing in the house's own report to read the rule from.

What these tests hold, on ledgers shaped as settlement writes them:

* an empty ledger carries the statistic's frame in the payload — the date,
  the floor, zero settled opinions, the below-floor reading — and no number,
  while its page stays the preseason text word for word; a written-off
  ledger renders zero against the floor;
* below the floor the reading is "the test did not run", the pooled number
  is not printed ("Do not read the number"), and voids and unsettleable
  rows do not count toward the floor; exactly 3,000 meets it;
* the population is every settled opinion in every market, pooled, one per
  wager after the existing best-price collapse — an opinion below the edge
  bar counts, a second book's quote does not;
* the interval is the pooled interval widened for the markets measured;
* above the floor, each reading uses the registered row's words, and before
  2027-04-25 the page says in terms that the decision is not due — a
  positive reading is a candidate on one season needing a second, never a
  green light, and not a decision either;
* the date and the floor match the registration, and the public site still
  publishes no return with the new key present.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.models.value import american_to_implied, profit_on_win
from nhl_betting_lab.stats import roi_interval


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BEFORE = datetime(2027, 1, 20, 15, 0, tzinfo=timezone.utc)
ON_THE_DATE = datetime(2027, 4, 25, 12, 0, tzinfo=timezone.utc)
ODDS = 100.0


def _row(market: str, index: int, outcome: str, *, p: float = 0.62,
         book: str = "DraftKings", odds: float = ODDS) -> dict:
    """One wager, its own player so no two indexes collapse."""
    won = outcome == "won"
    return {
        "snapshot_date": "2026-12-01", "commence_time": "2026-12-02T00:10:00Z",
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "market": market, "player": f"Player {market} {index}",
        "selection": "over", "line": 0.5, "american_odds": odds,
        "book": book, "model_probability": p,
        "edge": p - american_to_implied(odds), "verdicts_in_force": "x",
        "settled_at": "2026-12-03T12:00:00+00:00", "outcome": outcome,
        "actual": 1.0 if won else 0.0,
        "profit_units": (profit_on_win(odds) if won
                         else (-1.0 if outcome == "lost" else 0.0)),
    }


def _market(market: str, wins: int, losses: int, *, start: int = 0,
            p: float = 0.62) -> list[dict]:
    return ([_row(market, start + i, "won", p=p) for i in range(wins)]
            + [_row(market, start + wins + i, "lost", p=p)
               for i in range(losses)])


def _ledger(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))


def _section(rendered: str) -> str:
    head = "## Registered decision statistic"
    assert head in rendered, "the report has no registered-statistic section"
    tail = rendered.split(head, 1)[1]
    return tail.split("\n## ", 1)[0]


def test_an_empty_ledger_carries_the_frame_and_no_number() -> None:
    payload = fe.build_forward_report(_ledger([]), now=BEFORE)
    stat = payload["registered_statistic"]

    assert stat["decision_date"] == "2027-04-25"
    assert stat["sample_floor"] == 3000
    assert stat["settled_opinions"] == 0
    assert stat["meets_floor"] is False
    assert stat["reading"] == "below_floor"
    assert stat["decision_due"] is False
    for key in ("roi", "low", "high", "adjusted_low", "adjusted_high"):
        assert key not in stat

    # The preseason page stays word for word (the written-off-ledger tests
    # pin it); the frame travels in the JSON.
    rendered = fe.render_forward_report(payload)
    assert "## Nothing settled yet" in rendered
    assert "## Registered decision statistic" not in rendered


def test_a_written_off_ledger_reads_zero_against_the_floor() -> None:
    rows = [_row("points", i, "unsettleable") for i in range(4)]
    payload = fe.build_forward_report(_ledger(rows), now=BEFORE)
    stat = payload["registered_statistic"]
    assert stat["settled_opinions"] == 0
    assert stat["reading"] == "below_floor"
    section = _section(fe.render_forward_report(payload))
    assert "0, against the registration's floor of 3,000" in section
    assert "not due until 2027-04-25" in section


def test_below_the_floor_the_number_is_not_read() -> None:
    # 2,999 settled opinions: 1,800 won / 1,199 lost — a strong-looking
    # number the page must not print — plus voids and unsettleable rows
    # that push the ROW count past 3,000 but settle nothing.
    rows = _market("shots_on_goal", 1800, 1199)
    rows += [_row("points", i, "void") for i in range(10)]
    rows += [_row("points", 10 + i, "unsettleable") for i in range(10)]
    payload = fe.build_forward_report(_ledger(rows), now=BEFORE)
    stat = payload["registered_statistic"]

    assert stat["settled_opinions"] == 2999
    assert stat["meets_floor"] is False
    assert stat["reading"] == "below_floor"

    section = _section(fe.render_forward_report(payload))
    assert "2,999, against the registration's floor of 3,000" in section
    assert "the test did not run" in section.lower()
    assert "Do not read the number" in section
    assert "not due until 2027-04-25" in section
    assert f"{stat['roi']:+.1%}" not in section, (
        "below the floor the registration says do not read the number"
    )


def test_exactly_the_floor_meets_it() -> None:
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 1500, 1500)), now=BEFORE
    )
    stat = payload["registered_statistic"]
    assert stat["settled_opinions"] == 3000
    assert stat["meets_floor"] is True
    assert stat["reading"] != "below_floor"


def test_the_population_is_every_settled_opinion_pooled_once_per_wager() -> None:
    # Two markets. One carries opinions BELOW the shipped edge bar (p = 0.5
    # at +100 is zero edge): "opinions, not bets", so they count. One wager
    # is quoted by a second, worse book: one bet per wager, so it does not.
    rows = _market("shots_on_goal", 1000, 700)
    rows += _market("points", 600, 700, p=0.5)
    rows.append(_row("shots_on_goal", 0, "won", book="FanDuel", odds=-120.0))
    payload = fe.build_forward_report(_ledger(rows), now=BEFORE)
    stat = payload["registered_statistic"]

    assert stat["settled_opinions"] == 3000
    assert stat["markets"] == ["points", "shots_on_goal"]
    assert stat["looks"] == 2
    expected = roi_interval([1.0] * 1600 + [-1.0] * 1400, wins=1600, looks=2)
    assert stat["profit_units"] == pytest.approx(expected.profit)
    assert stat["roi"] == pytest.approx(expected.roi)
    assert stat["low"] == pytest.approx(expected.low)
    assert stat["high"] == pytest.approx(expected.high)
    assert stat["adjusted_low"] == pytest.approx(expected.adjusted_low)
    assert stat["adjusted_high"] == pytest.approx(expected.adjusted_high)
    # The corrected interval is wider than the plain one: two looks.
    assert stat["adjusted_low"] < stat["low"]
    # Counting is unchanged: the per-market view still counts the same
    # wagers, and the below-bar market still has no bets.
    assert payload["markets"]["points"]["opinions"] == 1300
    assert payload["markets"]["points"]["bets"] == 0


def test_above_the_floor_spanning_zero_reads_stop_but_is_not_the_decision() -> None:
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 1000, 1000)
                + _market("points", 520, 480)),
        now=BEFORE,
    )
    stat = payload["registered_statistic"]
    assert stat["meets_floor"] is True
    assert stat["adjusted_low"] <= 0.0 <= stat["adjusted_high"]
    assert stat["reading"] == "spans_zero"
    assert stat["decision_due"] is False

    section = _section(fe.render_forward_report(payload))
    assert "Corrected interval **spans zero**" in section
    assert "**Stop.**" in section
    assert "not due until 2027-04-25" in section
    assert "not the decision" in section
    assert f"{stat['adjusted_low']:+.1%}" in section
    assert "3,000, against the registration's floor of 3,000" in section


def test_the_reading_is_taken_from_the_corrected_interval() -> None:
    # +3.8% over 3,000 in two markets: the plain 95% interval excludes zero
    # and the interval corrected for the two markets spans it. The
    # registration reads the corrected one, so this is "spans zero".
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 800, 700)
                + _market("points", 757, 743, start=10_000)),
        now=BEFORE,
    )
    stat = payload["registered_statistic"]
    assert stat["low"] > 0.0
    assert stat["adjusted_low"] < 0.0
    assert stat["reading"] == "spans_zero"


def test_a_small_pooled_sample_never_reads_as_surviving() -> None:
    # 15-5 at even money over two markets: the corrected bounds exclude
    # zero, but under TOO_FEW_TO_SURVIVE nothing survives (the per-market
    # column's rule). The floor sits far above that threshold, so the
    # reading is "below_floor", and the stored property agrees.
    assert fe.SAMPLE_FLOOR > fe.TOO_FEW_TO_SURVIVE
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 8, 2)
                + _market("points", 7, 3, start=10_000)),
        now=ON_THE_DATE,
    )
    stat = payload["registered_statistic"]
    assert stat["settled_opinions"] == 20
    assert stat["adjusted_low"] > 0.0
    assert stat["survives_correction"] is False
    assert stat["reading"] == "below_floor"
    section = _section(fe.render_forward_report(payload))
    assert "excludes zero" not in section


def test_the_reading_follows_survives_correction(monkeypatch) -> None:
    # Were a floor ever at or under 30, a small sample must still not read
    # as excluding zero: the reading is taken from `survives_correction`.
    monkeypatch.setattr(fe, "SAMPLE_FLOOR", 10)
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 8, 2)
                + _market("points", 7, 3, start=10_000)),
        now=BEFORE,
    )
    stat = payload["registered_statistic"]
    assert stat["meets_floor"] is True
    assert stat["adjusted_low"] > 0.0
    assert stat["reading"] != "excludes_zero_positive"


def test_above_the_floor_negative_reads_confirmed_loser() -> None:
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 1200, 1800)), now=BEFORE
    )
    stat = payload["registered_statistic"]
    assert stat["adjusted_high"] < 0.0
    assert stat["reading"] == "excludes_zero_negative"
    section = _section(fe.render_forward_report(payload))
    assert "excludes zero, negative" in section
    assert "not due until 2027-04-25" in section


def test_a_positive_reading_is_a_one_season_candidate_and_not_a_decision() -> None:
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 928, 672)
                + _market("points", 928, 672, start=10_000)),
        now=BEFORE,
    )
    stat = payload["registered_statistic"]
    assert stat["adjusted_low"] > 0.0
    assert stat["reading"] == "excludes_zero_positive"
    assert stat["decision_due"] is False

    section = _section(fe.render_forward_report(payload))
    assert "excludes zero, positive" in section
    assert "**Not a green light.**" in section
    assert "second season" in section
    assert "not due until 2027-04-25" in section
    assert "not the decision" in section


def test_on_the_decision_date_the_reading_is_the_registered_outcome() -> None:
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 928, 672)
                + _market("points", 928, 672, start=10_000)),
        now=ON_THE_DATE,
    )
    stat = payload["registered_statistic"]
    assert stat["decision_due"] is True
    section = _section(fe.render_forward_report(payload))
    assert "not due until" not in section
    # Even on the date, a positive reading is still one season.
    assert "Not a green light" in section and "second season" in section


def test_the_day_before_the_date_is_still_not_due() -> None:
    payload = fe.build_forward_report(
        _ledger([]), now=datetime(2027, 4, 24, 23, 59, tzinfo=timezone.utc)
    )
    assert payload["registered_statistic"]["decision_due"] is False


def test_the_date_and_the_floor_match_the_registration() -> None:
    doc = (PROJECT_ROOT / "docs" / "when_this_ends.md").read_text(
        encoding="utf-8"
    )
    assert f"**Decision date: {fe.DECISION_DATE}**" in doc
    assert f"**Sample floor: {fe.SAMPLE_FLOOR:,} settled opinions.**" in doc


def test_the_site_still_publishes_no_return_with_the_statistic_present(
    tmp_path: Path,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "bsj_registered", PROJECT_ROOT / "web" / "build_site_json.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 928, 672)
                + _market("points", 928, 672, start=10_000)),
        now=BEFORE,
    )
    target = tmp_path / "forward_evidence.json"
    target.write_text(json.dumps(payload, default=str), encoding="utf-8")
    published = json.dumps(module.load_record(target))
    for key in ("roi", "low", "high", "profit_units", "reading",
                "registered_statistic", "adjusted_low"):
        assert key not in published
