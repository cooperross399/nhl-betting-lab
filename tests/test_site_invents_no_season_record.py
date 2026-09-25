"""The public board published a season record nobody tallied: 0–0, every day.

`web/build_site_json.py::load_record` built the board's `record` with
`straightUp {w:0, l:0}`, `puckLine {w:0, l:0, p:0}` and `totals {w:0, l:0,
p:0}`, updated only the sealed forward block, and returned those constants
on every path. Nothing in the site adds settled results into a season
record, and nothing anywhere grades a puck line. `web/lib/sports.js` renders
them as "Straight up 0–0 · — of games", "Puck line 0–0–0" and "Totals
0–0–0" — on the board and on the shareable graphic — beside a Results page
that settles real games every morning. Driven through the real `main()` for
eight regular-season mornings, results.json settled 55 games (28–27 straight
up) while every board still read 0–0. The one test covering these records
asserted the zeros on a mid-season fixture, so it pinned the defect.

Found by the failure-shape audit (3 of 3 refuters).

Publishing a real season tally would put a new figure on the public page,
which is the owner's decision. What is fixed here is that the page no longer
states a number nobody counted: an untallied record is None in board.json,
and the page renders it as an absence that says so, never as 0–0.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY,
    SLATE,
    build,
    make_lab,
    render_board,
    site_module,
)

ACCURACY = ("straightUp", "puckLine", "totals")


def test_a_settled_night_does_not_leave_the_board_claiming_zero_and_zero(
    tmp_path: Path, monkeypatch
) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    out = tmp_path / "out"
    build(lab, out, monkeypatch)

    board, results = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)

    settled = results["summary"]["straightUp"]
    assert settled["w"] + settled["l"] == len(SLATE), settled  # games did settle
    assert results["summary"]["totals"] != {"w": 0, "l": 0, "p": 0}
    for key in ACCURACY:
        assert board["record"][key] is None, (
            f"board.json published record.{key} = {board['record'][key]} the "
            f"morning after {len(SLATE)} games settled; nothing tallies it, so "
            "any number here is invented"
        )


def test_a_missing_or_broken_report_publishes_no_record_either(tmp_path: Path) -> None:
    module = site_module()
    garbage = tmp_path / "garbage.json"
    garbage.write_text("not json", encoding="utf-8")

    for path in (tmp_path / "absent.json", garbage):
        record = module.load_record(path)
        assert all(record[key] is None for key in ACCURACY), record
        assert record["forward"]["sealed"] is True


def _board(record: dict) -> dict:
    return {"generatedAt": "2026-10-09T15:00:00Z", "season": "2026–27",
            "phase": "regular", "boardDate": "2026-10-09", "notice": None,
            "record": record, "teams": {}, "games": [],
            "allowlistedMarkets": ["moneyline"]}


def test_the_page_renders_an_untallied_record_as_absent(tmp_path: Path) -> None:
    record = site_module().load_record(tmp_path / "absent.json")

    rendered = render_board(_board(record), tmp_path)

    cells = {c["label"]: c for c in rendered["board"]["strip"]}
    for label in ("Straight up", "Puck line", "Totals"):
        assert cells[label]["value"] == "—", cells[label]
        assert "0–0" not in json.dumps(cells[label], ensure_ascii=False), cells[label]
    assert "graded" in cells["Puck line"]["sub"].lower(), (
        "nothing grades a puck line; the cell must say so rather than imply a "
        f"tally exists: {cells['Puck line']['sub']!r}"
    )
    assert "Results" in cells["Straight up"]["sub"], cells["Straight up"]
    # The shareable graphic shows the first three cells of the same strip.
    assert [c["value"] for c in rendered["graphic"]["strip3"]] == ["—", "—", "—"]


def test_a_record_that_is_kept_is_still_rendered(tmp_path: Path) -> None:
    """The absent state must not swallow a real record if one is ever kept."""
    record = {"straightUp": {"w": 7, "l": 3}, "puckLine": {"w": 2, "l": 1, "p": 0},
              "totals": {"w": 4, "l": 5, "p": 1}, "forward": None}

    cells = {c["label"]: c for c in render_board(_board(record), tmp_path)["board"]["strip"]}

    assert cells["Straight up"]["value"] == "7–3"
    assert cells["Straight up"]["sub"] == "70.0% of games"
    assert cells["Puck line"]["value"] == "2–1–0"
    assert cells["Totals"]["value"] == "4–5–1"
