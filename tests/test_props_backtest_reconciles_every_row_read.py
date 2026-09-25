"""The props backtest's reconciliation could not fail, so it verified nothing.

`_reconciliation_line` checked `priced_outcomes` against the buckets, and
`priced_outcomes` is bumped at the top of the same loop that bumps every
bucket: "Accounted for: all of them." was printed by construction. Where rows
are really lost is before that loop — the phase filter and the best-price
collapse — and neither was in the identity. That is how the UTC-day collapse
(#135) lost 4,196 late-window and 5,337 card-window wager keys while the line
said "all of them". Found by the failure-shape audit (2 of 3 refuters; the
third agreed no input could fire it and called it a code-edit tripwire).

What the audit measured on one real week of the store (65,837 quotes,
`--phase card`): sending 30% of the quotes with an unparseable face-off or
snapshot cut priced outcomes from 13,227 to 11,901 and the report still said
"all of them", filing the 1,326 lost wagers under "outside the `card` window"
with the genuinely other-window rows (35,907 excluded against 23,056). Two
row shapes aborted the whole report instead of being counted: a blank line
(`float(nan)` passes the parse and `math.floor` raises in `counts.py`), and a
selection neither side names (`settle` raises once the edge clears) — while
an "o" selection was priced as an under and settled as an over.

What these tests hold:

* the reconciliation starts at every price row handed in and names each
  place a row can leave: another window, an unknown window, another book's
  quote on a wager already counted, and the five in-loop buckets;
* rows with no parseable window are named as that, not as another window;
* a blank or infinite line and an unknown selection are counted unparseable
  rather than ending the report or being settled against the other side;
* removing ANY statement that sets a counter the identity reads — mutated in
  memory from the module's own source — prints DOES NOT RECONCILE. That is
  the tripwire tested against the code it guards, where
  `test_a_gap_in_the_accounting_is_printed_loudly` edits a finished report.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import math
import sys

import pandas as pd
import pytest

from nhl_betting_lab.reports import player_props_backtest as bt


#: Keyed the way production keys it: normalized lowercase names.
TEAM_MAP = {"carolina hurricanes": "CAR", "new york islanders": "NYI"}

COMMENCE = "2025-11-04T00:10:00Z"  # 7:10pm ET on 2025-11-03
LATE = "2025-11-03T20:10:00Z"  # 4.0 hours out
CARD = "2025-11-03T14:40:00Z"  # 9.5 hours out


def _quote(player: str, *, market: str = "shots_on_goal", line=2.5,
           selection: str = "over", odds=200, book: str = "DraftKings",
           snapshot: str = LATE, commence: str = COMMENCE) -> dict:
    return {
        "date": "2025-11-04", "commence_time": commence, "snapshot": snapshot,
        "provider_event_id": "evt-car-nyi",
        "home_team": "Carolina Hurricanes", "away_team": "New York Islanders",
        "market": market, "player": player, "selection": selection,
        "line": line, "american_odds": odds, "book": book,
    }


def _sample(player: str, player_id: int, team: str, market: str,
            mean: float, actual: float) -> dict:
    return {"date": "2025-11-03", "market": market, "player": player,
            "player_id": player_id, "team": team, "line": 2.5, "mean": mean,
            "dispersion_r": None, "actual": actual}


def _samples() -> pd.DataFrame:
    return pd.DataFrame([
        _sample("Andrei Svechnikov", 12, "CAR", "shots_on_goal", 3.4, 4.0),
        _sample("Andrei Svechnikov", 12, "CAR", "points", 1.2, 1.0),
        # The same-game Aho case: both dressed, both in the priced game.
        _sample("Sebastian Aho", 10, "CAR", "points", 1.0, 1.0),
        _sample("Sebastian Aho", 11, "NYI", "points", 0.6, 0.0),
        # Plays for Toronto, so not in this game: a lone wrong-team candidate.
        _sample("Auston Matthews", 34, "TOR", "shots_on_goal", 4.0, 5.0),
    ])


#: One row for every place a row can leave, and the bucket it must land in.
EVERY_EXIT = [
    ("bet", _quote("Andrei Svechnikov", odds=200)),
    ("folded", _quote("Andrei Svechnikov", odds=150, book="FanDuel")),
    ("below_threshold", _quote("Andrei Svechnikov", line=4.5, odds=-500)),
    ("no_opinion", _quote("Nobody Known")),
    ("no_opinion", _quote("Auston Matthews")),
    ("unparseable", _quote("Andrei Svechnikov", line="no point")),
    ("unparseable", _quote("Andrei Svechnikov", line=float("nan"))),
    ("unparseable", _quote("Andrei Svechnikov", line=6.5, selection="maybe")),
    ("unparseable", _quote("Andrei Svechnikov", market="points", line=0.5,
                           odds="EVEN")),
    ("ambiguous", _quote("Sebastian Aho", market="points", line=0.5)),
    ("other_window", _quote("Andrei Svechnikov", snapshot=CARD, odds=400)),
    ("unknown_window", _quote("Andrei Svechnikov", snapshot="", odds=400)),
    ("unknown_window", _quote("Andrei Svechnikov", commence="not a time",
                              odds=400)),
]


def _every_exit() -> pd.DataFrame:
    return pd.DataFrame([row for _, row in EVERY_EXIT])


def _measure(module=bt, frame: pd.DataFrame | None = None):
    return module.run_backtest(
        _every_exit() if frame is None else frame, _samples(),
        edge_threshold=0.05, phase="late", team_names=TEAM_MAP,
    )


def _expected(bucket: str) -> int:
    return sum(1 for name, _ in EVERY_EXIT if name == bucket)


# --------------------------------------------------------------------------
# Every row read lands in one named bucket, and the report prints them all.
# --------------------------------------------------------------------------


def test_every_row_read_lands_in_exactly_one_named_bucket() -> None:
    report = _measure()

    assert report.rows_read == len(EVERY_EXIT)
    assert report.rows_other_window == _expected("other_window")
    assert report.rows_window_unknown == _expected("unknown_window")
    assert report.quotes_seen - report.wagers == _expected("folded")
    assert report.outcomes_without_a_model_opinion == _expected("no_opinion")
    assert report.outcomes_below_threshold == _expected("below_threshold")
    assert report.outcomes_unparseable == _expected("unparseable")
    assert report.outcomes_ambiguous == _expected("ambiguous")
    assert len(report.bets) == _expected("bet")

    rendered = bt.render_backtest(report)
    for label, count in (
        ("Price rows read", len(EVERY_EXIT)),
        ("Outside the measured window, excluded", _expected("other_window")),
        ("Window unknown", _expected("unknown_window")),
        ("already counted at its best price", _expected("folded")),
        ("Priced outcomes seen", report.priced_outcomes),
    ):
        line = next((ln for ln in rendered.splitlines() if label in ln), None)
        assert line is not None, f"the report must print {label!r}"
        assert line.rstrip().endswith(f": {count:,}"), line
    assert "Accounted for: all of them." in rendered
    assert "DOES NOT RECONCILE" not in rendered


def test_rows_with_no_parseable_window_are_not_called_another_window() -> None:
    """They were filed under "outside the `late` window" and explained as "a
    wager priced at two different moments" — which says nothing true about a
    row whose moment could not be read."""
    report = _measure()

    other = [n for n in report.notes if "outside the `late` window" in n]
    assert other and other[0].startswith(f"{_expected('other_window'):,} "), (
        f"the other-window note must count only other-window rows: {other}"
    )
    unknown = [n for n in report.notes if "no parseable snapshot or face-off" in n]
    assert unknown and unknown[0].startswith(f"{_expected('unknown_window'):,} ")


def test_the_not_measured_report_prints_the_accounting_too() -> None:
    """Where no bet is placed, the rows still went somewhere, and the section
    that says "nothing is measured" is where a reader looks for why."""
    frame = _every_exit()
    report = bt.run_backtest(frame, _samples(), edge_threshold=5.0,
                             phase="late", team_names=TEAM_MAP)
    rendered = bt.render_backtest(report)

    assert "## Not measured" in rendered
    assert f"- Price rows read: {len(frame):,}" in rendered
    assert "Accounted for: all of them." in rendered


# --------------------------------------------------------------------------
# Row shapes that ended the whole report now land in a bucket.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("line", [float("nan"), math.inf, -math.inf])
@pytest.mark.parametrize("player", ["Andrei Svechnikov", "Nobody Known"])
def test_a_line_that_is_not_a_number_is_unparseable(line: float, player: str) -> None:
    """A blank line reads as NaN, and `float(nan)` passes the parse. With a
    model opinion it raised in `math.floor` and ended the report; without
    one it was filed as "no model opinion". It is an unparseable line either
    way."""
    report = _measure(frame=pd.DataFrame([_quote(player, line=line)]))

    assert report.outcomes_unparseable == 1
    assert report.outcomes_without_a_model_opinion == 0
    assert not report.bets


@pytest.mark.parametrize("selection", ["maybe", "o", "U", "over/under", ""])
def test_a_selection_neither_side_names_is_unparseable(selection: str) -> None:
    """Pricing read anything but over/yes as an under, and settlement read
    anything starting with "o" as an over — so "o" was priced one way and
    settled the other — and "maybe" raised in `settle` and ended the report."""
    report = _measure(
        frame=pd.DataFrame([_quote("Andrei Svechnikov", selection=selection)])
    )

    assert report.outcomes_unparseable == 1
    assert not report.bets


@pytest.mark.parametrize("selection", ["Over", "UNDER", "yes", "No"])
def test_the_four_named_sides_are_still_priced(selection: str) -> None:
    report = bt.run_backtest(
        pd.DataFrame([_quote("Andrei Svechnikov", selection=selection)]),
        _samples(), edge_threshold=-1.0, phase="late", team_names=TEAM_MAP,
    )

    assert report.outcomes_unparseable == 0
    assert len(report.bets) == 1


# --------------------------------------------------------------------------
# The tripwire, tested against the code it guards.
# --------------------------------------------------------------------------

#: Every counter the identity reads. A statement setting one of these that is
#: deleted must be printed as DOES NOT RECONCILE.
COUNTERS = {
    "rows_read", "rows_other_window", "rows_window_unknown", "quotes_seen",
    "wagers", "priced_outcomes", "outcomes_without_a_model_opinion",
    "outcomes_below_threshold", "outcomes_unparseable", "outcomes_ambiguous",
    "bets",
}


def _counter_of(statement: ast.stmt) -> str | None:
    """The report counter a statement sets, if it sets one."""
    if isinstance(statement, (ast.Assign, ast.AugAssign)):
        targets = (
            statement.targets if isinstance(statement, ast.Assign)
            else [statement.target]
        )
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "report"
                and target.attr in COUNTERS
            ):
                return target.attr
    if (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr == "append"
        and ast.unparse(statement.value.func.value) == "report.bets"
    ):
        return "bets"
    return None


def _counter_statements() -> list[tuple[int, str]]:
    tree = ast.parse(inspect.getsource(bt))
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "run_backtest"
    )
    return [
        (node.lineno, counter)
        for node in ast.walk(function)
        if isinstance(node, ast.stmt) and (counter := _counter_of(node))
    ]


def _without_statement(lineno: int):
    """The module, rebuilt in memory with the statement at `lineno` deleted."""

    class Delete(ast.NodeTransformer):
        def generic_visit(self, node):
            super().generic_visit(node)
            for name in ("body", "orelse", "finalbody"):
                block = getattr(node, name, None)
                if isinstance(block, list) and any(
                    isinstance(s, ast.stmt) and s.lineno == lineno for s in block
                ):
                    kept = [s for s in block if getattr(s, "lineno", -1) != lineno]
                    setattr(node, name, kept or [ast.Pass()])
            return node

    tree = ast.fix_missing_locations(Delete().visit(ast.parse(inspect.getsource(bt))))
    name = f"_bt_without_line_{lineno}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        exec(compile(tree, bt.__file__, "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


def test_the_identity_reads_every_counter_the_measurement_sets() -> None:
    """If this finds nothing, every case below is vacuous. It must find each
    counter the identity reads, set inside `run_backtest`."""
    found = {counter for _, counter in _counter_statements()}

    assert found == COUNTERS, f"missing: {sorted(COUNTERS - found)}"


@pytest.mark.parametrize(
    ("lineno", "counter"), _counter_statements(),
    ids=[f"{counter}@{lineno}" for lineno, counter in _counter_statements()],
)
def test_losing_any_counter_is_printed_loudly(lineno: int, counter: str) -> None:
    baseline = _measure()
    assert "Accounted for: all of them." in bt.render_backtest(baseline)

    mutant = _without_statement(lineno)
    report = _measure(module=mutant)

    assert "DOES NOT RECONCILE" in mutant.render_backtest(report), (
        f"deleting the statement that sets `{counter}` (line {lineno}) left "
        "the report saying every row was accounted for"
    )
