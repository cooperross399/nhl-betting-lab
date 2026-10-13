"""Shadow models for three player props the card does not price.

The provider accepts `player_power_play_points`, `player_faceoffs_won` and
`player_shots` as market keys (`docs/periphery_markets_decision.md`,
re-probed 2026-09-01), and this lab has never modelled any of them. Cooper
asked for them on 2026-10-13. This module builds them beside the card, the
way the modern-stats shadow model was built, and measures them walk-forward
on outcomes only. **That can rule a model out and never in**: nothing here
has met a price, and reaching the card needs a price backtest and Cooper's
sign-off. Nothing on the card's path may import it
(`tests/test_player_extras.py` holds that apart).

## Where the counts come from

The boxscore cannot settle any of the three. It carries `powerPlayGoals` and
no power-play assists, and a faceoff percentage with no counts. So every
count is read from the NHL's free play-by-play
(`api-web.nhle.com/v1/gamecenter/{id}/play-by-play`), from the same cache
`nhl_betting_lab.shadow` writes (`data/raw/nhl/play_by_play/<id>.json`). This
module reads that cache with its own small fetcher instead of importing the
shadow package, because no module outside `shadow` may import it.

* **Power-play points** = power-play goals + power-play assists, from `goal`
  events (`scoringPlayerId`, `assist1PlayerId`, `assist2PlayerId`). A goal is
  a power-play goal when, by its `situationCode`, the scoring side has more
  skaters than the other once an empty net's extra attacker is taken off
  each side (`is_power_play`). So a 6-on-5 with the scoring side's goalie
  pulled for a delayed penalty is not a power play, and a 5-on-4 against a
  pulled goalie still is. The run checks every player's power-play goals
  against the boxscore's `powerPlayGoals`, which settles that rule on the
  goals and says nothing about the assists beyond them.
* **Faceoffs won** and **faceoffs taken**, from `faceoff` events
  (`winningPlayerId`, `losingPlayerId`).
* **Shot attempts** = goals + shots on goal + missed shots + the player's
  attempts the opponent blocked (`goal`, `shot-on-goal`, `missed-shot`,
  `blocked-shot`, each by its shooter). **Unblocked attempts** leave the
  blocked ones out.

**`player_shots` is ASSUMED to mean shot attempts.** The provider names it
apart from `player_shots_on_goal`, which is all this lab knows of it; no
posted line has been read. Before anything is settled on it, read a book's
posted `player_shots` line for a player and compare it with his attempts and
his unblocked attempts: a line near his shots on goal would mean the key is
shots on goal under another name, and neither count here would settle it.
Both counts are modelled and measured so either reading can be settled.

The shootout is excluded everywhere, as in the shadow model.

## The model

For each player-game, from games strictly before its date only:

1. **Rates per sixty minutes**, shrunk toward the league rate of the
   player's position group (centre, wing, defence: the roster's
   `positionCode`) in proportion to the ice time behind them, as
   `PlayerPropsModel` shrinks its rates (`SHRINKAGE_SECONDS`).
2. **Faceoffs won** = faceoffs taken per sixty over the last ten games (the
   player's current role, not shrunk) x a win rate over his whole history,
   shrunk toward the group's on faceoffs taken (`FACEOFF_WIN_SHRINKAGE`).
3. **Times expected ice time**, the mean of the last ten games, as the prop
   model does (`RECENT_GAMES`).
4. **A count distribution**: Poisson, or a negative binomial whose
   dispersion is fitted walk-forward on the model's own earlier residuals,
   per market and position group (`dispersion` columns). A count measured
   underdispersed (faceoffs can be) stays Poisson, which overstates its
   tails; the report prints the measured variance ratio so that shows.

The constants are stated choices, not tuned: nothing here was swept.

What it does not have: power-play ice time (only all-situation ice time
scales the power-play rate, so a promotion to the first unit shows up only
as it accumulates), opponents, venue, rest and linemates. Each is a
candidate for later, measured the same way.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

from nhl_betting_lab.data.nhl_api import (
    API_BASE_URL,
    CacheEntry,
    NhlApiError,
    Requester,
    _cache_root,
    _default_requester,
    _get_json,
    _read_cache,
    _write_cache,
    game_is_final,
)
from nhl_betting_lab.stats import clustered_mean_interval, clustered_wilson_interval


@dataclass(frozen=True)
class ExtraMarket:
    """One market as the measurement prices it."""

    name: str
    #: The provider's key. `player_shots` is an assumption; see the docstring.
    provider_key: str
    #: The count column it settles on.
    column: str
    lines: tuple[float, ...]
    #: Measured only on players who take faceoffs (`TAKER_FACEOFFS_PER_GAME`).
    takers_only: bool = False


MARKETS: tuple[ExtraMarket, ...] = (
    ExtraMarket("power_play_points", "player_power_play_points", "ppp", (0.5, 1.5)),
    ExtraMarket(
        "faceoffs_won",
        "player_faceoffs_won",
        "faceoffs_won",
        tuple(k + 0.5 for k in range(2, 16)),
        takers_only=True,
    ),
    ExtraMarket(
        "shot_attempts", "player_shots", "shot_attempts", tuple(k + 0.5 for k in range(1, 8))
    ),
    ExtraMarket(
        "unblocked_attempts",
        "player_shots",
        "unblocked_attempts",
        tuple(k + 0.5 for k in range(1, 8)),
    ),
)

#: Every count column the per player-game table carries.
COUNT_COLUMNS: tuple[str, ...] = (
    "goals",
    "shots_on_goal",
    "ppg",
    "ppa",
    "ppp",
    "faceoffs_won",
    "faceoffs_taken",
    "shot_attempts",
    "unblocked_attempts",
)

TABLE_COLUMNS: tuple[str, ...] = (
    "player_id",
    "game_id",
    "season",
    "game_type",
    "date",
    "team",
    "opponent",
    "position",
    *COUNT_COLUMNS,
)

#: Ice time at which a player keeps half his measured deviation from his
#: group's rate. Power-play points use the prop model's 70,000 seconds;
#: attempts and faceoffs are far more frequent events, so their rates settle
#: sooner and keep more of the player's own number.
SHRINKAGE_SECONDS: dict[str, float] = {
    "ppp": 70_000.0,
    "faceoffs_taken": 15_000.0,
    "shot_attempts": 25_000.0,
    "unblocked_attempts": 25_000.0,
}

#: Faceoffs taken at which a player keeps half his win rate's deviation.
FACEOFF_WIN_SHRINKAGE = 300.0

#: Games behind the expected ice time and the naive baseline.
RECENT_GAMES = 10

#: A player with fewer earlier games in the table is not priced.
MIN_GAMES = 10

#: Faceoff lines are measured on players taking at least this many a game
#: over their last `RECENT_GAMES`, known before the game: books post faceoff
#: props for the players who take them, mostly centres.
TAKER_FACEOFFS_PER_GAME = 5.0

#: Earlier priced rows a group needs before its dispersion is trusted.
MIN_DISPERSION_ROWS = 500

#: A fitted 1/r below this is Poisson (r above `models.counts.MAX_DISPERSION_R`).
MIN_INVERSE_R = 1.0 / 500.0

#: Probabilities are held inside [EPS, 1 - EPS] before a log loss, for the
#: model and the baseline alike, so a naive mean of zero costs a bounded
#: amount rather than infinity.
EPS = 1e-3

GROUPS = ("C", "W", "D")


# -- reading the play-by-play ---------------------------------------------


def fetch_play_by_play(
    game_id: int,
    *,
    requester: Requester | None = None,
    raw_dir: Path | None = None,
) -> CacheEntry:
    """One game's play-by-play, from the shared cache once it is final.

    The same path and rule as `shadow.play_by_play.fetch_play_by_play`
    (only a final game is written, and never fetched again), kept here
    because nothing outside `shadow` may import it.
    """
    identifier = int(game_id)
    if identifier <= 0:
        raise NhlApiError(f"{game_id!r} is not a usable NHL game id.")
    path = play_by_play_path(identifier, raw_dir=raw_dir)
    cached = _read_cache(path)
    if cached is not None and game_is_final(cached):
        return CacheEntry(path=path, payload=cached, from_cache=True, complete=True)
    payload = _get_json(
        f"{API_BASE_URL}/v1/gamecenter/{identifier}/play-by-play",
        requester=requester or _default_requester,
    )
    complete = game_is_final(payload)
    if complete:
        _write_cache(path, payload)
    return CacheEntry(path=path, payload=payload, from_cache=False, complete=complete)


def play_by_play_path(game_id: int, *, raw_dir: Path | None = None) -> Path:
    return _cache_root(raw_dir) / "play_by_play" / f"{int(game_id)}.json"


def read_cached_play_by_play(game_id: int, *, raw_dir: Path | None = None) -> Any | None:
    return _read_cache(play_by_play_path(game_id, raw_dir=raw_dir))


def _int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_situation(code: object) -> tuple[int, int, int, int] | None:
    """`situationCode` as (away goalie, away skaters, home skaters, home goalie)."""
    text = str(code or "").strip()
    if len(text) != 4 or not text.isdigit():
        return None
    a, b, c, d = (int(ch) for ch in text)
    return a, b, c, d


def is_power_play(situation: tuple[int, int, int, int], *, home: bool) -> bool:
    """Whether one side is on the power play in this situation.

    Each side's skaters are counted without an extra attacker for an empty
    net, because pulling a goalie changes the skaters on the ice and not the
    penalties: 6-on-5 with your own net empty (a delayed penalty, a late
    push) is not a power play, and 5-on-4 against a pulled goalie (shown as
    5-on-5) still is.
    """
    away_goalie, away_skaters, home_skaters, home_goalie = situation
    away_eff = away_skaters - (1 if away_goalie == 0 else 0)
    home_eff = home_skaters - (1 if home_goalie == 0 else 0)
    return home_eff > away_eff if home else away_eff > home_eff


def _is_shootout(play: Mapping[str, Any], game_type: object) -> bool:
    descriptor = play.get("periodDescriptor") or {}
    kind = str(descriptor.get("periodType") or "").upper()
    if kind:
        return kind == "SO"
    number = _int(descriptor.get("number")) or 0
    return number >= 5 and str(game_type) == "2"


def position_group(code: object) -> str:
    """`C` -> C; `L`, `R`, `W`, `F` -> W; `D` -> D; a goalie or nothing -> ""."""
    text = str(code or "").strip().upper()
    if not text or text.startswith("G"):
        return ""
    if text.startswith("C"):
        return "C"
    if text.startswith("D"):
        return "D"
    if text[0] in {"L", "R", "W", "F"}:
        return "W"
    return ""


@dataclass
class GameCounts:
    """One game's per-skater counts, and what could not be read."""

    game_id: int
    rows: list[dict[str, Any]]
    #: Goals whose strength could not be read (no usable situationCode).
    goals_without_strength: int = 0
    #: Events naming a player the game's roster does not list.
    unknown_players: int = 0


def player_game_counts(payload: Mapping[str, Any]) -> GameCounts:
    """Every dressed skater's power-play points, faceoffs and attempts."""
    game_id = _int(payload.get("id")) or 0
    home_block = payload.get("homeTeam") or {}
    away_block = payload.get("awayTeam") or {}
    home_id, away_id = _int(home_block.get("id")), _int(away_block.get("id"))
    abbrevs = {
        home_id: str(home_block.get("abbrev") or "").strip(),
        away_id: str(away_block.get("abbrev") or "").strip(),
    }
    result = GameCounts(game_id=game_id, rows=[])
    if home_id is None or away_id is None or not abbrevs[home_id] or not abbrevs[away_id]:
        return result
    game_type = payload.get("gameType")
    base = {
        "game_id": game_id,
        "season": _int(payload.get("season")),
        "game_type": _int(game_type),
        "date": str(payload.get("gameDate") or "")[:10],
    }

    counts: dict[int, dict[str, Any]] = {}
    goalies: set[int] = set()
    for spot in payload.get("rosterSpots") or []:
        if not isinstance(spot, Mapping):
            continue
        player, team = _int(spot.get("playerId")), _int(spot.get("teamId"))
        if player is None or team not in abbrevs:
            continue
        code = str(spot.get("positionCode") or "").strip().upper()
        if code.startswith("G"):
            goalies.add(player)
            continue
        counts[player] = {
            **base,
            "player_id": player,
            "team": abbrevs[team],
            "opponent": abbrevs[away_id if team == home_id else home_id],
            "position": code,
            **{column: 0 for column in COUNT_COLUMNS},
        }

    def bump(player: int | None, *columns: str) -> None:
        if player is None or player in goalies:
            return
        row = counts.get(player)
        if row is None:
            result.unknown_players += 1
            return
        for column in columns:
            row[column] += 1

    for play in payload.get("plays") or []:
        if not isinstance(play, Mapping) or _is_shootout(play, game_type):
            continue
        kind = str(play.get("typeDescKey") or "")
        details = play.get("details") or {}
        if kind == "goal":
            scorer = _int(details.get("scoringPlayerId"))
            bump(scorer, "goals", "shots_on_goal", "shot_attempts", "unblocked_attempts")
            team = counts[scorer]["team"] if scorer in counts else None
            if team is None:
                owner = _int(details.get("eventOwnerTeamId"))
                team = abbrevs.get(owner) if owner is not None else None
            situation = parse_situation(play.get("situationCode"))
            if situation is None or team not in (abbrevs[home_id], abbrevs[away_id]):
                result.goals_without_strength += 1
                continue
            if is_power_play(situation, home=team == abbrevs[home_id]):
                bump(scorer, "ppg", "ppp")
                for key in ("assist1PlayerId", "assist2PlayerId"):
                    bump(_int(details.get(key)), "ppa", "ppp")
        elif kind == "shot-on-goal":
            bump(_int(details.get("shootingPlayerId")), "shots_on_goal", "shot_attempts", "unblocked_attempts")
        elif kind == "missed-shot":
            bump(_int(details.get("shootingPlayerId")), "shot_attempts", "unblocked_attempts")
        elif kind == "blocked-shot":
            bump(_int(details.get("shootingPlayerId")), "shot_attempts")
        elif kind == "faceoff":
            bump(_int(details.get("winningPlayerId")), "faceoffs_won", "faceoffs_taken")
            bump(_int(details.get("losingPlayerId")), "faceoffs_taken")
    result.rows = list(counts.values())
    return result


def build_counts(payloads: Iterable[Mapping[str, Any]]) -> tuple[pd.DataFrame, dict[str, int]]:
    """The per player-game table, and what the parse could not read."""
    rows: list[dict[str, Any]] = []
    summary = {"games": 0, "goals_without_strength": 0, "unknown_players": 0}
    for payload in payloads:
        game = player_game_counts(payload)
        if not game.rows:
            continue
        summary["games"] += 1
        summary["goals_without_strength"] += game.goals_without_strength
        summary["unknown_players"] += game.unknown_players
        rows.extend(game.rows)
    table = pd.DataFrame(rows, columns=list(TABLE_COLUMNS))
    if not table.empty:
        table = table.sort_values(["date", "game_id", "team", "player_id"], ignore_index=True)
    return table, summary


def attach_ice_time(counts: pd.DataFrame, logs: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Join each counted skater to his boxscore line: ice time and checks.

    Inner join on (game, player): a row the boxscore does not hold has no
    ice time and is not priced. `box_*` columns carry the boxscore's goals,
    shots on goal and power-play goals so `validate` can compare them.
    """
    wanted = ["game_id", "player_id", "toi_seconds", "goals", "shots_on_goal", "power_play_goals", "position"]
    skaters = logs[logs["role"].astype(str) == "skater"] if "role" in logs else logs
    box = skaters[[c for c in wanted if c in skaters.columns]].rename(
        columns={
            "goals": "box_goals",
            "shots_on_goal": "box_sog",
            "power_play_goals": "box_ppg",
            "position": "box_position",
        }
    )
    box = box.drop_duplicates(["game_id", "player_id"])
    frame = counts.copy()
    for column in ("game_id", "player_id"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        box[column] = pd.to_numeric(box[column], errors="coerce")
    merged = frame.merge(box, on=["game_id", "player_id"], how="inner")
    if "box_position" in merged:
        blank = merged["position"].astype(str).str.strip().isin({"", "nan", "None"})
        merged.loc[blank, "position"] = merged.loc[blank, "box_position"]
        merged = merged.drop(columns=["box_position"])
    shared = set(frame["game_id"]) & set(box["game_id"])
    box_shared = box[box["game_id"].isin(shared)]
    summary = {
        "counted_rows": int(len(frame)),
        "matched_rows": int(len(merged)),
        "counted_without_boxscore": int(len(frame) - len(merged)),
        "boxscore_without_count": int(len(box_shared) - len(merged)),
    }
    return merged, summary


def validate(table: pd.DataFrame) -> dict[str, float]:
    """Share of player-games where the play-by-play agrees with the boxscore."""
    out: dict[str, float] = {"rows": float(len(table))}
    for ours, theirs, label in (
        ("goals", "box_goals", "goals_match"),
        ("shots_on_goal", "box_sog", "shots_on_goal_match"),
        ("ppg", "box_ppg", "power_play_goals_match"),
    ):
        if theirs not in table or table.empty:
            out[label] = float("nan")
            continue
        a = pd.to_numeric(table[ours], errors="coerce")
        b = pd.to_numeric(table[theirs], errors="coerce")
        known = b.notna()
        out[label] = float((a[known] == b[known]).mean()) if known.any() else float("nan")
    return out


# -- the walk-forward model --------------------------------------------------


def _shrunk_rate(prior: pd.Series, prior_toi: pd.Series, base: pd.Series, base_toi: pd.Series, k: float) -> pd.Series:
    """Per-60 rate shrunk toward the group's, by the ice time behind it."""
    base60 = (base / base_toi.where(base_toi > 0)) * 3600.0
    raw60 = (prior / prior_toi.where(prior_toi > 0)) * 3600.0
    weight = prior_toi / (prior_toi + k)
    return base60 + weight * (raw60.fillna(base60) - base60)


def walk_forward(table: pd.DataFrame, *, min_games: int = MIN_GAMES) -> pd.DataFrame:
    """Every player-game with each market's mean and dispersion, from the past only.

    Needs `toi_seconds` (from `attach_ice_time`). Adds, per market in
    `MARKETS`: `mu_<name>` (the model's mean), `inv_r_<name>` (negative
    binomial 1/r; 0 is Poisson) and `naive_<name>` (the trailing-ten mean),
    plus `priced` (enough history to price) and `faceoff_taker`.
    """
    frame = table.copy()
    for column in (*COUNT_COLUMNS, "toi_seconds"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype(float)
    frame = frame[frame["toi_seconds"] > 0].copy()
    frame["date"] = frame["date"].astype(str).str[:10]
    frame["group"] = frame["position"].map(position_group)
    frame = frame[frame["group"].isin(GROUPS)]
    frame = frame.sort_values(["player_id", "date", "game_id"], ignore_index=True)
    if frame.empty:
        return frame

    by_player = frame.groupby("player_id", sort=False)
    frame["prior_games"] = by_player.cumcount()
    rolling_columns = ["toi_seconds", *COUNT_COLUMNS]
    for column in rolling_columns:
        frame[f"prior_{column}"] = by_player[column].cumsum() - frame[column]
        frame[f"trail_{column}"] = by_player[column].transform(
            lambda s: s.shift(1).rolling(RECENT_GAMES, min_periods=1).mean()
        )
    frame["expected_toi"] = frame["trail_toi_seconds"]

    daily = frame.groupby(["group", "date"])[rolling_columns].sum().sort_index()
    before = daily.groupby(level="group").cumsum() - daily
    before.columns = [f"base_{c}" for c in before.columns]
    frame = frame.merge(before.reset_index(), on=["group", "date"], how="left")

    prior_toi, base_toi = frame["prior_toi_seconds"], frame["base_toi_seconds"]
    scale = frame["expected_toi"] / 3600.0
    for column in ("ppp", "shot_attempts", "unblocked_attempts"):
        rate = _shrunk_rate(frame[f"prior_{column}"], prior_toi, frame[f"base_{column}"], base_toi, SHRINKAGE_SECONDS[column])
        frame[f"mu_{column}"] = rate * scale
    # Faceoffs taken follow the player's current role (who takes the draws
    # on his line), not his career: a career rate shrunk toward the group
    # under-forecast takers by 0.5 a game (Shadow Stats run 38460470412,
    # model mean 5.385 against 5.891 observed, and the trailing mean beat
    # it). So the workload is his last ten games' rate per sixty, and only
    # the win rate is shrunk on his whole history.
    career_taken = _shrunk_rate(
        frame["prior_faceoffs_taken"], prior_toi, frame["base_faceoffs_taken"], base_toi, SHRINKAGE_SECONDS["faceoffs_taken"]
    )
    recent_taken = (frame["trail_faceoffs_taken"] * 3600.0 / frame["trail_toi_seconds"].where(frame["trail_toi_seconds"] > 0))
    taken = recent_taken.fillna(career_taken)
    base_win = (frame["base_faceoffs_won"] / frame["base_faceoffs_taken"].where(frame["base_faceoffs_taken"] > 0)).fillna(0.5)
    raw_win = (frame["prior_faceoffs_won"] / frame["prior_faceoffs_taken"].where(frame["prior_faceoffs_taken"] > 0)).fillna(base_win)
    win_weight = frame["prior_faceoffs_taken"] / (frame["prior_faceoffs_taken"] + FACEOFF_WIN_SHRINKAGE)
    frame["faceoff_win_rate"] = base_win + win_weight * (raw_win - base_win)
    frame["mu_faceoffs_taken"] = taken * scale
    frame["mu_faceoffs_won"] = frame["mu_faceoffs_taken"] * frame["faceoff_win_rate"]

    frame["priced"] = (
        (frame["prior_games"] >= min_games)
        & (frame["expected_toi"] > 0)
        & (base_toi > 0)
    )
    frame["faceoff_taker"] = frame["trail_faceoffs_taken"] >= TAKER_FACEOFFS_PER_GAME

    for market in MARKETS:
        mu = f"mu_{market.column}"
        frame[f"mu_{market.name}"] = frame[mu].clip(lower=1e-6)
        frame[f"naive_{market.name}"] = frame[f"trail_{market.column}"]
        frame[f"inv_r_{market.name}"] = _walk_forward_dispersion(frame, market)
    return frame.sort_values(["date", "game_id", "team", "player_id"], ignore_index=True)


def _walk_forward_dispersion(frame: pd.DataFrame, market: ExtraMarket) -> pd.Series:
    """Negative binomial 1/r per row, from earlier dates' residuals only.

    Method of moments on the model's own priced rows before the date, per
    position group: 1/r = sum((y - mu)^2 - mu) / sum(mu^2). Zero (Poisson)
    until `MIN_DISPERSION_ROWS` rows exist, or when the count was
    underdispersed.
    """
    mask = frame["priced"] & (frame["faceoff_taker"] if market.takers_only else True)
    y = frame[market.column]
    mu = frame[f"mu_{market.name}"]
    parts = pd.DataFrame(
        {
            "group": frame["group"],
            "date": frame["date"],
            "a": ((y - mu) ** 2 - mu).where(mask, 0.0),
            "b": (mu**2).where(mask, 0.0),
            "n": mask.astype(float),
        }
    )
    daily = parts.groupby(["group", "date"])[["a", "b", "n"]].sum().sort_index()
    before = (daily.groupby(level="group").cumsum() - daily).reset_index()
    joined = parts[["group", "date"]].merge(before, on=["group", "date"], how="left")
    inv = (joined["a"] / joined["b"].where(joined["b"] > 0)).fillna(0.0)
    inv = inv.where((joined["n"] >= MIN_DISPERSION_ROWS) & (inv >= MIN_INVERSE_R), 0.0)
    return pd.Series(inv.to_numpy(), index=frame.index)


def over_probability(mu: np.ndarray | pd.Series, inv_r: np.ndarray | pd.Series, line: float) -> np.ndarray:
    """P(count > line) for half-point lines: Poisson, or negative binomial."""
    if not math.isclose(line % 1.0, 0.5):
        raise ValueError(f"{line} is not a half-point line; a whole line can push.")
    k = math.floor(line)
    mean = np.clip(np.asarray(mu, dtype=float), 1e-9, None)
    inverse = np.asarray(inv_r, dtype=float)
    out = poisson.sf(k, mean)
    negative = inverse >= MIN_INVERSE_R
    if negative.any():
        r = 1.0 / inverse[negative]
        out[negative] = nbinom.sf(k, r, r / (r + mean[negative]))
    return out


# -- measurement -------------------------------------------------------------


def _log_loss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1.0 - EPS)
    return -(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))


def _interval(values: np.ndarray, games: np.ndarray, looks: int) -> dict[str, float]:
    result = clustered_mean_interval(values.tolist(), games.tolist(), looks=looks)
    return {
        "mean": result.roi,
        "low": result.low,
        "high": result.high,
        "adjusted_low": result.adjusted_low,
        "adjusted_high": result.adjusted_high,
    }


def _rate_interval(hits: np.ndarray, games: np.ndarray) -> tuple[float, float]:
    grouped = pd.DataFrame({"g": games, "h": hits}).groupby("g")["h"].agg(["sum", "count"])
    return clustered_wilson_interval(zip(grouped["sum"].astype(int), grouped["count"].astype(int)))


def _buckets(p: np.ndarray, y: np.ndarray, games: np.ndarray) -> list[dict[str, Any]]:
    edges = np.linspace(0.0, 1.0, 11)
    index = np.clip(np.digitize(p, edges[1:-1]), 0, 9)
    rows = []
    for b in range(10):
        chosen = index == b
        if not chosen.any():
            continue
        low, high = _rate_interval(y[chosen], games[chosen])
        rows.append(
            {
                "bucket": f"{int(edges[b] * 100)}-{int(edges[b + 1] * 100)}%",
                "samples": int(chosen.sum()),
                "games": int(len(set(games[chosen].tolist()))),
                "predicted": float(p[chosen].mean()),
                "observed": float(y[chosen].mean()),
                "low": low,
                "high": high,
            }
        )
    return rows


def _verdict(diff: dict[str, float], rows: int) -> str:
    if rows < 30:
        return "too few to read"
    if diff["low"] > 0:
        return "model beats the naive baseline"
    if diff["high"] < 0:
        return "naive baseline beats the model"
    return "no demonstrated difference"


def measure(predictions: pd.DataFrame, markets: tuple[ExtraMarket, ...] = MARKETS) -> dict[str, Any]:
    """Log loss, Brier and calibration per market and line, model vs naive.

    The naive baseline is the player's trailing-ten mean as a Poisson. Both
    are scored on the same rows. Differences are naive minus model (positive
    means the model is better), with 95% intervals clustered on the game,
    and a Bonferroni-adjusted pair counting every line measured.
    """
    looks = sum(len(m.lines) for m in markets)
    payload: dict[str, Any] = {"looks": looks, "markets": {}}
    if predictions.empty:
        return payload
    for market in markets:
        mask = predictions["priced"].astype(bool)
        if market.takers_only:
            mask &= predictions["faceoff_taker"].astype(bool)
        rows = predictions[mask]
        counts = rows[market.column].to_numpy(dtype=float)
        mu = rows[f"mu_{market.name}"].to_numpy(dtype=float)
        inv_r = rows[f"inv_r_{market.name}"].to_numpy(dtype=float)
        naive = rows[f"naive_{market.name}"].to_numpy(dtype=float)
        games = rows["game_id"].to_numpy()
        entry: dict[str, Any] = {
            "provider_key": market.provider_key,
            "column": market.column,
            "player_games": int(len(rows)),
            "games": int(len(set(games.tolist()))),
            "mean_count": float(counts.mean()) if len(rows) else float("nan"),
            "mean_model": float(mu.mean()) if len(rows) else float("nan"),
            "mean_naive": float(naive.mean()) if len(rows) else float("nan"),
            "variance_ratio": float(((counts - mu) ** 2).sum() / mu.sum()) if len(rows) and mu.sum() > 0 else float("nan"),
            "negative_binomial_share": float((inv_r >= MIN_INVERSE_R).mean()) if len(rows) else 0.0,
            "lines": [],
        }
        pooled_p: list[np.ndarray] = []
        pooled_y: list[np.ndarray] = []
        pooled_g: list[np.ndarray] = []
        for line in market.lines:
            y = (counts > line).astype(float)
            line_entry: dict[str, Any] = {"line": line, "samples": int(len(rows))}
            if len(rows) == 0:
                line_entry["verdict"] = "too few to read"
                entry["lines"].append(line_entry)
                continue
            p_model = over_probability(mu, inv_r, line)
            p_naive = poisson.sf(math.floor(line), np.clip(naive, 1e-9, None))
            ll_model, ll_naive = _log_loss(p_model, y), _log_loss(p_naive, y)
            br_model, br_naive = (p_model - y) ** 2, (p_naive - y) ** 2
            low, high = _rate_interval(y, games)
            log_diff = _interval(ll_naive - ll_model, games, looks)
            line_entry.update(
                {
                    "games": int(len(set(games.tolist()))),
                    "observed": float(y.mean()),
                    "observed_low": low,
                    "observed_high": high,
                    "predicted_model": float(p_model.mean()),
                    "predicted_naive": float(p_naive.mean()),
                    "log_loss_model": float(ll_model.mean()),
                    "log_loss_naive": float(ll_naive.mean()),
                    "brier_model": float(br_model.mean()),
                    "brier_naive": float(br_naive.mean()),
                    "log_loss_gain": log_diff,
                    "brier_gain": _interval(br_naive - br_model, games, looks),
                    "verdict": _verdict(log_diff, len(rows)),
                    "calibration": _buckets(p_model, y, games),
                }
            )
            entry["lines"].append(line_entry)
            pooled_p.append(p_model)
            pooled_y.append(y)
            pooled_g.append(games)
        entry["calibration"] = (
            _buckets(np.concatenate(pooled_p), np.concatenate(pooled_y), np.concatenate(pooled_g))
            if pooled_p
            else []
        )
        payload["markets"][market.name] = entry
    return payload
