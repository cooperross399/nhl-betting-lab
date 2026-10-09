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

The wait is by the entry's own result, not by its game's place in the team
tally, and it is bounded. Until 2026-10-07 `pending` counted only entries on
a game in results["games"]: a game not final two mornings on, or any entry on
a schedule-only board (which settles no team game), held nothing, so the
night was kept with the entry unread and read back that way all season; a
night kept by main before the list was graded (no `dueList` in the cache) was
read back the same way; and an entry that could never grade held its night
out of the cache for good, so one schedule outage dropped the night's team
record too. The tests from `test_a_game_not_final_for_two_days...` on hold
each of those: the night is settled again until the entry reads, a kept night
without the list is settled again once, and after DUE_LIST_PATIENCE_DAYS (the
forward ledger's patience) the night is kept with the entry uncounted.
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


def nightly_schedule(build_day: date, *, not_final: tuple[str, ...] = (), unreachable: tuple[date, ...] = ()):
    """The NHL schedule for NIGHTS: SLATE every night, final once the night is before `build_day`.

    A day in `unreachable` cannot be fetched (an outage): its request raises.
    """

    def schedule_for(day: date) -> list[dict]:
        if day in unreachable:
            raise OSError(f"schedule unreachable for {day}")
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
                unreachable: tuple[date, ...] = (), module=None) -> tuple[dict, dict]:
    """main() for `day`, as Publish Site runs it: the board for `day`, the results for the night before."""
    module = module or site_module()
    monkeypatch.setattr(module, "schedule_for", nightly_schedule(day, not_final=not_final, unreachable=unreachable))
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


#: The notional 0.25u track's keys on a season record (Cooper, 2026-10-09).
TRACKING_KEYS = {"stake", "units", "staked", "returnPct", "source"}


def _count(record: dict) -> dict:
    """A Due List record's count, without the notional 0.25u track beside it."""
    return {k: record[k] for k in ("w", "l", "p", "nights")}


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

    count = {k: board["record"]["dueList"][k] for k in ("w", "l", "p", "nights")}
    assert count == {"w": 4, "l": 2, "p": 0, "nights": 3}
    season = results["dueList"]["season"]
    assert season["byMarket"] == {"points": {"w": 1, "l": 1}, "goals": {"w": 1, "l": 1}, "assists": {"w": 2, "l": 0}}
    assert {k: season[k] for k in ("w", "l", "p", "nights")} == count
    assert results["seasonRecord"]["dueList"] == season
    # The record on the board is the page's own keys: the count and the
    # notional 0.25u track (Cooper, 2026-10-09), no category split.
    assert set(board["record"]["dueList"]) == {"w", "l", "p", "nights", "stake", "units", "staked"}
    assert board["record"]["dueList"]["stake"] == 0.25
    assert {k: season[k] for k in ("units", "staked")} == {k: board["record"]["dueList"][k] for k in ("units", "staked")}
    assert set(season) == {"w", "l", "p", "nights", "impliedPct", "byMarket"} | TRACKING_KEYS


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
    _, out, _, _, by_night = three_nights(tmp_path, monkeypatch)

    # The row is the FROZEN board's entry, every field as published (the tier
    # bars, rarity and cell record included), plus the game and its grade.
    frozen = json.loads((out / "history" / f"{D0.isoformat()}.json").read_text(encoding="utf-8"))
    published = next(e for g in frozen["games"] for e in (g.get("drought") or []) if e["player"] == "Alpha Points")
    alpha = next(r for r in by_night[D0]["dueList"]["rows"] if r["player"] == "Alpha Points")
    assert set(alpha) == SCHEMA_KEYS | {"gameId", "opp", "actual", "result", "units"}
    # -150 won at the notional 0.25u (Cooper, 2026-10-09): 0.25 x 100/150.
    assert alpha == {**published, "gameId": TOR_GAME[D0], "opp": "MTL", "actual": 2, "result": "win", "units": 0.1667}
    assert (published["playerId"], published["team"], published["market"], published["price"], published["book"]) == (1, "TOR", "points", -150, "DraftKings")
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
    assert {k: v for k, v in season["dueList"].items() if k not in TRACKING_KEYS} == {"w": 3, "l": 2, "p": 0, "nights": 2,
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
    assert _count(board["record"]["dueList"]) == {"w": 0, "l": 0, "p": 0, "nights": 1}, "the night settled; nothing on the list has"

    build_night(lab, out, monkeypatch, D2)
    assert not (out / "history" / "settled" / f"{D0.isoformat()}.json").exists(), "a night still waiting is not kept"

    write_logs(lab, LOGS)
    board, _ = build_night(lab, out, monkeypatch, D3)
    # D1 and D2 carried the list too (empty: nobody qualified) and settled,
    # so the record spans three nights; the grades are D0's alone.
    assert _count(board["record"]["dueList"]) == {"w": 2, "l": 1, "p": 0, "nights": 3}
    kept = json.loads((out / "history" / "settled" / f"{D0.isoformat()}.json").read_text(encoding="utf-8"))
    assert kept["dueList"]["w"] == 2 and kept["dueList"]["pending"] == 0


# -- the wait is by the entry, and bounded -----------------------------------

#: One priced entry on each game of the slate: Alpha on TOR's, Hotel on NYI's.
TWO_PLAYER_LIST = [
    row("TOR", "MTL", player="Alpha Points", player_id=1, market="points", american_odds=-150.0),
    row("NYI", "BOS", player="Hotel Points", player_id=8, market="points", american_odds=-110.0),
]

#: Both dressed and scored: Alpha a goal and an assist, Hotel three of each.
TWO_PLAYER_LOGS = [(TOR_GAME[D0], 1, "Alpha Points", "TOR", 1, 1), (NYI_GAME[D0], 8, "Hotel Points", "NYI", 3, 3)]


def _kept(out: Path, day: date) -> dict | None:
    path = out / "history" / "settled" / f"{day.isoformat()}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def test_a_game_not_final_for_two_days_is_graded_once_it_is_final(tmp_path: Path, monkeypatch) -> None:
    """NYI's game is not final on the next two mornings; the night waits for
    Hotel and grades him the morning it is, rather than keeping the night
    with him unread the moment the other game settled."""
    lab = make_due_list_lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    write_logs(lab, TWO_PLAYER_LOGS)
    write_list(lab, TWO_PLAYER_LIST, day=D0)
    build_night(lab, out, monkeypatch, D0)

    board, results = build_night(lab, out, monkeypatch, D1, not_final=(NYI_GAME[D0],))
    graded = {r["player"]: (r["actual"], r["result"]) for r in results["dueList"]["rows"]}
    assert graded == {"Alpha Points": (2, "win"), "Hotel Points": (None, None)}
    assert _count(board["record"]["dueList"]) == {"w": 1, "l": 0, "p": 0, "nights": 1}, "TOR's game settled; Hotel waits"

    build_night(lab, out, monkeypatch, D2, not_final=(NYI_GAME[D0],))
    assert _kept(out, D0) is None, "a night with an entry on a game not yet final is not kept"

    board, results = build_night(lab, out, monkeypatch, D3)
    assert _count(board["record"]["dueList"]) == {"w": 2, "l": 0, "p": 0, "nights": 3}, "Hotel's six points were graded"
    assert results["seasonRecord"]["dueList"]["impliedPct"] == round(100 * (_implied(-150) + _implied(-110)) / 2, 1)
    kept = _kept(out, D0)
    assert kept["dueList"]["w"] == 2 and kept["dueList"]["pending"] == 0 and kept["dueList"]["impliedCount"] == 2
    assert kept["games"] == 2, "both team games are in the kept night"


def test_a_night_with_no_final_at_all_waits_and_keeps_its_team_record(tmp_path: Path, monkeypatch) -> None:
    """Neither game is final for two mornings. The night is not kept as
    0 games; when both final it counts its Due List and its team games."""
    lab = make_due_list_lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    write_logs(lab, TWO_PLAYER_LOGS)
    write_list(lab, TWO_PLAYER_LIST, day=D0)
    build_night(lab, out, monkeypatch, D0)

    board, results = build_night(lab, out, monkeypatch, D1, not_final=(TOR_GAME[D0], NYI_GAME[D0]))
    assert [(r["actual"], r["result"]) for r in results["dueList"]["rows"]] == [(None, None)] * 2
    assert results["games"] == [] and "dueList" not in board["record"], "nothing settled, nothing counted"

    build_night(lab, out, monkeypatch, D2, not_final=(TOR_GAME[D0], NYI_GAME[D0]))
    assert _kept(out, D0) is None, "a night with nothing final is not kept with 0 games"

    board, results = build_night(lab, out, monkeypatch, D3)
    assert _count(board["record"]["dueList"]) == {"w": 2, "l": 0, "p": 0, "nights": 3}
    season = results["seasonRecord"]
    assert season["nights"] == 3 and season["missingNights"] == 0
    assert season["straightUp"]["w"] + season["straightUp"]["l"] == 3 * len(SLATE), "D0's team games count too"
    assert _kept(out, D0)["games"] == len(SLATE)


def test_a_schedule_only_board_that_carried_the_list_waits_for_the_logs_too(tmp_path: Path, monkeypatch) -> None:
    """A board frozen without the model (the model's game history did not
    reach the run) grades no team game, so results["games"] is empty every
    morning; the list it carried still waits for the box scores and is
    graded when they arrive, as a board with the model is."""
    lab = make_lab(tmp_path, monkeypatch, staged=False, model=False)
    (lab / "data" / "outputs" / "gameday_card.json").unlink()
    out = tmp_path / "out"
    write_list(lab, TWO_PLAYER_LIST, day=D0)
    board, _ = build_night(lab, out, monkeypatch, D0)
    assert not any("projGoals" in g["home"] for g in board["games"]), "a schedule-only board"
    assert [len(g["drought"]) for g in board["games"]] == [1, 1], "that carried the list"

    board, results = build_night(lab, out, monkeypatch, D1)
    assert results["games"] == [] and "dueList" in results
    assert [(r["actual"], r["result"]) for r in results["dueList"]["rows"]] == [(None, None)] * 2
    assert "dueList" not in board["record"]

    build_night(lab, out, monkeypatch, D2)
    assert _kept(out, D0) is None, "no team game settled, and the entries are unread: the night waits"

    write_logs(lab, TWO_PLAYER_LOGS)
    board, results = build_night(lab, out, monkeypatch, D3)
    assert _count(board["record"]["dueList"]) == {"w": 2, "l": 0, "p": 0, "nights": 1}
    assert results["seasonRecord"]["dueList"]["byMarket"]["points"] == {"w": 2, "l": 0}
    kept = _kept(out, D0)
    assert kept["games"] == 0 and kept["dueList"]["w"] == 2 and kept["dueList"]["pending"] == 0


def test_a_night_kept_before_the_list_was_graded_is_settled_again(tmp_path: Path, monkeypatch) -> None:
    """main's season_record kept `{resultsDate, games, summary}` and nothing
    else. A night it kept whose frozen board carries the list is settled
    again, once, and the cache rewritten with the list's tallies."""
    lab = make_due_list_lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    write_logs(lab, [(TOR_GAME[D0], 1, "Alpha Points", "TOR", 1, 1), (TOR_GAME[D1], 5, "Echo Points", "TOR", 0, 0)])
    write_list(lab, [row("TOR", "MTL", player="Alpha Points", player_id=1, market="points", american_odds=-150.0)], day=D0)
    build_night(lab, out, monkeypatch, D0)
    write_list(lab, [row("TOR", "MTL", player="Echo Points", player_id=5, market="points", american_odds=-200.0)], day=D1)
    board, results = build_night(lab, out, monkeypatch, D1)
    assert _count(board["record"]["dueList"]) == {"w": 1, "l": 0, "p": 0, "nights": 1}

    kept_dir = out / "history" / "settled"
    kept_dir.mkdir(parents=True)
    old_shape = {"resultsDate": D0.isoformat(), "games": len(results["games"]), "summary": results["summary"]}
    (kept_dir / f"{D0.isoformat()}.json").write_text(json.dumps(old_shape), encoding="utf-8")

    board, results = build_night(lab, out, monkeypatch, D2)
    assert _count(board["record"]["dueList"]) == {"w": 1, "l": 1, "p": 0, "nights": 2}, "D0's win is back in the record"
    kept = _kept(out, D0)
    assert kept["dueList"]["w"] == 1 and kept["dueList"]["pending"] == 0
    assert kept["games"] == old_shape["games"] and kept["summary"] == old_shape["summary"], "the team record is as it was"

    # Settled again once: the next run reads the rewritten cache without the network.
    board, results = build_night(lab, out, monkeypatch, D3, unreachable=(D0,))
    assert results["seasonRecord"]["missingNights"] == 0
    assert _count(board["record"]["dueList"]) == {"w": 1, "l": 1, "p": 0, "nights": 3}


def test_a_night_kept_for_a_board_without_the_list_is_read_as_kept(tmp_path: Path, monkeypatch) -> None:
    """A board frozen before #307 carries no `drought`; its night, kept in
    main's shape, has nothing to grade and is read back, never re-fetched."""
    lab = make_due_list_lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    build_night(lab, out, monkeypatch, D0)
    frozen = out / "history" / f"{D0.isoformat()}.json"
    payload = json.loads(frozen.read_text(encoding="utf-8"))
    for g in payload["games"]:
        del g["drought"]
    frozen.write_text(json.dumps(payload), encoding="utf-8")
    _, results = build_night(lab, out, monkeypatch, D1)
    assert "dueList" not in results
    kept_dir = out / "history" / "settled"
    kept_dir.mkdir(parents=True)
    old_shape = {"resultsDate": D0.isoformat(), "games": len(results["games"]), "summary": results["summary"]}
    (kept_dir / f"{D0.isoformat()}.json").write_text(json.dumps(old_shape), encoding="utf-8")

    board, results = build_night(lab, out, monkeypatch, D2, unreachable=(D0,))
    assert results["seasonRecord"]["missingNights"] == 0, "read from what was kept"
    assert results["seasonRecord"]["straightUp"]["w"] + results["seasonRecord"]["straightUp"]["l"] == 2 * len(SLATE)
    # D1's board carried the list (empty); D0's carried none, so it is one night of it, not two.
    assert _count(board["record"]["dueList"]) == {"w": 0, "l": 0, "p": 0, "nights": 1}
    assert _kept(out, D0) == old_shape


def test_an_entry_that_never_grades_holds_its_night_no_longer_than_the_patience_window(
        tmp_path: Path, monkeypatch) -> None:
    """NYI's game is final and its box score never reaches the logs (a game
    build_datasets dropped). The night is settled again each run through the
    live schedule, so an outage drops it; after DUE_LIST_PATIENCE_DAYS it is
    kept with Hotel uncounted, and read back without the network."""
    from nhl_betting_lab.forward_evidence import PATIENCE_DAYS

    module = site_module()
    lab = make_due_list_lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    write_logs(lab, TWO_PLAYER_LOGS[:1])
    write_list(lab, TWO_PLAYER_LIST, day=D0)
    for day in (D0, D1, D2, D3):
        board, results = build_night(lab, out, monkeypatch, day)
    assert _count(board["record"]["dueList"]) == {"w": 1, "l": 0, "p": 0, "nights": 3}
    assert _kept(out, D0) is None, "Hotel is unread, so the night waits"
    processed = lab / "data" / "processed"

    def record_on(today: date, *, outage: bool = False) -> dict:
        monkeypatch.setattr(module, "schedule_for", nightly_schedule(today, unreachable=(D0,) if outage else ()))
        yesterday = {"resultsDate": (today - timedelta(days=1)).isoformat(), "games": [], "summary": {}}
        return module.season_record(today, out / "history", yesterday, processed=processed)

    last_day_waiting = D0 + timedelta(days=PATIENCE_DAYS - 1)
    assert record_on(last_day_waiting)["dueList"]["w"] == 1
    assert _kept(out, D0) is None, "still waiting the day before the window closes"
    season = record_on(last_day_waiting, outage=True)
    # D1 and D2 carried the list too (empty: nobody qualified) and count as
    # nights of it; D0, held out and unreachable, is this run's missing night.
    assert season["missingNights"] == 1 and season["nights"] == 2, "held out, the night needs the schedule"
    assert {k: season["dueList"][k] for k in ("w", "l", "p", "nights")} == {"w": 0, "l": 0, "p": 0, "nights": 2}

    season = record_on(D0 + timedelta(days=PATIENCE_DAYS))
    assert season["missingNights"] == 0
    assert {k: season["dueList"][k] for k in ("w", "l", "p", "nights")} == {"w": 1, "l": 0, "p": 0, "nights": 3}
    kept = _kept(out, D0)
    assert kept is not None, "kept once the window closes"
    assert kept["dueList"]["pending"] == 1 and kept["dueList"]["w"] == 1, "kept, Hotel uncounted and still unread"
    assert kept["games"] == len(SLATE)

    season = record_on(D0 + timedelta(days=PATIENCE_DAYS + 1), outage=True)
    assert season["missingNights"] == 0, "read from what was kept"
    assert season["nights"] == 3 and season["straightUp"] == {"w": 3, "l": 3}
    assert {k: season["dueList"][k] for k in ("w", "l", "p", "nights")} == {"w": 1, "l": 0, "p": 0, "nights": 3}
    assert module.DUE_LIST_PATIENCE_DAYS == PATIENCE_DAYS == 14, "the forward ledger's rule, and the one tested above"


def test_a_kept_night_that_cannot_be_read_is_settled_again(tmp_path: Path, monkeypatch) -> None:
    """A half-written cache (a run killed mid-write) is settled again and
    rewritten, not a crash on every later publish."""
    lab = make_due_list_lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    write_logs(lab, TWO_PLAYER_LOGS)
    write_list(lab, TWO_PLAYER_LIST, day=D0)
    build_night(lab, out, monkeypatch, D0)
    build_night(lab, out, monkeypatch, D1)
    kept_dir = out / "history" / "settled"
    kept_dir.mkdir(parents=True)
    (kept_dir / f"{D0.isoformat()}.json").write_text('{"resultsDate": "', encoding="utf-8")

    board, results = build_night(lab, out, monkeypatch, D2)
    assert results["seasonRecord"]["missingNights"] == 0
    assert _count(board["record"]["dueList"]) == {"w": 2, "l": 0, "p": 0, "nights": 2}
    assert _kept(out, D0)["dueList"]["w"] == 2, "rewritten whole"
