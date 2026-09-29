"""The public board prices a game from rows for that game's league day only.

Since 2026-09-29 (PR #275) the `gameday-state` artifact carries
`data/staging`, so Publish Site restores the staged prices along with the
card. It restores "the newest Gameday Refresh run that carries state", and
that can be an earlier day's: its 14:45 UTC cron fires before a late Gameday
run has finished (this account's schedules run hours late), or the day's
state upload failed and yesterday's run is the newest carrier. Before the
PR such a build was honestly unpriced. After it, the restored folder held
yesterday's quotes, and `build_board` joined them to today's games by team
alone — the home side and the away side looked up independently — so:

* a team in the same role two nights running read `priced: true` with
  `moneyline.current: null`, and the page printed "No market clears the edge
  bar", a model judgement nobody made;
* a repeat pairing published yesterday's moneyline and total as today's, and
  yesterday's card's best bet as today's pick.

The freeze was guarded (`site_history.built_on_stale_state`); the live page
was not. Found by the adversarial review of PR #275 (two lenses, four
refuters, reproduced through the real `main()`).

The gate is `todays_rows`: a row is kept only when `league_day` of its
`commence_time` is the board's date. Not its `date` column — that is the
UTC date, and on opening night 286 of the 486 team rows carried the next
day's — and not `fetched_at`, which says when the row was asked for, not
which game it is about.

Driven through the sibling module's fixtures: the real `main()`, the real
`save_card`, a team-name map built from a boxscore cache, the page rendered
under node.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from nhl_betting_lab.season import game_date

from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY,
    CLUBS,
    SLATE,
    _price_rows,
    _write_csv,
    build,
    make_lab,
    page_games,
    render_board,
    site_module,
)

YESTERDAY = BOARD_DAY - timedelta(days=1)
STAGING = Path("data") / "staging" / "odds_api_prices_staging.csv"


def _rows(pairings, *, commence: str, fetched: str, offset: int = 0) -> list[dict]:
    """Staged rows shaped as tests/test_site_never_calls_an_unpriced_game_a_pass
    stages them (two books; the best home moneyline is 112 + offset), for the
    given (away, home) pairings at the given moment."""
    rows = []
    for away, home in pairings:
        for book, bump in (("draftkings", 0), ("fanduel", 4)):
            def add(market, selection, odds, line=""):
                rows.append({
                    "date": commence[:10], "commence_time": commence,
                    "provider_event_id": f"evt-{home}", "home_team": CLUBS[home][2],
                    "away_team": CLUBS[away][2], "market": market, "player": "",
                    "selection": selection, "line": line, "american_odds": odds,
                    "book": book, "fetched_at": fetched,
                })
            add("moneyline", "home", 108 + bump + offset)
            add("moneyline", "away", -130 - bump - offset)
            add("puck_line", "home", 210 + bump, -1.5)
            add("puck_line", "away", -250 - bump, 1.5)
            add("total_goals", "over", -110 + bump, 6.0)
            add("total_goals", "under", -110 - bump, 6.0)
            add("regulation_3_way", "home", 150 + bump)
            add("regulation_3_way", "draw", 330 + bump)
            add("regulation_3_way", "away", 190 + bump)
    return rows


def _pairings():
    return [(away, home) for away, home, _ in SLATE]


def test_the_rows_here_are_the_siblings_rows_on_its_own_day() -> None:
    """`_rows` is a copy of the sibling's `_price_rows` with the moment
    parameterised; this holds the copy to the original, so a market or a
    price the sibling changes cannot leave these tests staging a different
    shape while every assertion stays green."""
    assert _rows(_pairings(), commence=f"{BOARD_DAY.isoformat()}T23:00:00Z",
                 fetched=f"{BOARD_DAY.isoformat()}T13:00:00Z") == _price_rows()


def _assert_unpriced(board: dict, tmp_path: Path) -> None:
    assert [g["priced"] for g in board["games"]] == [False] * len(SLATE), board["games"]
    assert all(g["pick"] is None and "moneyline" not in g and "total" not in g for g in board["games"])
    assert "not priced" in (board["notice"] or "").lower(), board["notice"]
    for game in page_games(render_board(board, tmp_path)):
        assert game["pick"]["label"].startswith("Not priced"), game["pick"]


def test_yesterdays_rows_for_the_same_pairings_price_nothing(tmp_path: Path, monkeypatch) -> None:
    """The repeat-pairing case: without the gate this published yesterday's
    moneyline and total as today's and the card's best bet as today's pick."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    _write_csv(lab / STAGING, _rows(
        _pairings(), commence=f"{YESTERDAY.isoformat()}T23:00:00Z",
        fetched=f"{YESTERDAY.isoformat()}T13:00:00Z",
    ))

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    _assert_unpriced(board, tmp_path)


def test_yesterdays_rows_with_the_same_roles_price_nothing(tmp_path: Path, monkeypatch) -> None:
    """The independent-lookup case: MTL away and TOR home yesterday, in other
    games, made today's MTL @ TOR `priced: true` with no line at all."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    swapped = [("MTL", "NYI"), ("BOS", "TOR")]
    _write_csv(lab / STAGING, _rows(
        swapped, commence=f"{YESTERDAY.isoformat()}T23:00:00Z",
        fetched=f"{YESTERDAY.isoformat()}T13:00:00Z",
    ))

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    _assert_unpriced(board, tmp_path)


def test_a_row_for_yesterdays_game_prices_nothing_whenever_it_was_fetched(
    tmp_path: Path, monkeypatch
) -> None:
    """The gate reads which game a row is about, not when it was asked for."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    _write_csv(lab / STAGING, _rows(
        _pairings(), commence=f"{YESTERDAY.isoformat()}T23:00:00Z",
        fetched=f"{BOARD_DAY.isoformat()}T13:00:00Z",
    ))

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    _assert_unpriced(board, tmp_path)


def test_a_late_start_whose_utc_date_is_tomorrow_is_todays_game(tmp_path: Path, monkeypatch) -> None:
    """22:00 Eastern on the board day is 02:00 UTC the next day, and the
    staged `date` column says the next day. The row is today's, and the
    board prices from it — the companion that keeps the tests above from
    passing on a gate that drops everything."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    late = f"{(BOARD_DAY + timedelta(days=1)).isoformat()}T02:00:00Z"
    rows = _rows(_pairings(), commence=late, fetched=f"{BOARD_DAY.isoformat()}T13:00:00Z")
    assert {r["date"] for r in rows} == {(BOARD_DAY + timedelta(days=1)).isoformat()}
    _write_csv(lab / STAGING, rows)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    tor = next(g for g in board["games"] if g["home"]["abbr"] == "TOR")
    assert tor["priced"] is True
    assert tor["moneyline"]["current"] == {"home": 112.0, "away": -130.0}
    assert tor["total"]["current"] == 6.0
    assert tor["pick"] == {"kind": "bet", "market": "Moneyline", "label": "TOR +112", "price": 112, "edgePct": 11.0}
    assert board["notice"] is None


def test_todays_rows_are_read_past_yesterdays_in_the_same_file(tmp_path: Path, monkeypatch) -> None:
    """Both days in one file: today's quotes, not the best of the two days."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    stale = _rows(_pairings(), commence=f"{YESTERDAY.isoformat()}T23:00:00Z",
                  fetched=f"{YESTERDAY.isoformat()}T13:00:00Z", offset=20)
    fresh = _rows(_pairings(), commence=f"{BOARD_DAY.isoformat()}T23:00:00Z",
                  fetched=f"{BOARD_DAY.isoformat()}T13:00:00Z")
    _write_csv(lab / STAGING, stale + fresh)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    tor = next(g for g in board["games"] if g["home"]["abbr"] == "TOR")
    assert tor["priced"] is True
    assert tor["moneyline"]["current"] == {"home": 112.0, "away": -130.0}, (
        "yesterday's +132 was the best price on file and is not today's"
    )


# -- the copy agrees with the lab ------------------------------------------

#: Timestamps the two readers must agree on: UTC and offset spellings, the
#: edge where the league day turns (04:00 UTC in Eastern daylight time,
#: 05:00 UTC in Eastern standard time), and both daylight-saving
#: transitions (2026-11-01 back, 2027-03-14 forward).
AGREED = [
    "2026-10-08T23:00:00Z",
    "2026-10-08T23:00:00+00:00",
    "2026-10-08T19:00:00-04:00",
    "2026-10-09T02:30:00Z",
    "2026-10-09T03:59:59Z",
    "2026-10-09T04:00:00Z",
    "2026-10-09T04:00:01Z",
    "2026-11-01T05:30:00Z",
    "2026-11-01T06:30:00Z",
    "2026-11-02T04:59:59Z",
    "2026-11-02T05:00:00Z",
    "2027-03-14T06:30:00Z",
    "2027-03-14T07:30:00Z",
    "2027-03-15T03:59:59Z",
    "2027-03-15T04:00:00Z",
    "2026-09-29T21:10:47Z",
    "2026-09-30T02:10:00Z",
    "",
    None,
]


@pytest.mark.parametrize("stamp", AGREED, ids=[repr(s) for s in AGREED])
def test_league_day_is_the_labs_game_date(stamp) -> None:
    module = site_module()
    assert module.league_day(stamp) == game_date(stamp)


def test_the_readers_turn_the_day_at_midnight_eastern_in_winter_and_summer() -> None:
    """Not a tautology between two copies: the value both must produce —
    05:00 UTC in winter (EST), 04:00 UTC in summer (EDT)."""
    module = site_module()
    assert module.league_day("2026-11-02T04:59:59Z") == "2026-11-01"  # EST
    assert module.league_day("2026-11-02T05:00:00Z") == "2026-11-02"
    assert module.league_day("2027-03-15T03:59:59Z") == "2027-03-14"  # EDT
    assert module.league_day("2027-03-15T04:00:00Z") == "2027-03-15"
    assert game_date("2026-11-02T04:59:59Z") == "2026-11-01"
    assert game_date("2027-03-15T03:59:59Z") == "2027-03-14"


@pytest.mark.parametrize("stamp", ["2026-10-08T23:00:00", "2026-10-08", "garbage"])
def test_the_board_drops_what_the_lab_guesses_at(stamp) -> None:
    """The one documented divergence: a naive or unreadable value is the
    lab's best guess and the board's dropped row."""
    module = site_module()
    assert game_date(stamp) == stamp[:10]
    assert module.league_day(stamp) == ""


def test_todays_rows_keeps_a_row_only_for_the_asked_day() -> None:
    module = site_module()
    rows = [
        {"commence_time": "2026-10-09T02:00:00Z", "market": "moneyline"},  # 22:00 ET Oct 8
        {"commence_time": "2026-10-09T04:00:00Z", "market": "moneyline"},  # 00:00 ET Oct 9
        {"commence_time": "2026-10-08T23:00:00", "market": "moneyline"},   # naive: no day
        {"market": "moneyline"},                                           # no stamp: no day
    ]
    assert module.todays_rows(rows, date(2026, 10, 8)) == rows[:1]
    assert module.todays_rows(rows, date(2026, 10, 9)) == rows[1:2]
