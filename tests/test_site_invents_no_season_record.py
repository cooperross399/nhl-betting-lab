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

import test_site_never_calls_an_unpriced_game_a_pass as harness
from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY,
    SLATE,
    build,
    make_lab,
    render_board,
    render_results,
    site_module,
)
from test_site_publishes_no_forward_return import MID_SEASON, RETURN_FIELDS, THE_RETURN

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



def test_results_carry_no_tally_before_the_first_settled_night(tmp_path: Path, monkeypatch) -> None:
    """results.json's `seasonRecord` names the span and nothing else until a
    night settles: no tally key at all, so no 0–0 nobody counted."""
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    _, results = build(lab, tmp_path / "out", monkeypatch)

    season = results["seasonRecord"]
    assert season == {"nights": 0, "firstDate": None, "lastDate": None, "missingNights": 0}, season
    rendered = render_results(results, tmp_path)
    assert not [c for c in rendered["strip"] if "season" in c["label"].lower()], rendered["strip"]

def test_no_settled_night_publishes_no_props_or_due_list_record(tmp_path: Path, monkeypatch) -> None:
    """`record.props`, `record.propLeans`, `record.dueList` and
    `props.seasonLeans` are absent before a night settles, not {w: 0, l: 0}.
    The board carries a Due List tonight, so the absence is for want of a
    settled night, not of a list."""
    from test_the_site_board_carries_the_drought_list import build as build_with_list, row, write_list

    lab = make_lab(tmp_path, monkeypatch, staged=True)
    write_list(lab, [row("TOR", "MTL")])
    out = tmp_path / "out"
    board = build_with_list(lab, out, monkeypatch)
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))

    assert any(g["drought"] for g in board["games"]), board["games"]
    for key in ("props", "propLeans", "dueList"):
        assert key not in board["record"], (key, board["record"][key])
    assert "seasonLeans" not in (results.get("props") or {})
    assert "dueList" not in results and "dueList" not in results["seasonRecord"]
    assert results["seasonRecord"] == {"nights": 0, "firstDate": None, "lastDate": None, "missingNights": 0}


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


def _played(tally: dict) -> int:
    return sum(tally.values())


def test_an_unpriced_or_exhibition_row_never_counts_toward_the_season(
        tmp_path: Path, monkeypatch) -> None:
    """The season adds up only what the night's grading would grade.

    An unpriced game carries no pick and no total line, so it can add
    nothing to best bets, leans or totals. An exhibition is published as
    schedule only and never reaches results.json at all. The staged,
    all-regular slate in test_a_settled_night_is_the_boards_season_record
    is the companion that keeps both halves from passing on an empty tally:
    the same two games there count one best bet and two totals.
    """
    # Unpriced: both games are projected and played to a final, no price
    # reaches either.
    lab = make_lab(tmp_path / "unpriced", monkeypatch, staged=False)
    out = tmp_path / "unpriced" / "out"
    build(lab, out, monkeypatch)
    board, results = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)

    assert [g["priced"] for g in results["games"]] == [False] * len(SLATE), results["games"]
    assert results["seasonRecord"]["nights"] == 1  # the night was settled
    for key in ("picks", "leans", "totals"):
        assert _played(results["seasonRecord"][key]) == 0, (key, results["seasonRecord"][key])
        assert _played(board["record"][key]) == 0, (key, board["record"][key])

    # Exhibition: a priced slate where one of the two games is preseason.
    exhibition_home = SLATE[1][1]
    regular_only = harness.schedule

    def one_exhibition(day, *, final=False):
        games = regular_only(day, final=final)
        for game in games:
            if game["homeTeam"]["abbrev"] == exhibition_home:
                game["gameType"] = 1
        return games

    monkeypatch.setattr(harness, "schedule", one_exhibition)
    lab = make_lab(tmp_path / "exhibition", monkeypatch, staged=True)
    out = tmp_path / "exhibition" / "out"
    build(lab, out, monkeypatch)
    board, results = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)

    assert [g["home"]["abbr"] for g in results["games"]] == [SLATE[0][1]], results["games"]
    season = results["seasonRecord"]
    # One regular-season game: one straight-up call, one total, one best bet.
    assert _played(season["straightUp"]) == 1, season
    assert _played(season["totals"]) == 1, season
    assert _played(season["picks"]) == 1, season
    for key in ("straightUp", "picks", "leans", "totals"):
        assert board["record"][key] == season[key], (key, board["record"][key], season[key])


def _keys_and_numbers(node, keys: set, numbers: set) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            _keys_and_numbers(value, keys, numbers)
    elif isinstance(node, list):
        for value in node:
            _keys_and_numbers(value, keys, numbers)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        numbers.add(node)


def test_the_season_leaves_forward_alone_and_publishes_no_return(
        tmp_path: Path, monkeypatch) -> None:
    """Merging the season into `record` must not touch the sealed ledger.

    The ledger report here is mid-season and carries a per-market return
    (+6.1%, -2.2%) and its intervals, so a leak has something to leak.
    `forward` on the board must be exactly what load_record seals, before
    and after a night settles, and neither file may carry a return key or
    one of the report's return figures anywhere.
    """
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    report = lab / "data" / "outputs" / "forward_evidence.json"
    report.write_text(json.dumps(MID_SEASON), encoding="utf-8")
    sealed = site_module().load_record(report)["forward"]
    assert sealed["rows"] == MID_SEASON["rows"], "the fixture reached load_record"

    out = tmp_path / "out"
    before, _ = build(lab, out, monkeypatch)
    after, results = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)

    assert after["record"]["season"]["nights"] == 1, "the season was merged into the record"
    assert before["record"]["forward"] == sealed
    assert after["record"]["forward"] == sealed
    assert "forward" not in results["seasonRecord"]

    returns = {
        entry[key] for entry in MID_SEASON["markets"].values()
        for key in ("roi", "low", "high", "adjusted_low", "adjusted_high")
    }
    for name, payload in (("board.json", after), ("results.json", results)):
        keys: set = set()
        numbers: set = set()
        _keys_and_numbers(payload, keys, numbers)
        leaked = keys & (set(THE_RETURN) | set(RETURN_FIELDS))
        assert not leaked, f"{name} carries {sorted(leaked)}, a forward return sealed until 2027-04-25"
        assert not numbers & returns, f"{name} carries {sorted(numbers & returns)} from the ledger's return"


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
