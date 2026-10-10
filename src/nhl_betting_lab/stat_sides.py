"""Stat sides: the team the model expects to win each game, with its chance.

Cooper, 2026-10-10: "I want to make sure were not only looking for edges but
looking for sides that the stats say should win." The card's best bets are
where the model's probability beats the price, so a game whose favourite is
priced right never shows who the stats favour. This list shows it for every
priced game: the side with the larger moneyline win probability (the team
ratings the card prices on, xG plus goaltending and finishing since
2026-10-06), the best moneyline price staged for that side, and how the
probability compares with the price.

It is a LIST, like the Due List: no units, no stake, nothing in the best bets,
leans or passes, the selection fingerprint, the frozen snapshot, the forward
ledger or its report. It reads the same probability map the card prices from
and changes none of it, so the registered 2027-04-25 test is untouched.

A game is listed only when both moneyline sides carry a model probability
(absence means no opinion, never a default). A game that has started, or
whose start cannot be confirmed, is not listed (the puck-drop guard).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from nhl_betting_lab.models.value import (
    OddsError,
    american_to_implied,
    implied_to_american,
)
from nhl_betting_lab.puck_drop import apply_puck_drop_guard
from nhl_betting_lab.reports.card_pricing import _line, selection_key

SECTION_TITLE = "Stat sides"
MARKET = "moneyline"
SIDES = ("home", "away")


@dataclass
class StatSides:
    rows: list[dict[str, Any]] = field(default_factory=list)
    #: Games left out because their start has passed or cannot be confirmed.
    removed_by_guard: int = 0
    #: Games with moneyline prices but a model opinion on fewer than both sides.
    without_opinion: int = 0


def _best_prices(prices: pd.DataFrame) -> dict[tuple, Any]:
    """The best staged moneyline row per selection key, as the card takes it."""
    best: dict[tuple, Any] = {}
    if prices.empty or "market" not in prices.columns:
        return best
    rows = prices[prices["market"].astype(str).str.strip() == MARKET]
    for row in rows.itertuples():
        selection = str(getattr(row, "selection", "")).strip().lower()
        if selection not in SIDES:
            continue
        try:
            price = float(getattr(row, "american_odds"))
            american_to_implied(price)
        except (OddsError, TypeError, ValueError):
            continue
        key = selection_key(
            row, market=MARKET, selection=selection, line=_line(getattr(row, "line", None))
        )
        current = best.get(key)
        if current is None or price > float(getattr(current, "american_odds")):
            best[key] = row
    return best


def build_stat_sides(
    prices: pd.DataFrame,
    probabilities: Mapping[tuple, float],
    *,
    now: datetime | None = None,
    best_bets: Sequence[Mapping[str, Any]] = (),
    day: str | None = None,
) -> StatSides:
    """Every priced game's model-favoured side, soonest game first.

    `day` (a league date, YYYY-MM-DD) keeps only that night's games; the bulk
    board can carry tomorrow's too.
    """
    moment = now or datetime.now(timezone.utc)
    best = _best_prices(prices)
    games: dict[tuple, dict[str, Any]] = {}
    for key, row in best.items():
        _market, _player, home, away, selection, _line, game_day = key
        if day is not None and str(game_day) != str(day):
            continue
        games.setdefault((home, away, game_day), {})[selection] = (key, row)

    staked = {
        (str(r.get("home_team")), str(r.get("away_team")), str(r.get("selection")))
        for r in best_bets
        if str(r.get("market")) == MARKET
    }

    out = StatSides()
    candidates: list[dict[str, Any]] = []
    for (home, away, game_day), sides in games.items():
        chance = {
            side: probabilities.get(sides[side][0]) if side in sides else None
            for side in SIDES
        }
        if any(value is None for value in chance.values()):
            out.without_opinion += 1
            continue
        side = "home" if float(chance["home"]) >= float(chance["away"]) else "away"
        _key, row = sides[side]
        probability = float(chance[side])
        price = float(getattr(row, "american_odds"))
        implied = american_to_implied(price)
        candidates.append(
            {
                "date": game_day,
                "commence_time": str(getattr(row, "commence_time", "")),
                "home_team": home,
                "away_team": away,
                "side": side,
                "team": home if side == "home" else away,
                "opponent": away if side == "home" else home,
                "win_probability": round(probability, 4),
                "fair_american": implied_to_american(
                    min(max(probability, 1e-4), 1 - 1e-4)
                ),
                "american_odds": price,
                "book": str(getattr(row, "book", "")),
                "implied_probability": round(implied, 4),
                "edge": round(probability - implied, 4),
                "best_bet": (home, away, side) in staked,
            }
        )

    guarded = apply_puck_drop_guard(candidates, now=moment)
    out.removed_by_guard = len(guarded.quarantined)
    out.rows = sorted(
        (dict(row) for row in guarded.playable),
        key=lambda r: (r["commence_time"], -r["win_probability"], r["team"]),
    )
    return out


def price_verdict(row: Mapping[str, Any]) -> str:
    """Whether the stats' side is also value at the best price staged."""
    edge = float(row.get("edge", 0.0))
    if row.get("best_bet"):
        return "best bet on the card"
    if edge > 0:
        return f"price is {edge * 100:.1f} pts long, under the bar"
    return f"price is {-edge * 100:.1f} pts short"


def render_section(sides: StatSides | None, start_text) -> list[str]:
    """The card's section. `start_text` formats a row's puck drop."""
    if sides is None:
        return []
    lines = [
        f"## {SECTION_TITLE}",
        "",
        "Who the model expects to win each game, from the same team ratings "
        "the card prices on. A side is a bet only when its chance beats the "
        "price, which is what the best bets above are; the last column says "
        "how this side's chance compares with its best price.",
        "",
    ]
    if sides.rows:
        lines += [
            "| Game | Puck drop | Stats' side | Win chance | Fair | Best price | Book | Against the price |",
            "|:--|:--|:--|--:|--:|--:|:--|:--|",
        ]
        for row in sides.rows:
            price = float(row["american_odds"])
            price_text = f"{int(price):+d}" if price.is_integer() else f"{price:+.1f}"
            lines.append(
                f"| {row['away_team']} @ {row['home_team']} | {start_text(row)} "
                f"| **{row['team']}** | {float(row['win_probability']) * 100:.1f}% "
                f"| {int(row['fair_american']):+d} | {price_text} | {row['book'] or '-'} "
                f"| {price_verdict(row)} |"
            )
        lines += [
            "",
            "A list, not bets: no units, no stakes, nothing frozen into the "
            "forward ledger. The lab has no measurement showing that backing "
            "the stats' side at the market's price makes money.",
            "",
        ]
    else:
        lines += ["_No game on tonight's slate has a moneyline opinion to show._", ""]
    if sides.removed_by_guard:
        lines += [
            f"- {sides.removed_by_guard} game(s) not listed: started, or the start "
            "could not be confirmed.",
        ]
    if sides.without_opinion:
        lines += [
            f"- {sides.without_opinion} game(s) not listed: the model holds no "
            "opinion on both sides (a team name that did not resolve).",
        ]
    if sides.removed_by_guard or sides.without_opinion:
        lines.append("")
    return lines
