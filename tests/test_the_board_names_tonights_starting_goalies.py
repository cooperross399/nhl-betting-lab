"""The public board names each team's starting goalie, as Daily Faceoff lists him.

web/SCHEMA.md has named `away|home.goalie {name, status}` since the drop-6 pages, and the
Board renders a "G  Name  confirmed|projected" line under each team from it, but until
2026-10-20 `web/build_site_json.py` never wrote the key, so no live board carried a goalie.
Gameday Refresh already fetches Daily Faceoff on every pass
(`scripts/fetch_starting_goalies.py` -> `data/processed/starting_goalies.csv`, carried to
Publish Site in `gameday-state`), and the builder now reads that file on every build:

* the site's "Confirmed" label is published as "confirmed";
* "Likely", "Expected", "Unconfirmed" or any other label on a named goalie is "projected";
* a team with no listing, a listing with no goalie named, a file that lists another date,
  and no file at all each leave the key off: never a guess, never yesterday's word;
* a rebuild after the afternoon pass re-reads the file, so a confirmation replaces the
  morning's projection.

Offline: no page is fetched.
"""

from __future__ import annotations

import csv
from pathlib import Path

from test_site_never_calls_an_unpriced_game_a_pass import BOARD_DAY, build, make_lab, site_module

#: The columns `fetch_starting_goalies.py` writes (starting_goalies.COLUMNS).
COLUMNS = ("date", "starts_at", "team", "opponent", "side", "goalie", "strength", "news_at", "retrieved_at")


def write_listing(processed: Path, rows: list[dict]) -> None:
    processed.mkdir(parents=True, exist_ok=True)
    with (processed / "starting_goalies.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})


def listing(team: str, goalie: str, strength: str, *, day: str = BOARD_DAY.isoformat()) -> dict:
    return {"date": day, "team": team, "goalie": goalie, "strength": strength,
            "retrieved_at": f"{day}T12:00:00+00:00"}


def goalies(board: dict) -> dict[str, dict | None]:
    out = {}
    for game in board["games"]:
        for side in ("away", "home"):
            out[game[side]["abbr"]] = game[side].get("goalie")
    return out


def test_confirmed_is_confirmed_and_likely_is_projected(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    write_listing(lab / "data" / "processed", [
        # Daily Faceoff spells Montréal without the accent; the builder's TEAMS carries it.
        listing("Montreal Canadiens", "Samuel Montembeault", "Confirmed"),
        listing("Toronto Maple Leafs", "Joseph Woll", "Likely"),
        listing("Boston Bruins", "Jeremy Swayman", "Expected"),
        listing("New York Islanders", "Ilya Sorokin", "Unconfirmed"),
    ])

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    assert goalies(board) == {
        "MTL": {"name": "Samuel Montembeault", "status": "confirmed"},
        "TOR": {"name": "Joseph Woll", "status": "projected"},
        "BOS": {"name": "Jeremy Swayman", "status": "projected"},
        "NYI": {"name": "Ilya Sorokin", "status": "projected"},
    }


def test_a_team_with_no_listing_gets_no_key(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    write_listing(lab / "data" / "processed", [
        listing("Toronto Maple Leafs", "Joseph Woll", "Confirmed"),
        # Listed, but no goalie named yet: not a goalie.
        listing("Boston Bruins", "", "Unconfirmed"),
    ])

    board, _ = build(lab, tmp_path / "out", monkeypatch)
    found = goalies(board)

    assert found["TOR"] == {"name": "Joseph Woll", "status": "confirmed"}
    for abbr in ("MTL", "BOS", "NYI"):
        assert found[abbr] is None
    for game in board["games"]:
        for side in ("away", "home"):
            if game[side]["abbr"] != "TOR":
                assert "goalie" not in game[side]


def test_another_days_listing_is_never_used(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    yesterday = BOARD_DAY.replace(day=BOARD_DAY.day - 1).isoformat()
    write_listing(lab / "data" / "processed", [
        listing("Toronto Maple Leafs", "Joseph Woll", "Confirmed", day=yesterday),
        listing("Montreal Canadiens", "Samuel Montembeault", "Confirmed", day=yesterday),
    ])

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    assert all(value is None for value in goalies(board).values())


def test_no_file_means_no_goalie_anywhere(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    assert not (lab / "data" / "processed" / "starting_goalies.csv").exists()

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    assert all(value is None for value in goalies(board).values())


def test_an_afternoon_confirmation_replaces_the_morning_projection(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    processed = lab / "data" / "processed"
    write_listing(processed, [listing("Toronto Maple Leafs", "Joseph Woll", "Likely")])
    morning, _ = build(lab, tmp_path / "out-morning", monkeypatch)

    write_listing(processed, [listing("Toronto Maple Leafs", "Anthony Stolarz", "Confirmed")])
    afternoon, _ = build(lab, tmp_path / "out-afternoon", monkeypatch)

    assert goalies(morning)["TOR"] == {"name": "Joseph Woll", "status": "projected"}
    assert goalies(afternoon)["TOR"] == {"name": "Anthony Stolarz", "status": "confirmed"}


def test_the_status_words_are_the_two_the_page_shows() -> None:
    module = site_module()
    assert module.goalie_status("Confirmed") == "confirmed"
    assert module.goalie_status(" confirmed ") == "confirmed"
    for label in ("Likely", "Expected", "Unconfirmed", "", "Something New"):
        assert module.goalie_status(label) == "projected"


def test_a_damaged_file_is_no_listing(tmp_path: Path) -> None:
    module = site_module()
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "starting_goalies.csv").write_bytes(b"\xff\xfe\x00not csv")
    assert module.read_starting_goalies(processed, BOARD_DAY) == {}
