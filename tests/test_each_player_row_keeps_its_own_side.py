"""A player row could take the other club's team, opponent and venue, and no
test would have seen it.

`tests/conftest.py`'s `boxscore_payload` handed ONE stats dict to both
`homeTeam` and `awayTeam`, so the same two players played for Toronto and for
New Jersey at once — a shape `api-web.nhle.com` never returns (0 of the 3,936
cached final games list a player on both sides). With the two blocks
identical, reading the wrong side's block builds exactly the right rows, so
`build_datasets` reading the away block for the home side and the home block
for the away side left the whole suite green: 1,768 passed at the audit's
commit and 1,842 at this one. Found by the failure-shape audit (finding 64,
confirmed 3/3). Seven other edits were just as invisible, 1,842 passed each:
trading the team and opponent labels, trading only the venue label, trading
every label, writing a player's own club as his opponent, reading the home
block for both clubs, reading the away block for both, and the team row's
away shots read from the home club. The old fixture's `defense` list was
empty as well, so a build that never read the defense group was green too;
the defensemen below are filed under `defense`.

The production code is right today: rebuilt from 999 real 2023-24 boxscores
it matches `data/processed/player_game_logs.csv` on team and venue in all
39,952 rows. What the gap would have hidden, measured by the refuters on that
same season: under the swap all 39,952 rows take the other club's team,
opponent and venue; the fitted home shots-on-goal venue factor inverts
(1.0197 -> 0.9803); 0 of 974 fitted skaters keep their team; and McDavid's
expected shots against San Jose at home fall from 3.510 to 2.759 — priced onto
the card and into every props backtest without an error anywhere.

What these tests hold, on a boxscore whose two clubs have their own players
and whose lines add up to the team totals:

* each player's row carries the club whose block lists him, the other club as
  opponent, that club's venue, and his own stat line — once;
* each club's skater goals and shots add up to its own score and shots;
* each goalie's shots and goals against are the other club's shots and goals;
* every row's team, opponent and venue agree with the game's team row;
* the shared fixture gives each club its own players, so a test built on it
  can tell the two sides apart.

The reconciliations are real properties of the feed, measured read-only on
the cache: skater shots add up to the club's shots in 7,842 of 7,872
team-games, regulation skater goals to the club's score in 6,130 of 6,134,
and a lone goalie's shots against equal the other club's shots in 6,168 of
7,422 (1,250 of the other 1,254 differ by exactly the empty-net goals, which
no goalie faced). The boxscore below is the common case: regulation, one
goalie a side for sixty minutes, no empty net.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from conftest import boxscore_payload
from nhl_betting_lab.data import build_datasets as builder


GAME = 2024020001


def _skater(player_id: int, name: str, position: str, *, goals: int,
            assists: int, sog: int, blocked: int, hits: int, ppg: int,
            toi: str) -> dict:
    return {
        "playerId": player_id, "name": {"default": name}, "position": position,
        "goals": goals, "assists": assists, "points": goals + assists,
        "sog": sog, "blockedShots": blocked, "hits": hits,
        "powerPlayGoals": ppg, "toi": toi,
    }


def _goalie(player_id: int, name: str, *, saves: int, shots: int) -> dict:
    return {
        "playerId": player_id, "name": {"default": name}, "position": "G",
        "saveShotsAgainst": f"{saves}/{shots}", "goalsAgainst": shots - saves,
        "toi": "60:00",
    }


#: Toronto 4, New Jersey 2 in regulation; Toronto outshoots New Jersey 14-9.
#: Every number differs between the clubs, so a row read from the wrong block
#: cannot land on a value it was meant to have.
TORONTO_SKATERS = [
    _skater(8478483, "M. Marner", "R", goals=1, assists=2, sog=4, blocked=1,
            hits=2, ppg=1, toi="21:30"),
    _skater(8479318, "A. Matthews", "C", goals=2, assists=1, sog=7, blocked=0,
            hits=1, ppg=0, toi="20:45"),
    _skater(8476853, "M. Rielly", "D", goals=1, assists=1, sog=3, blocked=2,
            hits=0, ppg=0, toi="24:10"),
]
NEW_JERSEY_SKATERS = [
    _skater(8480002, "N. Hischier", "C", goals=1, assists=0, sog=3, blocked=1,
            hits=3, ppg=0, toi="19:40"),
    _skater(8481559, "J. Hughes", "C", goals=1, assists=1, sog=5, blocked=0,
            hits=0, ppg=1, toi="20:05"),
    _skater(8476462, "D. Hamilton", "D", goals=0, assists=1, sog=1, blocked=3,
            hits=1, ppg=0, toi="23:30"),
]
#: Each goalie faced the OTHER club's shots and let in its goals.
TORONTO_GOALIE = _goalie(8476932, "A. Stolarz", saves=7, shots=9)
NEW_JERSEY_GOALIE = _goalie(8474593, "J. Markstrom", saves=10, shots=14)

#: Written out by hand, not derived from the blocks above: player id ->
#: (team, opponent, venue, role, shots on goal, goals, saves, shots against).
EXPECTED = {
    8478483: ("TOR", "NJD", "home", "skater", 4, 1, 0, 0),
    8479318: ("TOR", "NJD", "home", "skater", 7, 2, 0, 0),
    8476853: ("TOR", "NJD", "home", "skater", 3, 1, 0, 0),
    8476932: ("TOR", "NJD", "home", "goalie", 0, 0, 7, 9),
    8480002: ("NJD", "TOR", "away", "skater", 3, 1, 0, 0),
    8481559: ("NJD", "TOR", "away", "skater", 5, 1, 0, 0),
    8476462: ("NJD", "TOR", "away", "skater", 1, 0, 0, 0),
    8474593: ("NJD", "TOR", "away", "goalie", 0, 0, 10, 14),
}


def _build(tmp_path: Path, payload: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    directory = tmp_path / "nhl" / "boxscore"
    directory.mkdir(parents=True)
    (directory / f"{payload['id']}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    players, teams, result = builder.build_datasets(
        raw_dir=tmp_path, processed_dir=tmp_path / "processed", write=False
    )
    assert result.games_used == 1
    return players, teams


def _toronto_hosts_new_jersey(tmp_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _build(
        tmp_path,
        boxscore_payload(
            game_id=GAME, game_state="OFF", home="TOR", away="NJD",
            home_score=4, away_score=2, home_shots=14, away_shots=9, period=3,
            home_skaters=TORONTO_SKATERS, away_skaters=NEW_JERSEY_SKATERS,
            home_goalies=[TORONTO_GOALIE], away_goalies=[NEW_JERSEY_GOALIE],
        ),
    )


def test_each_player_row_carries_the_club_whose_block_lists_him(
    tmp_path: Path,
) -> None:
    players, _ = _toronto_hosts_new_jersey(tmp_path)

    got = {
        int(row.player_id): (
            row.team, row.opponent, row.venue, row.role,
            int(row.shots_on_goal), int(row.goals), int(row.saves),
            int(row.shots_against),
        )
        for row in players.itertuples()
    }

    assert len(players) == len(EXPECTED), "a player appears twice or not at all"
    assert got == EXPECTED


def test_each_clubs_skaters_add_up_to_its_own_score_and_shots(
    tmp_path: Path,
) -> None:
    players, teams = _toronto_hosts_new_jersey(tmp_path)
    game = teams.iloc[0]
    skaters = players[players["role"] == "skater"]
    by_club = skaters.groupby("team")[["goals", "shots_on_goal"]].sum()

    assert sorted(by_club.index) == ["NJD", "TOR"]
    assert by_club.loc[game["home_team"]].tolist() == [
        game["home_goals"], game["home_shots"]
    ]
    assert by_club.loc[game["away_team"]].tolist() == [
        game["away_goals"], game["away_shots"]
    ]
    # Pinned as literals too, so a mistake made the same way on both tables
    # cannot reconcile with itself.
    assert by_club.loc["TOR"].tolist() == [4, 14]
    assert by_club.loc["NJD"].tolist() == [2, 9]
    assert [game["home_team"], game["home_goals"], game["home_shots"]] == ["TOR", 4, 14]
    assert [game["away_team"], game["away_goals"], game["away_shots"]] == ["NJD", 2, 9]


def test_each_goalie_faced_the_other_clubs_shots_and_goals(tmp_path: Path) -> None:
    players, teams = _toronto_hosts_new_jersey(tmp_path)
    game = teams.iloc[0]
    shots = {game["home_team"]: game["home_shots"], game["away_team"]: game["away_shots"]}
    goals = {game["home_team"]: game["home_goals"], game["away_team"]: game["away_goals"]}
    goalies = players[players["role"] == "goalie"]

    assert sorted(goalies["team"]) == ["NJD", "TOR"]
    for row in goalies.itertuples():
        assert row.opponent in shots and row.opponent != row.team, row.player_id
        assert (row.shots_against, row.goals_against) == (
            shots[row.opponent], goals[row.opponent]
        ), row.player_id


def test_every_rows_team_opponent_and_venue_agree_with_the_team_row(
    tmp_path: Path,
) -> None:
    players, teams = _toronto_hosts_new_jersey(tmp_path)
    game = teams.iloc[0]
    sides = {
        "home": (game["home_team"], game["away_team"]),
        "away": (game["away_team"], game["home_team"]),
    }

    assert set(players["venue"]) == {"home", "away"}
    for row in players.itertuples():
        assert (row.team, row.opponent) == sides[row.venue], row.player_id


def test_the_shared_boxscore_fixture_gives_each_club_its_own_players(
    tmp_path: Path,
) -> None:
    """The root of the gap: a default in which both clubs are the same
    players makes every test built on it blind to which side a row is from."""
    payload = boxscore_payload(game_state="OFF")
    blocks = payload["playerByGameStats"]
    listed = {
        side: {
            player["playerId"]
            for group in ("forwards", "defense", "goalies")
            for player in blocks[side][group]
        }
        for side in ("homeTeam", "awayTeam")
    }

    assert listed["homeTeam"] and listed["awayTeam"]
    assert not listed["homeTeam"] & listed["awayTeam"]

    players, _ = _build(tmp_path, payload)
    on_club = players.groupby("team")["player_id"].apply(set).to_dict()

    assert on_club == {"TOR": listed["homeTeam"], "NJD": listed["awayTeam"]}
    assert len(players) == len(listed["homeTeam"]) + len(listed["awayTeam"])
