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

Publishing a real season tally was the owner's decision, and on 2026-10-05
it was made: `season_record` now sums every frozen board's settlement into
the board's record (best bets, leans, straight up, totals). What these tests
hold is that the number is counted: it is the sum of nights actually
settled, a night whose finals cannot be fetched is named as missing rather
than counted 0–0, and before any night settles the page shows an absence,
never 0–0.
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
    render_results,
    site_module,
)

ACCURACY = ("straightUp", "puckLine", "totals")


def test_a_settled_night_is_the_boards_season_record(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    out = tmp_path / "out"
    board, _ = build(lab, out, monkeypatch)
    for key in ACCURACY:
        assert board["record"][key] is None, "nothing has settled yet"

    board, results = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)

    settled = results["summary"]
    assert settled["straightUp"]["w"] + settled["straightUp"]["l"] == len(SLATE)
    assert settled["picks"]["w"] + settled["picks"]["l"] + settled["picks"]["p"] == 1  # the one best bet
    for key in ("straightUp", "picks", "totals"):
        assert board["record"][key] == settled[key], (key, board["record"][key], settled[key])
    assert board["record"]["season"]["nights"] == 1
    assert results["seasonRecord"]["picks"] == settled["picks"]
    # `season` is the label the page's kicker prints; the tally must not
    # overwrite it ("[object Object] NHL" when it did).
    assert results["season"] == board["season"] == "2026–27"
    rendered = render_results(results, tmp_path)
    assert rendered["kicker"].startswith("2026–27 NHL"), rendered["kicker"]
    season_cells = [c for c in rendered["strip"] if c["label"] == "Best bets · season"]
    assert [c["value"] for c in season_cells] == [
        "{w}–{l}–{p}".format(**settled["picks"])], rendered["strip"]
    assert board["record"]["puckLine"] is None  # nothing grades a puck line


def test_the_season_sums_old_nights_from_what_was_kept(tmp_path: Path, monkeypatch) -> None:
    """An old night is settled once, kept, and read back without the network."""
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    out = tmp_path / "out"
    build(lab, out, monkeypatch)
    _, first = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)

    board, _ = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=3), finals=True)
    assert board["record"]["picks"] == first["summary"]["picks"]
    kept = out / "history" / "settled" / f"{BOARD_DAY.isoformat()}.json"
    assert kept.is_file(), "a night two days old is kept"

    module = site_module()

    def unreachable(_day):
        raise OSError("schedule unreachable")

    monkeypatch.setattr(module, "schedule_for", unreachable)
    # As main() calls it: yesterday is the night this run just settled.
    yesterday = {"resultsDate": (BOARD_DAY + timedelta(days=3)).isoformat(), "games": [], "summary": {}}
    season = module.season_record(BOARD_DAY + timedelta(days=4), out / "history", yesterday)
    assert season["picks"] == first["summary"]["picks"]
    assert season["straightUp"] == first["summary"]["straightUp"]
    assert season["missingNights"] == 0


def test_a_night_that_cannot_be_settled_is_missing_not_zero(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    out = tmp_path / "out"
    build(lab, out, monkeypatch)
    module = site_module()

    def unreachable(_day):
        raise OSError("schedule unreachable")

    monkeypatch.setattr(module, "schedule_for", unreachable)
    season = module.season_record(BOARD_DAY + timedelta(days=3), out / "history",
                                  {"resultsDate": "", "games": [], "summary": {}})

    assert season["missingNights"] == 1
    assert season["nights"] == 0
    assert not (out / "history" / "settled").exists(), "an unsettled night is never kept"


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
    for label in ("Best bets · season", "Straight up · season", "Totals · season", "Leans · season"):
        assert cells[label]["value"] == "—", cells[label]
        assert "0–0" not in json.dumps(cells[label], ensure_ascii=False), cells[label]
        assert "Results" in cells[label]["sub"], cells[label]
    # The shareable graphic shows the first three cells of the same strip.
    assert [c["value"] for c in rendered["graphic"]["strip3"]] == ["—", "—", "—"]


def test_a_record_that_is_kept_is_still_rendered(tmp_path: Path) -> None:
    """The absent state must not swallow a real record."""
    record = {"straightUp": {"w": 7, "l": 3}, "puckLine": None,
              "picks": {"w": 4, "l": 2, "p": 1}, "leans": {"w": 1, "l": 3, "p": 0},
              "totals": {"w": 4, "l": 5, "p": 1}, "forward": None,
              "season": {"nights": 5, "missingNights": 0}}

    cells = {c["label"]: c for c in render_board(_board(record), tmp_path)["board"]["strip"]}

    assert cells["Best bets · season"]["value"] == "4–2–1"
    assert "5 nights" in cells["Best bets · season"]["sub"]
    assert cells["Straight up · season"]["value"] == "7–3"
    assert cells["Straight up · season"]["sub"] == "70.0% of games"
    assert cells["Totals · season"]["value"] == "4–5–1"
    assert cells["Leans · season"]["value"] == "1–3–0"
    assert not any("forward" in label.lower() for label in cells)
