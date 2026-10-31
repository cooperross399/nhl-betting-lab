"""The Due List's round two (Cooper, 2026-10-31: "yes do all that except 4").

Each row gets tonight's posted line and power-play unit and how they moved, the
goalie he faces, and a player his club's posted lines leave out is taken off
the list and named. Every Monday the card carries the list's scorecard.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.data.starting_goalies import COLUMNS as GOALIE_COLUMNS, FILENAME as GOALIE_FILE
from nhl_betting_lab.drought_forward import (
    LEDGER_COLUMNS, LIST_COLUMNS, build_scorecard, record_list, render_scorecard, scorecard_week,
)
from nhl_betting_lab.due_context import CONTEXT_FIELDS, annotate, goalie_text, line_move, line_text
from nhl_betting_lab.lineups import LINES_DIRNAME, RATINGS_FILE
from nhl_betting_lab.reports.gameday_card import GamedayCard, render_drought_section

DAY = "2026-11-02"
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)
TEAM_NAMES = {"toronto maple leafs": "TOR", "montreal canadiens": "MTL"}


def skaters(team: str, named: dict[str, str], pp: dict[str, str] | None = None, *, filler: int = 16,
            retrieved_at: str = "2026-11-02T14:00:00+00:00", status: dict[str, str] | None = None) -> list[dict]:
    rows = []
    for i in range(filler):
        rows.append({"team_abbreviation": team, "player": f"Filler {team} {i}", "group_identifier": f"f{i % 4 + 1}"})
    for name, group in named.items():
        rows.append({"team_abbreviation": team, "player": name, "group_identifier": group,
                     "injury_status": (status or {}).get(name, "")})
    for name, group in (pp or {}).items():
        rows.append({"team_abbreviation": team, "player": name, "group_identifier": group})
    for r in rows:
        r.setdefault("injury_status", "")
        r["game_time_decision"] = "False"
        r["retrieved_at"] = retrieved_at
    return rows


def write_lines(processed: Path, day: str, rows: list[dict]) -> None:
    directory = processed / LINES_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(directory / f"{day}.csv", index=False)


def write_goalies(processed: Path, listings: list[tuple[str, str, str]]) -> None:
    rows = [{"date": DAY, "starts_at": "", "team": team, "opponent": "", "side": "", "goalie": goalie,
             "strength": strength, "news_at": "", "retrieved_at": "2026-11-02T14:30:00+00:00"}
            for team, goalie, strength in listings]
    pd.DataFrame(rows, columns=list(GOALIE_COLUMNS)).to_csv(processed / GOALIE_FILE, index=False)


def goalie_logs() -> pd.DataFrame:
    rows = []
    for i in range(12):
        rows.append({"role": "goalie", "team": "MTL", "player": "Sam Montembeault", "player_id": 31,
                     "date": f"2026-10-{i + 8:02d}", "toi_seconds": 3600})
    for i in range(4):
        rows.append({"role": "goalie", "team": "MTL", "player": "Jakub Dobes", "player_id": 32,
                     "date": f"2026-10-{i + 20:02d}", "toi_seconds": 3600})
    return pd.DataFrame(rows)


def listed(player: str, market: str = "goals", team: str = "TOR", opponent: str = "MTL", pid: int = 1) -> dict:
    return {"date": DAY, "home_team": team, "away_team": opponent, "team": team, "opponent": opponent,
            "player": player, "player_id": pid, "market": market, "selection": "over", "line": 0.5,
            "last_season": 40, "drought": 6, "american_odds": 150.0, "book": "FanDuel"}


def run(processed: Path, rows: list[dict], logs: pd.DataFrame | None = None):
    return annotate(rows, processed=processed, day=DAY, now=NOW, logs=goalie_logs() if logs is None else logs,
                    team_names=TEAM_NAMES)


def test_a_player_his_clubs_posted_lines_leave_out_is_taken_off_and_named(tmp_path) -> None:
    write_lines(tmp_path, DAY, skaters("TOR", {"Auston Matthews": "f1"}))
    kept, removed = run(tmp_path, [listed("Auston Matthews"), listed("William Nylander", pid=2)])

    assert [r["player"] for r in kept] == ["Auston Matthews"]
    assert removed == ["William Nylander (TOR, goals): not in TOR's posted lines tonight, so not listed."]


def test_a_club_with_no_lines_posted_keeps_every_row_with_null_context(tmp_path) -> None:
    write_lines(tmp_path, DAY, skaters("TOR", {"Auston Matthews": "f1"}, filler=5))  # too few to count as posted
    kept, removed = run(tmp_path, [listed("William Nylander")], logs=pd.DataFrame())

    assert removed == [] and len(kept) == 1
    assert all(kept[0][k] is None for k in CONTEXT_FIELDS) and kept[0]["line"] == 0.5


def test_the_line_and_unit_tonight_and_how_they_moved_since_the_last_capture(tmp_path) -> None:
    write_lines(tmp_path, "2026-10-30", skaters("TOR", {"Matthew Knies": "f2", "Max Domi": "f2"},
                                                {"Matthew Knies": "pp2", "Max Domi": "pp1"}))
    write_lines(tmp_path, "2026-10-31", skaters("MTL", {"Someone Else": "f1"}))  # not his club: skipped
    write_lines(tmp_path, DAY, skaters("TOR", {"Matthew Knies": "f1", "Max Domi": "f3"},
                                       {"Matthew Knies": "pp1"}, status={"Max Domi": "day-to-day"}))
    kept, _ = run(tmp_path, [listed("Matthew Knies"), listed("Max Domi", pid=2)])
    knies, domi = kept

    assert knies["line"] == 0.5, "the prop's own line is untouched"
    assert (knies["line_tonight"], knies["pp_tonight"], knies["line_before"], knies["pp_before"], knies["line_move"]) == (
        "F1", "PP1", "F2", "PP2", "up")
    assert (domi["line_tonight"], domi["pp_tonight"], domi["line_move"], domi["status"]) == ("F3", None, "down", "day-to-day")
    assert line_text(knies) == "F1, PP1 (up from F2, PP2)"
    assert line_text(domi) == "F3 (down from F2, PP1); day-to-day"


def test_line_move_reads_line_and_unit_together() -> None:
    assert line_move("F1", "", "F2", "PP1") == "mixed"
    assert line_move("F2", "PP2", "F2", "PP2") == "same"
    assert line_move("D1", "PP2", "D1", "") == "up"
    assert line_move("F1", "PP1", None, None) is None


def test_the_goalie_faced_says_backup_and_his_record_against_expected(tmp_path) -> None:
    write_goalies(tmp_path, [("Montreal Canadiens", "Jakub Dobes", "Confirmed")])
    (tmp_path / RATINGS_FILE).write_text(json.dumps({"goalies": {"32": 1.061, "31": 0.95}, "unseen_goalie": 1.02}))
    kept, _ = run(tmp_path, [listed("Auston Matthews")])
    row = kept[0]

    assert (row["opp_goalie"], row["opp_goalie_status"], row["opp_goalie_backup"]) == ("Jakub Dobes", "Confirmed", True)
    assert row["opp_goalie_vs_expected"] == 0.061
    assert goalie_text(row) == "backup Jakub Dobes (Confirmed), +6% goals vs expected"


def test_the_number_one_is_not_a_backup_and_no_ratings_file_says_nothing_of_his_record(tmp_path) -> None:
    write_goalies(tmp_path, [("Montreal Canadiens", "Sam Montembeault", "Likely")])
    row = run(tmp_path, [listed("Auston Matthews")])[0][0]

    assert row["opp_goalie_backup"] is False and row["opp_goalie_vs_expected"] is None
    assert goalie_text(row) == "Sam Montembeault (Likely)"


def test_a_stale_goalie_listing_names_nobody(tmp_path) -> None:
    write_goalies(tmp_path, [("Montreal Canadiens", "Jakub Dobes", "Confirmed")])
    late = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    row = annotate([listed("Auston Matthews")], processed=tmp_path, day=DAY, now=late, logs=goalie_logs(),
                   team_names=TEAM_NAMES)[0][0]
    assert row["opp_goalie"] is None and goalie_text(row) == "-"


# -- the Monday scorecard ----------------------------------------------------

def ledger_row(day: str, market: str, outcome: str, odds: float | None, profit: float, edge: float | None) -> dict:
    return {"date": day, "home_team": "TOR", "away_team": "MTL", "market": market, "american_odds": odds,
            "outcome": outcome, "profit_units": profit, "model_edge": edge}


def test_the_week_is_the_last_full_sunday_to_saturday() -> None:
    assert scorecard_week("2026-11-02") == ("2026-10-25", "2026-10-31")
    assert scorecard_week("2026-10-31") == ("2026-10-18", "2026-10-24")


def test_the_scorecard_counts_the_week_and_the_season_at_a_quarter_unit() -> None:
    ledger = pd.DataFrame([
        ledger_row("2026-10-25", "goals", "won", 200.0, 2.0, 0.05),
        ledger_row("2026-10-31", "assists", "lost", 150.0, -1.0, -0.02),
        ledger_row("2026-10-31", "points", "won", None, 0.0, None),   # not posted: a hit, not a wager
        ledger_row("2026-10-20", "goals", "lost", 120.0, -1.0, None),  # season only
        ledger_row("2026-11-01", "goals", "won", 110.0, 1.1, 0.01),    # this week, not last
    ])
    card = build_scorecard(ledger, "2026-11-02")
    week, season = card["slices"]["week"], card["slices"]["season"]

    assert week["overall"] == {"listed": 3, "graded": 3, "hits": 2, "wagers": 2, "units": 0.25}
    assert week["categories"]["goals"]["units"] == 0.5 and week["categories"]["points"]["units"] is None
    assert week["model_agreed"]["units"] == 0.5 and week["model_disagreed"]["units"] == -0.25
    assert season["overall"]["listed"] == 5 and season["overall"]["units"] == round((2 - 1 - 1 + 1.1) * 0.25, 2)
    text = "\n".join(render_scorecard(card))
    assert "## Due List scorecard, Sun Oct 25 to Sat Oct 31" in text
    assert "| all | 3 | 2/3 (67%) | +0.25u over 2 |" in text


def test_the_card_carries_the_scorecard_and_the_new_columns() -> None:
    card = GamedayCard(generated_at="2026-11-02T14:40:00+00:00", drought_built=True, drought_headline="h",
                       drought_rows=[{**listed("Matthew Knies"), "line_tonight": "F1", "pp_tonight": "PP1", "line_before": "F2",
                                      "pp_before": "PP2", "line_move": "up", "opp_goalie": "Jakub Dobes",
                                      "opp_goalie_status": "Confirmed", "opp_goalie_backup": True,
                                      "opp_goalie_vs_expected": 0.06}],
                       due_scorecard=["## Due List scorecard, Sun Oct 25 to Sat Oct 31", ""])
    text = "\n".join(render_drought_section(card))
    assert "| Line tonight | Goalie faced |" in text
    assert "| F1, PP1 (up from F2, PP2) | backup Jakub Dobes (Confirmed), +6% goals vs expected |" in text
    assert text.rstrip().endswith("## Due List scorecard, Sun Oct 25 to Sat Oct 31")


def test_an_old_list_file_without_the_model_columns_still_records_and_settles(tmp_path) -> None:
    directory = tmp_path / "drought_list"
    directory.mkdir()
    old_columns = [c for c in LIST_COLUMNS if c not in ("model_probability", "model_edge")]
    pd.DataFrame([{**listed("Auston Matthews"), "american_odds": None, "book": ""}], columns=old_columns).to_csv(
        directory / f"{DAY}.csv", index=False)
    message = record_list([{**listed("Auston Matthews"), "model_probability": 0.4, "model_edge": 0.02}], DAY,
                          processed_dir=tmp_path)
    frame = pd.read_csv(directory / f"{DAY}.csv")
    assert "row(s) recorded" in message and list(frame.columns) == list(LIST_COLUMNS)
    assert frame.loc[0, "american_odds"] == 150.0, "the price a row lacked is taken once, as before"
    assert "model_edge" in LEDGER_COLUMNS
