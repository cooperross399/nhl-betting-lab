"""Generate model-vs-outcome samples without ever leaking a result.

The rule is one sentence: **a game is priced by a model fitted only on games
that finished before it started.** Everything else here is bookkeeping in
service of that.

Refits happen on a cadence rather than per game, and the cadence is a real
trade-off rather than a shortcut. Refitting daily over three seasons means
about 600 fits over a growing dataset, which is slow enough that nobody runs
the measurement, and a measurement nobody runs is worse than a slightly
staler one. Every refit uses only games strictly before the window it prices,
so the cadence changes how *fresh* the model is, never what it can see.

A player who did not dress produces no sample. That matches how books settle
a prop on a player who never enters — the bet is void — and it keeps the
absence out of the measurement instead of scoring it as a loss.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from nhl_betting_lab.models.player_props import (
    GOALIE_SETTLEMENT_COLUMN,
    GOALIE_STAT,
    PlayerPropsModel,
    SKATER_STATS,
)


#: The lines the calibration measurement prices, per market. Chosen to sit
#: where books actually hang them, so a calibration result says something
#: about bets that exist rather than about arbitrary thresholds.
DEFAULT_LINES: dict[str, tuple[float, ...]] = {
    "shots_on_goal": (1.5, 2.5, 3.5, 4.5),
    "points": (0.5, 1.5, 2.5),
    # 0.5 is anytime goal scorer, which is where most of the goals volume is.
    "goals": (0.5, 1.5),
    "assists": (0.5, 1.5),
    "blocked_shots": (0.5, 1.5, 2.5, 3.5),
    "goalie_saves": (19.5, 24.5, 27.5, 29.5, 31.5),
}

#: Market key -> the log column it settles on.
#: Market key -> the log column it settles on. Every skater market shares its
#: name with its column; the goalie one does not, which is exactly why this
#: mapping exists rather than being assumed.
SETTLEMENT_COLUMNS: dict[str, str] = {
    **{stat: stat for stat in SKATER_STATS},
    GOALIE_STAT: GOALIE_SETTLEMENT_COLUMN,
}

#: A goalie appearance below this many seconds is a relief appearance, not a
#: start, and it produces no sample.
#:
#: This is not a convenience. The first calibration run priced every goalie in
#: every boxscore, and the under-12-minute bucket predicted 42.8% and observed
#: 0.3% across 16,145 samples. That is not a miscalibrated model — it is a
#: model being scored on bets that were never offered. A book posts a total
#: saves line for the expected starter; nobody can bet a total saves prop on a
#: goalie who comes in cold in the second period.
#:
#: Excluding relief appearances measures the model on the bets that exist. It
#: does **not** fix the underlying problem, which is that the model has no way
#: to know who starts. That is handled where it belongs, as a card-level gate:
#: see `docs/goalie_props_need_a_confirmed_starter.md`.
GOALIE_START_SECONDS = 2400

SAMPLE_COLUMNS = (
    "date",
    "game_id",
    "player_id",
    "player",
    "team",
    "opponent",
    "venue",
    "market",
    "line",
    "model_probability",
    "actual",
    "outcome",
    "toi_seconds",
)


@dataclass
class WalkForwardReport:
    """What the generation saw, so a thin measurement announces itself."""

    refits: int = 0
    windows_skipped_for_history: int = 0
    games_priced: int = 0
    samples: int = 0
    players_unpriced: int = 0
    first_priced_date: str = ""
    last_priced_date: str = ""
    lines: dict[str, tuple[float, ...]] = field(default_factory=dict)

    def summary_line(self) -> str:
        if not self.samples:
            return (
                "No samples were generated. Either there is no data, or every "
                "window was skipped for lack of prior history."
            )
        return (
            f"{self.samples:,} samples across {self.games_priced:,} games "
            f"({self.first_priced_date} to {self.last_priced_date}), from "
            f"{self.refits} walk-forward refits. "
            f"{self.windows_skipped_for_history} window(s) were skipped "
            "because too little history existed to fit on."
        )


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def generate_prop_samples(
    logs: pd.DataFrame,
    *,
    lines: Mapping[str, Sequence[float]] | None = None,
    refit_days: int = 14,
    minimum_history_games: int = 200,
    start_date: str = "",
    end_date: str = "",
) -> tuple[pd.DataFrame, WalkForwardReport]:
    """Price every player-game in the log with a model that could not see it."""
    wanted = {
        key: tuple(float(line) for line in values)
        for key, values in (lines or DEFAULT_LINES).items()
    }
    report = WalkForwardReport(lines=wanted)

    frame = logs.copy()
    if frame.empty:
        return pd.DataFrame(columns=list(SAMPLE_COLUMNS)), report
    frame["_date"] = frame["date"].map(_as_date)
    frame = frame.dropna(subset=["_date"]).sort_values(["_date", "game_id"])
    if start_date:
        frame = frame[frame["_date"] >= date.fromisoformat(start_date)]
    if end_date:
        frame = frame[frame["_date"] <= date.fromisoformat(end_date)]
    if frame.empty:
        return pd.DataFrame(columns=list(SAMPLE_COLUMNS)), report

    all_logs = logs.copy()
    all_logs["_date"] = all_logs["date"].map(_as_date)
    all_logs = all_logs.dropna(subset=["_date"])

    first = frame["_date"].min()
    last = frame["_date"].max()
    rows: list[dict[str, object]] = []
    unpriced: set[int] = set()

    window_start = first
    while window_start <= last:
        window_end = window_start + timedelta(days=max(1, int(refit_days)) - 1)
        # Strictly before the window: the model may not see a single game it
        # is about to price, not even one earlier the same day.
        history = all_logs[all_logs["_date"] < window_start]
        if history["game_id"].nunique() < minimum_history_games:
            report.windows_skipped_for_history += 1
            window_start = window_end + timedelta(days=1)
            continue
        try:
            model = PlayerPropsModel().fit(history.drop(columns=["_date"]))
        except (KeyError, ValueError):
            report.windows_skipped_for_history += 1
            window_start = window_end + timedelta(days=1)
            continue
        report.refits += 1

        window = frame[
            (frame["_date"] >= window_start) & (frame["_date"] <= window_end)
        ]
        for _, log in window.iterrows():
            player_id = int(log["player_id"])
            role = str(log["role"])
            if role == "goalie" and int(
                pd.to_numeric(log["toi_seconds"], errors="coerce") or 0
            ) < GOALIE_START_SECONDS:
                # A relief appearance. No book offered a saves prop on it.
                continue
            markets = (
                ("goalie_saves",)
                if role == "goalie"
                else tuple(key for key in wanted if key != "goalie_saves")
            )
            priced_any = False
            for market in markets:
                column = SETTLEMENT_COLUMNS.get(market)
                if column is None or column not in log:
                    continue
                actual = float(pd.to_numeric(log[column], errors="coerce") or 0.0)
                for line in wanted.get(market, ()):
                    probability = model.over_probability(
                        player_id,
                        market,
                        line,
                        opponent=str(log["opponent"]),
                        venue=str(log["venue"]),
                    )
                    if probability is None:
                        continue
                    priced_any = True
                    rows.append(
                        {
                            "date": str(log["date"])[:10],
                            "game_id": int(log["game_id"]),
                            "player_id": player_id,
                            "player": str(log.get("player", "")),
                            "team": str(log["team"]),
                            "opponent": str(log["opponent"]),
                            "venue": str(log["venue"]),
                            "market": market,
                            "line": line,
                            "model_probability": float(probability),
                            "actual": actual,
                            "outcome": bool(actual > line),
                            "toi_seconds": int(
                                pd.to_numeric(log["toi_seconds"], errors="coerce")
                                or 0
                            ),
                        }
                    )
            if not priced_any:
                unpriced.add(player_id)
        report.games_priced += int(window["game_id"].nunique())
        window_start = window_end + timedelta(days=1)

    samples = pd.DataFrame(rows, columns=list(SAMPLE_COLUMNS))
    report.samples = len(samples)
    report.players_unpriced = len(unpriced)
    if not samples.empty:
        report.first_priced_date = str(samples["date"].min())
        report.last_priced_date = str(samples["date"].max())
    return samples, report
