"""Cooper's Due List, in one place, for the evidence and for the card.

The rule (Cooper, 2026-10-07 evening; it replaces the flat 5-game rule shipped
that morning in #307): a skater with 70+ points, 25+ goals or 60+ assists LAST
regular season is listed in that category when his current drought (regular-
season games he dressed for without one in that category, carried across the
season boundary) reaches EITHER of two bars. The better the player, the
shorter the drought:

1. The TIER bar, from last season's total in the category (`TIERS`):
   points 100+ -> 3, 85-99 -> 4, 70-84 -> 5; goals 40+ -> 5, 25-39 -> 10;
   assists 60+ -> 3. (Goals until 2026-10-10: 30+ to qualify, 40+ -> 3,
   35-39 -> 4, 30-34 -> 5, plus the surprise bar. Assists until 2026-10-31:
   30+ to qualify, 60+ -> 3, 45-59 -> 4, 30-44 -> 5.)
2. The SURPRISE bar (equal surprise, points and assists only:
   `SURPRISE_MARKETS`), from his own prior-season hit rate
   p = (prior-season regular-season games with one or more in the category)
   / (prior-season regular-season games dressed): the smallest n >= 1 with
   (1 - p)^n <= `SURPRISE_LEVEL` (0.05). Undefined when p == 0 (he never
   qualifies on this bar); 1 when p == 1.

Each listed row says which bars the drought has reached (`rule`: "tier",
"surprise" or "both"), his hit rate, the rarity of a streak this long for HIM
((1 - p)^drought, and `one_in`: "1 in N for him" from the unrounded figure)
and the band's measured record from the committed backtest. Since
2026-10-31 it also carries his shots on goal a game during the drought
against his usual rate (`shots_during_drought`), and the card's own chance of
the over at the best price (`model_probability`, `model_edge`): information
beside the row for Cooper's pick, never a filter or a stake.

`scripts/run_drought_rule_backtest.py` measures it against bought prices and
the Gameday card lists tonight's qualifiers from it. Both call `prepare_logs`
below, so the card cannot disagree with the evidence about who qualifies: the
card asks it about a game that has not happened yet (`qualifiers_entering`),
which is the same function with one more row per player.

This is a list Cooper picks from. Its order (rarest streak first, within each
category) is for reading, not a stake size: nothing here stakes or sizes a
selection, and nothing here reaches the model's selections, the edge bar, the
market list or the registered forward test.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nhl_betting_lab.config import MAX_DEFAULT_JUICE
from nhl_betting_lab.models.player_props import player_name_aliases
from nhl_betting_lab.providers.team_names import resolve_team
from nhl_betting_lab.puck_drop import apply_puck_drop_guard
from nhl_betting_lab.season import clean_text, row_game_date, season_id

#: The base qualifier: last regular season's total in the category.
#: Assists moved from 30+ to 60+ on 2026-10-31 (Cooper, "Yes, 60+ assists
#: only"): the 30-59 bands lost on two bought seasons and on the list's own
#: first three weeks; 60+ at 3 was the one assists band that made money.
THRESHOLDS = {"points": 60, "goals": 20, "assists": 40}
#: The tier bar: (floor of last season's total, drought that lists him), best
#: band first. The last floor of each category is the base qualifier.
TIERS: dict[str, tuple[tuple[int, int], ...]] = {
    "points": ((100, 2), (85, 3), (70, 4), (60, 5)),
    "goals": ((40, 4), (25, 8), (20, 10)),
    "assists": ((60, 3), (40, 4)),
}
#: The surprise bar's level: the smallest drought with (1 - p)^n <= this.
SURPRISE_LEVEL = 0.05
#: The categories the surprise bar lists in. Goals left it on 2026-10-10
#: (Cooper, after `scripts/run_due_list_tuning.py`): 25+ goals at a 10-game
#: drought was the one setting both bought seasons chose, and he kept 40+ at 5.
SURPRISE_MARKETS = ("points", "assists")
LINE = 0.5
#: The shots check (2026-10-31): shots on goal a game during the drought
#: against his own rate over the games before it, up to this many.
USUAL_SHOTS_GAMES = 82
#: Shots ratio cut-offs the card labels and the backtest splits on.
SHOTS_UP = 1.0
SHOTS_DOWN = 0.8
BACKTEST_JSON = "drought_rule_backtest.json"
SECTION_TITLE = "Due List"

#: Prices shorter than this are flagged on the row, never hidden: Cooper picks.
HEAVY_JUICE = MAX_DEFAULT_JUICE

#: A game id no real game has, so the sentinel row sorts after every real one
#: and is told apart from them.
_TONIGHT_GAME_ID = 10**12

assert all(tiers[-1][0] == THRESHOLDS[m] for m, tiers in TIERS.items()), "the lowest tier is the base qualifier"


def tier_bar(market: str, prior_total) -> int | None:
    """The drought that lists a player on last season's total; None below the base qualifier."""
    if prior_total is None or pd.isna(prior_total):
        return None
    for floor, bar in TIERS[market]:
        if prior_total >= floor:
            return bar
    return None


def band_label(market: str, prior_total) -> str | None:
    """The tier band last season's total falls in ("100+", "85-99", ...); None below the qualifier."""
    if prior_total is None or pd.isna(prior_total):
        return None
    tiers = TIERS[market]
    for i, (floor, _) in enumerate(tiers):
        if prior_total >= floor:
            return f"{floor}+" if i == 0 else f"{floor}-{tiers[i - 1][0] - 1}"
    return None


def _at_most(value: float, level: float) -> bool:
    """`value <= level`, with a 19/20 hit rate's (1 - p) reading as 0.05 and not 0.05000000000000004."""
    return value <= level or math.isclose(value, level, rel_tol=1e-9)


def surprise_bar(hit_rate) -> int | None:
    """The smallest n >= 1 with (1 - p)^n <= SURPRISE_LEVEL; None when p == 0 (undefined), 1 when p == 1.

    A p too small for 1 - p to differ from 1 (below about 1e-16; no hit rate
    of games dressed, at most one in 85, gets near it) is treated as p == 0.
    """
    if hit_rate is None or pd.isna(hit_rate) or hit_rate <= 0:
        return None
    if hit_rate >= 1:
        return 1
    miss = 1.0 - float(hit_rate)
    if miss >= 1.0:
        return None
    n = max(1, math.ceil(math.log(SURPRISE_LEVEL) / math.log(miss)))
    while n > 1 and _at_most(miss ** (n - 1), SURPRISE_LEVEL):
        n -= 1
    while not _at_most(miss ** n, SURPRISE_LEVEL):
        n += 1
    return n


def one_in(hit_rate, drought: int) -> int | None:
    """N in "1 in N for him": round(1 / (1 - p)^drought) from the UNROUNDED figure.

    The row's `rarity` is that figure rounded to 4 dp, which quantises the
    rarest rows (0.25^7 is 1 in 16,384, and 0.0001 reads as 1 in 10,000), so
    N is computed here once and carried on the row. None when the figure is
    0: p == 1 (he hit in every game last season), or a drought so long the
    float underflows.
    """
    p = 0.0 if hit_rate is None or pd.isna(hit_rate) else float(hit_rate)
    chance = (1.0 - p) ** int(drought)
    return None if chance <= 0 else int(round(1.0 / chance))


def bars_reached(market: str, prior_total, hit_rate, drought: int) -> dict[str, Any] | None:
    """What the two bars say about one player in one category entering a game.

    None when he is not listed: below the base qualifier, or a drought that
    has reached neither bar. Otherwise the row's own fields: `tier_bar`,
    `surprise_bar` (None when undefined, or for a category outside
    `SURPRISE_MARKETS`), `hit_rate` (p, 3 dp), `rarity`
    ((1 - p)^drought, 4 dp: how unlikely a streak this long is for HIM),
    `one_in` (N in "1 in N for him" from the unrounded figure; None when it
    is 0), `rule` ("tier", "surprise" or "both": the bars the drought has
    reached) and `band` (the tier band's label).
    """
    tier = tier_bar(market, prior_total)
    if tier is None:
        return None
    p = 0.0 if hit_rate is None or pd.isna(hit_rate) else float(hit_rate)
    surprise = surprise_bar(p) if market in SURPRISE_MARKETS else None
    reached = [name for name, bar in (("tier", tier), ("surprise", surprise)) if bar is not None and drought >= bar]
    if not reached:
        return None
    return {
        "tier_bar": tier, "surprise_bar": surprise, "hit_rate": round(p, 3),
        "rarity": round((1.0 - p) ** int(drought), 4), "one_in": one_in(p, drought),
        "rule": "both" if len(reached) == 2 else reached[0],
        "band": band_label(market, prior_total),
    }


def drought_before(values) -> list[int]:
    """Games in a row without the stat, entering each game (the game itself excluded).

    A missing stat (None or NaN) is refused: counted as a hit it would end a
    drought nobody saw end, counted as a miss it would lengthen one. The
    built logs carry none (int64 columns), so this names a loader defect.
    """
    out, run = [], 0
    for v in values:
        if v is None or v != v:
            raise ValueError("a player-game row has no stat recorded, so its drought cannot be counted")
        out.append(run)
        run = 0 if v >= 1 else run + 1
    return out


def prepare_logs(logs: pd.DataFrame) -> pd.DataFrame:
    """Skater games with each category's drought entering the game and last season's record.

    Last season's record, per player: `prior_<market>` (the total), `prior_gp`
    (regular-season games dressed) and `prior_hit_<market>` (games with one or
    more), so the hit rate behind the surprise bar is `prior_hit_<market> /
    prior_gp`: games he dressed for, never his team's games.
    """
    logs = logs[(logs.role == "skater") & (logs.game_type == 2)].copy()
    logs = logs.sort_values(["player_id", "date", "game_id"])
    logs["season_start"] = logs.season // 10000
    for market in THRESHOLDS:
        logs["drought_" + market] = logs.groupby("player_id")[market].transform(
            lambda s: pd.Series(drought_before(s.values), index=s.index))
    if "shots_on_goal" in logs.columns:
        for market in THRESHOLDS:
            shots = shots_during_drought(logs, market)
            logs["drought_sog_" + market] = shots["drought_sog"]
            logs["usual_sog_" + market] = shots["usual_sog"]
    per_game = logs[["player_id", "season_start", *THRESHOLDS]].copy()
    for market in THRESHOLDS:
        per_game["hit_" + market] = (per_game[market] >= 1).astype(int)
    per_game["gp"] = 1
    prior = per_game.groupby(["player_id", "season_start"]).sum().reset_index()
    prior["season_start"] += 1
    prior = prior.rename(columns={**{m: "prior_" + m for m in THRESHOLDS},
                                  **{"hit_" + m: "prior_hit_" + m for m in THRESHOLDS}, "gp": "prior_gp"})
    return logs.merge(prior, on=["player_id", "season_start"], how="left")


def shots_during_drought(logs: pd.DataFrame, market: str) -> pd.DataFrame:
    """Shots on goal a game during each row's drought, and his usual rate before it.

    `logs` is sorted by player and date with `drought_<market>` set, as
    `prepare_logs` leaves it. For a game entered on a drought of d, the
    drought games are the d before it and the usual games are up to
    `USUAL_SHOTS_GAMES` before those. NaN when there are none (no drought, or
    no earlier games). A missing shot count is NaN and left out of both means.
    """
    out = pd.DataFrame(index=logs.index, columns=["drought_sog", "usual_sog"], dtype=float)
    for _, g in logs.groupby("player_id", sort=False):
        sog = pd.to_numeric(g["shots_on_goal"], errors="coerce").to_numpy(dtype=float)
        have = ~np.isnan(sog)
        csum = np.concatenate([[0.0], np.cumsum(np.where(have, sog, 0.0))])
        cnt = np.concatenate([[0], np.cumsum(have)])
        d = g["drought_" + market].to_numpy(dtype=int)
        i = np.arange(len(g))
        start = i - d
        lo = np.maximum(0, start - USUAL_SHOTS_GAMES)
        dn, un = cnt[i] - cnt[start], cnt[start] - cnt[lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            out.loc[g.index, "drought_sog"] = np.where(dn > 0, (csum[i] - csum[start]) / np.maximum(dn, 1), np.nan)
            out.loc[g.index, "usual_sog"] = np.where(un > 0, (csum[start] - csum[lo]) / np.maximum(un, 1), np.nan)
    return out


def shots_ratio(drought_sog, usual_sog) -> float | None:
    """Drought shots over usual shots; None when either is missing or he usually takes none."""
    try:
        d, u = float(drought_sog), float(usual_sog)
    except (TypeError, ValueError):
        return None
    if math.isnan(d) or math.isnan(u) or u <= 0:
        return None
    return d / u


def shots_label(ratio) -> str:
    """"shots up", "shots steady" or "shots down", by `SHOTS_UP` / `SHOTS_DOWN`; "-" when unknown."""
    if ratio is None or (isinstance(ratio, float) and math.isnan(ratio)):
        return "-"
    if ratio >= SHOTS_UP:
        return "shots up"
    return "shots down" if ratio < SHOTS_DOWN else "shots steady"


QUALIFIER_COLUMNS = ["player_id", "player", "market", "last_season", "drought",
                     "tier_bar", "surprise_bar", "hit_rate", "rarity", "one_in", "rule", "band",
                     "drought_sog", "usual_sog"]


def qualifiers_entering(logs: pd.DataFrame, day: str) -> pd.DataFrame:
    """Every (player, category) that is listed for a game on league date `day`.

    Columns: `QUALIFIER_COLUMNS`. Built by giving each skater one more game,
    dated after every real one and in `day`'s season, with a point, a goal and
    an assist, and asking `prepare_logs` what that game's drought and last
    season's record are. `prepare_logs` is the backtest's own function, so the
    drought runs across the season boundary and counts only regular-season
    games the player dressed for, exactly as the evidence does. Games dated on
    or after `day` are left out: tonight is entered, not played. A row is
    listed when the drought has reached either bar (`bars_reached`).
    """
    columns = list(QUALIFIER_COLUMNS)
    needed = {"role", "game_type", "season", "date", "game_id", "player_id", "player", *THRESHOLDS}
    if logs.empty or not needed <= set(logs.columns):
        return pd.DataFrame(columns=columns)
    before = logs[logs["date"].astype(str).str.slice(0, 10) < day]
    skaters = before[(before.role == "skater") & (before.game_type == 2)]
    if skaters.empty:
        return pd.DataFrame(columns=columns)
    names = skaters.sort_values(["date", "game_id"]).groupby("player_id").player.last()
    tonight = pd.DataFrame({
        "game_id": _TONIGHT_GAME_ID, "season": int(season_id(day)), "game_type": 2,
        "date": "9999-12-31", "player_id": names.index, "player": names.to_numpy(),
        "role": "skater", **{market: 1 for market in THRESHOLDS},
    })
    if "shots_on_goal" in skaters.columns:
        tonight["shots_on_goal"] = np.nan
    both = pd.concat([skaters[list(tonight.columns)], tonight], ignore_index=True)
    entering = prepare_logs(both)
    entering = entering[entering.game_id == _TONIGHT_GAME_ID]
    rows = []
    for market, bar in THRESHOLDS.items():
        qualified = entering[entering["prior_" + market] >= bar]
        for r in qualified.itertuples():
            total, drought = int(getattr(r, "prior_" + market)), int(getattr(r, "drought_" + market))
            hit_rate = float(getattr(r, "prior_hit_" + market)) / float(r.prior_gp) if r.prior_gp else 0.0
            found = bars_reached(market, total, hit_rate, drought)
            if found is None:
                continue
            shots = {k: (None if pd.isna(v) else round(float(v), 2)) for k, v in (
                ("drought_sog", getattr(r, "drought_sog_" + market, np.nan)),
                ("usual_sog", getattr(r, "usual_sog_" + market, np.nan)))}
            rows.append({"player_id": int(r.player_id), "player": r.player, "market": market,
                         "last_season": total, "drought": drought, **found, **shots})
    return pd.DataFrame(rows, columns=columns)


#: Big games (Cooper, 2026-11-04: "work shutouts/2 goal games/hat tricks into
#: the due list for the really elite goalscorers/goalies"). Each is its own
#: category beside points, goals and assists: `floor` is last season's total
#: that makes a player elite for it (goals for the two scoring categories,
#: shutouts for goalies) and `bar` the drought that lists him (games dressed
#: without the event for skaters, starts without one for goalies). `price`
#: is the provider market and line its best price is read from; a shutout
#: has no market any book in this lab's feed quotes, so it is never priced.
BIG_GAMES: dict[str, dict[str, Any]] = {
    "two_goals": {"role": "skater", "count": 2, "line": 1.5, "price": ("goals", 1.5), "floor": 35, "bar": 15},
    "hat_trick": {"role": "skater", "count": 3, "line": 2.5, "price": ("goals", 2.5), "floor": 40, "bar": 30},
    "shutout": {"role": "goalie", "count": 1, "line": 0.5, "price": None, "floor": 4, "bar": 12},
}
#: Every category the list carries, in its order on the card.
CATEGORIES = (*THRESHOLDS, *BIG_GAMES)
#: How the card names each category.
CATEGORY_LABELS = {"points": "points", "goals": "goals", "assists": "assists",
                   "two_goals": "2+ goals", "hat_trick": "hat trick", "shutout": "shutout"}
#: The big games' measured records, card window, 2024-25 and 2025-26, best
#: price, flat stake, 95% interval bootstrapped over nights, at the shipped
#: floor and bar: `scripts/run_due_list_big_games.py`, Due List Tuning run
#: 41759820070 (2026-11-04). A shutout has no price, so no record.
BIG_GAMES_RECORDS: dict[tuple[str, str], dict[str, Any]] = {
    ("two_goals", "40+"): {"wagers": 391, "roi": -0.236, "ci_low": -0.479, "ci_high": 0.026},
    ("hat_trick", "40+"): {"wagers": 1269, "roi": -0.586, "ci_low": -0.811, "ci_high": -0.332},
}
#: One line for the card, from the same run.
BIG_GAMES_HEADLINE = (
    "Big games, measured on 2024-25 and 2025-26 (scripts/run_due_list_big_games.py), with the floor and bar "
    "picked from that sweep as the least bad: no setting makes any of them likelier than the player's own rate. "
    "2+ goals, 40+ goal scorers 20+ games without one: hit 7.7% against 10.7% implied, -23.6% over 391 "
    "(95% -47.9% to +2.6%; -24.3% in 2024-25, -21.0% in 2025-26), no demonstrated edge. Hat trick, 40+ at "
    "30+: -58.6% over 1,269 (95% -81.1% to -33.2%), a demonstrated loss at every setting tried. Shutouts, 5+ "
    "last season at 15+ starts without one: 6.7% of 210 starts against 11.4% the season before; no book in "
    "this feed prices a shutout, so those rows are graded for hits only. Across 16 seasons of NHL game logs "
    "(2010-11 to 2025-26) a drought never made any of the three likelier than for the same players at any "
    "drought: 2+ goals 6.7% against 7.7% (1,776 games), hat tricks 1.1% against 1.3% (5,436), shutouts 7.0% "
    "against 7.3% (1,850 starts). Cooper picks from the list."
)


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(str(category), str(category))
#: A goalie start, as the backtest counts one (`walk_forward.GOALIE_START_SECONDS`).
GOALIE_START_SECONDS = 2400
#: A shutout: a start with no goal against and this much ice time (the whole
#: game; a shootout goal is not a goal against).
SHUTOUT_SECONDS = 59 * 60
#: The provider market and line each priced category reads its best over from.
PRICE_OF: dict[str, tuple[str, float]] = {
    **{m: (m, LINE) for m in THRESHOLDS},
    **{c: spec["price"] for c, spec in BIG_GAMES.items() if spec["price"] is not None},
}


def line_of(category: str) -> float:
    """The over a category is graded on: 0.5, or 1.5 / 2.5 for 2+ goals and hat tricks."""
    return float(BIG_GAMES[category]["line"]) if category in BIG_GAMES else LINE


def is_shutout(goals_against, toi_seconds) -> bool:
    """A shutout: no goal against over (practically) the whole game."""
    ga, toi = pd.to_numeric(goals_against, errors="coerce"), pd.to_numeric(toi_seconds, errors="coerce")
    return bool(not pd.isna(ga) and not pd.isna(toi) and ga == 0 and toi >= SHUTOUT_SECONDS)


def big_game_events(logs: pd.DataFrame) -> pd.DataFrame:
    """One row per regular-season skater game dressed or goalie start, with each big game's flag.

    Columns: player_id, player, date, game_id, season, season_start, role, and a
    0/1 column per `BIG_GAMES` category (0 on rows of the other role).
    """
    needed = {"role", "game_type", "season", "date", "game_id", "player_id", "player", "goals"}
    if logs.empty or not needed <= set(logs.columns):
        return pd.DataFrame(columns=["player_id", "player", "date", "game_id", "season", "season_start", "role",
                                     *BIG_GAMES])
    rs = logs[logs.game_type == 2]
    skaters = rs[rs.role == "skater"].copy()
    goalies = rs[rs.role == "goalie"].copy()
    if "toi_seconds" in goalies.columns:
        goalies = goalies[pd.to_numeric(goalies.toi_seconds, errors="coerce") >= GOALIE_START_SECONDS]
    else:
        goalies = goalies.iloc[0:0]
    goals = pd.to_numeric(skaters.goals, errors="coerce")
    for category, spec in BIG_GAMES.items():
        if spec["role"] == "skater":
            skaters[category] = (goals >= spec["count"]).astype(int)
            goalies[category] = 0
        else:
            ga = goalies["goals_against"] if "goals_against" in goalies.columns else pd.Series(np.nan, index=goalies.index)
            toi = goalies["toi_seconds"] if "toi_seconds" in goalies.columns else pd.Series(np.nan, index=goalies.index)
            goalies[category] = [int(is_shutout(a, s)) for a, s in zip(ga, toi)]
            skaters[category] = 0
    both = pd.concat([skaters, goalies], ignore_index=True)
    both["season_start"] = pd.to_numeric(both.season, errors="coerce") // 10000
    return both[["player_id", "player", "date", "game_id", "season", "season_start", "role", *BIG_GAMES]]


def big_game_qualifiers_entering(logs: pd.DataFrame, day: str) -> pd.DataFrame:
    """Every (player, big-game category) listed for a game on league date `day`.

    Same columns as `qualifiers_entering`. Last season's total is goals (2+
    goals, hat tricks) or shutouts; the drought is regular-season games dressed
    (starts, for a goalie) since his last such game, carried across the season
    boundary; the hit rate is last season's share of games (starts) with one.
    A player is listed when last season's total reaches the category's floor
    and the drought its bar. Only games before `day` are read.
    """
    columns = list(QUALIFIER_COLUMNS)
    events = big_game_events(logs)
    events = events[events["date"].astype(str).str.slice(0, 10) < day]
    if events.empty:
        return pd.DataFrame(columns=columns)
    events = events.sort_values(["player_id", "date", "game_id"])
    tonight_season = int(season_id(day)) // 10000
    prior_rows = events[events.season_start == tonight_season - 1]
    goals_by = {}
    if not logs.empty and "goals" in logs.columns:
        sk = logs[(logs.role == "skater") & (logs.game_type == 2)]
        sk = sk[(pd.to_numeric(sk.season, errors="coerce") // 10000) == tonight_season - 1]
        sk = sk[sk["date"].astype(str).str.slice(0, 10) < day]
        goals_by = pd.to_numeric(sk.goals, errors="coerce").groupby(sk.player_id).sum().to_dict()
    rows = []
    for category, spec in BIG_GAMES.items():
        mine = events[events.role == spec["role"]]
        prior = prior_rows[prior_rows.role == spec["role"]].groupby("player_id")[category].agg(["sum", "size"])
        for pid, g in mine.groupby("player_id", sort=False):
            if pid not in prior.index:
                continue
            total = int(goals_by.get(pid, 0)) if spec["role"] == "skater" else int(prior.at[pid, "sum"])
            if total < spec["floor"]:
                continue
            flags = g[category].to_numpy()
            hit = np.flatnonzero(flags >= 1)
            drought = int(len(flags) - (hit[-1] + 1)) if len(hit) else int(len(flags))
            if drought < spec["bar"]:
                continue
            games = int(prior.at[pid, "size"])
            p = float(prior.at[pid, "sum"]) / games if games else 0.0
            rows.append({"player_id": int(pid), "player": g.player.iloc[-1], "market": category,
                         "last_season": total, "drought": drought, "tier_bar": int(spec["bar"]),
                         "surprise_bar": None, "hit_rate": round(p, 3),
                         "rarity": round((1.0 - p) ** drought, 4), "one_in": one_in(p, drought),
                         "rule": "tier", "band": f"{spec['floor']}+", "drought_sog": None, "usual_sog": None})
    return pd.DataFrame(rows, columns=columns)


@dataclass
class DroughtList:
    """Tonight's list, and what could not be placed on it."""

    day: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    #: Qualifiers whose game had started or whose start could not be confirmed.
    removed_by_guard: int = 0
    #: Why the list is empty or short for a reason other than "nobody qualifies".
    notes: list[str] = field(default_factory=list)


def _optional_int(value) -> int | None:
    return None if value is None or pd.isna(value) else int(value)


def build_drought_list(
    *,
    logs: pd.DataFrame,
    rosters: Mapping[int, str],
    starts: Mapping[tuple[str, str, str], str],
    prices: pd.DataFrame,
    team_names: Mapping[str, str],
    day: str,
    now: datetime,
    records: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
    probabilities: Mapping[tuple, float] | None = None,
) -> DroughtList:
    """Tonight's qualifiers with the best staged price each, if any is posted.

    Needs only logs, rosters and the schedule; `prices` may be empty, and then
    every row reads "not posted". A price is the best American odds any book
    staged for that player's over 0.5 in that game. It is never filled in:
    no price, no number. A price name that matches two players on the game
    resolves to neither and is listed in `unresolved`. `records` is
    `cell_records(...)`, the band records the committed backtest measured;
    a row whose band has none carries `cell_record` None, never a guess.
    `probabilities` is the card's own probability map: a priced row carries
    `model_probability` (the card's chance of the over) and `model_edge`
    (that chance minus the best price's implied chance), both None when the
    card has no opinion. Information beside the row, never a filter.
    Every row also carries `drought_sog` and `usual_sog` (shots on goal a
    game during the drought and before it) and `shots` (`shots_label`).
    Sorted by category, then rarity (rarest first), then longest drought,
    then name.
    """
    result = DroughtList(day=day)
    if logs.empty:
        result.notes.append("No player logs are on disk, so no qualifier could be found.")
        return result
    if not rosters:
        result.notes.append(
            "No rosters are cached, so no qualifier can be placed on a team and none is listed. "
            "A player's last club in the logs is not his club now."
        )
        return result
    games = {(h, a): start for (d, h, a), start in starts.items() if d == day}
    if not games:
        result.notes.append(f"No regular-season game is scheduled for {day}.")
        return result

    parts = [f for f in (qualifiers_entering(logs, day), big_game_qualifiers_entering(logs, day)) if not f.empty]
    qualified = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=QUALIFIER_COLUMNS)
    team_of = {pid: str(team).strip().upper() for pid, team in rosters.items()}
    playing = {team: (h, a) for (h, a) in games for team in (h, a)}
    records = {**BIG_GAMES_RECORDS, **(records or {})}
    candidates: list[dict[str, Any]] = []
    for q in qualified.itertuples():
        team = team_of.get(int(q.player_id))
        if team not in playing:
            continue
        home, away = playing[team]
        record = records.get((q.market, q.band))
        candidates.append({
            "date": day, "commence_time": games[(home, away)], "home_team": home, "away_team": away,
            "team": team, "opponent": away if team == home else home,
            "player": q.player, "player_id": int(q.player_id), "market": q.market, "line": line_of(q.market),
            "selection": "over", "last_season": int(q.last_season), "drought": int(q.drought),
            "tier_bar": int(q.tier_bar), "surprise_bar": _optional_int(q.surprise_bar),
            "hit_rate": float(q.hit_rate), "rarity": float(q.rarity), "one_in": _optional_int(q.one_in),
            "rule": str(q.rule), "band": str(q.band),
            "cell_record": dict(record) if record is not None else None,
            "drought_sog": None if q.drought_sog is None or pd.isna(q.drought_sog) else q.drought_sog,
            "usual_sog": None if q.usual_sog is None or pd.isna(q.usual_sog) else q.usual_sog,
            "shots": shots_label(shots_ratio(q.drought_sog, q.usual_sog)),
            "american_odds": None, "book": "", "heavy_juice": False,
            "model_probability": None, "model_edge": None,
        })
    guarded = apply_puck_drop_guard(candidates, now=now)
    result.removed_by_guard = len(guarded.quarantined)
    rows = [{k: v for k, v in row.items() if not k.startswith("puck_drop_")} for row in guarded.playable]

    best, unresolved = best_over_prices(rows, prices=prices, logs=logs, team_of=team_of,
                                        playing=playing, team_names=team_names, day=day,
                                        probabilities=probabilities)
    for row in rows:
        priced = best.get((row["player_id"], row["market"]))
        if priced:
            row["american_odds"], row["book"] = priced[0], priced[1]
            row["heavy_juice"] = priced[0] < HEAVY_JUICE
            chance = priced[2] if len(priced) > 2 else None
            if chance is not None:
                row["model_probability"] = round(float(chance), 4)
                row["model_edge"] = round(float(chance) - 1 / _decimal(priced[0]), 4)
    order = {m: i for i, m in enumerate(CATEGORIES)}
    rows.sort(key=lambda r: (order[r["market"]], r["rarity"], -r["drought"], r["player"]))
    result.rows = rows
    result.unresolved = sorted(unresolved)
    return result


def best_over_prices(
    rows: list[Mapping[str, Any]],
    *,
    prices: pd.DataFrame,
    logs: pd.DataFrame,
    team_of: Mapping[int, str],
    playing: Mapping[str, tuple[str, str]],
    team_names: Mapping[str, str],
    day: str,
    probabilities: Mapping[tuple, float] | None = None,
) -> tuple[dict[tuple[int, str], tuple[float, str, float | None]], set[str]]:
    """The best over 0.5 price any book in `prices` quoted for each listed row.

    Returns ({(player id, market): (American odds, book, model chance)},
    unresolved names); the model chance is `probabilities` at that quote's
    `selection_key`, the first any quote of the selection carries, or None.
    `team_of` is {player id: club} and `playing` {club: (home, away)} for the
    day's games. A price name that matches two players on its game resolves
    to neither and is named in the second element. Never filled in: a row
    no book quoted is absent from the first.
    """
    # Every skater on a tonight club, for telling a shared name apart.
    known = (logs[(logs.role == "skater")].sort_values(["date", "game_id"])
             .groupby("player_id").player.last() if "role" in logs.columns and not logs.empty else pd.Series(dtype=object))
    on_game: dict[tuple[str, str], dict[str, set[int]]] = {}
    for pid, team in team_of.items():
        if team in playing and pid in known.index:
            for alias in player_name_aliases(known[pid]):
                on_game.setdefault(playing[team], {}).setdefault(alias, set()).add(int(pid))
    best: dict[tuple[int, str], tuple[float, str, float | None]] = {}
    chances: dict[tuple[int, str], float] = {}
    unresolved: set[str] = set()
    wanted = {(r["player_id"], r["market"]) for r in rows}
    if prices is not None and not prices.empty and rows:
        category_of = {spec: c for c, spec in PRICE_OF.items()}
        lines = pd.to_numeric(prices["line"], errors="coerce")
        markets = prices["market"].astype(str).str.strip()
        quotes = prices[(prices["selection"].astype(str).str.strip().str.lower() == "over")
                        & pd.Series([(m, ln) in category_of for m, ln in zip(markets, lines)], index=prices.index)]
        for p in quotes.itertuples():
            game = (resolve_team(clean_text(p.home_team), team_names), resolve_team(clean_text(p.away_team), team_names))
            if game not in on_game or row_game_date(p) != day:
                continue
            ids: set[int] = set()
            for alias in player_name_aliases(p.player):
                ids |= on_game[game].get(alias, set())
            provider_market, line = str(p.market).strip(), float(p.line)
            market = category_of[(provider_market, line)]
            hit = {pid for pid in ids if (pid, market) in wanted}
            if not hit:
                continue
            if len(ids) > 1:
                unresolved.add(f"{clean_text(p.player)} ({market}, {game[1]} @ {game[0]})")
                continue
            odds = pd.to_numeric(p.american_odds, errors="coerce")
            if pd.isna(odds):
                continue
            key = (next(iter(hit)), market)
            if probabilities and key not in chances:
                from nhl_betting_lab.reports.card_pricing import selection_key

                chance = probabilities.get(selection_key(p, market=provider_market, selection="over", line=line))
                if chance is not None and not pd.isna(chance):
                    chances[key] = float(chance)
            if key not in best or _decimal(float(odds)) > _decimal(best[key][0]):
                best[key] = (float(odds), clean_text(p.book), None)
    best = {k: (v[0], v[1], chances.get(k)) for k, v in best.items()}
    return best, unresolved


def _decimal(american: float) -> float:
    return 1 + american / 100 if american > 0 else 1 + 100 / -american


def _backtest_path(directory: Path | None, fallback: Path | None) -> Path | None:
    for base in (directory, fallback):
        path = Path(base) / BACKTEST_JSON if base else None
        if path and path.is_file():
            return path
    return None


SHIPPED_BUCKET = "SHIPPED: either bar"
TIER_BUCKET_PREFIX = "TIER "


def tier_bucket(band: str, bar: int, *, exactly: bool = False) -> str:
    """The backtest's bucket label for a band: "TIER 60+ @3" (drought at or past the bar) or "TIER 60+ ==3"."""
    return f"{TIER_BUCKET_PREFIX}{band} {'==' if exactly else '@'}{bar}"


def cell_records(directory: Path | None = None, *, fallback: Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """Each band's measured record, read from the committed backtest: {(market, band): {...}}.

    The card window, both seasons, bucket `tier_bucket(band, bar)`: wagers,
    roi, ci_low, ci_high. `directory` first, then `fallback`. Empty when no
    file can be read, and a band whose bucket is missing, or whose bar is not
    the one `TIERS` gives that band today, has no entry: the row then carries
    no record, never a guessed or a stale one.
    """
    path = _backtest_path(directory, fallback)
    if path is None:
        return {}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for market, tiers in TIERS.items():
            for floor, bar in tiers:
                band = band_label(market, floor)
                for b in payload["buckets"]:
                    if (b["window"] == "card" and b["season"] == "both" and b["market"] == market
                            and b["bucket"] == tier_bucket(band, bar)):
                        out[(market, band)] = {"wagers": int(b["wagers"]), "roi": float(b["roi"]),
                                               "ci_low": float(b["ci_low"]), "ci_high": float(b["ci_high"])}
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    return out


def backtest_headline(directory: Path | None = None, *, fallback: Path | None = None) -> str:
    """One line: what the committed backtest measured for the shipped rule, read from its own JSON.

    `directory` first, then `fallback` (the repository's outputs). The figures
    are the `SHIPPED_BUCKET` (either bar) per category, card window, both
    seasons. Words only where the numbers permit them: "no category's interval
    sits above zero" is printed only when no card-window interval sits above
    zero, and otherwise the categories whose intervals do are named. With no
    file, it says so.
    """
    path = _backtest_path(directory, fallback)
    if path is None:
        return f"Backtest headline unavailable: {BACKTEST_JSON} was not found."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rule = {b["market"]: b for b in payload["buckets"]
                if b["window"] == "card" and b["season"] == "both" and b["bucket"] == SHIPPED_BUCKET}
        parts = [f"{m} {rule[m]['roi'] * 100:+.1f}% over {rule[m]['wagers']} wagers "
                 f"(95% {rule[m]['ci_low'] * 100:+.1f}% to {rule[m]['ci_high'] * 100:+.1f}%)" for m in THRESHOLDS]
        above = [m for m in THRESHOLDS if rule[m]["ci_low"] > 0]
    except (OSError, ValueError, KeyError, TypeError):
        return f"Backtest headline unavailable: {BACKTEST_JSON} could not be read."
    verdict = ("no category's interval sits above zero" if not above
               else f"{', '.join(above)} {'sits' if len(above) == 1 else 'sit'} above zero")
    return ("Backtest of the shipped rule (either bar) on 2024-25 and 2025-26 bought prices, best price, "
            "card window, flat stake: " + "; ".join(parts) + f"; {verdict}.")


def price_text(row: Mapping[str, Any]) -> str:
    odds = row.get("american_odds")
    if odds is None or (isinstance(odds, float) and np.isnan(odds)):
        return "not posted"
    return f"{int(odds):+d}" if float(odds).is_integer() else f"{float(odds):+.1f}"


def bar_text(row: Mapping[str, Any]) -> str:
    """The highest bar the drought has reached and which rule(s) list him: "3 (tier)", "4 (both)"."""
    bars = [bar for name, bar in (("tier", row.get("tier_bar")), ("surprise", row.get("surprise_bar")))
            if bar is not None and row.get("rule") in (name, "both")]
    if not bars:
        return "-"
    return f"{max(int(b) for b in bars)} ({row.get('rule')})"


def bars_text(row: Mapping[str, Any]) -> str:
    """Both bars as set for him: "tier 5 / surprise 3"; "surprise -" when undefined."""
    surprise = row.get("surprise_bar")
    return f"tier {row.get('tier_bar')} / surprise {'-' if surprise is None else int(surprise)}"


def rarity_text(row: Mapping[str, Any]) -> str:
    """"1 in N for him", N = the row's `one_in` (computed by `one_in` from the unrounded figure).

    A row carrying no `one_in` (written before it existed) falls back to
    N = round(1 / rarity), whose 4-dp rounding reaches two ends that are named:
    0 is "never last season" when he hit in every game, otherwise rarer than
    the rounding can say.
    """
    n, rarity, hit_rate = row.get("one_in"), row.get("rarity"), row.get("hit_rate")
    if n is not None and not (isinstance(n, float) and np.isnan(n)):
        return f"1 in {int(n):,} for him"
    if rarity is None or (isinstance(rarity, float) and np.isnan(rarity)):
        return "-"
    if float(rarity) <= 0:
        return "never last season" if hit_rate is not None and float(hit_rate) >= 1 else "rarer than 1 in 10,000 for him"
    return f"1 in {round(1 / float(rarity)):,} for him"


def record_text(row: Mapping[str, Any]) -> str:
    """The band's measured record: "band 60+ @3: +10.5% over 184 (95% -1.7% to +23.9%)", or "no record"."""
    record = row.get("cell_record")
    if not record:
        return "no record"
    return (f"band {row.get('band')} @{row.get('tier_bar')}: {record['roi'] * 100:+.1f}% over {record['wagers']} "
            f"(95% {record['ci_low'] * 100:+.1f}% to {record['ci_high'] * 100:+.1f}%)")


def shots_text(row: Mapping[str, Any]) -> str:
    """"shots up: 3.4 a game vs 2.9 usual", or "-" when either rate is missing."""
    d, u = row.get("drought_sog"), row.get("usual_sog")
    label = shots_label(shots_ratio(d, u))
    if label == "-":
        return "-"
    return f"{label}: {float(d):.1f} a game vs {float(u):.1f} usual"


def model_text(row: Mapping[str, Any]) -> str:
    """"model 41% (+3.2 pts)", or "-" when the card has no opinion on the row."""
    chance, edge = row.get("model_probability"), row.get("model_edge")
    if chance is None or (isinstance(chance, float) and np.isnan(chance)):
        return "-"
    text = f"model {float(chance) * 100:.0f}%"
    if edge is not None and not (isinstance(edge, float) and np.isnan(edge)):
        text += f" ({float(edge) * 100:+.1f} pts)"
    return text


def fingerprint(rows: list[Mapping[str, Any]]) -> str:
    """Who is listed, not at what price: a moving line is not a changed list."""
    return "\n".join(sorted(f"{r.get('date')}|{r.get('player_id')}|{r.get('market')}" for r in rows))


SITE_LIST_FILENAME = "drought_list.json"


def site_payload(result: DroughtList, headline: str, generated_at: str) -> dict[str, Any]:
    """What the site builder reads: the list as the card showed it, in one file.

    The site imports nothing from the card; it restores this file with the
    rest of `gameday-reports` and reads it. A price the card did not stage is
    `null`, never a number.
    """
    return {"generated_at": generated_at, "day": result.day, "headline": headline,
            "rows": result.rows, "unresolved": result.unresolved, "notes": result.notes}


def save_site_list(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
