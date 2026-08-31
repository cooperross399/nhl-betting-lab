"""Walk-forward team-market samples, on the same rule as the props ones.

**A game is priced by a model fitted only on games that finished before it
started.** Refits happen on a cadence; every refit uses only games strictly
before the window it prices, so the cadence changes how fresh the model is and
never what it can see.

Three outcomes are recorded per game, and the distinction between them is the
whole reason this is separate from the props path:

* **moneyline** settles on the final result including overtime and the
  shootout, so a regulation tie is not a push — it is decided;
* **puck line** at 1.5 settles on the margin, and an overtime or shootout
  winner takes the game by exactly one, so a -1.5 bet cannot win in overtime;
* **totals** settle on the final score, so a game that goes to overtime adds
  exactly one goal.

Getting any of those wrong produces a measurement that looks fine and is
systematically biased. They are handled explicitly rather than by a shared
"who won" column.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.rest import played_previous_day


#: Total lines the calibration sweep prices. 5.5 is where the NHL headline
#: total sits almost every night; the neighbours are where the alternate
#: ladder lives.
#: Every total line the bought prices actually sit on. The half-line-only
#: grid silently dropped 2,780 of 8,136 bought totals — 34%, uncounted — and
#: the drop was biased: books hang 6.0 exactly on the games they judge
#: closest to six goals, so the measured subset excluded the mid-total
#: matchups specifically. The same grid-loss shape the props path fixed by
#: storing distributions; team samples price a fixed grid, so the grid must
#: cover what the books actually hang.
# Every total the bought store actually holds, not the handful the books hang
# most often. Buying both seasons in full surfaced lines from 2.0 to 13.5:
# the deep ones are thin (4 rows at 2.0, 10 at 13.0) but a line the grid does
# not carry is a price the measurement silently discards, which is precisely
# how a third of the bought totals once vanished. The discipline test
# `test_the_sample_grid_covers_every_line_the_bought_file_holds` fails the
# build when the store outgrows this tuple again.
DEFAULT_TOTAL_LINES: tuple[float, ...] = (
    2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5,
    9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 13.0, 13.5,
)

#: The puck line. Alternates exist at 2.5 but are thin, so the sweep prices
#: the one that is always quoted.
PUCK_LINE = 1.5

#: The alternate spread ladder the bought prices include. ±2.5 rows exist in
#: the purchased file and joined nothing while the samples carried ±1.5 only.
PUCK_LINES: tuple[float, ...] = (
    1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.5,
)

SAMPLE_COLUMNS = (
    "date",
    "game_id",
    "home_team",
    "away_team",
    "market",
    "selection",
    "line",
    "model_probability",
    "outcome",
    "push",
    "home_goals",
    "away_goals",
    "regulation",
)


@dataclass
class TeamWalkForwardReport:
    refits: int = 0
    windows_skipped_for_history: int = 0
    games_priced: int = 0
    samples: int = 0
    first_priced_date: str = ""
    last_priced_date: str = ""

    def summary_line(self) -> str:
        if not self.samples:
            return (
                "No team samples were generated. Either there is no data, or "
                "every window was skipped for lack of prior history."
            )
        return (
            f"{self.samples:,} team-market samples across "
            f"{self.games_priced:,} games ({self.first_priced_date} to "
            f"{self.last_priced_date}), from {self.refits} walk-forward "
            f"refits. {self.windows_skipped_for_history} window(s) were "
            "skipped because too little history existed to fit on."
        )


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def settle_moneyline(home_goals: int, away_goals: int) -> str:
    """Who won, including overtime and the shootout. Never a draw."""
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    # The NHL has no ties. A boxscore showing one is a data fault, not an
    # outcome, and calling it a home win would quietly bias every measurement.
    raise ValueError(
        "A completed NHL game cannot be level; this row is a data fault."
    )


def settle_regulation_3_way(
    home_goals: int, away_goals: int, *, regulation: bool
) -> str:
    """Who led after sixty minutes, with the draw as a real outcome.

    A game that went past regulation was level at sixty whatever the boxscore
    says the final score was, because every goal after that belongs to
    overtime. Reading the final score here would settle a draw as a win and
    make the market look far more decisive than it is.
    """
    if not regulation:
        return "draw"
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    # Regulation flagged true and level is a contradiction: a level game goes
    # to overtime by rule, so the flag is wrong rather than the score.
    raise ValueError(
        "A game cannot be level and end in regulation; this row is a data "
        "fault."
    )


def settle_puck_line(
    home_goals: int, away_goals: int, *, regulation: bool, line: float = PUCK_LINE
) -> dict[str, tuple[bool, bool]]:
    """`(won, push)` for each puck-line side, on the final margin.

    An overtime or shootout winner takes the game by exactly one, whatever the
    boxscore's final margin says, because the winning goal is the only one
    scored after regulation. So a non-regulation game can never cover -1.5 —
    and on the ±1 line it *pushes*, which whole-number spreads do on any exact
    margin. A book refunds a push; settling one as a loss would make every
    whole-number rung look worse than it is.
    """
    margin = int(home_goals) - int(away_goals)
    if not regulation:
        margin = 1 if margin > 0 else -1
    size = abs(float(line))

    def side(win: bool, at: float) -> tuple[bool, bool]:
        push = float(size).is_integer() and margin == at
        return (win and not push, push)

    return {
        "home_minus": side(margin > size, size),
        "home_plus": side(margin > -size, -size),
        "away_minus": side(-margin > size, -size),
        "away_plus": side(-margin > -size, size),
    }


def settle_total(
    home_goals: int, away_goals: int, line: float
) -> tuple[bool, bool]:
    """`(over, push)` for a totals line, on the final score."""
    total = int(home_goals) + int(away_goals)
    if float(line).is_integer() and total == int(line):
        return False, True
    return total > float(line), False


def settle_team_total(side_goals: int, line: float) -> tuple[bool, bool]:
    """`(over, push)` for one side's goals, on the final score.

    The boxscore's final already contains any overtime goal, so no
    regulation adjustment applies here — the model carries that reasoning,
    the settlement just reads the score. Whole-number lines push on an
    exact hit, the same rule as every other total.
    """
    goals = int(side_goals)
    if float(line).is_integer() and goals == int(line):
        return False, True
    return goals > float(line), False


def _with_back_to_backs(games: pd.DataFrame) -> pd.DataFrame:
    """Mark whether each side played the previous league day.

    Rest derives from the schedule, which is known before puck drop, so this
    leaks nothing — a team's previous game is in the past whichever window is
    being priced. The rule itself lives in `rest.py`, shared with the live
    card, so the policy the experiment measured and the policy the card ships
    are one function rather than two copies.
    """
    ordered = games.sort_values("date").copy()
    last_played: dict[str, str] = {}
    home_flags: list[bool] = []
    away_flags: list[bool] = []
    for row in ordered.itertuples():
        day = str(row.date)[:10]
        for team, flags in (
            (str(row.home_team), home_flags),
            (str(row.away_team), away_flags),
        ):
            flags.append(played_previous_day(last_played, team, day))
            last_played[team] = day
    ordered["home_b2b"] = home_flags
    ordered["away_b2b"] = away_flags
    return ordered


def generate_team_samples(
    games: pd.DataFrame,
    *,
    total_lines: Sequence[float] = DEFAULT_TOTAL_LINES,
    refit_days: int = 14,
    minimum_history_games: int = 200,
    start_date: str = "",
    end_date: str = "",
    use_rest: bool = True,
) -> tuple[pd.DataFrame, TeamWalkForwardReport]:
    """Price every game with a model that could not see it.

    `use_rest=False` prices with rest ignored, which exists so the two
    policies can be compared on identical games — the comparison that decides
    whether the back-to-back adjustment ships.
    """
    report = TeamWalkForwardReport()
    if games.empty:
        return pd.DataFrame(columns=list(SAMPLE_COLUMNS)), report

    frame = _with_back_to_backs(games)
    frame["_date"] = frame["date"].map(_as_date)
    frame = frame.dropna(subset=["_date"]).sort_values(["_date", "game_id"])
    for column in ("home_goals", "away_goals"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["home_goals", "away_goals"])
    if start_date:
        frame = frame[frame["_date"] >= date.fromisoformat(start_date)]
    if end_date:
        frame = frame[frame["_date"] <= date.fromisoformat(end_date)]
    if frame.empty:
        return pd.DataFrame(columns=list(SAMPLE_COLUMNS)), report

    all_games = games.copy()
    all_games["_date"] = all_games["date"].map(_as_date)
    all_games = all_games.dropna(subset=["_date"])

    rows: list[dict[str, object]] = []
    window_start = frame["_date"].min()
    last = frame["_date"].max()

    while window_start <= last:
        window_end = window_start + timedelta(days=max(1, int(refit_days)) - 1)
        history = all_games[all_games["_date"] < window_start]
        if len(history) < minimum_history_games:
            report.windows_skipped_for_history += 1
            window_start = window_end + timedelta(days=1)
            continue
        try:
            model = TeamModel().fit(history.drop(columns=["_date"]))
        except (KeyError, ValueError):
            report.windows_skipped_for_history += 1
            window_start = window_end + timedelta(days=1)
            continue
        report.refits += 1

        window = frame[
            (frame["_date"] >= window_start) & (frame["_date"] <= window_end)
        ]
        for game in window.itertuples():
            home = str(game.home_team)
            away = str(game.away_team)
            rest_kwargs = (
                {
                    "home_b2b": bool(getattr(game, "home_b2b", False)),
                    "away_b2b": bool(getattr(game, "away_b2b", False)),
                }
                if use_rest
                else {}
            )
            home_goals = int(game.home_goals)
            away_goals = int(game.away_goals)
            regulation = bool(getattr(game, "regulation", True))
            shared = {
                "date": str(game.date)[:10],
                "game_id": int(game.game_id),
                "home_team": home,
                "away_team": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "regulation": regulation,
            }
            try:
                winner = settle_moneyline(home_goals, away_goals)
            except ValueError:
                continue

            regulation_result = settle_regulation_3_way(
                home_goals, away_goals, regulation=regulation
            )
            three_way = model.regulation_3_way_probabilities(
                home, away, **rest_kwargs
            )
            for side in ("home", "draw", "away"):
                rows.append(
                    {
                        **shared,
                        "market": "regulation_3_way",
                        "selection": side,
                        "line": None,
                        "model_probability": three_way[side],
                        "outcome": regulation_result == side,
                        "push": False,
                    }
                )

            moneyline = model.moneyline_probabilities(home, away, **rest_kwargs)
            for side in ("home", "away"):
                rows.append(
                    {
                        **shared,
                        "market": "moneyline",
                        "selection": side,
                        "line": None,
                        "model_probability": moneyline[side],
                        "outcome": winner == side,
                        "push": False,
                    }
                )

            for puck_line in PUCK_LINES:
                covered = settle_puck_line(
                    home_goals, away_goals, regulation=regulation,
                    line=puck_line,
                )
                puck = model.puck_line_probabilities(
                    home, away, line=puck_line, **rest_kwargs
                )
                for key, line in (
                    ("home_minus", -puck_line),
                    ("home_plus", puck_line),
                    ("away_minus", -puck_line),
                    ("away_plus", puck_line),
                ):
                    won, push = covered[key]
                    rows.append(
                        {
                            **shared,
                            "market": "puck_line",
                            "selection": key,
                            "line": line,
                            "model_probability": puck[key],
                            "outcome": won,
                            "push": push,
                        }
                    )

            for line in total_lines:
                over, push = settle_total(home_goals, away_goals, line)
                totals = model.total_probabilities(
                    home, away, line=line, **rest_kwargs
                )
                for side, happened in (("over", over), ("under", not over and not push)):
                    rows.append(
                        {
                            **shared,
                            "market": "total_goals",
                            "selection": side,
                            "line": line,
                            "model_probability": totals[side],
                            "outcome": happened,
                            "push": push,
                        }
                    )
        report.games_priced += len(window)
        window_start = window_end + timedelta(days=1)

    samples = pd.DataFrame(rows, columns=list(SAMPLE_COLUMNS))
    report.samples = len(samples)
    if not samples.empty:
        report.first_priced_date = str(samples["date"].min())
        report.last_priced_date = str(samples["date"].max())
    return samples, report
