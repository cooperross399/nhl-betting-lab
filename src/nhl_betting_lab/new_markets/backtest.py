"""The new markets against prices that were for sale: one bet per wager, best price.

The shadow models in this package were measured on outcomes, which can rule a
model out and never in. This is the price backtest the 2026-10-13 shadow
bullet in `CLAUDE.md` said had to come next: every bought price is joined to
the model's walk-forward opinion of that selection, and the model bets a
selection when its edge clears the card's MEASUREMENT bar (3.5% for the period
markets, which are team markets; 6% for the player markets), one bet per
wager at the best price any book quoted, flat stake.

**Nothing here reaches the card.** It reads the shadow models and the private
price cache and writes an aggregate report.

## The rules this applies, and where each comes from

* **One bet per wager.** Eight books quoting one selection are one bet, at
  the best price (`stores.best_price_per_wager`, the defect that once
  published -1.6% over 73,918 as a demonstrated loss). The wager key is the
  game, the market family and period, the player (`player_key`), the
  selection and the line, so a featured line and the same rung of its
  alternate ladder are one wager.
* **Best-of-N is optimistic.** The best price is the likeliest to be stale,
  so the printed return leans favourable, as the props backtest says of its
  own.
* **Intervals count the game, not the wager** (`stats.clustered_mean_interval`
  on the game): every period, player and side of one game settles on one
  play-by-play.
* **Corrected across every figure measured** (Bonferroni, as the props
  backtest corrects), and an interval that includes zero is **no
  demonstrated edge**.
* **Edge** is the model's chance of winning given no push, minus the price's
  implied probability (vig included), as the card's `value.edge`.

## Settlement, as the models assume it

* `h2h_pN`: two-way, **a tied period is a push** (`periods` docstring). The
  edge is on P(win | no tie), the draw-no-bet reading.
* `h2h_3_way_pN`: home, draw, away for the period.
* `spreads_pN`, `totals_pN`: the period's margin and total; a whole line
  that lands exactly is a push.
* `player_power_play_points`, `player_faceoffs_won`: the play-by-play counts
  (`player_extras`); a whole line that lands exactly is a push.
* `player_shots`: **settled two ways**, because what the key means is not
  confirmed (`player_extras` docstring): as shot attempts and as unblocked
  attempts, each its own figure. The report also sets the mean posted line
  beside each count, which is the check that docstring asks for.
* First and last scorer: overtime counts, the shootout never, empty-net goals
  count, and a selection with no goal in play wins only for "no goalscorer"
  (`scorers` docstring). A player this lab cannot find among the game's
  dressed skaters gets no opinion and is not bet (a book voids a player who
  did not dress).

A price with no opinion (a game before the models' minimum history, a player
the logs do not name, a line the model does not price) is counted and never
bet. Nothing is guessed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

from nhl_betting_lab.config import MIN_EDGE, MIN_PROP_EDGE
from nhl_betting_lab.models.player_props import player_key, player_name_aliases
from nhl_betting_lab.models.value import american_to_decimal
from nhl_betting_lab.new_markets.periods import period_matrix
from nhl_betting_lab.new_markets.player_extras import MIN_INVERSE_R
from nhl_betting_lab.new_markets.prices import NO_SCORER
from nhl_betting_lab.providers.team_names import resolve_team
from nhl_betting_lab.season import game_date
from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE, clustered_mean_interval
from nhl_betting_lab.stores import best_price_per_wager

PERIOD_FAMILIES = ("h2h", "h2h_3_way", "spreads", "totals")
#: The player families as measured. `shots` is measured under both readings.
COUNT_FAMILIES: dict[str, str] = {
    "power_play_points": "ppp",
    "faceoffs_won": "faceoffs_won",
    "shots_as_attempts": "shot_attempts",
    "shots_as_unblocked": "unblocked_attempts",
}
#: The extras model's market name for each measured family (`mu_<name>`).
EXTRAS_MODEL_NAME: dict[str, str] = {
    "power_play_points": "power_play_points",
    "faceoffs_won": "faceoffs_won",
    "shots_as_attempts": "shot_attempts",
    "shots_as_unblocked": "unblocked_attempts",
}
SCORER_FAMILIES = {"first_scorer": "first", "last_scorer": "last"}

#: The period models measured against prices. The league baseline carries no
#: team information and is not a betting model.
PERIOD_MODELS = ("goals", "xg")

#: Hours either side of the asked window a snapshot may sit.
WINDOW_TOLERANCE_HOURS = 1.0

WAGER_KEY = ["game_id", "family", "period", "player_key", "selection", "line_key"]


def edge_bar(family: str) -> float:
    """The card's measurement bar: 3.5% for team (period) markets, 6% for props."""
    return MIN_EDGE if family in PERIOD_FAMILIES else MIN_PROP_EDGE


# -- preparing the prices -------------------------------------------------------


def lead_hours(prices: pd.DataFrame) -> pd.Series:
    start = pd.to_datetime(prices["commence_time"], utc=True, errors="coerce", format="mixed")
    taken = pd.to_datetime(prices["snapshot"], utc=True, errors="coerce", format="mixed")
    return (start - taken).dt.total_seconds() / 3600.0


def select_window(
    prices: pd.DataFrame, hours_before: float, *, tolerance: float = WINDOW_TOLERANCE_HOURS
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """The prices taken `hours_before` face-off (within `tolerance`), strictly
    before it, and only the latest snapshot of each event inside the window.

    A window that matches nothing measures nothing and says so; it never falls
    through to every price (`CLAUDE.md`: a filter that does nothing when it
    matches nothing is not a filter).
    """
    if prices.empty:
        return prices.copy(), {"rows": 0, "kept": 0, "events": 0, "median_lead_hours": None}
    lead = lead_hours(prices)
    keep = lead.notna() & (lead > 0) & ((lead - float(hours_before)).abs() <= float(tolerance))
    kept = prices[keep].copy()
    if not kept.empty:
        kept["_taken"] = pd.to_datetime(kept["snapshot"], utc=True, errors="coerce", format="mixed")
        latest = kept.groupby("provider_event_id")["_taken"].transform("max")
        kept = kept[kept["_taken"] == latest].drop(columns=["_taken"])
    summary = {
        "rows": int(len(prices)),
        "kept": int(len(kept)),
        "events": int(kept["provider_event_id"].nunique()) if not kept.empty else 0,
        "median_lead_hours": float(lead[keep].median()) if keep.any() else None,
    }
    return kept, summary


def attach_games(
    prices: pd.DataFrame, team_games: pd.DataFrame, team_map: Mapping[str, str]
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Each price's NHL game, by (league date, home, away), both teams resolved.

    A price whose two teams do not both resolve, or whose game the team games
    do not hold, is counted and left out.
    """
    if prices.empty:
        return prices.assign(game_id=pd.Series(dtype="int64")), {"events": 0, "unresolved_teams": 0, "no_game": 0}
    games = team_games.copy()
    games["game_id"] = pd.to_numeric(games["game_id"], errors="coerce")
    games = games.dropna(subset=["game_id"])
    index = {
        (str(row.date)[:10], str(row.home_team), str(row.away_team)): int(row.game_id)
        for row in games.itertuples()
    }
    events = prices.drop_duplicates("provider_event_id")[
        ["provider_event_id", "commence_time", "home_team", "away_team"]
    ]
    found: dict[str, int] = {}
    unresolved = no_game = 0
    for event in events.itertuples():
        home = resolve_team(event.home_team, team_map)
        away = resolve_team(event.away_team, team_map)
        if home is None or away is None:
            unresolved += 1
            continue
        gid = index.get((game_date(event.commence_time), home, away))
        if gid is None:
            no_game += 1
            continue
        found[str(event.provider_event_id)] = gid
    out = prices[prices["provider_event_id"].astype(str).isin(found)].copy()
    out["game_id"] = out["provider_event_id"].astype(str).map(found).astype("int64")
    return out, {"events": int(len(events)), "unresolved_teams": unresolved, "no_game": no_game}


def _line_key(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return "" if math.isnan(number) else f"{number:g}"


def wagers(prices: pd.DataFrame) -> pd.DataFrame:
    """One row per wager, at the best price any book quoted on it.

    `player_shots` prices appear twice, once per reading (`shots_as_attempts`,
    `shots_as_unblocked`), because which count settles them is unconfirmed.
    """
    if prices.empty:
        return prices.assign(player_key="", line_key="")
    frame = prices.copy()
    frame["player_key"] = frame["player"].fillna("").map(player_key)
    frame["line_key"] = frame["line"].map(_line_key)
    shots = frame[frame["family"] == "shots"]
    frame = pd.concat(
        [
            frame[frame["family"] != "shots"],
            shots.assign(family="shots_as_attempts"),
            shots.assign(family="shots_as_unblocked"),
        ],
        ignore_index=True,
    )
    return best_price_per_wager(frame, WAGER_KEY)


# -- the model's opinion of each wager --------------------------------------------


def _count_outcome_probabilities(mu: float, inv_r: float, line: float) -> tuple[float, float, float]:
    """(P(X > line), P(X == line), P(X < line)) for a count, any line."""
    mean = max(float(mu), 1e-9)
    if inv_r == inv_r and inv_r >= MIN_INVERSE_R:
        r = 1.0 / float(inv_r)
        dist = nbinom(r, r / (r + mean))
    else:
        dist = poisson(mean)
    if float(line).is_integer():
        k = int(line)
        push = float(dist.pmf(k))
        over = float(dist.sf(k))
        return over, push, max(0.0, 1.0 - over - push)
    k = math.floor(float(line))
    over = float(dist.sf(k))
    return over, 0.0, 1.0 - over


def _period_outcome(matrix: np.ndarray, family: str, selection: str, line: float | None) -> tuple[float, float]:
    """(P(win), P(push)) of one period selection under one scoreline matrix."""
    grid = np.arange(matrix.shape[0])
    margin = np.subtract.outer(grid, grid)  # home minus away
    total = np.add.outer(grid, grid)
    if family in ("h2h", "h2h_3_way"):
        home = float(matrix[margin > 0].sum())
        away = float(matrix[margin < 0].sum())
        draw = float(matrix[margin == 0].sum())
        win = {"home": home, "away": away, "draw": draw}.get(selection)
        if win is None:
            raise KeyError(selection)
        return win, (draw if family == "h2h" and selection != "draw" else 0.0)
    if line is None:
        raise KeyError("a period spread or total needs a line")
    if family == "spreads":
        signed = margin if selection == "home" else -margin
        if selection not in ("home", "away"):
            raise KeyError(selection)
        return float(matrix[signed + line > 0].sum()), float(matrix[signed + line == 0].sum())
    if family == "totals":
        if selection == "over":
            return float(matrix[total > line].sum()), float(matrix[total == line].sum())
        if selection == "under":
            return float(matrix[total < line].sum()), float(matrix[total == line].sum())
        raise KeyError(selection)
    raise KeyError(family)


def _period_result(home: int, away: int, family: str, selection: str, line: float | None) -> str:
    margin = home - away
    if family == "h2h":
        if margin == 0:
            return "push"
        return "win" if (margin > 0) == (selection == "home") else "loss"
    if family == "h2h_3_way":
        outcome = "home" if margin > 0 else "away" if margin < 0 else "draw"
        return "win" if outcome == selection else "loss"
    assert line is not None
    if family == "spreads":
        value = (margin if selection == "home" else -margin) + line
    else:
        value = (home + away - line) if selection == "over" else (line - home - away)
    return "win" if value > 0 else "push" if value == 0 else "loss"


def _count_result(count: float, selection: str, line: float) -> str:
    value = (count - line) if selection == "over" else (line - count)
    return "win" if value > 0 else "push" if value == 0 else "loss"


def price_periods(
    bets: pd.DataFrame, rates: pd.DataFrame, period_goals: pd.DataFrame
) -> pd.DataFrame:
    """Opinion and result of every period wager, once per period model."""
    columns = [*bets.columns, "model", "p_win", "p_push", "result"]
    chosen = bets[bets["family"].isin(PERIOD_FAMILIES)]
    if chosen.empty or rates.empty:
        return pd.DataFrame(columns=columns)
    goals = period_goals.copy()
    goals["game_id"] = pd.to_numeric(goals["game_id"], errors="coerce")
    goals = goals.dropna(subset=["game_id"]).drop_duplicates("game_id")
    goals = goals.set_index(goals["game_id"].astype(int))
    rate_index = {
        (int(r.game_id), int(r.period), str(r.model)): (float(r.home_rate), float(r.away_rate))
        for r in rates.itertuples()
    }
    rows = []
    cache: dict[tuple[float, float], np.ndarray] = {}
    for bet in chosen.to_dict("records"):
        gid, period = int(bet["game_id"]), int(bet["period"])
        if gid not in goals.index:
            continue
        line = None if bet["line_key"] == "" else float(bet["line_key"])
        home_goals = int(goals.at[gid, f"home_p{period}"])
        away_goals = int(goals.at[gid, f"away_p{period}"])
        for model in PERIOD_MODELS:
            pair = rate_index.get((gid, period, model))
            if pair is None:
                continue
            matrix = cache.get(pair)
            if matrix is None:
                matrix = cache[pair] = period_matrix(*pair)
            try:
                win, push = _period_outcome(matrix, bet["family"], bet["selection"], line)
            except KeyError:
                continue
            rows.append({**bet, "model": model, "p_win": win, "p_push": push,
                         "result": _period_result(home_goals, away_goals, bet["family"], bet["selection"], line)})
    return pd.DataFrame(rows, columns=columns)


def _alias_index(players: pd.DataFrame) -> dict[int, dict[str, set[int]]]:
    """Per game, every alias of every listed player's name -> player ids."""
    index: dict[int, dict[str, set[int]]] = {}
    for row in players.itertuples():
        forms = index.setdefault(int(row.game_id), {})
        for alias in player_name_aliases(row.player):
            forms.setdefault(alias, set()).add(int(row.player_id))
    return index


def _resolve(index: Mapping[int, Mapping[str, set[int]]], gid: int, name: str) -> int | None:
    """The one player in the game every alias of `name` reaches, or None."""
    forms = index.get(gid, {})
    found: set[int] = set()
    for alias in player_name_aliases(name):
        found |= forms.get(alias, set())
    return next(iter(found)) if len(found) == 1 else None


def price_counts(bets: pd.DataFrame, predictions: pd.DataFrame, logs: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Opinion and result of every power-play, faceoff and shots wager.

    `predictions` is `player_extras.walk_forward`'s frame. A player is found
    among the game's logged skaters by every alias of his name, and only a
    row the model priced (`priced`) gives an opinion.
    """
    columns = [*bets.columns, "model", "p_win", "p_push", "result", "count", "shots_on_goal"]
    chosen = bets[bets["family"].isin(COUNT_FAMILIES)]
    counts = {"no_player": 0, "not_priced": 0}
    if chosen.empty or predictions.empty:
        return pd.DataFrame(columns=columns), counts
    names = logs[["game_id", "player_id", "player"]].dropna().copy()
    names["game_id"] = pd.to_numeric(names["game_id"], errors="coerce")
    names["player_id"] = pd.to_numeric(names["player_id"], errors="coerce")
    names = names.dropna().astype({"game_id": int, "player_id": int}).drop_duplicates(["game_id", "player_id"])
    index = _alias_index(names)
    table = predictions.copy()
    table["game_id"] = pd.to_numeric(table["game_id"], errors="coerce").astype(int)
    table["player_id"] = pd.to_numeric(table["player_id"], errors="coerce").astype(int)
    by_row = table.set_index(["game_id", "player_id"])
    by_row = by_row[~by_row.index.duplicated()]
    rows = []
    for bet in chosen.to_dict("records"):
        gid = int(bet["game_id"])
        pid = _resolve(index, gid, bet["player"])
        if pid is None or (gid, pid) not in by_row.index:
            counts["no_player"] += 1
            continue
        record = by_row.loc[(gid, pid)]
        if not bool(record["priced"]):
            counts["not_priced"] += 1
            continue
        name = EXTRAS_MODEL_NAME[bet["family"]]
        line = float(bet["line_key"])
        over, push, under = _count_outcome_probabilities(
            float(record[f"mu_{name}"]), float(record[f"inv_r_{name}"]), line
        )
        count = float(record[COUNT_FAMILIES[bet["family"]]])
        win = over if bet["selection"] == "over" else under
        rows.append({**bet, "model": "extras", "p_win": win, "p_push": push,
                     "result": _count_result(count, bet["selection"], line), "count": count,
                     "shots_on_goal": float(record["shots_on_goal"]) if "shots_on_goal" in record else float("nan")})
    return pd.DataFrame(rows, columns=columns), counts


def price_scorers(bets: pd.DataFrame, selections: pd.DataFrame, logs: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Opinion and result of every first and last scorer wager.

    `selections` is `scorers.measure(..., selections=True).selections`: every
    dressed skater and "no goalscorer", with its probability and whether it
    won, for every game priced walk-forward, whoever scored.
    """
    columns = [*bets.columns, "model", "p_win", "p_push", "result"]
    chosen = bets[bets["family"].isin(SCORER_FAMILIES)]
    counts = {"no_player": 0}
    if chosen.empty or selections.empty:
        return pd.DataFrame(columns=columns), counts
    names = logs[["game_id", "player_id", "player"]].dropna().copy()
    names["game_id"] = pd.to_numeric(names["game_id"], errors="coerce")
    names["player_id"] = pd.to_numeric(names["player_id"], errors="coerce")
    names = names.dropna().astype({"game_id": int, "player_id": int}).drop_duplicates(["game_id", "player_id"])
    index = _alias_index(names)
    priced = {
        (int(r.game_id), str(r.market), str(r.selection)): (float(r.p), bool(r.won))
        for r in selections.itertuples()
    }
    rows = []
    for bet in chosen.to_dict("records"):
        gid = int(bet["game_id"])
        market = SCORER_FAMILIES[bet["family"]]
        if bet["selection"] == NO_SCORER:
            target = NO_SCORER
        else:
            pid = _resolve(index, gid, bet["player"])
            target = str(pid) if pid is not None else ""
        opinion = priced.get((gid, market, target)) if target else None
        if opinion is None:
            counts["no_player"] += 1
            continue
        p, won = opinion
        if bet["selection"] == "no":
            p, won = 1.0 - p, not won
        rows.append({**bet, "model": "scorers", "p_win": p, "p_push": 0.0,
                     "result": "win" if won else "loss"})
    return pd.DataFrame(rows, columns=columns), counts


# -- the measurement ------------------------------------------------------------------


def score(priced: pd.DataFrame) -> pd.DataFrame:
    """Edge, bet flag and flat-stake profit of every priced wager."""
    frame = priced.copy()
    if frame.empty:
        return frame.assign(decimal=[], implied=[], edge=[], bet=[], profit=[])
    frame["decimal"] = frame["american_odds"].map(american_to_decimal)
    frame["implied"] = 1.0 / frame["decimal"]
    decided = (1.0 - frame["p_push"]).clip(lower=1e-12)
    frame["edge"] = frame["p_win"] / decided - frame["implied"]
    frame["bet"] = frame["edge"] >= frame["family"].map(edge_bar)
    frame["profit"] = np.where(
        frame["result"] == "win", frame["decimal"] - 1.0, np.where(frame["result"] == "push", 0.0, -1.0)
    )
    return frame


@dataclass
class Figure:
    label: str
    family: str
    model: str
    bar: float
    bets: int
    wins: int
    pushes: int
    games: int
    profit: float
    roi: float
    low: float
    high: float
    adjusted_low: float
    adjusted_high: float
    survives: bool
    includes_zero: bool
    priced_wagers: int
    priced_roi: float | None
    verdict: str
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out = dict(self.__dict__)
        for key in ("roi", "low", "high", "adjusted_low", "adjusted_high", "profit"):
            value = out[key]
            out[key] = None if value is None or not math.isfinite(value) else float(value)
        return out


def _verdict(bets: int, includes_zero: bool, survives: bool, roi: float) -> str:
    if bets == 0:
        return "no bets"
    if bets < 30:
        return f"too few bets (<30): {NO_DEMONSTRATED_EDGE}"
    if includes_zero or not survives:
        return NO_DEMONSTRATED_EDGE
    return "demonstrated edge" if roi > 0 else "demonstrated loss"


def measure(scored: pd.DataFrame) -> list[Figure]:
    """One figure per (family, model), plus the pooled figure per model group.

    Every interval is clustered on the game and corrected for every figure
    returned (Bonferroni), which is the family of tests actually run.
    """
    if scored.empty:
        return []
    groups: list[tuple[str, str, str, pd.DataFrame]] = []
    for (family, model), frame in scored.groupby(["family", "model"], sort=True):
        groups.append((f"{family} ({model})", str(family), str(model), frame))
    for model in sorted(scored["model"].unique()):
        frame = scored[scored["model"] == model]
        if frame["family"].nunique() > 1:
            groups.append((f"all {model} families pooled", "pooled", str(model), frame))
    looks = len(groups)
    family_text = f"{looks} figures measured on the same prices"
    figures = []
    for label, family, model, frame in groups:
        bets = frame[frame["bet"]]
        interval = clustered_mean_interval(
            bets["profit"].tolist(), bets["game_id"].tolist(), looks=looks, family=family_text
        )
        bar = edge_bar(family) if family != "pooled" else float("nan")
        roi = interval.roi
        verdict = _verdict(interval.bets, interval.includes_zero, interval.survives_correction, roi)
        figures.append(
            Figure(
                label=label,
                family=family,
                model=model,
                bar=bar,
                bets=interval.bets,
                wins=int((bets["result"] == "win").sum()),
                pushes=int((bets["result"] == "push").sum()),
                games=int(bets["game_id"].nunique()),
                profit=float(interval.profit),
                roi=float(roi),
                low=float(interval.low),
                high=float(interval.high),
                adjusted_low=float(interval.adjusted_low),
                adjusted_high=float(interval.adjusted_high),
                survives=bool(interval.survives_correction),
                includes_zero=bool(interval.includes_zero),
                priced_wagers=int(len(frame)),
                priced_roi=float(frame["profit"].mean()) if len(frame) else None,
                verdict=verdict,
            )
        )
    return figures


def shots_definition_check(counts: pd.DataFrame) -> dict[str, Any]:
    """Mean posted `player_shots` line beside the counts it could mean.

    Aggregates only, over the player-games a `player_shots` price was
    matched to: the number of wagers, the mean and median posted line, and
    the mean shot attempts, unblocked attempts and shots on goal those
    players recorded. A line nearer shots on goal than either attempt count
    would mean the key is shots on goal under another name, and neither
    reading here would settle it.
    """
    if counts.empty:
        return {"wagers": 0}
    attempts = counts[counts["family"] == "shots_as_attempts"]
    unblocked = counts[counts["family"] == "shots_as_unblocked"]
    if attempts.empty:
        return {"wagers": 0}
    lines = attempts["line_key"].astype(float)
    return {
        "wagers": int(len(attempts)),
        "mean_line": float(lines.mean()),
        "median_line": float(lines.median()),
        "mean_shot_attempts": float(attempts["count"].mean()),
        "mean_unblocked_attempts": float(unblocked["count"].mean()) if not unblocked.empty else None,
        "mean_shots_on_goal": float(attempts["shots_on_goal"].mean()),
    }
