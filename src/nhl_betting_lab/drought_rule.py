"""Cooper's Due List, in one place, for the evidence and for the card.

The rule (Cooper, 2026-10-07 evening; it replaces the flat 5-game rule shipped
that morning in #307): a skater with 70+ points, 25+ goals or 30+ assists LAST
regular season is listed in that category when his current drought (regular-
season games he dressed for without one in that category, carried across the
season boundary) reaches EITHER of two bars. The better the player, the
shorter the drought:

1. The TIER bar, from last season's total in the category (`TIERS`):
   points 100+ -> 3, 85-99 -> 4, 70-84 -> 5; goals 40+ -> 5, 25-39 -> 10;
   assists 60+ -> 3, 45-59 -> 4, 30-44 -> 5. (Goals until 2026-10-10:
   30+ to qualify, 40+ -> 3, 35-39 -> 4, 30-34 -> 5, plus the surprise bar.)
2. The SURPRISE bar (equal surprise, points and assists only:
   `SURPRISE_MARKETS`), from his own prior-season hit rate
   p = (prior-season regular-season games with one or more in the category)
   / (prior-season regular-season games dressed): the smallest n >= 1 with
   (1 - p)^n <= `SURPRISE_LEVEL` (0.05). Undefined when p == 0 (he never
   qualifies on this bar); 1 when p == 1.

Each listed row says which bars the drought has reached (`rule`: "tier",
"surprise" or "both"), his hit rate, the rarity of a streak this long for HIM
((1 - p)^drought, and `one_in`: "1 in N for him" from the unrounded figure)
and the band's measured record from the committed backtest.

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
THRESHOLDS = {"points": 70, "goals": 25, "assists": 30}
#: The tier bar: (floor of last season's total, drought that lists him), best
#: band first. The last floor of each category is the base qualifier.
TIERS: dict[str, tuple[tuple[int, int], ...]] = {
    "points": ((100, 3), (85, 4), (70, 5)),
    "goals": ((40, 5), (25, 10)),
    "assists": ((60, 3), (45, 4), (30, 5)),
}
#: The surprise bar's level: the smallest drought with (1 - p)^n <= this.
SURPRISE_LEVEL = 0.05
#: The categories the surprise bar lists in. Goals left it on 2026-10-10
#: (Cooper, after `scripts/run_due_list_tuning.py`): 25+ goals at a 10-game
#: drought was the one setting both bought seasons chose, and he kept 40+ at 5.
SURPRISE_MARKETS = ("points", "assists")
LINE = 0.5
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
    per_game = logs[["player_id", "season_start", *THRESHOLDS]].copy()
    for market in THRESHOLDS:
        per_game["hit_" + market] = (per_game[market] >= 1).astype(int)
    per_game["gp"] = 1
    prior = per_game.groupby(["player_id", "season_start"]).sum().reset_index()
    prior["season_start"] += 1
    prior = prior.rename(columns={**{m: "prior_" + m for m in THRESHOLDS},
                                  **{"hit_" + m: "prior_hit_" + m for m in THRESHOLDS}, "gp": "prior_gp"})
    return logs.merge(prior, on=["player_id", "season_start"], how="left")


QUALIFIER_COLUMNS = ["player_id", "player", "market", "last_season", "drought",
                     "tier_bar", "surprise_bar", "hit_rate", "rarity", "one_in", "rule", "band"]


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
            rows.append({"player_id": int(r.player_id), "player": r.player, "market": market,
                         "last_season": total, "drought": drought, **found})
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
) -> DroughtList:
    """Tonight's qualifiers with the best staged price each, if any is posted.

    Needs only logs, rosters and the schedule; `prices` may be empty, and then
    every row reads "not posted". A price is the best American odds any book
    staged for that player's over 0.5 in that game. It is never filled in:
    no price, no number. A price name that matches two players on the game
    resolves to neither and is listed in `unresolved`. `records` is
    `cell_records(...)`, the band records the committed backtest measured;
    a row whose band has none carries `cell_record` None, never a guess.
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

    qualified = qualifiers_entering(logs, day)
    team_of = {pid: str(team).strip().upper() for pid, team in rosters.items()}
    playing = {team: (h, a) for (h, a) in games for team in (h, a)}
    records = records or {}
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
            "player": q.player, "player_id": int(q.player_id), "market": q.market, "line": LINE,
            "selection": "over", "last_season": int(q.last_season), "drought": int(q.drought),
            "tier_bar": int(q.tier_bar), "surprise_bar": _optional_int(q.surprise_bar),
            "hit_rate": float(q.hit_rate), "rarity": float(q.rarity), "one_in": _optional_int(q.one_in),
            "rule": str(q.rule), "band": str(q.band),
            "cell_record": dict(record) if record is not None else None,
            "american_odds": None, "book": "", "heavy_juice": False,
        })
    guarded = apply_puck_drop_guard(candidates, now=now)
    result.removed_by_guard = len(guarded.quarantined)
    rows = [{k: v for k, v in row.items() if not k.startswith("puck_drop_")} for row in guarded.playable]

    best, unresolved = best_over_prices(rows, prices=prices, logs=logs, team_of=team_of,
                                        playing=playing, team_names=team_names, day=day)
    for row in rows:
        priced = best.get((row["player_id"], row["market"]))
        if priced:
            row["american_odds"], row["book"] = priced
            row["heavy_juice"] = priced[0] < HEAVY_JUICE
    order = {m: i for i, m in enumerate(THRESHOLDS)}
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
) -> tuple[dict[tuple[int, str], tuple[float, str]], set[str]]:
    """The best over 0.5 price any book in `prices` quoted for each listed row.

    Returns ({(player id, market): (American odds, book)}, unresolved names).
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
    best: dict[tuple[int, str], tuple[float, str]] = {}
    unresolved: set[str] = set()
    wanted = {(r["player_id"], r["market"]) for r in rows}
    if prices is not None and not prices.empty and rows:
        quotes = prices[prices["market"].astype(str).str.strip().isin(THRESHOLDS)
                        & (prices["selection"].astype(str).str.strip().str.lower() == "over")
                        & (pd.to_numeric(prices["line"], errors="coerce") == LINE)]
        for p in quotes.itertuples():
            game = (resolve_team(clean_text(p.home_team), team_names), resolve_team(clean_text(p.away_team), team_names))
            if game not in on_game or row_game_date(p) != day:
                continue
            ids: set[int] = set()
            for alias in player_name_aliases(p.player):
                ids |= on_game[game].get(alias, set())
            market = str(p.market).strip()
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
            if key not in best or _decimal(float(odds)) > _decimal(best[key][0]):
                best[key] = (float(odds), clean_text(p.book))
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
