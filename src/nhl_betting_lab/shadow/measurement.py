"""Does a modern stat forecast better than what the card runs on? Walk-forward.

Two comparisons, each on games the model could not see:

**Team strength.** The card's `TeamModel` rates attack and defence on goals.
Each shadow variant keeps that exact structure (same league rate, same home
advantage, same shrinkage, same back-to-back adjustment, same 14-day refit
cadence) and swaps only the stat a team is rated on: shots, Corsi, xG, xG
weighted toward recent games, and xG with a goaltending and a finishing
factor regressed heavily toward average, which is the reference document's
recommended stack. All are scored by one probability engine on the same
games, so a difference is the stat and nothing else.

**Prop rates.** The card prices shots on goal and goals as a shrunk per-60
box-score rate times expected ice time. The shadow versions keep the ice time
and the shrinkage and swap the rate: unblocked attempts (iFF/60) or all
attempts (iCF/60) times a shrunk on-net share for shots, and ixG/60 times a
shrunk finishing rate for goals.

**What this can and cannot say.** It measures forecasting on outcomes. That
can rule a stat out; it can never rule one in. `CLAUDE.md`: where historical
prices exist, a price backtest decides, and the market already prices most of
what these stats see. A better log-likelihood here is the precondition for
that backtest, not a claim of edge.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import poisson

from nhl_betting_lab.backtest.team_walk_forward import _with_back_to_backs
from nhl_betting_lab.models.team_model import TeamModel

REFIT_DAYS = 14
MINIMUM_HISTORY_GAMES = 200
TEAM_SHRINKAGE_GAMES = TeamModel.SHRINKAGE_GAMES
#: Goaltending and finishing are mostly noise over a season, which is the
#: point of regressing them "heavily": a team keeps a third of its measured
#: deviation after 50 games.
LUCK_SHRINKAGE_GAMES = 100
#: Recent-weighted variants halve a game's weight every this many games, and
#: halve last season's games again.
HALF_LIFE_GAMES = 30
BOOTSTRAP_DRAWS = 1000

PROP_SHRINKAGE_SECONDS = 70_000  # PlayerPropsModel.SHRINKAGE_SECONDS
PROP_MINIMUM_GAMES = 15  # PlayerPropsModel.MINIMUM_GAMES
PROP_RECENT_GAMES = 10  # PlayerPropsModel.RECENT_GAMES
ON_NET_PRIOR_ATTEMPTS = 100.0
FINISHING_PRIOR_XG = 20.0


@dataclass(frozen=True)
class TeamVariant:
    key: str
    label: str
    stat_for: str
    stat_against: str
    recent: bool = False
    luck: bool = False


TEAM_VARIANTS: tuple[TeamVariant, ...] = (
    TeamVariant("goals_recent", "Goals, weighted to recent games", "gf", "ga", recent=True),
    TeamVariant("shots", "Shots on goal (SF/SA)", "sf", "sa"),
    TeamVariant("corsi", "Corsi (CF/CA)", "cf", "ca"),
    TeamVariant("fenwick", "Fenwick (FF/FA)", "ff", "fa"),
    TeamVariant("xg", "Expected goals (xGF/xGA)", "xgf", "xga"),
    TeamVariant("xg_recent", "xG, weighted to recent games", "xgf", "xga", recent=True),
    TeamVariant(
        "xg_luck",
        "xG, recent, plus goaltending (GSAx) and finishing",
        "xgf",
        "xga",
        recent=True,
        luck=True,
    ),
)

#: The variant the public site rates teams on: the one that forecast best on
#: every column in the first measurement (2026-10-05, moneyline +7.58 per
#: 1,000 games [+3.46, +12.15] against the card's goals-based ratings).
SITE_VARIANT_KEY = "xg_luck"
#: A shadow table covering less of the model's regular-season games than this
#: is not used: the ratings would describe a different set of games from the
#: rest of the model.
SITE_MINIMUM_COVERAGE = 0.95


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _weights(history: pd.DataFrame, recent: bool) -> pd.Series:
    """Per team-game weight: 1, or a half-life by game count within a team."""
    if not recent:
        return pd.Series(1.0, index=history.index)
    ordered = history.sort_values(["team", "_date"], ascending=[True, False])
    rank = ordered.groupby("team").cumcount()
    latest = ordered.groupby("team")["season"].transform("max")
    weight = np.power(0.5, rank / HALF_LIFE_GAMES) * np.where(
        ordered["season"] < latest, 0.5, 1.0
    )
    return pd.Series(weight, index=ordered.index).reindex(history.index)


def _shrunk_ratio(numerator: float, denominator: float, games: float, k: float) -> float:
    if denominator <= 0:
        return 1.0
    weight = games / (games + k)
    return 1.0 + weight * (numerator / denominator - 1.0)


def shadow_factors(
    history: pd.DataFrame, variant: TeamVariant, home_advantage: float
) -> dict[str, dict[str, float]]:
    """attack/defence (and goalie/finishing) per team, TeamModel's construction."""
    frame = history.copy()
    frame["_w"] = _weights(frame, variant.recent)
    venue = np.where(frame["is_home"].astype(bool), 1.0 / home_advantage, home_advantage)
    frame["_for"] = frame[variant.stat_for].astype(float) * venue
    frame["_against"] = frame[variant.stat_against].astype(float) / venue
    league = float(frame[variant.stat_for].astype(float).mean())
    out: dict[str, dict[str, float]] = {}
    if league <= 0:
        return out
    for team, rows in frame.groupby("team"):
        w = rows["_w"].to_numpy()
        total = w.sum()
        if total <= 0:
            continue
        games = total**2 / float((w**2).sum())
        attack_raw = float((w * rows["_for"]).sum() / total) / league
        defence_raw = float((w * rows["_against"]).sum() / total) / league
        weight = games / (games + TEAM_SHRINKAGE_GAMES)
        factors = {
            "attack": 1.0 + weight * (attack_raw - 1.0),
            "defence": 1.0 + weight * (defence_raw - 1.0),
            "goalie": 1.0,
            "finishing": 1.0,
        }
        if variant.luck:
            factors["goalie"] = _shrunk_ratio(
                float((w * rows["goalie_ga"]).sum()),
                float((w * rows["goalie_xga"]).sum()),
                games,
                LUCK_SHRINKAGE_GAMES,
            )
            factors["finishing"] = _shrunk_ratio(
                float((w * rows["gf"]).sum()),
                float((w * rows["xgf"]).sum()),
                games,
                LUCK_SHRINKAGE_GAMES,
            )
        out[str(team)] = factors
    return out


GOAL_GRID = np.arange(0, 16)


def score_game(home_rate: float, away_rate: float, home_goals: int, away_goals: int) -> dict[str, float]:
    """Log-likelihoods under independent Poisson: goals, moneyline, total 5.5."""
    home_rate = max(home_rate, 1e-6)
    away_rate = max(away_rate, 1e-6)
    ph = poisson.pmf(GOAL_GRID, home_rate)
    pa = poisson.pmf(GOAL_GRID, away_rate)
    matrix = np.outer(ph, pa)
    home_win = float(np.tril(matrix, -1).sum() + 0.5 * np.trace(matrix))
    totals = np.add.outer(GOAL_GRID, GOAL_GRID)
    over = float(matrix[totals > 5.5].sum())
    clamp = lambda p: min(max(p, 1e-9), 1 - 1e-9)  # noqa: E731
    won = home_goals > away_goals
    went_over = home_goals + away_goals > 5.5
    return {
        "goals_ll": float(
            poisson.logpmf(home_goals, home_rate) + poisson.logpmf(away_goals, away_rate)
        ),
        "moneyline_ll": math.log(clamp(home_win) if won else clamp(1 - home_win)),
        "total_ll": math.log(clamp(over) if went_over else clamp(1 - over)),
    }


def clustered_difference(
    diffs: np.ndarray, clusters: np.ndarray, *, draws: int = BOOTSTRAP_DRAWS, seed: int = 20261005
) -> tuple[float, float, float]:
    """Mean per-row difference and a 95% interval resampling whole dates."""
    if len(diffs) == 0:
        return float("nan"), float("nan"), float("nan")
    codes, inverse = np.unique(clusters, return_inverse=True)
    sums = np.bincount(inverse, weights=diffs)
    counts = np.bincount(inverse).astype(float)
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(codes), size=(draws, len(codes)))
    means = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    return float(diffs.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _verdict(low: float, high: float) -> str:
    if low != low:
        return "not measured"
    if low > 0:
        return "better than the card's model"
    if high < 0:
        return "worse than the card's model"
    return "no demonstrated difference"


def compare_team_models(
    team_games: pd.DataFrame,
    team_metrics: pd.DataFrame,
    *,
    scored_seasons: set[int],
) -> tuple[pd.DataFrame, list[dict]]:
    """Per-game log-likelihoods for the card's model and every shadow variant."""
    games = team_games.copy()
    games = games[pd.to_numeric(games["game_type"], errors="coerce") == 2]
    for column in ("home_goals", "away_goals"):
        games[column] = pd.to_numeric(games[column], errors="coerce")
    games = games.dropna(subset=["home_goals", "away_goals"])
    games = _with_back_to_backs(games)
    games["_date"] = games["date"].map(_as_date)
    games = games.dropna(subset=["_date"]).sort_values(["_date", "game_id"])
    covered = set(team_metrics["game_id"].astype(int))
    metrics = team_metrics.merge(
        games[["game_id", "_date"]], on="game_id", how="inner"
    )

    rows: list[dict] = []
    if games.empty:
        return pd.DataFrame(rows), []
    window_start = games["_date"].min()
    last = games["_date"].max()
    while window_start <= last:
        window_end = window_start + timedelta(days=REFIT_DAYS - 1)
        history = games[games["_date"] < window_start]
        window = games[(games["_date"] >= window_start) & (games["_date"] <= window_end)]
        window_start = window_end + timedelta(days=1)
        if len(history) < MINIMUM_HISTORY_GAMES or window.empty:
            continue
        current = TeamModel().fit(history.drop(columns=["_date"]))
        shadow_history = metrics[metrics["_date"] < window["_date"].min()]
        fitted = {
            v.key: shadow_factors(shadow_history, v, current.home_advantage)
            for v in TEAM_VARIANTS
        }
        half = current.league_goals_per_game / 2.0
        for game in window.itertuples():
            gid = int(game.game_id)
            season = int(str(gid)[:4]) * 10000 + int(str(gid)[:4]) + 1
            if season not in scored_seasons or gid not in covered:
                continue
            home, away = str(game.home_team), str(game.away_team)
            hb, ab = bool(game.home_b2b), bool(game.away_b2b)
            plain = current.expected_goals(home, away)
            rested = current.expected_goals(home, away, home_b2b=hb, away_b2b=ab)
            home_mult = rested[0] / plain[0] if plain[0] > 0 else 1.0
            away_mult = rested[1] / plain[1] if plain[1] > 0 else 1.0
            hg, ag = int(game.home_goals), int(game.away_goals)
            base = {
                "game_id": gid,
                "date": str(game.date)[:10],
                "season": season,
            }
            rows.append({**base, "variant": "current", **score_game(rested[0], rested[1], hg, ag)})
            for variant in TEAM_VARIANTS:
                factors = fitted[variant.key]
                default = {"attack": 1.0, "defence": 1.0, "goalie": 1.0, "finishing": 1.0}
                h = factors.get(home, default)
                a = factors.get(away, default)
                home_rate = (
                    half * current.home_advantage * h["attack"] * a["defence"]
                    * h["finishing"] * a["goalie"] * home_mult
                )
                away_rate = (
                    half / current.home_advantage * a["attack"] * h["defence"]
                    * a["finishing"] * h["goalie"] * away_mult
                )
                rows.append(
                    {**base, "variant": variant.key, **score_game(home_rate, away_rate, hg, ag)}
                )
    frame = pd.DataFrame(rows)
    return frame, summarise(frame, [(v.key, v.label) for v in TEAM_VARIANTS],
                            ("goals_ll", "moneyline_ll", "total_ll"), id_column="game_id")


def summarise(
    frame: pd.DataFrame,
    variants: list[tuple[str, str]],
    metrics: tuple[str, ...],
    *,
    id_column: str,
    reference: str = "current",
) -> list[dict]:
    """Each variant against the reference, paired row by row, dates resampled."""
    out: list[dict] = []
    if frame.empty:
        return out
    base = frame[frame["variant"] == reference].set_index(id_column)
    for key, label in variants:
        other = frame[frame["variant"] == key].set_index(id_column)
        joined = base.join(other, rsuffix="_v", how="inner")
        entry: dict = {"variant": key, "label": label, "rows": int(len(joined))}
        for metric in metrics:
            diffs = (joined[f"{metric}_v"] - joined[metric]).to_numpy(dtype=float)
            mean, low, high = clustered_difference(diffs, joined["date"].to_numpy())
            entry[metric] = {
                "per_1000": mean * 1000,
                "low": low * 1000,
                "high": high * 1000,
                "verdict": _verdict(low, high),
            }
        out.append(entry)
    return out


PROP_VARIANTS: dict[str, list[tuple[str, str]]] = {
    "shots_on_goal": [
        ("fenwick", "Unblocked attempts (iFF/60) x on-net share"),
        ("corsi", "All attempts (iCF/60) x on-net share"),
    ],
    "goals": [
        ("ixg_finishing", "ixG/60 x shrunk finishing"),
        ("ixg", "ixG/60 x league finishing"),
    ],
}


def compare_prop_rates(
    player_logs: pd.DataFrame,
    player_metrics: pd.DataFrame,
    *,
    scored_seasons: set[int],
    covered_games: set[int],
) -> tuple[pd.DataFrame, dict[str, list[dict]]]:
    """Per player-game Poisson log-likelihoods, current rate vs shadow rates."""
    logs = player_logs.copy()
    logs = logs[pd.to_numeric(logs["game_type"], errors="coerce") == 2]
    logs = logs[logs["role"].astype(str).str.lower() == "skater"]
    logs["toi_seconds"] = pd.to_numeric(logs["toi_seconds"], errors="coerce").fillna(0)
    logs = logs[logs["toi_seconds"] > 0]
    logs = logs[logs["game_id"].astype(int).isin(covered_games)]
    pm = player_metrics[["game_id", "player_id", "icf", "iff", "ixg"]].copy()
    logs = logs.merge(pm, on=["game_id", "player_id"], how="left")
    for column in ("icf", "iff", "ixg"):
        logs[column] = logs[column].fillna(0.0)
    logs["group"] = np.where(logs["position"].astype(str).str.upper().str[0] == "D", "D", "F")
    logs["_date"] = logs["date"].map(_as_date)
    logs = logs.dropna(subset=["_date"]).sort_values(["_date", "game_id"])

    stats = ("toi_seconds", "shots_on_goal", "goals", "icf", "iff", "ixg")
    player: dict[int, dict[str, float]] = defaultdict(lambda: dict.fromkeys(stats + ("games",), 0.0))
    recent: dict[int, deque] = defaultdict(lambda: deque(maxlen=PROP_RECENT_GAMES))
    league: dict[str, dict[str, float]] = defaultdict(lambda: dict.fromkeys(stats, 0.0))

    def per60(own: dict[str, float], base: dict[str, float], stat: str) -> float:
        seconds = own["toi_seconds"]
        base_rate = base[stat] / base["toi_seconds"] * 3600 if base["toi_seconds"] else 0.0
        raw = own[stat] / seconds * 3600 if seconds else base_rate
        weight = seconds / (seconds + PROP_SHRINKAGE_SECONDS)
        return base_rate + weight * (raw - base_rate)

    def share(num: float, den: float, base_num: float, base_den: float, k: float) -> float:
        prior = base_num / base_den if base_den else 0.0
        return (num + k * prior) / (den + k)

    rows: list[dict] = []
    for day, today in logs.groupby("_date", sort=True):
        for row in today.itertuples():
            pid = int(row.player_id)
            own = player[pid]
            season = int(str(int(row.game_id))[:4]) * 10000 + int(str(int(row.game_id))[:4]) + 1
            if own["games"] >= PROP_MINIMUM_GAMES and season in scored_seasons:
                base = league[row.group]
                hours = (sum(recent[pid]) / len(recent[pid])) / 3600.0
                rates: dict[str, float] = {
                    ("shots_on_goal", "current"): per60(own, base, "shots_on_goal"),
                    ("shots_on_goal", "fenwick"): per60(own, base, "iff")
                    * share(own["shots_on_goal"], own["iff"], base["shots_on_goal"], base["iff"], ON_NET_PRIOR_ATTEMPTS),
                    ("shots_on_goal", "corsi"): per60(own, base, "icf")
                    * share(own["shots_on_goal"], own["icf"], base["shots_on_goal"], base["icf"], ON_NET_PRIOR_ATTEMPTS),
                    ("goals", "current"): per60(own, base, "goals"),
                    ("goals", "ixg_finishing"): per60(own, base, "ixg")
                    * share(own["goals"], own["ixg"], base["goals"], base["ixg"], FINISHING_PRIOR_XG),
                    ("goals", "ixg"): per60(own, base, "ixg")
                    * (base["goals"] / base["ixg"] if base["ixg"] else 1.0),
                }  # type: ignore[dict-item]
                for (stat, variant), rate in rates.items():
                    mean = max(rate * hours, 1e-6)
                    actual = int(getattr(row, stat))
                    rows.append(
                        {
                            "key": f"{int(row.game_id)}-{pid}",
                            "date": str(day),
                            "stat": stat,
                            "variant": variant,
                            "ll": float(poisson.logpmf(actual, mean)),
                        }
                    )
        for row in today.itertuples():
            pid = int(row.player_id)
            for stat in stats:
                value = float(getattr(row, stat))
                player[pid][stat] += value
                league[row.group][stat] += value
            player[pid]["games"] += 1
            recent[pid].append(float(row.toi_seconds))

    frame = pd.DataFrame(rows)
    summaries: dict[str, list[dict]] = {}
    for stat, variants in PROP_VARIANTS.items():
        part = frame[frame["stat"] == stat] if not frame.empty else frame
        summaries[stat] = summarise(part, variants, ("ll",), id_column="key")
    return frame, summaries


def validate_against_boxscores(
    team_games: pd.DataFrame, team_metrics: pd.DataFrame
) -> dict[str, float]:
    """How often play-by-play shots and goals match the boxscore exactly."""
    if team_metrics.empty or team_games.empty:
        return {"games": 0, "shots_match": 0.0, "goals_match": 0.0}
    home = team_metrics[team_metrics["is_home"].astype(bool)][["game_id", "sf", "gf"]]
    away = team_metrics[~team_metrics["is_home"].astype(bool)][["game_id", "sf", "gf"]]
    joined = (
        team_games[["game_id", "home_shots", "away_shots", "home_goals", "away_goals", "regulation"]]
        .merge(home, on="game_id")
        .merge(away, on="game_id", suffixes=("_home", "_away"))
    )
    if joined.empty:
        return {"games": 0, "shots_match": 0.0, "goals_match": 0.0}
    shots_ok = (joined["sf_home"] == joined["home_shots"]) & (joined["sf_away"] == joined["away_shots"])
    pbp_total = joined["gf_home"] + joined["gf_away"]
    final_total = joined["home_goals"] + joined["away_goals"]
    # A shootout awards the winner one goal the play-by-play never shows.
    goals_ok = (pbp_total == final_total) | ((final_total - pbp_total == 1) & ~joined["regulation"].astype(bool))
    return {
        "games": int(len(joined)),
        "shots_match": float(shots_ok.mean()),
        "goals_match": float(goals_ok.mean()),
    }


def latest_season_table(team_metrics: pd.DataFrame) -> pd.DataFrame:
    """The latest regular season's team stats, the reference doc's core list."""
    frame = team_metrics[team_metrics["game_id"].astype(str).str[4:6] == "02"]
    if frame.empty:
        return pd.DataFrame()
    season = int(frame["season"].max())
    frame = frame[frame["season"] == season]
    g = frame.groupby("team").sum(numeric_only=True)
    games = frame.groupby("team").size()
    pct: Callable[[pd.Series, pd.Series], pd.Series] = lambda f, a: 100 * f / (f + a)  # noqa: E731
    table = pd.DataFrame(
        {
            "GP": games,
            "CF%": pct(g["cf"], g["ca"]),
            "FF%": pct(g["ff"], g["fa"]),
            "xGF%": pct(g["xgf"], g["xga"]),
            "5v5 xGF%": pct(g["xgf_5v5"], g["xga_5v5"]),
            "HDFF%": pct(g["hdff"], g["hdfa"]),
            "5v5 PDO": 100 * (g["gf_5v5"] / g["sf_5v5"] + 1 - g["ga_5v5"] / g["sa_5v5"]),
            "GF-xGF": g["gf"] - g["xgf"],
            "GSAx": g["goalie_xga"] - g["goalie_ga"],
            "PP xGF/60": g["xgf_pp"] / g["toi_pp"].where(g["toi_pp"] > 0) * 3600,
            "PK xGA/60": g["xga_sh"] / g["toi_sh"].where(g["toi_sh"] > 0) * 3600,
            "Pen diff/game": (g["pen_drawn"] - g["pen_taken"]) / games,
        }
    )
    table.attrs["season"] = season
    return table.sort_values("5v5 xGF%", ascending=False).round(2)


def xg_team_ratings(
    home_advantage: float, team_games: pd.DataFrame, team_metrics: pd.DataFrame
) -> dict:
    """Attack and defence per team on `SITE_VARIANT_KEY`, for the public site.

    Built exactly as the measurement builds them: recent-weighted xGF/xGA,
    times a finishing factor on attack and a goaltending (GSAx) factor on
    defence, each regressed toward average. A `TeamModel` fitted with this
    `home_advantage` that takes these as its teams' attack and defence prices
    every market off them, as the measurement scored them.

    The public site and the card's team markets read them from the file
    `scripts/run_shadow_stats.py --tables-only` writes
    (`models.team_ratings`), never by importing this package
    (tests/test_the_shadow_model_cannot_reach_the_card.py). Raises ValueError
    when the table covers less than `SITE_MINIMUM_COVERAGE` of the
    regular-season games.
    """
    games = team_games.copy()
    games = games[pd.to_numeric(games["game_type"], errors="coerce") == 2]
    games["game_id"] = pd.to_numeric(games["game_id"], errors="coerce")
    games["_date"] = games["date"].map(_as_date)
    games = games.dropna(subset=["game_id", "_date"])
    metrics = team_metrics.copy()
    metrics["game_id"] = pd.to_numeric(metrics["game_id"], errors="coerce")
    metrics = metrics.merge(games[["game_id", "_date"]], on="game_id", how="inner")
    wanted = int(games["game_id"].nunique())
    covered = int(metrics["game_id"].nunique())
    if not wanted or covered < SITE_MINIMUM_COVERAGE * wanted:
        raise ValueError(
            f"The play-by-play table covers {covered} of {wanted} regular-season "
            f"games, under {SITE_MINIMUM_COVERAGE:.0%}."
        )
    variant = next(v for v in TEAM_VARIANTS if v.key == SITE_VARIANT_KEY)
    factors = shadow_factors(metrics, variant, home_advantage)
    return {
        "variant": SITE_VARIANT_KEY,
        "home_advantage": home_advantage,
        "games_covered": covered,
        "games_wanted": wanted,
        "last_game_date": str(games["_date"].max()),
        "teams": {
            team: {
                "attack": f["attack"] * f["finishing"],
                "defence": f["defence"] * f["goalie"],
            }
            for team, f in sorted(factors.items())
        },
    }
