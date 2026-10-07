"""Cooper's drought rule, in one place, for the evidence and for the card.

The rule (Cooper, 2026-10-07): a skater with 70+ points, 30+ goals or 30+
assists LAST regular season, on a run of 5+ straight games without one in that
category, is a bet on the over 0.5 in that category.

`scripts/run_drought_rule_backtest.py` measures it against bought prices and
the Gameday card lists tonight's qualifiers from it. Both call `prepare_logs`
below, so the card cannot disagree with the evidence about who qualifies: the
card asks it about a game that has not happened yet (`qualifiers_entering`),
which is the same function with one more row per player.

This is a list Cooper picks from. Nothing here stakes, tiers or ranks a
selection, and nothing here reaches the model's selections, the edge bar, the
market list or the registered forward test.
"""

from __future__ import annotations

import json
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

THRESHOLDS = {"points": 70, "goals": 30, "assists": 30}
MIN_DROUGHT = 5
LINE = 0.5
BACKTEST_JSON = "drought_rule_backtest.json"
SECTION_TITLE = "Drought rule — Cooper's list"

#: Prices shorter than this are flagged on the row, never hidden: Cooper picks.
HEAVY_JUICE = MAX_DEFAULT_JUICE

#: A game id no real game has, so the sentinel row sorts after every real one
#: and is told apart from them.
_TONIGHT_GAME_ID = 10**12


def drought_before(values) -> list[int]:
    """Games in a row without the stat, entering each game (the game itself excluded)."""
    out, run = [], 0
    for v in values:
        out.append(run)
        run = run + 1 if v == 0 else 0
    return out


def prepare_logs(logs: pd.DataFrame) -> pd.DataFrame:
    """Skater games with each category's drought entering the game and last season's totals."""
    logs = logs[(logs.role == "skater") & (logs.game_type == 2)].copy()
    logs = logs.sort_values(["player_id", "date", "game_id"])
    logs["season_start"] = logs.season // 10000
    for market in THRESHOLDS:
        logs["drought_" + market] = logs.groupby("player_id")[market].transform(
            lambda s: pd.Series(drought_before(s.values), index=s.index))
    prior = logs.groupby(["player_id", "season_start"])[list(THRESHOLDS)].sum().reset_index()
    prior["season_start"] += 1
    prior = prior.rename(columns={m: "prior_" + m for m in THRESHOLDS})
    return logs.merge(prior, on=["player_id", "season_start"], how="left")


def qualifiers_entering(logs: pd.DataFrame, day: str) -> pd.DataFrame:
    """Every (player, category) that qualifies for a game on league date `day`.

    Columns: player_id, player, market, last_season, drought. Built by giving
    each skater one more game, dated after every real one and in `day`'s
    season, with a point, a goal and an assist, and asking `prepare_logs`
    what that game's drought and prior totals are. `prepare_logs` is the
    backtest's own function, so the drought runs across the season boundary
    and counts only regular-season games the player dressed for, exactly as
    the evidence does. Games dated on or after `day` are left out: tonight is
    entered, not played.
    """
    columns = ["player_id", "player", "market", "last_season", "drought"]
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
        hit = entering[(entering["prior_" + market] >= bar) & (entering["drought_" + market] >= MIN_DROUGHT)]
        for r in hit.itertuples():
            rows.append({"player_id": int(r.player_id), "player": r.player, "market": market,
                         "last_season": int(getattr(r, "prior_" + market)),
                         "drought": int(getattr(r, "drought_" + market))})
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


def build_drought_list(
    *,
    logs: pd.DataFrame,
    rosters: Mapping[int, str],
    starts: Mapping[tuple[str, str, str], str],
    prices: pd.DataFrame,
    team_names: Mapping[str, str],
    day: str,
    now: datetime,
) -> DroughtList:
    """Tonight's qualifiers with the best staged price each, if any is posted.

    Needs only logs, rosters and the schedule; `prices` may be empty, and then
    every row reads "not posted". A price is the best American odds any book
    staged for that player's over 0.5 in that game. It is never filled in:
    no price, no number. A price name that matches two players on the game
    resolves to neither and is listed in `unresolved`.
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
    candidates: list[dict[str, Any]] = []
    for q in qualified.itertuples():
        team = team_of.get(int(q.player_id))
        if team not in playing:
            continue
        home, away = playing[team]
        candidates.append({
            "date": day, "commence_time": games[(home, away)], "home_team": home, "away_team": away,
            "team": team, "opponent": away if team == home else home,
            "player": q.player, "player_id": int(q.player_id), "market": q.market, "line": LINE,
            "selection": "over", "last_season": int(q.last_season), "drought": int(q.drought),
            "american_odds": None, "book": "", "heavy_juice": False,
        })
    guarded = apply_puck_drop_guard(candidates, now=now)
    result.removed_by_guard = len(guarded.quarantined)
    rows = [{k: v for k, v in row.items() if not k.startswith("puck_drop_")} for row in guarded.playable]

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
    if not prices.empty and rows:
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
    for row in rows:
        priced = best.get((row["player_id"], row["market"]))
        if priced:
            row["american_odds"], row["book"] = priced
            row["heavy_juice"] = priced[0] < HEAVY_JUICE
    order = {m: i for i, m in enumerate(THRESHOLDS)}
    rows.sort(key=lambda r: (order[r["market"]], -r["drought"], r["player"]))
    result.rows = rows
    result.unresolved = sorted(unresolved)
    return result


def _decimal(american: float) -> float:
    return 1 + american / 100 if american > 0 else 1 + 100 / -american


def backtest_headline(directory: Path | None = None, *, fallback: Path | None = None) -> str:
    """One line: what the committed backtest measured, read from its own JSON.

    `directory` first, then `fallback` (the repository's outputs). Words only
    where the numbers permit them: "no category clears zero" is printed only
    when no card-window interval sits above zero. With no file, it says so.
    """
    for base in (directory, fallback):
        path = Path(base) / BACKTEST_JSON if base else None
        if path and path.is_file():
            break
    else:
        return f"Backtest headline unavailable: {BACKTEST_JSON} was not found."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rule = {b["market"]: b for b in payload["buckets"]
                if b["window"] == "card" and b["season"] == "both" and b["bucket"].startswith("RULE")}
        parts = [f"{m} {rule[m]['roi'] * 100:+.1f}% over {rule[m]['wagers']} wagers "
                 f"(95% {rule[m]['ci_low'] * 100:+.1f}% to {rule[m]['ci_high'] * 100:+.1f}%)" for m in THRESHOLDS]
        above = [m for m in THRESHOLDS if rule[m]["ci_low"] > 0]
    except (OSError, ValueError, KeyError, TypeError):
        return f"Backtest headline unavailable: {BACKTEST_JSON} could not be read."
    verdict = ("no category's interval sits above zero" if not above
               else f"{', '.join(above)} sits above zero")
    return ("Backtest on 2024-25 and 2025-26 bought prices, best price, card window, flat stake: "
            + "; ".join(parts) + f"; {verdict}.")


def price_text(row: Mapping[str, Any]) -> str:
    odds = row.get("american_odds")
    if odds is None or (isinstance(odds, float) and np.isnan(odds)):
        return "not posted"
    return f"{int(odds):+d}" if float(odds).is_integer() else f"{float(odds):+.1f}"


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
