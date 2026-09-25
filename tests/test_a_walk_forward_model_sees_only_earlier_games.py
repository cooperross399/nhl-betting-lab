"""A walk-forward model sees only games dated before the window it prices.

Both walk-forwards state one rule: **a game is priced by a model fitted only
on games that finished before it started** (`backtest/walk_forward.py` for
props, `backtest/team_walk_forward.py` for team markets). Every held-out
number the lab has published rests on it: the 2.5M prop samples behind
`props_calibration.md`, the props backtest and both prop experiments, and the
team measurement's moneyline 954, puck line 1,117 and totals 1,216 bets.

The code obeys the rule today. The tests named for it could not tell if it
stopped. The failure-shape audit found that both
`tests/test_walk_forward.py::test_a_model_never_sees_the_game_it_prices` and
`tests/test_team_walk_forward.py::test_the_model_never_sees_the_game_it_prices`
count the games dated before the first priced sample and assert there are at
least 50. That is a property of the window-skip gate, not of the frame handed
to `fit`, and on top of that the props fixture gives every skater the same box
score in every game, so a leaky fit and an honest one price identically. With
the fit changed to see every game through the end of the window it prices
(`<= window_end`: mutant m12 for props, m13 for team) the whole suite passed,
1768 of 1768 when the audit ran it. Measured again before this file existed,
1842 of 1842 passed under each of eight leaks, four per walk-forward: m12 or
m13, a fit on every game, and a same-day leak (`<` changed to `<=` at the
window start) on the history line and on the fit line, the same-day leak
being exactly the case the code's own comment forbids. Measured on the real
data by the refuters, read-only: the props leak moved 100% of sample means
and improved every market's Brier score while the report still said
"held-out"; the team leak flipped all three team ROIs positive (moneyline
-6.6% to +3.0%, puck line -4.2% to +3.4%, totals -4.0% to +6.3%, with a raw
totals interval excluding zero). Nothing would have failed.

The old tests stay: they are what catches a leak that also moves the skip
gate (`history <= window_end`), the only leak the suite caught before. These
test what the model knew instead, on fixtures whose box scores vary by game
and which have games on every day, so the first day of every window has
something to leak:

* a spy on `fit` records the latest date of the frame each refit received,
  and every sample must be dated strictly after the latest game its model saw;
* rewriting every box score on and after a day must leave the price of every
  game on or before that day unchanged, while it does change that day's
  settlement and later windows' prices (so the rewrite is visible to a model
  that looks);
* no player is priced on a game before he has played one.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd
import pytest

from nhl_betting_lab.backtest import team_walk_forward as twf
from nhl_betting_lab.backtest import walk_forward as wf
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel

FIRST_DAY = date(2025, 1, 1)
DAYS = 150  # 2025-01-01 .. 2025-05-30, two games on every one of them
REFIT_DAYS = 30
MINIMUM_HISTORY = 50
#: Windows step from the first game date in REFIT_DAYS blocks. The first,
#: 2025-01-01..01-30, has no history and is skipped; the rest are priced, and
#: each starts on a day with games, which is what a same-day leak needs.
WINDOW_STARTS = ("2025-01-31", "2025-03-02", "2025-04-01", "2025-05-01")
TEAMS = ("TOR", "BOS", "MTL", "OTT")
DEBUTANT = 99
DEBUT = "2025-03-02"


def _pairings(day_index: int) -> list[tuple[str, str]]:
    a, b, c, d = TEAMS
    rotation = (
        [(a, b), (c, d)],
        [(a, c), (b, d)],
        [(a, d), (b, c)],
    )[day_index % 3]
    if day_index % 2:
        rotation = [(away, home) for home, away in rotation]
    return rotation


def _schedule() -> list[tuple[int, str, str, str]]:
    """(game_id, date, home, away): two games a day, every day."""
    games = []
    for day_index in range(DAYS):
        day = (FIRST_DAY + timedelta(days=day_index)).isoformat()
        for slot, (home, away) in enumerate(_pairings(day_index)):
            games.append((day_index * 2 + slot, day, home, away))
    return games


def _skater(game_id: int, day: str, player_id: int, team: str, opponent: str,
            venue: str, position: str) -> dict:
    rng = random.Random(game_id * 1000 + player_id)
    goals = rng.choice((0, 0, 0, 1, 1, 2))
    assists = rng.randint(0, 2)
    return {
        "game_id": game_id, "date": day, "player_id": player_id,
        "player": f"Player {player_id}", "role": "skater",
        "position": position, "team": team, "opponent": opponent,
        "venue": venue, "toi_seconds": rng.randint(900, 1500),
        "shots_on_goal": rng.randint(0, 6), "goals": goals,
        "assists": assists, "points": goals + assists,
        "blocked_shots": rng.randint(0, 3), "hits": rng.randint(0, 5),
        "power_play_goals": min(goals, rng.randint(0, 1)),
        "saves": 0, "shots_against": 0,
    }


def _goalie(game_id: int, day: str, player_id: int, team: str, opponent: str,
            venue: str) -> dict:
    rng = random.Random(game_id * 1000 + player_id)
    shots = rng.randint(22, 38)
    return {
        "game_id": game_id, "date": day, "player_id": player_id,
        "player": f"Goalie {player_id}", "role": "goalie", "position": "G",
        "team": team, "opponent": opponent, "venue": venue,
        "toi_seconds": 3600, "shots_on_goal": 0, "goals": 0, "assists": 0,
        "points": 0, "blocked_shots": 0, "hits": 0, "power_play_goals": 0,
        "saves": shots - rng.randint(0, 5), "shots_against": shots,
    }


def varied_logs() -> pd.DataFrame:
    """Box scores that differ game to game, and a player who debuts mid-run.

    Each team dresses two skaters and a starting goalie. TOR adds a third
    skater, DEBUTANT, from the first day of the third window onwards.
    """
    rows = []
    for game_id, day, home, away in _schedule():
        for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
            base = TEAMS.index(team) * 10
            rows.append(_skater(game_id, day, base + 1, team, opponent, venue, "C"))
            rows.append(_skater(game_id, day, base + 2, team, opponent, venue, "D"))
            rows.append(_goalie(game_id, day, base + 9, team, opponent, venue))
            if team == "TOR" and day >= DEBUT:
                rows.append(
                    _skater(game_id, day, DEBUTANT, team, opponent, venue, "C")
                )
    return pd.DataFrame(rows)


def varied_games() -> pd.DataFrame:
    rows = []
    for game_id, day, home, away in _schedule():
        rng = random.Random(game_id)
        home_goals, away_goals = rng.randint(0, 6), rng.randint(0, 6)
        regulation = home_goals != away_goals
        if not regulation:
            if rng.random() < 0.5:
                home_goals += 1
            else:
                away_goals += 1
        rows.append({
            "game_id": game_id, "date": day, "home_team": home,
            "away_team": away, "home_goals": home_goals,
            "away_goals": away_goals, "regulation": regulation,
        })
    return pd.DataFrame(rows)


def _props(logs: pd.DataFrame) -> pd.DataFrame:
    return _props_run(logs)[0]


def _props_run(logs: pd.DataFrame):
    return wf.generate_prop_samples(
        logs, minimum_history_games=MINIMUM_HISTORY, refit_days=REFIT_DAYS
    )


def _team(games: pd.DataFrame) -> pd.DataFrame:
    return _team_run(games)[0]


def _team_run(games: pd.DataFrame):
    # Two total lines rather than the full ladder: which lines are priced has
    # nothing to do with what the model saw, and the ladder triples the run.
    return twf.generate_team_samples(
        games,
        minimum_history_games=MINIMUM_HISTORY,
        refit_days=REFIT_DAYS,
        total_lines=(5.5, 6.0),
    )


def test_the_fixtures_are_what_these_tests_rely_on() -> None:
    """A constant fixture cannot be measured, and a window that starts on a
    day without games cannot show a same-day leak. Pin both, and pin the
    window arithmetic WINDOW_STARTS is written from."""
    logs = varied_logs()
    skaters = logs[logs["role"] == "skater"]
    assert skaters.groupby("player_id")["shots_on_goal"].nunique().min() > 3
    assert logs[logs["role"] == "goalie"]["saves"].nunique() > 10
    games = varied_games()
    assert games["home_goals"].nunique() > 3
    assert set(games["date"]) >= set(WINDOW_STARTS)

    samples, report = _props_run(logs)
    assert report.first_priced_date == WINDOW_STARTS[0]
    assert report.refits == len(WINDOW_STARTS)
    assert set(WINDOW_STARTS) <= set(samples["date"])

    team_samples, team_report = _team_run(games)
    assert team_report.first_priced_date == WINDOW_STARTS[0]
    assert team_report.refits == len(WINDOW_STARTS)
    assert set(WINDOW_STARTS) <= set(team_samples["date"])


# -- what each refit was handed ------------------------------------------


def test_every_prop_sample_is_priced_by_a_model_that_saw_only_earlier_games(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fitted_through: list[str] = []
    priced_by: list[str] = []

    class SeesThrough(PlayerPropsModel):
        def fit(self, logs: pd.DataFrame) -> "SeesThrough":
            self.saw_through = max(str(day)[:10] for day in logs["date"])
            fitted_through.append(self.saw_through)
            return super().fit(logs)

        def distribution(self, *args, **kwargs):
            shape = super().distribution(*args, **kwargs)
            if shape is not None:
                priced_by.append(self.saw_through)
            return shape

    monkeypatch.setattr(wf, "PlayerPropsModel", SeesThrough)
    samples = _props(varied_logs())

    assert len(fitted_through) == len(WINDOW_STARTS), fitted_through
    # One sample per priced distribution, in order; if that ever stops being
    # true this pairing is wrong, so say so rather than compare nonsense.
    assert len(priced_by) == len(samples) > 0
    leaked = [
        (day, seen)
        for day, seen in zip(samples["date"], priced_by)
        if seen >= day
    ]
    assert not leaked, (
        f"{len(leaked)} of {len(samples)} samples were priced by a model that "
        f"had seen a game on or after their own date, e.g. {leaked[:3]}"
    )


def test_every_team_sample_is_priced_by_a_model_that_saw_only_earlier_games(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fitted_through: list[str] = []
    priced_by: list[str] = []

    class SeesThrough(TeamModel):
        def fit(self, games: pd.DataFrame) -> "SeesThrough":
            self.saw_through = max(str(day)[:10] for day in games["date"])
            fitted_through.append(self.saw_through)
            return super().fit(games)

        def moneyline_probabilities(self, *args, **kwargs):
            priced_by.append(self.saw_through)
            return super().moneyline_probabilities(*args, **kwargs)

    monkeypatch.setattr(twf, "TeamModel", SeesThrough)
    samples = _team(varied_games())

    assert len(fitted_through) == len(WINDOW_STARTS), fitted_through
    # Every priced game writes its home then its away moneyline row, from one
    # moneyline call on the model that prices every market of that game.
    moneyline = samples[samples["market"] == "moneyline"]
    game_dates = list(moneyline["date"].iloc[::2])
    assert len(priced_by) == len(game_dates) > 0
    leaked = [
        (day, seen) for day, seen in zip(game_dates, priced_by) if seen >= day
    ]
    assert not leaked, (
        f"{len(leaked)} of {len(game_dates)} games were priced by a model "
        f"that had seen a game on or after their own date, e.g. {leaked[:3]}"
    )


# -- what the prices depend on -------------------------------------------

#: Every window start, plus a day in the middle of a window.
CUTOFFS = (*WINDOW_STARTS[:-1], "2025-03-16")


def _rewrite_prop_box_scores(logs: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    """Every box score on and after `cutoff`, replaced by an extreme one.

    Schedule facts (who, where, against whom) are left alone: those are known
    before puck drop and a price may use them. A goalie's ice time is left at
    a full start, so the same appearances are priced in both runs.
    """
    out = logs.copy()
    late = out["date"] >= cutoff
    skaters = late & (out["role"] == "skater")
    goalies = late & (out["role"] == "goalie")
    for column, value in (
        ("shots_on_goal", 15), ("goals", 4), ("assists", 4), ("points", 8),
        ("blocked_shots", 7), ("hits", 11), ("power_play_goals", 2),
        ("toi_seconds", 2700),
    ):
        out.loc[skaters, column] = value
    out.loc[goalies, "shots_against"] = 60
    out.loc[goalies, "saves"] = 45
    return out


def _differs(left: pd.Series, right: pd.Series) -> pd.Series:
    """Element-wise inequality in which two missing values are equal: a
    Poisson sample stores no dispersion, and NaN != NaN."""
    return ~(left.isna() & right.isna()) & (left != right)


@pytest.fixture(scope="module")
def honest_prop_samples() -> pd.DataFrame:
    return _props(varied_logs())


@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_no_box_score_on_or_after_a_day_moves_a_prop_price_up_to_that_day(
    cutoff: str, honest_prop_samples: pd.DataFrame
) -> None:
    key = ["game_id", "player_id", "market"]
    before = honest_prop_samples.set_index(key)
    after = _props(_rewrite_prop_box_scores(varied_logs(), cutoff)).set_index(key)

    up_to = before.index[before["date"] <= cutoff]
    assert set(up_to) == set(after.index[after["date"] <= cutoff])
    # The rewrite reached the day itself: its settlements changed ...
    on_the_day = before.index[before["date"] == cutoff]
    assert len(on_the_day) > 0
    assert _differs(
        before.loc[on_the_day, "actual"], after.loc[on_the_day, "actual"]
    ).any()
    # ... and a model that is allowed to see it prices differently from it.
    later_window = min(start for start in WINDOW_STARTS if start > cutoff)
    later = before.index[before["date"] >= later_window].intersection(after.index)
    assert _differs(before.loc[later, "mean"], after.loc[later, "mean"]).any(), (
        "the rewrite never reached a model at all, so it proves nothing"
    )

    moved = {
        column: int(
            _differs(before.loc[up_to, column], after.loc[up_to, column]).sum()
        )
        for column in ("mean", "dispersion_r", "expected_toi_seconds")
    }
    assert moved == dict.fromkeys(moved, 0), (
        f"rewriting box scores from {cutoff} on moved prices of games on or "
        f"before it, out of {len(up_to)} samples: {moved}"
    )


def _rewrite_team_results(games: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    out = games.copy()
    late = out["date"] >= cutoff
    out.loc[late, "home_goals"] = 1
    out.loc[late, "away_goals"] = 8
    out.loc[late, "regulation"] = True
    return out


@pytest.fixture(scope="module")
def honest_team_samples() -> pd.DataFrame:
    return _team(varied_games())


@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_no_result_on_or_after_a_day_moves_a_team_price_up_to_that_day(
    cutoff: str, honest_team_samples: pd.DataFrame
) -> None:
    def keyed(samples: pd.DataFrame) -> pd.DataFrame:
        samples = samples.copy()
        samples["line"] = samples["line"].fillna(0.0)
        return samples.set_index(["game_id", "market", "selection", "line"])

    before = keyed(honest_team_samples)
    after = keyed(_team(_rewrite_team_results(varied_games(), cutoff)))

    up_to = before.index[before["date"] <= cutoff]
    assert set(up_to) == set(after.index[after["date"] <= cutoff])
    # The rewrite reached the day itself: its results changed ...
    on_the_day = before.index[before["date"] == cutoff]
    assert len(on_the_day) > 0
    assert (
        before.loc[on_the_day, "home_goals"] != after.loc[on_the_day, "home_goals"]
    ).any()
    # ... and a model that is allowed to see it prices differently from it.
    later_window = min(start for start in WINDOW_STARTS if start > cutoff)
    later = before.index[before["date"] >= later_window].intersection(after.index)
    assert (
        before.loc[later, "model_probability"]
        != after.loc[later, "model_probability"]
    ).any(), "the rewrite never reached a model at all, so it proves nothing"

    moved = (
        before.loc[up_to, "model_probability"]
        - after.loc[up_to, "model_probability"]
    ).abs()
    assert moved.max() == 0.0, (
        f"rewriting results from {cutoff} on moved {int((moved > 0).sum())} "
        f"of {len(up_to)} team prices of games on or before it, by up to "
        f"{moved.max():.4f}"
    )


# -- who can be priced ---------------------------------------------------


def test_no_player_is_priced_before_he_has_played_a_game(
    honest_prop_samples: pd.DataFrame,
) -> None:
    """A model can only know a player from games before the one it prices.

    DEBUTANT's first game opens the third window, so the honest walk-forward
    cannot price him anywhere in it; a fit that sees the window meets him
    thirty times inside it, twice the fifteen games a skater needs to be
    priced, and prices his debut.
    """
    logs = varied_logs()
    first_game = logs.groupby("player_id")["date"].min()
    early = honest_prop_samples[
        honest_prop_samples["date"]
        <= honest_prop_samples["player_id"].map(first_game)
    ]
    assert early.empty, early[["date", "player_id", "market"]].head().to_dict("records")
    # He is priced once the model has seen him play, so the fixture can show it.
    assert (honest_prop_samples["player_id"] == DEBUTANT).any()
