"""The board's "Open" pooled the whole day's captures, and its total was a ladder rung.

`web/build_site_json.py::earliest_capture` globbed
`data/processed/line_movement/<day>*.csv` and returned every row of the
first file it found. `scripts/capture_line_movement.py` writes ONE file per
league day, `capture_path(day)` = `line_movement/<day>.csv`, and appends
every capture of the day to it, each row stamped with its `captured_at`. So
"the earliest capture" was every capture at once, and a later capture moved
the open. The capture also asks the provider for the per-event markets and
their alternate ladders only (`PER_EVENT_PROVIDER_MARKETS +
ALTERNATE_PROVIDER_MARKETS`), never the bulk `h2h`, `spreads` or `totals`:
it holds no moneyline at all, and every `total_goals` row in it is an
`alternate_totals` rung. `headline_line` took the most common line over
those rows, which is whichever rung the ladder repeats most, not the line.

Found by the failure-shape audit (3 of 3 refuters). Reproduced with the real
`capture_path` and the capture's own append: a 14:00 capture (main line
6.0) plus an 18:00 capture (main line moved to 5.5) published
`total.open = 4.5` against `total.current = 6.0`, and `moneyline.open`
None. With the 14:00 capture alone `total.open` read 6.5; appending the
18:00 capture moved it to 5.5. With the bulk `h2h` captured too (the
owner's option of capturing the team markets) the moneyline "open" was the
18:00 price, +135, not the opening +110. The one test that pinned the open,
`test_a_captured_open_is_published_as_the_open`, wrote
`line_movement/<day>_1300.csv`, a name no writer produces, filled with bulk
moneyline and main-line totals the capture never holds, so it passed
whatever the reader did with a real day file.

The same mode-over-rungs reached the CURRENT total. `read_prices` pools
`data/staging/*.csv`, and `player_props_staging.csv` holds the per-event
fetch, `alternate_totals` staged as `total_goals`, beside the bulk file:
with both on disk the board published `total.current = 4.5` (over -350,
under +295) against a bulk main line of 6.0.

Latent today: Publish Site restores neither `data/staging` nor
`line_movement`, so every public open and line is null. It goes live under
the owner's options of carrying prices to Publish Site and restoring line
movement, and on any local build (`run_provider_shadow.py --props`, then
`capture_line_movement.py`, then `web/build_site_json.py`).

These tests write captures where and how `capture_line_movement.main`
writes them (the script needs `--live`, which no test may pass), from
provider-shaped payloads through the real `odds_api.normalize_event`; stage
prices through the real `odds_api.write_staging` under the real file names;
and build the board through the site's own `main()` with only the NHL
schedule stubbed. The page is rendered through `web/lib/sports.js`.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.providers import odds_api

from test_scripts import load_script
from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY,
    CLUBS,
    SLATE,
    build,
    make_lab,
    page_games,
    render_board,
    site_module,
)

DAY = BOARD_DAY.isoformat()
#: Two captures of one day, stamped as `capture_line_movement.main` stamps.
FIRST, LATER = f"{DAY}T14:00:00+00:00", f"{DAY}T18:00:00+00:00"
STAGED_AT = f"{DAY}T13:00:00+00:00"

#: Everything the capture asks the provider for, so everything a capture
#: written today can hold.
CAPTURED_KEYS = frozenset(odds_api.PER_EVENT_PROVIDER_MARKETS) | frozenset(
    odds_api.ALTERNATE_PROVIDER_MARKETS
)

#: The featured total, which only the bulk `totals` market carries, and the
#: alternate ladder around it. Three books ladder and two quote the featured
#: line, so every rung is quoted more often than the line is.
MAIN = 6.0
RUNGS = {4.5: (-350, 295), 5.5: (-160, 135), 6.5: (135, -160), 7.5: (240, -300), 8.5: (400, -550)}
BULK_BOOKS = ("DraftKings", "FanDuel")
LADDER_BOOKS = ("DraftKings", "FanDuel", "BetMGM")


def _teams(away: str, home: str) -> tuple[str, str]:
    """(home, away) as the provider spells them."""
    return CLUBS[home][2], CLUBS[away][2]


def _event(away: str, home: str, books: tuple[str, ...], markets: list[dict]) -> dict:
    """One event as the odds endpoints return it."""
    home_name, away_name = _teams(away, home)
    return {
        "id": f"evt-{home}", "commence_time": f"{DAY}T23:00:00Z",
        "home_team": home_name, "away_team": away_name,
        "bookmakers": [{"key": book.lower(), "title": book, "markets": markets} for book in books],
    }


def bulk_event(away: str, home: str, *, home_price: int = 112, away_price: int = -130,
               h2h_only: bool = False) -> dict:
    """What the bulk endpoint (`fetch_team_markets`) returns: featured lines."""
    home_name, away_name = _teams(away, home)
    markets = [{"key": "h2h", "outcomes": [{"name": home_name, "price": home_price},
                                           {"name": away_name, "price": away_price}]}]
    if not h2h_only:
        markets += [
            {"key": "totals", "outcomes": [{"name": "Over", "price": -105, "point": MAIN},
                                           {"name": "Under", "price": -115, "point": MAIN}]},
            {"key": "spreads", "outcomes": [{"name": home_name, "price": 210, "point": -1.5},
                                            {"name": away_name, "price": -250, "point": 1.5}]},
        ]
    assert {m["key"] for m in markets} <= set(odds_api.BULK_PROVIDER_MARKETS)
    return _event(away, home, BULK_BOOKS, markets)


def ladder_event(away: str, home: str, *, three_way_home: int = 150) -> dict:
    """What the per-event fetch the capture makes returns for one game: the
    alternate ladders and the regulation three-way, nothing bulk."""
    home_name, away_name = _teams(away, home)
    markets = [
        {"key": "alternate_totals", "outcomes": [
            outcome
            for line, (over, under) in RUNGS.items()
            for outcome in ({"name": "Over", "price": over, "point": line},
                            {"name": "Under", "price": under, "point": line})
        ]},
        {"key": "alternate_spreads", "outcomes": [
            outcome
            for point, (fav, dog) in ((1.5, (210, -250)), (2.5, (420, -600)))
            for outcome in ({"name": home_name, "price": fav, "point": -point},
                            {"name": away_name, "price": dog, "point": point})
        ]},
        {"key": "h2h_3_way", "outcomes": [{"name": home_name, "price": three_way_home},
                                          {"name": away_name, "price": 190},
                                          {"name": "Draw", "price": 330}]},
    ]
    assert {m["key"] for m in markets} <= CAPTURED_KEYS, "the capture never asks for this"
    return _event(away, home, LADDER_BOOKS, markets)


def capture(processed: Path, events: list[dict], at: str) -> Path:
    """Appended where and how `capture_line_movement.main` appends."""
    movement = load_script("capture_line_movement.py")
    frame = pd.DataFrame([row for event in events for row in odds_api.normalize_event(event, fetched_at=at)])
    frame["captured_at"] = at
    path = movement.capture_path(DAY, processed_dir=processed)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, mode="a", header=not path.is_file(), index=False, lineterminator="\n")
    return path


def stage(lab: Path, *, bulk: bool = True, per_event: bool = False) -> None:
    """Staged as `run_provider_shadow.py --props` stages: the bulk fetch in one
    file, the per-event fetch (alternate ladders included) in the other."""
    staging = lab / "data" / "staging"
    if bulk:
        rows = [row for away, home, _ in SLATE
                for row in odds_api.normalize_event(bulk_event(away, home), fetched_at=STAGED_AT)]
        odds_api.write_staging(rows, filename=odds_api.STAGING_PRICES_FILENAME, staging_dir=staging)
    if per_event:
        rows = [row for away, home, _ in SLATE
                for row in odds_api.normalize_event(ladder_event(away, home), fetched_at=STAGED_AT)]
        odds_api.write_staging(rows, filename=odds_api.STAGING_PROPS_FILENAME, staging_dir=staging)


def game(board: dict, home: str) -> dict:
    return next(g for g in board["games"] if g["home"]["abbr"] == home)


def total_cell(board: dict, home: str, tmp_path: Path) -> dict:
    shown = next(g for g in page_games(render_board(board, tmp_path)) if g["sides"][1]["abbr"] == home)
    return next(cell for cell in shown["cells"] if cell["title"] == "Total")


# -- the open ------------------------------------------------------------------


def test_a_capture_as_the_script_writes_it_publishes_no_open_total(
    tmp_path: Path, monkeypatch
) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    stage(lab)
    processed = lab / "data" / "processed"
    for at in (FIRST, LATER):
        path = capture(processed, [ladder_event(away, home) for away, home, _ in SLATE], at)
    with path.open(newline="", encoding="utf-8") as fh:
        held = {row["market"] for row in csv.DictReader(fh)}
    # Not vacuous: the day file holds total rows the old reader read a line
    # from, and no moneyline, because the capture asks for none.
    assert {"total_goals", "puck_line", "regulation_3_way"} <= held and "moneyline" not in held, held

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    tor = game(board, "TOR")
    assert tor["total"]["current"] == MAIN, tor["total"]
    assert tor["total"]["open"] is None, (
        f"the board published {tor['total']['open']} as the open total; every total row a "
        "capture holds is a rung of alternate_totals, and a rung is not the line"
    )
    assert tor["moneyline"]["open"] is None, tor["moneyline"]
    assert total_cell(board, "TOR", tmp_path)["rows"][0]["value"] == "— / 6.0"


def test_the_open_is_one_capture_not_the_day_pooled(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    capture(processed, [ladder_event("MTL", "TOR", three_way_home=150)], FIRST)
    capture(processed, [ladder_event("MTL", "TOR", three_way_home=175)], LATER)

    opens = site_module().earliest_capture(processed, BOARD_DAY)

    assert opens, "the day's capture file was not read at all"
    assert {row["captured_at"] for row in opens} == {FIRST}, (
        "the open pooled every capture appended to the day's file"
    )
    assert {float(row["american_odds"]) for row in opens
            if row["market"] == "regulation_3_way" and row["selection"] == "home"} == {150.0}
    assert not {row["market"] for row in opens} & {"total_goals", "puck_line"}, (
        "a ladder rung was offered to the board as an opening line"
    )


def test_a_later_capture_does_not_move_a_captured_moneyline_open(
    tmp_path: Path, monkeypatch
) -> None:
    """The capture buys no moneyline today. If it also bought the bulk `h2h`
    (the owner's option of capturing the team markets), the open is the
    first capture's price, and a later capture does not rewrite it."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    stage(lab)
    processed = lab / "data" / "processed"
    capture(processed, [ladder_event("MTL", "TOR"),
                        bulk_event("MTL", "TOR", home_price=110, away_price=-130, h2h_only=True)], FIRST)
    before, _ = build(lab, tmp_path / "out-first", monkeypatch)
    assert game(before, "TOR")["moneyline"]["open"] == {"home": 110.0, "away": -130.0}

    capture(processed, [ladder_event("MTL", "TOR"),
                        bulk_event("MTL", "TOR", home_price=135, away_price=-155, h2h_only=True)], LATER)
    after, _ = build(lab, tmp_path / "out-later", monkeypatch)

    assert game(after, "TOR")["moneyline"]["open"] == {"home": 110.0, "away": -130.0}, (
        "the 18:00 capture moved the 14:00 open"
    )
    assert game(after, "TOR")["moneyline"]["current"] == {"home": 112.0, "away": -130.0}


def test_a_moneyline_first_captured_later_opens_at_its_own_first_capture(
    tmp_path: Path, monkeypatch
) -> None:
    """Each game's market opens at the first capture that held it. NYI's
    first capture held only its ladders; its moneyline first appears at
    18:00, and that is its open, not a missing one."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    stage(lab)
    processed = lab / "data" / "processed"
    capture(processed, [ladder_event("MTL", "TOR"), ladder_event("BOS", "NYI"),
                        bulk_event("MTL", "TOR", home_price=110, away_price=-130, h2h_only=True)], FIRST)
    capture(processed, [ladder_event("MTL", "TOR"), ladder_event("BOS", "NYI"),
                        bulk_event("MTL", "TOR", home_price=135, away_price=-155, h2h_only=True),
                        bulk_event("BOS", "NYI", home_price=-120, away_price=102, h2h_only=True)], LATER)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    assert game(board, "TOR")["moneyline"]["open"] == {"home": 110.0, "away": -130.0}
    assert game(board, "NYI")["moneyline"]["open"] == {"home": -120.0, "away": 102.0}


@pytest.mark.parametrize(
    "captured_at",
    [None, "", "not a time", f"{DAY}T14:00:00"],
    ids=["no-column", "blank", "unreadable", "no-offset"],
)
def test_a_capture_that_cannot_say_when_it_was_taken_opens_nothing(
    tmp_path: Path, monkeypatch, captured_at: str | None
) -> None:
    """A row that cannot be placed in time cannot be placed in a capture, so
    it is no capture's first row. Missing stays missing. The capture stamps
    every row with a UTC offset; a stamp without one is not a moment."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    stage(lab)
    frame = pd.DataFrame(odds_api.normalize_event(
        bulk_event("MTL", "TOR", home_price=110, away_price=-130, h2h_only=True), fetched_at=FIRST
    ))
    if captured_at is not None:
        frame["captured_at"] = captured_at
    path = load_script("capture_line_movement.py").capture_path(DAY, processed_dir=lab / "data" / "processed")
    path.parent.mkdir(parents=True)
    frame.to_csv(path, index=False, lineterminator="\n")

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    assert game(board, "TOR")["moneyline"]["open"] is None


def test_a_file_the_capture_never_writes_is_not_read_as_the_open(
    tmp_path: Path, monkeypatch
) -> None:
    """`<day>_1300.csv` is the name the old test used and no writer produces.
    The open is read from the file `capture_path` names, and from nothing else."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    stage(lab)
    processed = lab / "data" / "processed"
    written = capture(processed, [bulk_event("MTL", "TOR", home_price=110, away_price=-130,
                                             h2h_only=True)], FIRST)
    written.rename(written.with_name(f"{DAY}_1300.csv"))

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    assert game(board, "TOR")["moneyline"]["open"] is None


# -- the current line ----------------------------------------------------------


def test_a_staged_ladder_is_never_the_current_total(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    stage(lab, bulk=True, per_event=True)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    total = game(board, "TOR")["total"]
    assert total["current"] == MAIN, (
        f"the board published {total['current']} as the line; it is a rung of the staged "
        f"alternate_totals ladder, and the bulk main line is {MAIN}"
    )
    assert (total["overPrice"], total["underPrice"]) == (-105.0, -115.0), total
    assert total_cell(board, "TOR", tmp_path)["rows"][0]["value"] == "— / 6.0"


def test_a_board_staged_with_ladders_alone_publishes_no_total_line(
    tmp_path: Path, monkeypatch
) -> None:
    """With the bulk file missing no staged row is the featured line, so the
    line is missing. The ladder does not stand in for it."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    stage(lab, bulk=False, per_event=True)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    tor = game(board, "TOR")
    assert tor["priced"] is True, "the per-event prices still reached the board"
    assert "total" not in tor, tor.get("total")
