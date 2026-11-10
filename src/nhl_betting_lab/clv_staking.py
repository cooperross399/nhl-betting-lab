"""Stake more where the card beats the close, less where it does not.

Cooper, 2026-11-10 ("ALL"), NOT a defect fix: a staking change he made
before the 2027-04-25 decision date. The CLV report showed the bets
(population B, the measurement bar) beating the close in `shots_on_goal`,
`goals` and `assists`, with every other market's interval spanning zero.
This turns that table into a stake multiplier per market, refreshed every
run:

* Gameday Refresh's "Report closing-line value" step, the one step that may
  read the private capture store, writes `clv_by_market.json`
  (`market_table`): per market, the bets' count, games, mean CLV and its
  95% game-clustered interval. Aggregate only, never a price, line or book.
  It goes to `data/processed` (carried to the next run in gameday-state) and
  `data/outputs` (the reports artifact).
* The next card reads it (`load_table`) and `stake_multiplier` sizes each
  best bet's tier stake by its market's row.

**The rule, fixed before it was applied.** A market needs at least
`MIN_WAGERS` matched bets over at least `MIN_GAMES` games to move at all;
under that it is unmeasured and keeps its tier stake (this is the
minimum-sample rule: nothing moves on a handful of games). Then, on the
plain 95% game-clustered interval of mean CLV (the interval Cooper read on
the report, not corrected across markets):

* wholly above zero: **beats the close**, stake x`BEAT_MULTIPLIER`;
* spanning zero: **no demonstrated CLV**, stake x`SPAN_MULTIPLIER`;
* wholly below zero: **loses to the close**, stake x`LOSE_MULTIPLIER`.

A table older than `FRESH_DAYS`, or none at all, moves nothing, and the card
says so. The multiplier moves stakes only: the snapshot is frozen before the
card is built, so the forward ledger and the registered test are unchanged.
`points` stays unstaked whatever its CLV (`STAKE_EXCLUDED_MARKETS`).
CLV is a measure of price, not of profit: beating the close here is not a
demonstrated edge, and every return the lab measures still says so.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

TABLE_FILENAME = "clv_by_market.json"

MIN_WAGERS = 200
MIN_GAMES = 30
BEAT_MULTIPLIER = 1.5
SPAN_MULTIPLIER = 0.5
LOSE_MULTIPLIER = 0.25
FRESH_DAYS = 4

BEATS = "beats the close"
SPANS = "no demonstrated CLV"
LOSES = "loses to the close"
THIN = "too few to judge"

#: (market, side) whose CLV bump is held at x1. A cut below x1 still applies.
#: Cooper's decision of 2026-11-10 (via the coordinator): since 2026-10-28
#: the forward ledger's population B `shots_on_goal` overs hit 14.8% where
#: the model said 26.7% (310 wagers, -93.1u at 1u, best frozen price), so a
#: market-level CLV verdict must not size the overs up until the over model
#: is fixed.
BUMP_HELD_SIDES: dict[tuple[str, str], str] = {
    ("shots_on_goal", "over"): (
        "`shots_on_goal` overs keep x1 until the over model is fixed: since "
        "2026-10-28 they hit 14.8% against a model 26.7% (310 wagers, -93.1u)"
    ),
}


def market_table(report: Mapping[str, Any], *, generated: str) -> dict[str, Any]:
    """The per-market CLV of the bets (population B), from `build_clv_report`."""
    markets: dict[str, Any] = {}
    for market, views in sorted((report.get("markets") or {}).items()):
        bets = (views or {}).get("bets") or {}
        if not bets.get("bets"):
            continue
        markets[str(market)] = {
            "wagers": int(bets.get("bets", 0)),
            "games": int(bets.get("games", 0)),
            "mean_clv": _finite(bets.get("mean_clv_pct")),
            "low": _finite(bets.get("clv_low")),
            "high": _finite(bets.get("clv_high")),
            "beat_rate": _finite(bets.get("beat_rate")),
        }
    for row in markets.values():
        row["verdict"], row["multiplier"] = classify(row)
    return {
        "generated_at": generated,
        "population": "bets: opinions clearing the measurement bar, one per wager at the best price",
        "interval": "95%, clustered by game, not corrected across markets",
        "rule": {
            "min_wagers": MIN_WAGERS,
            "min_games": MIN_GAMES,
            "beat": BEAT_MULTIPLIER,
            "span": SPAN_MULTIPLIER,
            "lose": LOSE_MULTIPLIER,
        },
        "markets": markets,
    }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def classify(row: Mapping[str, Any]) -> tuple[str, float]:
    """(verdict, multiplier) for one market's row."""
    if int(row.get("wagers") or 0) < MIN_WAGERS or int(row.get("games") or 0) < MIN_GAMES:
        return THIN, 1.0
    low, high = row.get("low"), row.get("high")
    if low is None or high is None:
        return THIN, 1.0
    if low > 0:
        return BEATS, BEAT_MULTIPLIER
    if high < 0:
        return LOSES, LOSE_MULTIPLIER
    return SPANS, SPAN_MULTIPLIER


def save_table(table: Mapping[str, Any], *directories: Path) -> list[Path]:
    written = []
    for directory in directories:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / TABLE_FILENAME
        path.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def load_table(
    processed_dir: Path, *, now: datetime | None = None
) -> tuple[dict[str, Any] | None, str]:
    """(table, note): the table when it exists, reads and is fresh, else None
    with the reason, which the card prints."""
    path = Path(processed_dir) / TABLE_FILENAME
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "No closing-line table has been written yet, so every stake is its tier's."
    except (OSError, ValueError) as exc:
        return None, f"The closing-line table could not be read ({type(exc).__name__}), so every stake is its tier's."
    if not isinstance(table, dict) or not isinstance(table.get("markets"), dict):
        return None, "The closing-line table holds no markets, so every stake is its tier's."
    try:
        stamp = datetime.fromisoformat(str(table.get("generated_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return None, "The closing-line table carries no date, so every stake is its tier's."
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    moment = now or datetime.now(timezone.utc)
    age = (moment - stamp).total_seconds() / 86400
    if age > FRESH_DAYS:
        return None, (
            f"The closing-line table is {age:.1f} days old (over {FRESH_DAYS}), so every "
            "stake is its tier's."
        )
    return table, ""


def stake_multiplier(
    market: str, table: Mapping[str, Any] | None, selection: str = ""
) -> tuple[float, str]:
    """(multiplier, reason) for a best bet in `market`. 1.0 and "" when the
    table says nothing about it. A side in `BUMP_HELD_SIDES` never goes
    above x1, and its reason says so."""
    if not table:
        return 1.0, ""
    row = (table.get("markets") or {}).get(market)
    if not row:
        return 1.0, ""
    verdict, multiplier = classify(row)
    if multiplier == 1.0:
        return 1.0, ""
    held = BUMP_HELD_SIDES.get((market, str(selection or "").lower()))
    if held and multiplier > 1.0:
        return 1.0, f"CLV: `{market}` {verdict} (x{multiplier:g}) held at x1; {held}"
    return multiplier, (
        f"CLV: `{market}` {verdict} ({_pct(row.get('mean_clv'))} over "
        f"{int(row.get('wagers') or 0):,} bets, [{_pct(row.get('low'))}, "
        f"{_pct(row.get('high'))}]), stake x{multiplier:g}"
    )


def _pct(value: Any) -> str:
    number = _finite(value)
    return "n/a" if number is None else f"{number:+.2%}"


def note_lines(table: Mapping[str, Any] | None, note: str) -> list[str]:
    """The card's standing note on how CLV sized tonight's stakes."""
    if not table:
        return [note] if note else []
    parts = []
    for market, row in sorted((table.get("markets") or {}).items()):
        verdict, multiplier = classify(row)
        parts.append(
            f"`{market}` x{multiplier:g} ({verdict}, {_pct(row.get('mean_clv'))} over "
            f"{int(row.get('wagers') or 0):,})"
        )
    return [
        "Stakes are sized by each market's closing-line value (Cooper, 2026-11-10): "
        f"x{BEAT_MULTIPLIER:g} where the bets' 95% game-clustered CLV interval sits "
        f"above zero, x{SPAN_MULTIPLIER:g} where it spans zero, x{LOSE_MULTIPLIER:g} "
        f"below it, unchanged under {MIN_WAGERS} bets or {MIN_GAMES} games. "
        f"Table of {str(table.get('generated_at', ''))[:16]}: " + "; ".join(parts) + ". "
        "Beating the close is not a demonstrated edge."
    ]
