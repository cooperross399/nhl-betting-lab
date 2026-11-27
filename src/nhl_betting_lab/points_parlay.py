"""Points parlay: one player from every game, points over 0.5.

Cooper, 2026-11-27: "Make me a point parlay with a player from every game on
the slate today", then "pick a player from each game based on how we think the
game will go and who may score", then "I want this done everyday for however
many games are on the slate".

For each game on tonight's slate the leg is the player whose points over 0.5
the model gives the highest chance. That chance is the card's own probability
map, which already carries the team ratings, tonight's opponent, home ice,
form, the posted lines and the scoring environment, so "how the game will go"
is in it. The leg's price is the best staged points over 0.5 price for him.
The section prints each leg, the model's projected winner for that game, the
combined price (the legs multiplied, at each one's best book) and the model's
combined chance (the legs multiplied, as if independent, which they are not
quite), and the stake from the tracked ladder.

It is a LIST, like the Due List: nothing here is a best bet, lean or pass, a
stake on the card, or in the selection fingerprint, the frozen snapshot, the
forward ledger or its report. A game with no points price posted, or none the
model has an opinion on, has no leg and is named; the parlay then covers fewer
games, and says so. A game that has started, or whose start cannot be
confirmed, is left out (the puck-drop guard). No measurement shows this makes
money: a long parlay of short prices pays the book's margin on every leg.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

from nhl_betting_lab.drought_forward import tracked_stake
from nhl_betting_lab.models.value import OddsError, american_to_decimal, american_to_implied
from nhl_betting_lab.puck_drop import apply_puck_drop_guard
from nhl_betting_lab.reports.card_pricing import _line, selection_key

SECTION_TITLE = "Points parlay"
MARKET = "points"
SELECTION = "over"
LINE = 0.5


@dataclass
class PointsParlay:
    legs: list[dict[str, Any]] = field(default_factory=list)
    #: Games tonight with no leg: no points price posted, or no opinion.
    missing_games: list[str] = field(default_factory=list)
    removed_by_guard: int = 0


def _game_label(home: str, away: str) -> str:
    return f"{away} @ {home}"


def build_points_parlay(
    prices: pd.DataFrame,
    probabilities: Mapping[tuple, float],
    *,
    now: datetime | None = None,
    day: str | None = None,
    stat_sides: Sequence[Mapping[str, Any]] = (),
) -> PointsParlay:
    """One leg per game on `day`: the highest model points-over-0.5 chance."""
    moment = now or datetime.now(timezone.utc)
    out = PointsParlay()
    if prices.empty or "market" not in prices.columns:
        return out
    frame = prices[prices["market"].astype(str).str.strip() == MARKET]
    games: dict[tuple, str] = {}
    for row in prices.itertuples():
        key = selection_key(row, market="", selection="", line=None)
        _m, _p, home, away, _s, _l, game_day = key
        if day is not None and str(game_day) != str(day):
            continue
        games.setdefault((home, away, game_day), str(getattr(row, "commence_time", "")))

    best: dict[tuple, Any] = {}
    for row in frame.itertuples():
        if str(getattr(row, "selection", "")).strip().lower() != SELECTION:
            continue
        if _line(getattr(row, "line", None)) != LINE:
            continue
        try:
            price = float(getattr(row, "american_odds"))
            american_to_implied(price)
        except (OddsError, TypeError, ValueError):
            continue
        key = selection_key(row, market=MARKET, selection=SELECTION, line=LINE)
        if day is not None and str(key[6]) != str(day):
            continue
        current = best.get(key)
        if current is None or price > float(getattr(current, "american_odds")):
            best[key] = row

    winners = {
        (str(s.get("home_team")), str(s.get("away_team"))): s for s in stat_sides
    }
    chosen: dict[tuple, dict[str, Any]] = {}
    for key, row in best.items():
        chance = probabilities.get(key)
        if chance is None:
            continue
        _m, _p, home, away, _s, _l, game_day = key
        game = (home, away, game_day)
        price = float(getattr(row, "american_odds"))
        leg = {
            "date": game_day,
            "commence_time": str(getattr(row, "commence_time", "")),
            "home_team": home,
            "away_team": away,
            "player": str(getattr(row, "player", "")).strip(),
            "american_odds": price,
            "book": str(getattr(row, "book", "")),
            "model_probability": round(float(chance), 4),
        }
        side = winners.get((home, away))
        if side is not None:
            leg["projected_winner"] = side.get("team")
            leg["projected_win"] = side.get("win_probability")
        current = chosen.get(game)
        if current is None or (leg["model_probability"], price) > (
            current["model_probability"], current["american_odds"]
        ):
            chosen[game] = leg

    for game in games:
        if game not in chosen:
            out.missing_games.append(_game_label(game[0], game[1]))

    guarded = apply_puck_drop_guard(list(chosen.values()), now=moment)
    out.removed_by_guard = len(guarded.quarantined)
    out.legs = sorted(
        (dict(leg) for leg in guarded.playable),
        key=lambda r: (r["commence_time"], r["away_team"]),
    )
    return out


def combined(legs: Sequence[Mapping[str, Any]]) -> tuple[float, float, float] | None:
    """(American price, model chance, tracked stake) of the whole parlay."""
    if not legs:
        return None
    decimal = 1.0
    chance = 1.0
    for leg in legs:
        decimal *= american_to_decimal(float(leg["american_odds"]))
        chance *= float(leg["model_probability"])
    american = (decimal - 1) * 100 if decimal >= 2 else -100 / (decimal - 1)
    return american, chance, tracked_stake(price=american)


def _price_text(price: float) -> str:
    return f"{int(round(price)):+,d}"


def render_section(
    parlay: PointsParlay | None, start_text: Callable[[Mapping[str, Any]], str]
) -> list[str]:
    if parlay is None:
        return []
    lines = [
        f"## {SECTION_TITLE}",
        "",
        "One player from every game, points over 0.5 (a goal or an assist): in "
        "each game the player the model gives the best chance of a point, from "
        "the same ratings, opponent, lines and form the card prices on. Price is "
        "his best staged price; books differ by leg.",
        "",
    ]
    if not parlay.legs:
        lines += ["No game tonight has a points price the model has an opinion on.", ""]
    else:
        lines += [
            "| Game | Puck drop | Model's winner | Player | Model | Price | Book |",
            "|:--|:--|:--|:--|--:|--:|:--|",
        ]
        for leg in parlay.legs:
            winner = leg.get("projected_winner")
            win = leg.get("projected_win")
            winner_text = f"{winner} {float(win) * 100:.0f}%" if winner and win is not None else "-"
            lines.append(
                f"| {_game_label(leg['home_team'], leg['away_team'])} | {start_text(leg)} "
                f"| {winner_text} | **{leg['player']}** "
                f"| {float(leg['model_probability']) * 100:.1f}% "
                f"| {_price_text(float(leg['american_odds']))} | {leg['book'] or '-'} |"
            )
        total = combined(parlay.legs)
        assert total is not None
        price, chance, stake = total
        lines += [
            "",
            f"**{len(parlay.legs)} legs. Combined {_price_text(price)}; model chance "
            f"{chance * 100:.2f}% (about 1 in {max(1, round(1 / chance)):,}). "
            f"Tracked at {stake:g}u.** The chance multiplies the legs as if "
            "independent; books often cap a parlay's payout below the full price.",
            "",
        ]
    if parlay.missing_games:
        lines.append(
            "No leg (no points price posted, or no opinion): "
            + ", ".join(parlay.missing_games) + "."
        )
    if parlay.removed_by_guard:
        lines.append(
            f"{parlay.removed_by_guard} game(s) left out: started, or start not confirmed."
        )
    lines += [
        "",
        "A list, not a bet on the card: no units on the card, nothing frozen into "
        "the forward ledger. No measurement shows a long parlay of short prices "
        "makes money.",
        "",
    ]
    return lines
