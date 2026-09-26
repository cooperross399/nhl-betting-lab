"""The forward report never computed the statistic the lab is decided on.

`docs/when_this_ends.md` registers the 2027-04-25 stop/continue decision on
one number: "the forward ledger's pooled return on frozen opinions, one bet
per wager at the best price the card could have taken, corrected across the
markets measured", with a floor of 3,000 settled opinions. `build_forward_
report` produced only per-market figures, so on 2027-04-25 there would have
been no pooled number and no floor check in the house's own report.

The registration is ambiguous on WHICH opinions. "Opinions, not bets" reads
as every settled opinion (A); "a frozen opinion scored against the price it
was frozen at is the same test", with the edge bar among what it freezes,
reads as the opinions clearing the edge bar (B). A pools both sides of every
line and reads negative from the vig alone. Choosing is Cooper's decision,
so the report computes both and attaches no registered outcome to either.

What these tests hold, on ledgers shaped as settlement writes them:

* an empty ledger carries both populations' frame in the payload and no
  number, while its page stays the preseason text word for word; a
  written-off ledger renders both at zero against the floor;
* each population is one per wager after the existing best-price collapse,
  pooled across markets, widened for the markets measured, and counted
  against the floor in its own settled opinions: A counts an opinion below
  the edge bar, B does not, neither counts a second book's quote, a void or
  an unsettleable row; exactly 3,000 meets the floor;
* below the floor a population's number is not printed ("Do not read the
  number"), per population, even when the other one prints;
* the interval is described from the CORRECTED interval, and a small sample
  never reads as excluding zero;
* no registered outcome — Stop, candidate, green light, diagnose — is
  attached to either reading, the page says the population is ambiguous and
  Cooper decides, and no reading is the decision: before 2027-04-25 it is
  not due, and on the date it waits on the population;
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
EVERY = "population_every_opinion"
CLEARS = "population_clears_edge_bar"
#: A model probability whose edge at +100 clears both shipped bars.
ABOVE = 0.62
#: Zero edge at +100: an opinion, and below every bar.
BELOW = 0.5
#: Registered outcomes: none may be attached to either reading.
OUTCOME_WORDS = ("Stop", "candidate", "green light", "Diagnose",
                 "Confirmed loser", "second season")


def _row(market: str, index: int, outcome: str, *, p: float = ABOVE,
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
            p: float = ABOVE) -> list[dict]:
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


def _population_row(section: str, label: str) -> str:
    for line in section.splitlines():
        if line.startswith(f"| {label}"):
            return line
    raise AssertionError(f"no row for {label}")


def _assert_no_outcome(section: str) -> None:
    for word in OUTCOME_WORDS:
        assert word not in section, (
            f"{word!r} attaches a registered outcome to a reading whose "
            "population is undecided"
        )


def test_an_empty_ledger_carries_both_frames_and_no_number() -> None:
    payload = fe.build_forward_report(_ledger([]), now=BEFORE)
    stat = payload["registered_statistic"]

    assert stat["decision_date"] == "2027-04-25"
    assert stat["sample_floor"] == 3000
    assert stat["decision_due"] is False
    assert stat["population_undecided"] is True
    for key in (EVERY, CLEARS):
        population = stat[key]
        assert population["settled_opinions"] == 0
        assert population["meets_floor"] is False
        assert population["corrected_interval"] == "below_floor"
        assert population["definition"]
        for number in ("roi", "low", "high", "adjusted_low", "adjusted_high"):
            assert number not in population

    # The preseason page stays word for word (the written-off-ledger tests
    # pin it); the frame travels in the JSON.
    rendered = fe.render_forward_report(payload)
    assert "## Nothing settled yet" in rendered
    assert "## Registered decision statistic" not in rendered


def test_a_written_off_ledger_reads_both_at_zero_against_the_floor() -> None:
    rows = [_row("points", i, "unsettleable") for i in range(4)]
    payload = fe.build_forward_report(_ledger(rows), now=BEFORE)
    stat = payload["registered_statistic"]
    assert stat[EVERY]["settled_opinions"] == 0
    assert stat[CLEARS]["settled_opinions"] == 0
    section = _section(fe.render_forward_report(payload))
    assert section.count("0, against the floor of 3,000 — below the floor") == 2
    assert section.count("Do not read the number") == 2
    assert "not due until 2027-04-25" in section
    _assert_no_outcome(section)


def test_the_populations_differ_only_by_the_edge_bar() -> None:
    # shots_on_goal clears the prop bar; points sits at zero edge, below
    # it. One wager is quoted by a second, worse book: one per wager.
    # A void and an unsettleable row settle nothing in either population.
    rows = _market("shots_on_goal", 1000, 700)
    rows += _market("points", 600, 700, p=BELOW)
    rows.append(_row("shots_on_goal", 0, "won", book="FanDuel", odds=-120.0))
    rows += [_row("points", 5000, "void"), _row("points", 5001, "unsettleable")]
    payload = fe.build_forward_report(_ledger(rows), now=BEFORE)
    stat = payload["registered_statistic"]

    assert stat["markets"] == ["points", "shots_on_goal"]
    every, clears = stat[EVERY], stat[CLEARS]
    assert every["settled_opinions"] == 3000
    assert clears["settled_opinions"] == 1700
    assert every["looks"] == clears["looks"] == 2

    expected = roi_interval([1.0] * 1600 + [-1.0] * 1400, wins=1600, looks=2)
    assert every["roi"] == pytest.approx(expected.roi)
    assert every["profit_units"] == pytest.approx(expected.profit)
    assert every["low"] == pytest.approx(expected.low)
    assert every["adjusted_low"] == pytest.approx(expected.adjusted_low)
    assert every["adjusted_high"] == pytest.approx(expected.adjusted_high)
    assert every["adjusted_low"] < every["low"]  # two looks widen it

    bets = roi_interval([1.0] * 1000 + [-1.0] * 700, wins=1000, looks=2)
    assert clears["roi"] == pytest.approx(bets.roi)
    assert clears["adjusted_low"] == pytest.approx(bets.adjusted_low)
    # B is exactly the per-market Bets stream, pooled.
    assert clears["settled_opinions"] == sum(
        entry["bets"] for entry in payload["markets"].values()
    )
    assert payload["markets"]["points"]["bets"] == 0
    assert payload["markets"]["points"]["opinions"] == 1300


def test_b_uses_each_market_s_own_bar() -> None:
    # A 5-point edge clears the team bar (3.5) and not the prop bar (6), so
    # it is in B for a moneyline and out of B for shots on goal: the same
    # `edge_bar` the per-market Bets view uses.
    rows = _market("moneyline", 6, 4, p=0.55)
    rows += _market("shots_on_goal", 6, 4, p=0.55, start=100)
    payload = fe.build_forward_report(_ledger(rows), now=BEFORE)
    stat = payload["registered_statistic"]
    assert stat[EVERY]["settled_opinions"] == 20
    assert stat[CLEARS]["settled_opinions"] == 10
    assert payload["markets"]["moneyline"]["bets"] == 10
    assert payload["markets"]["shots_on_goal"]["bets"] == 0


def test_each_population_meets_the_floor_in_its_own_units() -> None:
    # 3,000 settled opinions, 2,999 of them clearing the bar: A meets the
    # floor exactly, B is one short and must not print.
    rows = _market("shots_on_goal", 1500, 1499)
    rows.append(_row("points", 0, "lost", p=BELOW))
    payload = fe.build_forward_report(_ledger(rows), now=BEFORE)
    stat = payload["registered_statistic"]
    assert stat[EVERY]["settled_opinions"] == 3000
    assert stat[EVERY]["meets_floor"] is True
    assert stat[EVERY]["corrected_interval"] != "below_floor"
    assert stat[CLEARS]["settled_opinions"] == 2999
    assert stat[CLEARS]["meets_floor"] is False
    assert stat[CLEARS]["corrected_interval"] == "below_floor"

    section = _section(fe.render_forward_report(payload))
    every_row = _population_row(section, "A. Every settled opinion")
    clears_row = _population_row(section, "B. Opinions clearing the edge bar")
    assert "3,000, against the floor of 3,000 — floor met" in every_row
    assert f"{stat[EVERY]['roi']:+.1%}" in every_row
    assert "2,999, against the floor of 3,000 — below the floor" in clears_row
    assert "Do not read the number" in clears_row
    assert f"{stat[CLEARS]['roi']:+.1%}" not in clears_row


def test_below_the_floor_neither_number_is_printed() -> None:
    # 2,999 settled at a strong-looking +20%, with voids and unsettleable
    # rows pushing the ROW count past 3,000.
    rows = _market("shots_on_goal", 1800, 1199)
    rows += [_row("points", i, "void") for i in range(10)]
    rows += [_row("points", 10 + i, "unsettleable") for i in range(10)]
    payload = fe.build_forward_report(_ledger(rows), now=BEFORE)
    stat = payload["registered_statistic"]
    assert stat[EVERY]["settled_opinions"] == 2999
    assert stat[EVERY]["meets_floor"] is False

    section = _section(fe.render_forward_report(payload))
    assert section.count("Do not read the number") == 2
    assert f"{stat[EVERY]['roi']:+.1%}" not in section
    assert "not due until 2027-04-25" in section
    _assert_no_outcome(section)


def test_the_description_reads_the_corrected_interval() -> None:
    # +3.8% over 3,000 in two markets: the plain 95% interval excludes zero
    # and the interval corrected for the two markets spans it.
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 800, 700)
                + _market("points", 757, 743, start=10_000)),
        now=BEFORE,
    )
    every = payload["registered_statistic"][EVERY]
    assert every["low"] > 0.0
    assert every["adjusted_low"] < 0.0
    assert every["corrected_interval"] == "spans_zero"


def test_a_small_pooled_sample_never_reads_as_surviving() -> None:
    assert fe.SAMPLE_FLOOR > fe.TOO_FEW_TO_SURVIVE
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 8, 2)
                + _market("points", 7, 3, start=10_000)),
        now=ON_THE_DATE,
    )
    every = payload["registered_statistic"][EVERY]
    assert every["settled_opinions"] == 20
    assert every["adjusted_low"] > 0.0
    assert every["survives_correction"] is False
    assert every["corrected_interval"] == "below_floor"


def test_the_description_follows_survives_correction(monkeypatch) -> None:
    # Were the floor ever at or under 30, a small sample must still not
    # read as excluding zero.
    monkeypatch.setattr(fe, "SAMPLE_FLOOR", 10)
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 8, 2)
                + _market("points", 7, 3, start=10_000)),
        now=BEFORE,
    )
    every = payload["registered_statistic"][EVERY]
    assert every["meets_floor"] is True
    assert every["adjusted_low"] > 0.0
    assert every["corrected_interval"] != "excludes_zero_positive"


@pytest.mark.parametrize(
    ("wins", "losses", "described"),
    [(1520, 1480, "spans zero (no demonstrated edge)"), (928 * 2, 672 * 2, "excludes zero, positive"),
     (1200, 1800, "excludes zero, negative")],
    ids=["spans", "positive", "negative"],
)
def test_above_the_floor_no_outcome_is_attached(
    wins: int, losses: int, described: str
) -> None:
    half_w, half_l = wins // 2, losses // 2
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", half_w, half_l)
                + _market("points", wins - half_w, losses - half_l,
                          start=10_000)),
        now=BEFORE,
    )
    stat = payload["registered_statistic"]
    assert stat[EVERY]["meets_floor"] is True
    assert stat["population_undecided"] is True
    assert stat["decision_due"] is False

    section = _section(fe.render_forward_report(payload))
    row = _population_row(section, "A. Every settled opinion")
    assert row.rstrip().endswith(f"| {described} |")
    assert f"{stat[EVERY]['adjusted_low']:+.1%}" in row
    assert "ambiguous on which population it means" in section
    assert "Cooper must decide before 2027-04-25" in section
    assert "No reading here is the decision" in section
    assert "not due until 2027-04-25" in section
    _assert_no_outcome(section)


def test_on_the_decision_date_the_decision_waits_on_the_population() -> None:
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 928, 672)
                + _market("points", 928, 672, start=10_000)),
        now=ON_THE_DATE,
    )
    stat = payload["registered_statistic"]
    assert stat["decision_due"] is True
    section = _section(fe.render_forward_report(payload))
    assert "not due until" not in section
    assert "No reading here is the decision" in section
    assert "waits on Cooper's choice of population" in section
    _assert_no_outcome(section)


def test_the_day_before_the_date_is_still_not_due() -> None:
    payload = fe.build_forward_report(
        _ledger([]), now=datetime(2027, 4, 24, 23, 59, tzinfo=timezone.utc)
    )
    assert payload["registered_statistic"]["decision_due"] is False


def test_both_definitions_are_on_the_page() -> None:
    payload = fe.build_forward_report(
        _ledger(_market("shots_on_goal", 10, 10)), now=BEFORE
    )
    section = _section(fe.render_forward_report(payload))
    for key in (EVERY, CLEARS):
        assert fe.REGISTERED_POPULATIONS[key] in section


def test_the_date_and_the_floor_match_the_registration() -> None:
    doc = (PROJECT_ROOT / "docs" / "when_this_ends.md").read_text(
        encoding="utf-8"
    )
    assert f"**Decision date: {fe.DECISION_DATE}**" in doc
    assert f"**Sample floor: {fe.SAMPLE_FLOOR:,} settled opinions.**" in doc
    # Both readings the report quotes are the registration's own words.
    assert "Opinions, not bets" in doc
    assert (
        "a frozen opinion scored against the price it was frozen at is the\n"
        "same test" in doc
    )
    assert "the edge\nbar" in doc or "the edge bar" in doc


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
    for key in ("roi", "low", "high", "profit_units", "corrected_interval",
                "registered_statistic", "adjusted_low", EVERY, CLEARS):
        assert key not in published
