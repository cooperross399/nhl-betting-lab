"""The Due List is graded from the frozen board, every night, and summed for the season.

Cooper's Due List (`games[].drought`, 2026-10-07) is his own list: never staked,
never units, never a best bet. What the site owes it is a record. `web/
build_site_json.py::grade_due_list` grades every entry a FROZEN board published,
priced or not, against the player's final count in his category from the
box-score logs (`data/processed/player_game_logs.csv`), and `season_record`
sums every night into `record.dueList` on board.json and `dueList.season` on
results.json, split by category, with the mean implied probability of the
posted prices that were graded.

What these tests hold, through the real `main()` over three frozen nights with
only the NHL schedule stubbed: the sums are the sums of what was graded; a
player who did not dress is void and in neither tally; a game not final is
result null and uncounted; an unpriced entry is counted and excluded from
`impliedPct` alone; a board listing one player twice grades him once; and a
final game whose box score has not reached the logs waits (null, the night
not kept) rather than voiding the whole list.
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

from test_site_never_calls_an_unpriced_game_a_pass import BOARD_DAY, CLUBS, SLATE, make_lab, site_module
from test_the_site_board_carries_the_drought_list import SCHEMA_KEYS, row, write_list

D0 = BOARD_DAY
D1, D2, D3 = (BOARD_DAY + timedelta(days=n) for n in (1, 2, 3))
NIGHTS = (D0, D1, D2)

#: Far enough ahead that the puck-drop guard never empties a list, whatever
#: day the suite runs (the board lists nobody for a game that has started).
START = "2099-10-08T23:00:00Z"


def game_id(day: date, index: int) -> str:
    """One id per game per night: the slate's position, prefixed by the night."""
    return f"20260201{(day - D0).days}{index}"


def nightly_schedule(build_day: date, *, not_final: tuple[str, ...] = ()):
    """The NHL schedule for NIGHTS: SLATE every night, final once the night is before `build_day`."""

    def schedule_for(day: date) -> list[dict]:
        if day not in NIGHTS:
            return []
        games = []
        for index, (away, home, _) in enumerate(SLATE):
            gid = game_id(day, index)

            def side(abbrev: str, score: int) -> dict:
                place, common, _ = CLUBS[abbrev]
                entry = {"abbrev": abbrev, "placeName": {"default": place},
                         "commonName": {"default": common}, "record": "1-0-0"}
                if day < build_day:
                    entry["score"] = score
                return entry

            game = {"id": int(gid), "gameType": 2, "startTimeUTC": START, "venue": {"default": "Arena"},
                    "venueLocation": {"default": "City"}, "tvBroadcasts": [],
                    "awayTeam": side(away, 2), "homeTeam": side(home, 5)}
            if day < build_day and gid not in not_final:
                game.update(gameState="OFF", gameOutcome={"lastPeriodType": "REG"})
            games.append(game)
        return games

    return schedule_for


def build_night(lab: Path, out: Path, monkeypatch, day: date, *, not_final: tuple[str, ...] = (),
                module=None) -> tuple[dict, dict]:
    """main() for `day`, as Publish Site runs it: the board for `day`, the results for the night before."""
    module = module or site_module()
    monkeypatch.setattr(module, "schedule_for", nightly_schedule(day, not_final=not_final))
    monkeypatch.setattr(module, "allowlisted_markets", lambda _lab: ["moneyline"])
    assert module.main(["--lab", str(lab), "--out", str(out), "--date", day.isoformat()]) == 0
    board = json.loads((out / "board.json").read_text(encoding="utf-8"))
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    return board, results


def make_due_list_lab(tmp_path: Path, monkeypatch, *, staged: bool = False) -> Path:
    """The runner's lab with no card: a board built on no card is never stale
    (site_history.built_on_stale_state), so every night here freezes."""
    lab = make_lab(tmp_path, monkeypatch, staged=staged)
    (lab / "data" / "outputs" / "gameday_card.json").unlink()
    return lab


LOG_COLUMNS = ("game_id", "season", "game_type", "date", "start_time_utc", "player_id", "player",
               "team", "opponent", "goals", "assists", "points")


def write_logs(lab: Path, rows: list[tuple[str, int, str, str, int, int]]) -> None:
    """player_game_logs.csv as build_datasets writes it: (game id, player id, player, team, goals, assists)."""
    path = lab / "data" / "processed" / "player_game_logs.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(LOG_COLUMNS)
        for gid, pid, player, team, goals, assists in rows:
            writer.writerow([gid, 20262027, 2, "2026-10-08", START, pid, player, team, "OPP", goals, assists, goals + assists])


# The three nights. TOR hosts MTL and NYI hosts BOS every night (SLATE).
TOR_GAME = {d: game_id(d, 0) for d in NIGHTS}
NYI_GAME = {d: game_id(d, 1) for d in NIGHTS}

LISTS = {
    D0: [
        row("TOR", "MTL", player="Alpha Points", player_id=1, market="points", american_odds=-150.0),
        row("TOR", "MTL", team="MTL", player="Bravo Goals", player_id=2, market="goals", american_odds=140.0),
        row("NYI", "BOS", player="Charlie Assists", player_id=3, market="assists", american_odds=None, book=""),
        row("NYI", "BOS", team="BOS", player="Delta Scratch", player_id=4, market="goals", american_odds=200.0),
    ],
    D1: [
        row("TOR", "MTL", player="Echo Points", player_id=5, market="points", american_odds=-200.0),
        row("NYI", "BOS", player="Foxtrot Assists", player_id=6, market="assists", american_odds=120.0),
        row("NYI", "BOS", player="Foxtrot Assists", player_id=6, market="assists", american_odds=120.0),
    ],
    D2: [
        row("TOR", "MTL", team="MTL", player="Golf Goals", player_id=7, market="goals", american_odds=110.0),
        row("NYI", "BOS", player="Hotel Points", player_id=8, market="points", american_odds=-110.0),
    ],
}

#: (game id, player id, player, team, goals, assists): Delta never dresses;
#: Hotel's game is never final, so his row is never read.
LOGS = [
    (TOR_GAME[D0], 1, "Alpha Points", "TOR", 1, 1),
    (TOR_GAME[D0], 2, "Bravo Goals", "MTL", 0, 1),
    (NYI_GAME[D0], 3, "Charlie Assists", "NYI", 0, 1),
    (NYI_GAME[D0], 99, "Someone Else", "BOS", 0, 0),
    (TOR_GAME[D1], 5, "Echo Points", "TOR", 0, 0),
    (NYI_GAME[D1], 6, "Foxtrot Assists", "NYI", 0, 2),
    (TOR_GAME[D2], 7, "Golf Goals", "MTL", 1, 0),
    (NYI_GAME[D2], 8, "Hotel Points", "NYI", 3, 3),
]

#: The posted prices of the five entries that were graded: Alpha, Bravo,
#: Echo, Foxtrot, Golf. Charlie is graded with no price; Delta is void;
#: Hotel's game is not final.
GRADED_PRICES = (-150, 140, -200, 120, 110)


def _implied(american: int) -> float:
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def three_nights(tmp_path: Path, monkeypatch) -> tuple[Path, Path, dict, dict, dict]:
    """Boards for D0, D1 and D2, each morning after through D3; Hotel's game stays unfinished.

    Returns the lab, the output directory, D3's board, D2's results (the
    night D3 settled) and every night's results by its date.
    """
    lab = make_due_list_lab(tmp_path, monkeypatch)
    write_logs(lab, LOGS)
    out = tmp_path / "out"
    results_by_night = {}
    board = {}
    for day in (D0, D1, D2, D3):
        if day in LISTS:
            write_list(lab, LISTS[day], day=day)
        board, results = build_night(lab, out, monkeypatch, day, not_final=(NYI_GAME[D2],))
        results_by_night[day - timedelta(days=1)] = results
    return lab, out, board, results_by_night[D2], results_by_night


def test_three_frozen_nights_sum_into_the_season_record(tmp_path: Path, monkeypatch) -> None:
    _, _, board, results, _ = three_nights(tmp_path, monkeypatch)

    assert board["record"]["dueList"] == {"w": 4, "l": 2, "p": 0, "nights": 3}
    season = results["dueList"]["season"]
    assert season["byMarket"] == {"points": {"w": 1, "l": 1}, "goals": {"w": 1, "l": 1}, "assists": {"w": 2, "l": 0}}
    assert {k: season[k] for k in ("w", "l", "p", "nights")} == board["record"]["dueList"]
    assert results["seasonRecord"]["dueList"] == season
    # The record on the board is a count and nothing else: the page's own
    # keys, no category split and no price figure.
    assert set(board["record"]["dueList"]) == {"w", "l", "p", "nights"}
    assert set(season) == {"w", "l", "p", "nights", "impliedPct", "byMarket"}


def test_an_unpriced_entry_is_counted_and_left_out_of_the_implied_rate(tmp_path: Path, monkeypatch) -> None:
    _, _, board, results, by_night = three_nights(tmp_path, monkeypatch)

    charlie = next(r for r in by_night[D0]["dueList"]["rows"] if r["player"] == "Charlie Assists")
    assert (charlie["price"], charlie["book"], charlie["actual"], charlie["result"]) == (None, None, 1, "win")
    # Five priced entries were graded; the sixth, Charlie, carries no price.
    assert sum(board["record"]["dueList"][k] for k in ("w", "l", "p")) == len(GRADED_PRICES) + 1
    expected = round(100 * sum(_implied(p) for p in GRADED_PRICES) / len(GRADED_PRICES), 1)
    assert expected == 52.3
    assert results["dueList"]["season"]["impliedPct"] == expected
    assert results["dueList"]["season"]["impliedPct"] != round(
        100 * (sum(_implied(p) for p in GRADED_PRICES) + 0.5) / (len(GRADED_PRICES) + 1), 1
    ), "a missing price was averaged in as even money"


def test_a_scratched_player_is_void_and_in_neither_tally(tmp_path: Path, monkeypatch) -> None:
    _, _, board, _, by_night = three_nights(tmp_path, monkeypatch)

    night = by_night[D0]["dueList"]
    delta = next(r for r in night["rows"] if r["player"] == "Delta Scratch")
    assert (delta["actual"], delta["result"]) == (None, "void")
    assert night["summary"] == {"w": 2, "l": 1, "p": 0}, night["summary"]
    assert len(night["rows"]) == 4, "a void entry is still listed"
    # Delta's price (+200) would have moved the implied rate had he been graded.
    assert board["record"]["dueList"]["w"] + board["record"]["dueList"]["l"] == 6


def test_a_game_not_final_is_result_null_and_not_counted(tmp_path: Path, monkeypatch) -> None:
    _, _, board, results, _ = three_nights(tmp_path, monkeypatch)

    hotel = next(r for r in results["dueList"]["rows"] if r["player"] == "Hotel Points")
    assert (hotel["actual"], hotel["result"]) == (None, None), hotel
    assert results["dueList"]["summary"] == {"w": 1, "l": 0, "p": 0}
    golf = next(r for r in results["dueList"]["rows"] if r["player"] == "Golf Goals")
    assert (golf["actual"], golf["result"], golf["opp"], golf["gameId"]) == (1, "win", "TOR", TOR_GAME[D2])
    assert board["record"]["dueList"]["w"] + board["record"]["dueList"]["l"] == 6


def test_one_entry_per_player_and_category_a_night(tmp_path: Path, monkeypatch) -> None:
    _, out, board, results, by_night = three_nights(tmp_path, monkeypatch)

    frozen = json.loads((out / "history" / f"{D1.isoformat()}.json").read_text(encoding="utf-8"))
    nyi = next(g for g in frozen["games"] if g["home"]["abbr"] == "NYI")
    assert [e["player"] for e in nyi["drought"]] == ["Foxtrot Assists"] * 2, "the frozen board lists him twice"
    night = by_night[D1]["dueList"]
    assert [r["player"] for r in night["rows"]] == ["Echo Points", "Foxtrot Assists"]
    assert night["summary"] == {"w": 1, "l": 1, "p": 0}
    assert results["dueList"]["season"]["byMarket"]["assists"] == {"w": 2, "l": 0}


def test_the_rows_are_the_frozen_entries_with_their_grade(tmp_path: Path, monkeypatch) -> None:
    _, _, _, _, by_night = three_nights(tmp_path, monkeypatch)

    alpha = next(r for r in by_night[D0]["dueList"]["rows"] if r["player"] == "Alpha Points")
    assert set(alpha) == SCHEMA_KEYS | {"gameId", "opp", "actual", "result"}
    assert alpha == {"gameId": TOR_GAME[D0], "player": "Alpha Points", "playerId": 1, "team": "TOR", "opp": "MTL",
                     "market": "points", "line": 0.5, "lastSeason": 31, "drought": 6, "price": -150,
                     "book": "DraftKings", "heavyJuice": False, "actual": 2, "result": "win"}
    bravo = next(r for r in by_night[D0]["dueList"]["rows"] if r["player"] == "Bravo Goals")
    assert (bravo["team"], bravo["opp"], bravo["actual"], bravo["result"]) == ("MTL", "TOR", 0, "loss")


def test_old_nights_are_kept_with_their_tallies_and_read_back(tmp_path: Path, monkeypatch) -> None:
    _, out, board, _, _ = three_nights(tmp_path, monkeypatch)

    kept = out / "history" / "settled"
    assert sorted(p.name for p in kept.glob("*.json")) == [f"{D0.isoformat()}.json", f"{D1.isoformat()}.json"]
    first = json.loads((kept / f"{D0.isoformat()}.json").read_text(encoding="utf-8"))
    assert first["dueList"]["w"] == 2 and first["dueList"]["l"] == 1 and first["dueList"]["pending"] == 0
    assert first["dueList"]["impliedCount"] == 2, "Alpha and Bravo were priced; Charlie was not"

    module = site_module()

    def unreachable(_day):
        raise OSError("schedule unreachable")

    monkeypatch.setattr(module, "schedule_for", unreachable)
    yesterday = {"resultsDate": D3.isoformat(), "games": [], "summary": {}}
    # D2 is yesterday's-yesterday on D4 and was never kept (its night held the
    # unfinished game), so it is asked for again and is missing without the
    # network; D0 and D1 are read from what was kept.
    season = module.season_record(D3 + timedelta(days=1), out / "history", yesterday)
    assert season["missingNights"] == 1
    assert season["dueList"] == {"w": 3, "l": 2, "p": 0, "nights": 2,
                                 "byMarket": {"points": {"w": 1, "l": 1}, "goals": {"w": 0, "l": 1}, "assists": {"w": 2, "l": 0}},
                                 "impliedPct": round(100 * sum(_implied(p) for p in (-150, 140, -200, 120)) / 4, 1)}
    assert board["record"]["dueList"]["nights"] == 3, "the live build, with the network, counted all three"


def test_a_final_game_whose_box_score_has_not_reached_the_logs_waits_rather_than_voiding(
        tmp_path: Path, monkeypatch) -> None:
    """No row for a player in a game the logs hold is a scratch. No row for
    the GAME is a box score that has not arrived: every entry is null, the
    night is not kept, and the next build that holds it grades it."""
    lab = make_due_list_lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    write_list(lab, LISTS[D0], day=D0)
    build_night(lab, out, monkeypatch, D0)
    assert not (lab / "data" / "processed" / "player_game_logs.csv").exists()

    board, results = build_night(lab, out, monkeypatch, D1)
    assert [(r["actual"], r["result"]) for r in results["dueList"]["rows"]] == [(None, None)] * 4
    assert "void" not in {r["result"] for r in results["dueList"]["rows"]}
    assert results["dueList"]["summary"] == {"w": 0, "l": 0, "p": 0}
    assert board["record"]["dueList"] == {"w": 0, "l": 0, "p": 0, "nights": 1}, "the night settled; nothing on the list has"

    build_night(lab, out, monkeypatch, D2)
    assert not (out / "history" / "settled" / f"{D0.isoformat()}.json").exists(), "a night still waiting is not kept"

    write_logs(lab, LOGS)
    board, _ = build_night(lab, out, monkeypatch, D3)
    # D1 and D2 carried the list too (empty: nobody qualified) and settled,
    # so the record spans three nights; the grades are D0's alone.
    assert board["record"]["dueList"] == {"w": 2, "l": 1, "p": 0, "nights": 3}
    kept = json.loads((out / "history" / "settled" / f"{D0.isoformat()}.json").read_text(encoding="utf-8"))
    assert kept["dueList"]["w"] == 2 and kept["dueList"]["pending"] == 0
