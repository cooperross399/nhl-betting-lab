"""The public board counted every book's quote as an opinion, and called settled opinions frozen.

`web/build_site_json.py::load_record` published forward_evidence.json's
`rows` — the ledger's length — and `web/lib/sports.js` rendered it as
"{rows} opinions frozen across N markets". Both halves were wrong:

* A ledger row is one BOOK'S QUOTE. The snapshot freezes one row per book
  and settlement appends one ledger row per snapshot row, so one selection
  quoted by three books published "3 opinions". On the bought card window
  that is about 3.7 rows per opinion (2,544,921 quotes over 685,746
  wagers); on one real league slate run through the card's own pricer it was
  180 rows from 18 opinions across 16 books, and the tile read "180 opinions
  frozen across 3 markets". docs/when_this_ends.md registers the forward
  decision on one bet per wager at the best price, and since 2026-09-25
  `build_forward_report` writes that count as `wagers` beside `rows`. The
  site went on publishing `rows`.
* The ledger holds only slates whose games have all finished; today's frozen
  opinions are not in it. So on opening night — 1,144 rows (118 opinions)
  frozen, nothing settled — the page said "Nothing frozen yet".

Found by the failure-shape audit (2 of 3 refuters; the third read an
opinion as a per-book row, which is the unit `build_forward_report` retired
when it began counting one wager per selection).

These tests drive the real freeze -> settle -> report -> `load_record` path
and render the result through the page's own adapter under node. They also
hold the part a relabel alone would leave open: a report written before the
wager count existed publishes no count, never the per-quote one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from test_forward_evidence import _games, _logs, _price_row, _settle, _snapshot
from test_site_never_calls_an_unpriced_game_a_pass import render_board, site_module

FORWARD = "Forward ledger · sealed"

BOOKS = ("DraftKings", "FanDuel", "BetMGM", "Caesars")

#: (books quoting each selection, lines priced) -> the wagers they collapse
#: to. Two shapes, so a count that happened to equal a constant cannot pass.
SHAPES = {
    "one-selection-three-books": (3, (3.5,), 1),
    "two-selections-four-books": (4, (3.5, 4.5), 2),
}


def _settled_report(tmp_path: Path, books: int, lines: tuple[float, ...]) -> Path:
    """Freeze, settle and report exactly as the Gameday Refresh job does."""
    rows = [
        _price_row(book=BOOKS[index], american_odds=110 + 5 * index, line=line)
        for line in lines
        for index in range(books)
    ]
    _snapshot(tmp_path, rows)
    _settle(tmp_path, _logs(shots=5.0), _games())
    payload = fe.build_forward_report(fe.load_ledger(tmp_path / "processed"))
    written = fe.save_forward_report(payload, output_dir=tmp_path / "outputs")
    return Path(written["json"])


def _board(record: dict) -> dict:
    return {"generatedAt": "2026-10-09T15:00:00Z", "season": "2026–27",
            "phase": "regular", "boardDate": "2026-10-09", "notice": None,
            "record": record, "teams": {}, "games": [],
            "allowlistedMarkets": ["moneyline"]}


def _forward_cell(record: dict, tmp_path: Path) -> dict:
    cells = [c for c in render_board(_board(record), tmp_path)["board"]["strip"] if c["label"] == FORWARD]
    assert len(cells) == 1, cells
    return cells[0]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_wager_quoted_by_several_books_is_one_opinion(tmp_path: Path, shape: str) -> None:
    books, lines, wagers = SHAPES[shape]
    report = _settled_report(tmp_path, books, lines)
    assert json.loads(report.read_text())["rows"] == books * len(lines)  # the ledger is per book

    forward = site_module().load_record(report)["forward"]

    assert forward["wagers"] == wagers, (
        f"published {forward.get('wagers')} opinions for {wagers} wager(s) "
        f"quoted by {books} books; the registered unit is one bet per wager"
    )
    assert forward["rows"] == books * len(lines), "rows stays the per-quote size it is"


def test_the_page_prints_the_wager_count_as_settled_opinions(tmp_path: Path) -> None:
    books, lines, wagers = SHAPES["one-selection-three-books"]
    record = site_module().load_record(_settled_report(tmp_path, books, lines))

    cell = _forward_cell(record, tmp_path)

    assert cell["value"] == str(wagers), cell
    assert "frozen" not in cell["sub"], (
        "the ledger holds settled slates only; today's frozen opinions are not "
        f"in it, so 'frozen' misdescribes the count: {cell['sub']!r}"
    )
    assert "settled slate" in cell["sub"], cell


def test_opening_night_does_not_say_nothing_is_frozen(tmp_path: Path) -> None:
    """The card froze the slate that morning; none of its games has finished."""
    _snapshot(tmp_path, [_price_row(book=book) for book in BOOKS[:3]])
    waiting = _settle(tmp_path, _logs(), pd.DataFrame())
    assert waiting.snapshots_waiting == 1
    payload = fe.build_forward_report(fe.load_ledger(tmp_path / "processed"))
    written = fe.save_forward_report(payload, output_dir=tmp_path / "outputs")

    record = site_module().load_record(Path(written["json"]))
    assert record["forward"]["wagers"] == 0

    cell = _forward_cell(record, tmp_path)
    assert "Nothing frozen" not in cell["sub"], (
        f"three quotes were frozen this morning and the page said {cell['sub']!r}"
    )
    assert "No slate settled yet" in cell["sub"], cell


def test_a_report_without_a_wager_count_never_publishes_the_quote_count(tmp_path: Path) -> None:
    """Reports written before the wager count existed carry `rows` only.

    Zero rows is zero wagers. Any other row count cannot be turned into
    wagers, and publishing it would be the per-quote count this file retires.
    """
    module = site_module()
    target = tmp_path / "forward_evidence.json"

    target.write_text(json.dumps({"rows": 0, "markets": {}, "unsettleable": 0}))
    assert module.load_record(target)["forward"]["wagers"] == 0

    target.write_text(json.dumps({"rows": 180, "markets": {}, "unsettleable": 0}))
    record = module.load_record(target)
    assert record["forward"]["wagers"] is None

    cell = _forward_cell(record, tmp_path)
    assert cell["value"] == "—" and "180" not in json.dumps(cell), cell
    assert "not reported" in cell["sub"], (
        "180 ledger rows are not 'no slate settled'; an unknown count must "
        f"say it is unknown: {cell['sub']!r}"
    )


@pytest.mark.parametrize("content", [None, "{not json", "[]", b"\xff\xfe"],
                         ids=["missing", "malformed", "not-an-object", "not-utf-8"])
def test_a_report_that_cannot_be_read_is_an_unknown_count_not_zero(
    tmp_path: Path, content: str | bytes | None
) -> None:
    """Publish Site restores forward_evidence.json with the run's reports, so
    a board built without a readable one knows nothing about the ledger. It
    used to publish 0 wagers, and the page read "No slate settled yet" —
    false from the first settled night on. No count is published instead,
    and the seal holds either way."""
    module = site_module()
    target = tmp_path / "forward_evidence.json"
    if isinstance(content, bytes):
        target.write_bytes(content)
    elif content is not None:
        target.write_text(content)

    record = module.load_record(target)

    assert record["forward"]["sealed"] is True
    assert record["forward"]["wagers"] is None
    cell = _forward_cell(record, tmp_path)
    assert cell["value"] == "—", cell
    assert "not reported" in cell["sub"] and "No slate settled" not in cell["sub"], cell
