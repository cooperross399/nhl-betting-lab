"""Cooper's Hot List: the opposite of the Due List, an unstaked list he picks from.

Cooper, 2026-11-19: "could we investigate the possibility of adding a HOT list
like guys who are playing super well or on point/goal/assist streaks". The
rules were picked by `scripts/run_due_hot_research.py` (Due List Tuning on
#491): every floor (last season's total in the stat), streak length (games in
a row with one) and last-five total was measured on the two bought seasons at
the best card-window over 0.5, and each market's setting is the one whose
WORSE season returned most, with 150+ wagers and 50+ in each season. Then the
pick was read on this season's forward ledger, which it was not chosen on:

- points: 80+ points last season and 8+ points in his last 5 games.
  Bought seasons +0.7% over 360 (95% -6.6% to +7.6%); this season +1.2% over
  141.
- assists: 60+ assists last season and 6+ assists in his last 5 games.
  Bought seasons -0.6% over 382 (-8.0% to +7.1%); this season +11.4% over
  101 (-6.6% to +29.0%).
- goals: 40+ goals last season and a goal in each of his last 2+ games.
  Bought seasons -0.9% over 264 (-15.6% to +14.0%); this season -13.6% over
  38.

Every interval spans zero: no demonstrated edge. The list is close to break
even where the average over 0.5 loses (every points over 0.5 -4.4% over
36,933 on the bought seasons, assists -8.8%, goals -19.8%): the books already
price a hot streak. A streak counts regular-season games he dressed for and
runs across the season boundary, exactly as the research counts it.

It is a LIST, like the Due List: no units, nothing in the model's selections,
the selection fingerprint, the stakes, the snapshot, the forward ledger or the
registered test. The site tracks it at the Due List's notional sizes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.drought_rule import HEAVY_JUICE, DroughtList, _decimal, best_over_prices, drop_short_points
from nhl_betting_lab.puck_drop import apply_puck_drop_guard
from nhl_betting_lab.season import season_id

SECTION_TITLE = "Hot List"
LINE = 0.5
FORM_GAMES = 5

#: Per market: the floor on last season's total, and the form that lists him
#: ("last5": `bar` or more in his last FORM_GAMES games; "streak": one or more
#: in each of his last `bar` games or more).
HOT_RULES: dict[str, dict[str, Any]] = {
    "points": {"floor": 80, "kind": "last5", "bar": 8},
    "assists": {"floor": 60, "kind": "last5", "bar": 6},
    "goals": {"floor": 40, "kind": "streak", "bar": 2},
}

#: Each rule's measured record (research run 44436727242, card window, best
#: price, 1u flat, 95% interval bootstrapped over nights). Read beside the row,
#: never a filter.
HOT_RECORDS: dict[str, dict[str, Any]] = {
    "points": {"wagers": 360, "returnPct": 0.7, "lowPct": -6.6, "highPct": 7.6,
               "liveWagers": 141, "liveReturnPct": 1.2},
    "assists": {"wagers": 382, "returnPct": -0.6, "lowPct": -8.0, "highPct": 7.1,
                "liveWagers": 101, "liveReturnPct": 11.4},
    "goals": {"wagers": 264, "returnPct": -0.9, "lowPct": -15.6, "highPct": 14.0,
              "liveWagers": 38, "liveReturnPct": -13.6},
}

HEADLINE = (
    "Hot List: 80+ points last season and 8+ points in his last 5; 60+ assists and 6+ assists in his last 5; "
    "40+ goals and a goal in 2+ straight games. On two past seasons at the best price: points +0.7% over 360, "
    "assists -0.6% over 382, goals -0.9% over 264; this season so far +1.2% over 141, +11.4% over 101 and "
    "-13.6% over 38. Every range spans zero: no demonstrated edge. Books already price a hot streak."
)

QUALIFIER_COLUMNS = ["player_id", "player", "market", "last_season", "last5", "streak", "rule", "bar"]
SITE_LIST_FILENAME = "hot_list.json"
CATEGORY_LABELS = {"points": "1+ point", "goals": "anytime goal", "assists": "1+ assist"}


def streak_entering(values) -> int:
    """Games in a row with one or more, ending at his last game."""
    run = 0
    for v in reversed(list(values)):
        if v >= 1:
            run += 1
        else:
            break
    return run


def form_text(row: Mapping[str, Any]) -> str:
    unit = {"points": "points", "goals": "goals", "assists": "assists"}.get(str(row.get("market")), "")
    if row.get("rule") == "streak":
        return f"{row.get('streak')} straight games with one"
    return f"{row.get('last5')} {unit} in his last {FORM_GAMES}"


def hot_qualifiers_entering(logs: pd.DataFrame, day: str) -> pd.DataFrame:
    """Every (player, market) on the Hot List for a game on league date `day`.

    Read from regular-season skater games dated before `day`: last season's
    total in the stat, his last FORM_GAMES games' total and his streak, both
    running across the season boundary.
    """
    needed = {"role", "game_type", "season", "date", "game_id", "player_id", "player", *HOT_RULES}
    if logs.empty or not needed <= set(logs.columns):
        return pd.DataFrame(columns=QUALIFIER_COLUMNS)
    before = logs[logs["date"].astype(str).str.slice(0, 10) < day]
    s = before[(before.role == "skater") & (before.game_type == 2)].sort_values(["player_id", "date", "game_id"])
    if s.empty:
        return pd.DataFrame(columns=QUALIFIER_COLUMNS)
    prior_start = int(season_id(day)) // 10000 - 1
    prior = s[pd.to_numeric(s.season, errors="coerce") // 10000 == prior_start]
    totals = {m: pd.to_numeric(prior[m], errors="coerce").fillna(0).groupby(prior.player_id).sum() for m in HOT_RULES}
    rows = []
    for market, rule in HOT_RULES.items():
        eligible = totals[market][totals[market] >= rule["floor"]].index
        for pid in eligible:
            g = s[s.player_id == pid]
            vals = pd.to_numeric(g[market], errors="coerce").fillna(0).to_numpy()
            last5 = int(vals[-FORM_GAMES:].sum()) if len(vals) >= FORM_GAMES else None
            streak = streak_entering(vals)
            reached = (last5 is not None and last5 >= rule["bar"]) if rule["kind"] == "last5" else streak >= rule["bar"]
            if reached:
                rows.append({"player_id": int(pid), "player": g.player.iloc[-1], "market": market,
                             "last_season": int(totals[market][pid]), "last5": last5, "streak": streak,
                             "rule": rule["kind"], "bar": int(rule["bar"])})
    return pd.DataFrame(rows, columns=QUALIFIER_COLUMNS)


def build_hot_list(
    *,
    logs: pd.DataFrame,
    rosters: Mapping[int, str],
    starts: Mapping[tuple[str, str, str], str],
    prices: pd.DataFrame,
    team_names: Mapping[str, str],
    day: str,
    now: datetime,
    probabilities: Mapping[tuple, float] | None = None,
) -> DroughtList:
    """Tonight's Hot List with the best staged over 0.5 price each, if any is posted.

    The Due List's own plumbing: the club is the roster's, the puck-drop guard
    applies, and a price is the best any book staged, never filled in.
    Sorted by market, then hottest first, then name.
    """
    result = DroughtList(day=day)
    if logs.empty:
        result.notes.append("No player logs are on disk, so no qualifier could be found.")
        return result
    if not rosters:
        result.notes.append("No rosters are cached, so no qualifier can be placed on a team and none is listed.")
        return result
    games = {(h, a): start for (d, h, a), start in starts.items() if d == day}
    if not games:
        result.notes.append(f"No regular-season game is scheduled for {day}.")
        return result
    qualified = hot_qualifiers_entering(logs, day)
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
            "selection": "over", "last_season": int(q.last_season),
            "last5": None if q.last5 is None or pd.isna(q.last5) else int(q.last5), "streak": int(q.streak),
            "rule": str(q.rule), "bar": int(q.bar), "record": dict(HOT_RECORDS.get(q.market, {})) or None,
            "american_odds": None, "book": "", "heavy_juice": False,
            "model_probability": None, "model_edge": None,
        })
    guarded = apply_puck_drop_guard(candidates, now=now)
    result.removed_by_guard = len(guarded.quarantined)
    rows = [{k: v for k, v in row.items() if not k.startswith("puck_drop_")} for row in guarded.playable]
    best, unresolved = best_over_prices(rows, prices=prices, logs=logs, team_of=team_of, playing=playing,
                                        team_names=team_names, day=day, probabilities=probabilities)
    for row in rows:
        priced = best.get((row["player_id"], row["market"]))
        if priced:
            row["american_odds"], row["book"] = priced[0], priced[1]
            row["heavy_juice"] = priced[0] < HEAVY_JUICE
            chance = priced[2] if len(priced) > 2 else None
            if chance is not None:
                row["model_probability"] = round(float(chance), 4)
                row["model_edge"] = round(float(chance) - 1 / _decimal(priced[0]), 4)
    rows = drop_short_points(rows, result.notes)
    order = {m: i for i, m in enumerate(HOT_RULES)}
    rows.sort(key=lambda r: (order[r["market"]], -(r["last5"] or 0) if r["rule"] == "last5" else -r["streak"], r["player"]))
    result.rows = rows
    result.unresolved = sorted(unresolved)
    return result


def site_payload(result: DroughtList, generated_at: str) -> dict[str, Any]:
    """What the site builder reads; a price the card did not stage is null."""
    return {"generated_at": generated_at, "day": result.day, "headline": HEADLINE,
            "rows": result.rows, "unresolved": result.unresolved, "notes": result.notes}


def save_site_list(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")


def render_section(rows: list[Mapping[str, Any]], notes: list[str], unresolved: list[str]) -> list[str]:
    """The card's Hot List section, under the Due List."""
    from nhl_betting_lab.drought_forward import tracked_stake

    lines = [f"## {SECTION_TITLE}", "", HEADLINE, ""]
    if rows:
        lines += ["| Player | Team | Opponent | Category | Line | Last season | Form | Model | Best price | Book "
                  "| Tracked at | Flag |", "|:--|:--|:--|:--|--:|--:|:--|:--|--:|:--|--:|:--|"]
        for row in rows:
            odds = row.get("american_odds")
            priced = odds is not None and not (isinstance(odds, float) and odds != odds)
            price = (f"{int(odds):+d}" if priced else "not posted")
            chance = row.get("model_probability")
            model = f"{chance:.0%}" if isinstance(chance, (int, float)) and chance == chance else "-"
            lines.append(
                f"| {row.get('player')} | {row.get('team')} | {row.get('opponent')} "
                f"| {CATEGORY_LABELS.get(str(row.get('market')), row.get('market'))} | over {LINE} "
                f"| {row.get('last_season')} | {form_text(row)} | {model} | {price} | {row.get('book') or '-'} "
                f"| {f'{tracked_stake(price=odds):g}u' if priced else '-'} "
                f"| {'heavy juice (shorter than -160)' if row.get('heavy_juice') else ''} |"
            )
        lines += ["", "A list, not bets: no units, no stakes, and none of it is in the best bets above. "
                  "\"Tracked at\" is the notional size the site's Hot List record counts it at.", ""]
    else:
        lines += ["_Nobody on tonight's slate qualifies._", ""]
    lines += [f"- {n}" for n in notes]
    lines += [f"- Not resolved, so no price is shown for it: {n}" for n in unresolved]
    if notes or unresolved:
        lines.append("")
    return lines


__all__ = ["HOT_RULES", "HOT_RECORDS", "HEADLINE", "SITE_LIST_FILENAME", "build_hot_list",
           "hot_qualifiers_entering", "render_section", "save_site_list", "site_payload", "streak_entering"]

