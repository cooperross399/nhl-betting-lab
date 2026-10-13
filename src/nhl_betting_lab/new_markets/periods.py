"""Period markets (1st, 2nd, 3rd period): a shadow model, measured on outcomes.

Cooper asked for period markets. `docs/periphery_markets_decision.md` deferred
them because **no period model existed**, and a period price made by scaling
the full-game model would be an unmeasured model shipped under a measured
one's name. This is that model, built the way the deferral said one must
start: walk-forward, measured on outcomes first. It is not on the card and
nothing on the card's path imports it; a price backtest and Cooper's decision
come before that.

## The markets (provider keys, from the 2026-09-01 re-probe)

* `h2h_p1` / `h2h_p2` / `h2h_p3`: who wins the period, two ways. **A tied
  period is a push (stake returned).** That is inferred, not read from a
  book's rules: the provider serves a separate `h2h_3_way_p1` carrying the
  draw, and a two-way market beside a three-way one is the "draw no bet"
  shape, which voids the tie. So the two-way probability here is
  P(win | the period is not tied), and a tied period is scored nowhere in the
  two-way rows (it is counted as void). Each book's house rule must be read
  before any price backtest; a book that grades the tie as a loss for both
  sides would make this the wrong conditioning.
* `h2h_3_way_p1` (and `_p2`, `_p3`, which the probe did not see quoted):
  home, draw, away for the period alone.
* `spreads_p1..p3` at ±0.5 and ±1.5: the period's goal margin. Half lines,
  so no push. Home -0.5 is "home wins the period"; home +0.5 is "home does
  not lose it".
* `totals_p1..p3` at 0.5, 1.5 and 2.5: goals in the period, both teams.

Periods 1-3 are regulation periods. Overtime and the shootout belong to no
period market here.

## The model

1. Each side's expected full-game goals from `TeamModel` (the card's goals
   ratings, with its back-to-back factors), fitted only on games before the
   date priced. Optionally the site's xG ratings (`xg_luck`, recent xG with
   finishing and goaltending factors) built from the shadow play-by-play
   table on earlier games only.
2. A league share of a side's full-game goals scored in each period, by venue
   and period, fitted on the earlier games' play-by-play:
   share = goals in period p / final goals (overtime and the shootout goal
   included, because that is what `TeamModel`'s rate describes). The third
   period's share carries its empty-net goals; nothing else models them.
3. Each side's goals in each period are independent Poisson at
   full-game rate x share.

The naive baseline is the same Poisson with every game at the league's mean
goals per period by venue, fitted on the same earlier games: no team
information. The measurement asks whether team information helps, on outcomes;
it cannot say whether anything beats a price.

What the independent Poisson cannot see, stated rather than hidden: the score
after two periods (a team protecting a lead, a pulled goalie), so the third
period is the one most likely to be wrong; and the full-game model's known
overconfidence on favourites (`models/team_model.py`) carries straight into
every period.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from nhl_betting_lab.backtest.team_walk_forward import _with_back_to_backs
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.stats import clustered_mean_interval

PERIODS = (1, 2, 3)

#: The home side's line on the period spread. Away's are the complements:
#: home -1.5 against away +1.5, and so on.
SPREAD_LINES = (-1.5, -0.5, 0.5, 1.5)
TOTAL_LINES = (0.5, 1.5, 2.5)

#: Goals per side per period are summed to this; a period rate is under 1.5,
#: so the tail beyond is far below a millionth. The matrix is renormalised.
MAX_PERIOD_GOALS = 12

REFIT_DAYS = 14
#: Full games before the first window priced, as the shadow measurement.
MINIMUM_HISTORY_GAMES = 200
#: Games with play-by-play before a period share is trusted.
MINIMUM_PERIOD_GAMES = 200

#: A log loss on a probability of zero is infinite; clamp it.
PROBABILITY_FLOOR = 1e-12

MODELS = ("baseline", "goals", "xg")
MODEL_LABELS = {
    "baseline": "League period rates, no team information",
    "goals": "Card's goals ratings (TeamModel) x league period shares",
    "xg": "Site's xG ratings (xg_luck) x league period shares",
}


def market_key(kind: str, period: int) -> str:
    """The provider's market key: `h2h_p1`, `h2h_3_way_p2`, `spreads_p3`..."""
    return f"{kind}_p{int(period)}"


# -- parsing -----------------------------------------------------------------


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass
class PeriodGoals:
    """One game's goals by period, from the play-by-play."""

    game_id: int
    home: str
    away: str
    #: (side, period) -> goals, side "home" or "away", periods 1-3.
    goals: dict[tuple[str, int], int] = field(default_factory=dict)
    overtime: dict[str, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    shootout: bool = False
    #: Goal events whose scoring side could not be told.
    unattributed: int = 0

    def row(self) -> dict[str, Any]:
        out: dict[str, Any] = {"game_id": self.game_id, "home_team": self.home, "away_team": self.away}
        for side in ("home", "away"):
            for period in PERIODS:
                out[f"{side}_p{period}"] = self.goals.get((side, period), 0)
            out[f"{side}_ot"] = self.overtime[side]
        out["shootout"] = self.shootout
        out["unattributed"] = self.unattributed
        return out


def period_goals(payload: Mapping[str, Any]) -> PeriodGoals | None:
    """Goals in each regulation period, read from goal events.

    The scoring side is read from the running score the goal event carries
    (`details.homeScore` / `awayScore`), and from `eventOwnerTeamId` when the
    score is missing or did not move by exactly one goal. Shootout goals are
    skipped and only flag the shootout. None when the payload names no teams.
    """
    home_block = payload.get("homeTeam") or {}
    away_block = payload.get("awayTeam") or {}
    home_id = _int_or_none(home_block.get("id"))
    away_id = _int_or_none(away_block.get("id"))
    home = str(home_block.get("abbrev") or "").strip()
    away = str(away_block.get("abbrev") or "").strip()
    if home_id is None or away_id is None or not home or not away:
        return None
    result = PeriodGoals(game_id=int(_int_or_none(payload.get("id")) or 0), home=home, away=away)
    outcome = payload.get("gameOutcome") or {}
    if str(outcome.get("lastPeriodType") or "").upper() == "SO":
        result.shootout = True
    plays = [p for p in payload.get("plays") or [] if isinstance(p, Mapping)]
    if plays and all(_int_or_none(p.get("sortOrder")) is not None for p in plays):
        plays = sorted(plays, key=lambda p: int(p["sortOrder"]))
    regular_season = str(payload.get("gameType")) == "2"
    score = {"home": 0, "away": 0}
    for play in plays:
        descriptor = play.get("periodDescriptor") or {}
        number = _int_or_none(descriptor.get("number")) or 0
        kind = str(descriptor.get("periodType") or "").upper()
        if not kind:
            kind = "REG" if 1 <= number <= 3 else ("SO" if number >= 5 and regular_season else "OT")
        if kind == "SO":
            result.shootout = True
            continue
        if str(play.get("typeDescKey") or "") != "goal":
            continue
        details = play.get("details") or {}
        side: str | None = None
        home_score = _int_or_none(details.get("homeScore"))
        away_score = _int_or_none(details.get("awayScore"))
        if home_score is not None and away_score is not None:
            moved = (home_score - score["home"], away_score - score["away"])
            if moved == (1, 0):
                side = "home"
            elif moved == (0, 1):
                side = "away"
        if side is None:
            owner = _int_or_none(details.get("eventOwnerTeamId"))
            side = "home" if owner == home_id else "away" if owner == away_id else None
        if home_score is not None and away_score is not None:
            score = {"home": home_score, "away": away_score}
        elif side is not None:
            score[side] += 1
        if side is None:
            result.unattributed += 1
            continue
        if kind == "REG" and number in PERIODS:
            result.goals[(side, number)] = result.goals.get((side, number), 0) + 1
        else:
            result.overtime[side] += 1
    return result


def validate_against_boxscores(team_games: pd.DataFrame, periods: pd.DataFrame) -> dict[str, Any]:
    """How often the parsed goals rebuild the boxscore's final score.

    Final = regulation + overtime goals, plus one for the shootout winner.
    """
    games = team_games[["game_id", "home_goals", "away_goals"]].copy()
    games["game_id"] = pd.to_numeric(games["game_id"], errors="coerce")
    merged = periods.merge(games.dropna(), on="game_id", how="inner")
    if merged.empty:
        return {"games": 0, "match": float("nan")}
    home_won = merged["home_goals"].astype(float) > merged["away_goals"].astype(float)
    so = merged["shootout"].astype(bool)
    home = merged[[f"home_p{p}" for p in PERIODS]].sum(axis=1) + merged["home_ot"] + (so & home_won)
    away = merged[[f"away_p{p}" for p in PERIODS]].sum(axis=1) + merged["away_ot"] + (so & ~home_won)
    matched = (home == merged["home_goals"].astype(float)) & (away == merged["away_goals"].astype(float))
    return {"games": int(len(merged)), "match": float(matched.mean())}


# -- the model ---------------------------------------------------------------


@dataclass(frozen=True)
class PeriodShares:
    """League period shares of final goals, and league period rates, by venue."""

    #: (side, period) -> share of that side's final goals scored in the period.
    shares: dict[tuple[str, int], float]
    #: (side, period) -> mean goals in the period (the baseline's rate).
    rates: dict[tuple[str, int], float]
    games: int


def fit_period_shares(history: pd.DataFrame) -> PeriodShares:
    """Shares and rates from earlier games' period goals and final scores."""
    if history.empty:
        raise ValueError("No games with period goals to fit period shares on.")
    shares: dict[tuple[str, int], float] = {}
    rates: dict[tuple[str, int], float] = {}
    for side in ("home", "away"):
        final = float(pd.to_numeric(history[f"{side}_goals"], errors="coerce").sum())
        for period in PERIODS:
            goals = pd.to_numeric(history[f"{side}_p{period}"], errors="coerce")
            rates[(side, period)] = float(goals.mean())
            shares[(side, period)] = float(goals.sum()) / final if final > 0 else 0.0
    return PeriodShares(shares=shares, rates=rates, games=int(len(history)))


def period_matrix(home_rate: float, away_rate: float) -> np.ndarray:
    """P(home = i, away = j) in one period, independent Poisson, renormalised."""
    grid = np.arange(MAX_PERIOD_GOALS + 1)

    def pmf(rate: float) -> np.ndarray:
        rate = max(float(rate), 1e-9)
        logs = grid * math.log(rate) - rate - np.array([math.lgamma(k + 1) for k in grid])
        return np.exp(logs)

    matrix = np.outer(pmf(home_rate), pmf(away_rate))
    return matrix / matrix.sum()


def period_probabilities(home_rate: float, away_rate: float) -> dict[str, Any]:
    """Every period market at once.

    `h2h` is two-way with the tie a push: `home` and `away` are conditioned on
    no tie and `push` is P(tie). `spreads` maps home's line to P(home covers);
    `totals` maps the line to P(over).
    """
    matrix = period_matrix(home_rate, away_rate)
    grid = np.arange(matrix.shape[0])
    margin = np.subtract.outer(grid, grid)
    total = np.add.outer(grid, grid)
    home = float(matrix[margin > 0].sum())
    draw = float(matrix[margin == 0].sum())
    away = float(matrix[margin < 0].sum())
    decided = home + away
    return {
        "h2h": {
            "home": home / decided if decided > 0 else 0.5,
            "away": away / decided if decided > 0 else 0.5,
            "push": draw,
        },
        "three_way": {"home": home, "draw": draw, "away": away},
        "spreads": {line: float(matrix[margin + line > 0].sum()) for line in SPREAD_LINES},
        "totals": {line: float(matrix[total > line].sum()) for line in TOTAL_LINES},
    }


def _spread_label(line: float) -> str:
    return f"home {line:+.1f}"


def _binary(p: float, y: bool) -> tuple[float, float]:
    p = min(max(float(p), PROBABILITY_FLOOR), 1 - PROBABILITY_FLOOR)
    return -math.log(p if y else 1 - p), (p - float(y)) ** 2


def score_period(probabilities: Mapping[str, Any], period: int, home_goals: int, away_goals: int) -> list[dict]:
    """Log loss and Brier for every market and line of one period.

    One row per (market, line). Two-sided markets are one binary each (home
    -1.5 and away +1.5 are the same question). A tied period voids the
    two-way h2h, which then has a row with `void` set and no score.
    """
    rows: list[dict] = []
    margin = home_goals - away_goals
    h2h = probabilities["h2h"]
    if margin == 0:
        rows.append({"market": market_key("h2h", period), "line": "home", "p": h2h["home"],
                     "y": float("nan"), "log_loss": float("nan"), "brier": float("nan"), "void": True})
    else:
        loss, brier = _binary(h2h["home"], margin > 0)
        rows.append({"market": market_key("h2h", period), "line": "home", "p": h2h["home"],
                     "y": float(margin > 0), "log_loss": loss, "brier": brier, "void": False})
    three = probabilities["three_way"]
    outcome = "home" if margin > 0 else "away" if margin < 0 else "draw"
    p_outcome = min(max(three[outcome], PROBABILITY_FLOOR), 1.0)
    rows.append({
        "market": market_key("h2h_3_way", period), "line": "home/draw/away", "p": three[outcome],
        "y": 1.0, "log_loss": -math.log(p_outcome),
        "brier": sum((three[k] - float(k == outcome)) ** 2 for k in ("home", "draw", "away")),
        "void": False,
    })
    for line, p in probabilities["spreads"].items():
        loss, brier = _binary(p, margin + line > 0)
        rows.append({"market": market_key("spreads", period), "line": _spread_label(line), "p": p,
                     "y": float(margin + line > 0), "log_loss": loss, "brier": brier, "void": False})
    for line, p in probabilities["totals"].items():
        went_over = home_goals + away_goals > line
        loss, brier = _binary(p, went_over)
        rows.append({"market": market_key("totals", period), "line": f"over {line:.1f}", "p": p,
                     "y": float(went_over), "log_loss": loss, "brier": brier, "void": False})
    for row in rows:
        row["period"] = int(period)
    return rows


# -- walk-forward ------------------------------------------------------------


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _regular_finals(team_games: pd.DataFrame) -> pd.DataFrame:
    games = team_games.copy()
    games = games[pd.to_numeric(games["game_type"], errors="coerce") == 2]
    games["game_id"] = pd.to_numeric(games["game_id"], errors="coerce")
    for column in ("home_goals", "away_goals"):
        games[column] = pd.to_numeric(games[column], errors="coerce")
    games = games.dropna(subset=["game_id", "home_goals", "away_goals"])
    games["game_id"] = games["game_id"].astype(int)
    games = _with_back_to_backs(games)
    games["_date"] = games["date"].map(_as_date)
    return games.dropna(subset=["_date"]).sort_values(["_date", "game_id"])


def _xg_factors(metrics: pd.DataFrame, home_advantage: float) -> dict[str, dict[str, float]]:
    # Imported here so a run without the shadow table never needs it.
    from nhl_betting_lab.shadow import measurement

    variant = next(v for v in measurement.TEAM_VARIANTS if v.key == measurement.SITE_VARIANT_KEY)
    if metrics.empty or not measurement._has_columns(metrics, variant):
        return {}
    return measurement.shadow_factors(metrics, variant, home_advantage)


def walk_forward(
    team_games: pd.DataFrame,
    periods: pd.DataFrame,
    *,
    xg_metrics: pd.DataFrame | None = None,
    refit_days: int = REFIT_DAYS,
    minimum_history: int = MINIMUM_HISTORY_GAMES,
    minimum_period_history: int = MINIMUM_PERIOD_GAMES,
) -> pd.DataFrame:
    """Score every regular-season game with period goals, refitting every window.

    Each window of `refit_days` is priced on a `TeamModel` and period shares
    fitted only on games dated before the window. With `xg_metrics` (the
    shadow play-by-play team table), the xG ratings are scored too. Returns
    one row per (game, model, period, market, line).
    """
    games = _regular_finals(team_games)
    columns = ["game_id", "date", "season", "model", "period", "market", "line",
               "p", "y", "log_loss", "brier", "void"]
    if games.empty or periods.empty:
        return pd.DataFrame(columns=columns)
    table = periods.drop(columns=[c for c in ("home_team", "away_team") if c in periods]).copy()
    table["game_id"] = pd.to_numeric(table["game_id"], errors="coerce")
    table = table.dropna(subset=["game_id"]).drop_duplicates("game_id")
    table["game_id"] = table["game_id"].astype(int)
    period_frame = games.merge(table, on="game_id", how="inner")
    by_game = period_frame.set_index("game_id")
    metrics = pd.DataFrame()
    if xg_metrics is not None and not xg_metrics.empty:
        metrics = xg_metrics.copy()
        metrics["game_id"] = pd.to_numeric(metrics["game_id"], errors="coerce")
        metrics = metrics.merge(games[["game_id", "_date"]], on="game_id", how="inner")

    rows: list[dict] = []
    window_start = games["_date"].min()
    last = games["_date"].max()
    while window_start <= last:
        window_end = window_start + timedelta(days=refit_days - 1)
        history = games[games["_date"] < window_start]
        window = period_frame[(period_frame["_date"] >= window_start) & (period_frame["_date"] <= window_end)]
        start = window_start
        window_start = window_end + timedelta(days=1)
        if len(history) < minimum_history or window.empty:
            continue
        period_history = period_frame[period_frame["_date"] < start]
        if len(period_history) < minimum_period_history:
            continue
        model = TeamModel().fit(history.drop(columns=["_date"]))
        shares = fit_period_shares(period_history)
        xg = _xg_factors(metrics[metrics["_date"] < start], model.home_advantage) if not metrics.empty else {}
        half = model.league_goals_per_game / 2.0
        for game in window.itertuples():
            gid = int(game.game_id)
            home, away = str(game.home_team), str(game.away_team)
            hb, ab = bool(game.home_b2b), bool(game.away_b2b)
            full = {"goals": model.expected_goals(home, away, home_b2b=hb, away_b2b=ab)}
            if xg:
                plain = model.expected_goals(home, away)
                home_mult = full["goals"][0] / plain[0] if plain[0] > 0 else 1.0
                away_mult = full["goals"][1] / plain[1] if plain[1] > 0 else 1.0
                default = {"attack": 1.0, "defence": 1.0, "goalie": 1.0, "finishing": 1.0}
                h, a = xg.get(home, default), xg.get(away, default)
                full["xg"] = (
                    half * model.home_advantage * h["attack"] * a["defence"] * h["finishing"] * a["goalie"] * home_mult,
                    half / model.home_advantage * a["attack"] * h["defence"] * a["finishing"] * h["goalie"] * away_mult,
                )
            record = by_game.loc[gid]
            base = {"game_id": gid, "date": str(game.date)[:10], "season": getattr(game, "season", "")}
            for period in PERIODS:
                hg = int(record[f"home_p{period}"])
                ag = int(record[f"away_p{period}"])
                rates = {"baseline": (shares.rates[("home", period)], shares.rates[("away", period)])}
                for key, (home_full, away_full) in full.items():
                    rates[key] = (
                        home_full * shares.shares[("home", period)],
                        away_full * shares.shares[("away", period)],
                    )
                for key, (home_rate, away_rate) in rates.items():
                    probabilities = period_probabilities(home_rate, away_rate)
                    for row in score_period(probabilities, period, hg, ag):
                        rows.append({**base, "model": key, **row})
    return pd.DataFrame(rows, columns=columns)


# -- summary -----------------------------------------------------------------


def _finite(value: float) -> float | None:
    return float(value) if value == value and math.isfinite(value) else None


def _verdict(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "not measured"
    if low > 0:
        return "better than the baseline"
    if high < 0:
        return "worse than the baseline"
    return "no demonstrated difference"


def summarise(scored: pd.DataFrame) -> list[dict]:
    """Each model against the baseline, per (market, line), per market, overall.

    Gains are baseline minus model, per 1,000 rows, so positive is better.
    Intervals are clustered on the game (`stats.clustered_mean_interval`):
    the rows of one game share its outcome. `adjusted_low/high` correct for
    every (market, line) measured for that model.
    """
    if scored.empty:
        return []
    live = scored[~scored["void"].astype(bool)]
    keys = ["game_id", "period", "market", "line"]
    baseline = live[live["model"] == "baseline"][keys + ["log_loss", "brier"]]
    void_counts = scored[(scored["model"] == "baseline") & scored["void"].astype(bool)].groupby(["market", "line"]).size()
    out: list[dict] = []
    for model in [m for m in MODELS if m != "baseline" and m in set(live["model"])]:
        mine = live[live["model"] == model][keys + ["log_loss", "brier", "p", "y"]]
        paired = mine.merge(baseline, on=keys, suffixes=("", "_base"))
        if paired.empty:
            continue
        paired["ll_gain"] = 1000.0 * (paired["log_loss_base"] - paired["log_loss"])
        paired["brier_gain"] = 1000.0 * (paired["brier_base"] - paired["brier"])
        cells = list(paired.groupby(["market", "line"], sort=False))
        looks = len(cells)
        family = f"{looks} market-lines measured for this model"

        def summary(frame: pd.DataFrame, market: str, line: str, scope: str) -> dict:
            ll = clustered_mean_interval(frame["ll_gain"], frame["game_id"], looks=looks, family=family)
            br = clustered_mean_interval(frame["brier_gain"], frame["game_id"], looks=looks, family=family)
            binary = not market.startswith("h2h_3_way") and scope == "line"
            low, high = _finite(ll.low), _finite(ll.high)
            return {
                "model": model,
                "scope": scope,
                "market": market,
                "line": line,
                "rows": int(len(frame)),
                "games": int(frame["game_id"].nunique()),
                "void": int(void_counts.get((market, line), 0)) if scope == "line" else None,
                "log_loss": float(frame["log_loss"].mean()),
                "baseline_log_loss": float(frame["log_loss_base"].mean()),
                "ll_gain_per_1000": float(ll.roi),
                "low": low,
                "high": high,
                "adjusted_low": _finite(ll.adjusted_low),
                "adjusted_high": _finite(ll.adjusted_high),
                "brier": float(frame["brier"].mean()),
                "baseline_brier": float(frame["brier_base"].mean()),
                "brier_gain_per_1000": float(br.roi),
                "brier_low": _finite(br.low),
                "brier_high": _finite(br.high),
                "mean_p": float(frame["p"].mean()) if binary else None,
                "observed": float(frame["y"].mean()) if binary else None,
                "verdict": _verdict(low, high),
            }

        for (market, line), frame in cells:
            out.append(summary(frame, str(market), str(line), "line"))
        for market, frame in paired.groupby("market", sort=False):
            out.append(summary(frame, str(market), "all lines", "market"))
        out.append(summary(paired, "all period markets", "all lines", "overall"))
    return out
