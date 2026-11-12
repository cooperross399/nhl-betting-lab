"""The weekly review's scorecard (Cooper, 2026-11-12).

Cooper: "I want this to become a weekly task where you analyze the entire
model, the lineup, and the nhl section of website and you find
improvements/upgrades/ways to make more profits." The weekly task reads
this file first, so every week starts from the same numbers rather than
from a fresh hand-rolled analysis.

It answers three questions from what the lab already holds, offline and
for no credit:

1. **How much does the card stake?** Best bets by the league day that first
   listed them, from card-feed's card history, with their units. A card
   staking one bet a night where it staked twenty is a change worth seeing
   even when no single night looks wrong.
2. **How have the staked best bets done?** Settled on the forward ledger at
   the card's listed price, one unit flat and at the card's own units, by
   market and side, for the season and for the last seven league days.
3. **Which market and side keeps losing?** Every settled opinion clearing
   the measurement bar on its SELF-LEARNED edge (`self_learning`, fitted
   each day on the ledger before it, after a week's warm-up, as the card
   applies it), by market and side, split into the window's two halves. A
   side losing in both halves is flagged, and so is one winning in both.

A flag is a lead for the weekly task to look into, never a change on its
own: two halves of a few weeks cannot separate a side from zero, and the
report says so. Aggregates only: no price, line, book or player.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from nhl_betting_lab.self_learning import (
    TEAM_MARKETS,
    Trust,
    adjusted,
    fit_trust,
    learnable_wagers,
    side_key,
    side_of,
)

#: The measurement bars the walk-forward population is cut at, as the CLV
#: report's Bets view and the forward report's population B cut.
PROP_BAR = 0.06
TEAM_BAR = 0.035
#: Prices the card may stake.
SHORTEST = -160.0
LONGEST = 600.0
#: Days of ledger before the first day the walk-forward scores.
WARMUP_DAYS = 7
#: The fewest wagers in each half before a side is flagged either way.
MIN_PER_HALF = 20
#: Bootstrap draws for the game-clustered interval.
DRAWS = 2000

_KEY = ["snapshot_date", "home_team", "away_team", "market", "player", "selection", "line", "american_odds"]


@dataclass(frozen=True)
class Interval:
    n: int
    games: int
    units: float
    roi: float
    low: float
    high: float


def clustered_roi(units: Sequence[float], games: Sequence[object], *, seed: int = 0) -> Interval | None:
    """Return on one unit flat, with a 95% interval bootstrapped over games.

    Every rung, side and player of one game settles on one boxscore, so the
    game is the draw. None for no wagers; one game gives an unbounded
    interval, printed as such.
    """
    frame = pd.DataFrame({"u": list(units), "g": [str(g) for g in games]})
    if frame.empty:
        return None
    per = frame.groupby("g")["u"].agg(["sum", "size"])
    total = float(per["sum"].sum())
    n = int(per["size"].sum())
    roi = total / n
    if len(per) < 2:
        return Interval(n, len(per), total, roi, -math.inf, math.inf)
    rng = np.random.default_rng(seed)
    sums = per["sum"].to_numpy()
    sizes = per["size"].to_numpy()
    draws = rng.integers(0, len(per), size=(DRAWS, len(per)))
    rois = sums[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    return Interval(n, len(per), total, roi, float(np.percentile(rois, 2.5)), float(np.percentile(rois, 97.5)))


def side_label(market: str, selection: object, line: object = None) -> str:
    """The side a pick sits on, in the self-learning's vocabulary."""
    return side_of(market, selection, line)


def staked_volume(listings: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Best bets and units by the league day that first listed them."""
    if not listings:
        return pd.DataFrame(columns=["day", "best_bets", "units"])
    frame = pd.DataFrame(
        {"day": [item["day"] for item in listings], "units": [float(item.get("units") or 0.0) for item in listings]}
    )
    out = frame.groupby("day").agg(best_bets=("units", "size"), units=("units", "sum")).reset_index()
    return out.sort_values("day").reset_index(drop=True)


def staked_record(
    listings: Sequence[Mapping[str, Any]], scored: Sequence[Mapping[str, Any]], *, since: str | None = None
) -> list[dict[str, Any]]:
    """The settled best bets by market and side: W-L-P, units at 1u and at
    the card's own units. `scored` is `pick_timing.score` of `listings`, in
    the same order."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item, result in zip(listings, scored):
        if since and str(item["day"]) < since:
            continue
        profit = result.get("profit")
        outcome = str(result.get("outcome", ""))
        if profit is None and outcome != "push":
            continue
        key = (str(item["market"]), side_label(str(item["market"]), item.get("selection"), item.get("line")))
        row = groups.setdefault(key, {"market": key[0], "side": key[1], "won": 0, "lost": 0, "push": 0,
                                      "units_flat": 0.0, "units_card": 0.0, "units_n": []})
        if outcome == "won":
            row["won"] += 1
        elif outcome == "lost":
            row["lost"] += 1
        else:
            row["push"] += 1
        flat = float(profit or 0.0)
        row["units_flat"] += flat
        row["units_card"] += flat * float(item.get("units") or 0.0)
    out = []
    for row in groups.values():
        row.pop("units_n")
        row["bets"] = row["won"] + row["lost"] + row["push"]
        out.append(row)
    return sorted(out, key=lambda r: (r["market"], r["side"]))


def learned_population(ledger: pd.DataFrame, *, warmup_days: int = WARMUP_DAYS) -> pd.DataFrame:
    """Every settled wager with its self-learned edge, each day learned on
    the ledger settled before it (by side, as the card learns)."""
    wagers = learnable_wagers(ledger)
    if wagers.empty:
        return pd.DataFrame()
    units = ledger.assign(
        player=ledger["player"].fillna(""), line=pd.to_numeric(ledger["line"], errors="coerce").fillna(-999.0)
    ).drop_duplicates(_KEY)
    wagers = wagers.merge(units[_KEY + ["profit_units"]], on=_KEY, how="left")
    days = sorted(wagers["snapshot_date"].astype(str).unique())
    rows = []
    for day in days[warmup_days:]:
        trust = fit_trust(ledger[ledger["snapshot_date"].astype(str) < day], by_side=True)
        for row in wagers[wagers["snapshot_date"].astype(str) == day].itertuples():
            if pd.isna(row.profit_units):
                continue
            side = side_of(row.market, row.selection, row.line)
            learned_trust = trust.get(side_key(row.market, side)) or trust.get(row.market, Trust())
            probability = adjusted(row.model_probability, row.american_odds, learned_trust)
            rows.append({
                "day": day,
                "game": f"{day}|{row.home_team}|{row.away_team}",
                "market": row.market,
                "side": side,
                "american_odds": float(row.american_odds),
                "edge": probability - 1.0 / float(row.decimal),
                "units": float(row.profit_units),
            })
    return pd.DataFrame(rows)


def side_trends(population: pd.DataFrame) -> tuple[list[dict[str, Any]], str]:
    """Each market and side above the measurement bar, by half of the window."""
    if population.empty:
        return [], ""
    frame = population[
        (population["american_odds"] >= SHORTEST) & (population["american_odds"] <= LONGEST)
    ]
    team = frame["market"].isin(TEAM_MARKETS)
    frame = frame[(team & (frame["edge"] >= TEAM_BAR)) | (~team & (frame["edge"] >= PROP_BAR))]
    if frame.empty:
        return [], ""
    days = sorted(population["day"].unique())
    split = days[len(days) // 2]
    out = []
    for (market, side), part in frame.groupby(["market", "side"]):
        first = part[part["day"] < split]
        second = part[part["day"] >= split]
        whole = clustered_roi(part["units"], part["game"])
        flag = ""
        if len(first) >= MIN_PER_HALF and len(second) >= MIN_PER_HALF:
            if first["units"].sum() < 0 and second["units"].sum() < 0:
                flag = "loses in both halves"
            elif first["units"].sum() > 0 and second["units"].sum() > 0:
                flag = "wins in both halves"
        out.append({
            "market": market,
            "side": side,
            "wagers": whole.n if whole else 0,
            "games": whole.games if whole else 0,
            "units": whole.units if whole else 0.0,
            "roi": whole.roi if whole else 0.0,
            "low": whole.low if whole else None,
            "high": whole.high if whole else None,
            "first_half": {"wagers": len(first), "units": float(first["units"].sum())},
            "second_half": {"wagers": len(second), "units": float(second["units"].sum())},
            "flag": flag,
        })
    return sorted(out, key=lambda r: r["units"]), split


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    if math.isinf(value):
        return "+inf%" if value > 0 else "-inf%"
    return f"{100 * value:+.1f}%"


def build_review(
    listings: Sequence[Mapping[str, Any]],
    scored: Sequence[Mapping[str, Any]],
    population: pd.DataFrame,
    *,
    today: str,
    last_week_from: str,
) -> dict[str, Any]:
    volume = staked_volume(listings)
    trends, split = side_trends(population)
    return {
        "today": today,
        "last_week_from": last_week_from,
        "volume": volume.to_dict("records"),
        "season": staked_record(listings, scored),
        "last_week": staked_record(listings, scored, since=last_week_from),
        "trends": trends,
        "split_day": split,
        "window": [str(population["day"].min()), str(population["day"].max())] if not population.empty else [],
        "bars": {"prop": PROP_BAR, "team": TEAM_BAR, "shortest": SHORTEST, "longest": LONGEST},
    }


def _record_table(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    if not rows:
        return ["No settled best bets in this window.", ""]
    lines = [
        "| Market | Side | Bets | W-L-P | Units at 1u | Units at the card's stake |",
        "|:--|:--|--:|:--|--:|--:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['market']}` | {r['side']} | {r['bets']} | {r['won']}-{r['lost']}-{r['push']} "
            f"| {r['units_flat']:+.2f}u | {r['units_card']:+.2f}u |"
        )
    flat = sum(r["units_flat"] for r in rows)
    card = sum(r["units_card"] for r in rows)
    bets = sum(r["bets"] for r in rows)
    lines.append(f"| **All** | | {bets} | | {flat:+.2f}u | {card:+.2f}u |")
    lines.append("")
    return lines


def render(review: Mapping[str, Any], *, generated: str = "") -> str:
    lines = ["# Weekly review", ""]
    if generated:
        lines.append(f"- Generated: {generated}")
    lines += [
        "- Sources: every card on card-feed (best bets at the run that first listed them, at the card's "
        "listed price) and the forward ledger. Offline, no credit.",
        "- Aggregates only: no price, line, book or player.",
        "",
        "## How much the card stakes",
        "",
        "| League day | Best bets | Units |",
        "|:--|--:|--:|",
    ]
    for row in list(review["volume"])[-21:]:
        lines.append(f"| {row['day']} | {int(row['best_bets'])} | {float(row['units']):.2f} |")
    lines += ["", f"## Best bets since {review['last_week_from']}", ""]
    lines += _record_table(review["last_week"])
    lines += ["## Best bets this season", ""]
    lines += _record_table(review["season"])
    bars = review["bars"]
    window = review.get("window") or ["", ""]
    lines += [
        "## Market and side on the self-learned edge",
        "",
        f"Every settled opinion whose self-learned edge clears {bars['prop']:.0%} (prop) or "
        f"{bars['team']:.1%} (team), priced {bars['shortest']:+.0f} to {bars['longest']:+.0f}, one bet per "
        f"wager at the best frozen price, one unit flat, {window[0]} to {window[-1]} after a "
        f"{WARMUP_DAYS}-day warm-up, each day learned only on what had settled before it. Split at "
        f"{review.get('split_day') or '—'}. A side is flagged only with {MIN_PER_HALF}+ wagers in each half.",
        "",
        "| Market | Side | Wagers | Games | Units | ROI [95%, by game] | First half | Second half | Flag |",
        "|:--|:--|--:|--:|--:|:--|:--|:--|:--|",
    ]
    for r in review["trends"]:
        lines.append(
            f"| `{r['market']}` | {r['side']} | {r['wagers']} | {r['games']} | {r['units']:+.1f}u "
            f"| {_pct(r['roi'])} [{_pct(r['low'])}, {_pct(r['high'])}] "
            f"| {r['first_half']['units']:+.1f}u / {r['first_half']['wagers']} "
            f"| {r['second_half']['units']:+.1f}u / {r['second_half']['wagers']} | {r['flag'] or '—'} |"
        )
    lines += [
        "",
        "A flag is a lead, not a finding: an interval that includes zero means **no demonstrated edge**, "
        "and a change made on a flag alone is tuning on noise. The weekly task looks into each flag before "
        "anything moves on the card.",
        "",
    ]
    return "\n".join(lines)
