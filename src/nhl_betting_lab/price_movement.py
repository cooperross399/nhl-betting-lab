"""How far the books have moved since the day's first card, read into the model.

Cooper, 2026-10-21, asked for line movement since open to be factored in. The
open is the day's first priced snapshot (`forward_evidence.write_snapshot`),
which holds every book's price on every selection the morning card had an
opinion on; the current price is this run's staged quote from the same book.
So the first card of a day sees no movement, and a later run (the 20:30 UTC
re-price) sees what moved since the morning.

For each selection, the move is the median, over the books quoting it both
then and now, of the change in implied probability; a price that shortened
moved toward that side. The model's probability moves `WEIGHT` of the way
with it, never more than `MAX_SHIFT` either way: the market's move carries
information the model lacks (a scratch, a goalie, sharp money), and the
model is not replaced by it. Nothing here is measured against prices, and
the constants are this lab's choice.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from statistics import median

import pandas as pd

from nhl_betting_lab.forward_evidence import read_snapshot, snapshots_dir
from nhl_betting_lab.models.value import OddsError, american_to_implied
from nhl_betting_lab.season import clean_text

WEIGHT = 0.5
MAX_SHIFT = 0.05

KeyFor = Callable[..., tuple]


def _implied_by_book(frame: pd.DataFrame | None, key_for: KeyFor) -> dict[tuple, dict[str, float]]:
    out: dict[tuple, dict[str, float]] = {}
    if frame is None or frame.empty:
        return out
    for row in frame.itertuples():
        market = clean_text(getattr(row, "market", ""))
        selection = clean_text(getattr(row, "selection", "")).lower()
        try:
            value = getattr(row, "line", None)
            line = None if value is None or pd.isna(value) else float(value)
            implied = american_to_implied(getattr(row, "american_odds"))
        except (OddsError, TypeError, ValueError):
            continue
        book = clean_text(getattr(row, "book", ""))
        if not book:
            continue
        key = key_for(row, market=market, selection=selection, line=line)
        out.setdefault(key, {})[book] = implied
    return out


def movement(
    opened: pd.DataFrame | None, current: pd.DataFrame, key_for: KeyFor
) -> dict[tuple, float]:
    """Selection -> median change in implied probability since the open."""
    before = _implied_by_book(opened, key_for)
    now = _implied_by_book(current, key_for)
    moves: dict[tuple, float] = {}
    for key, books in now.items():
        then = before.get(key)
        if not then:
            continue
        changes = [books[b] - then[b] for b in books if b in then]
        if changes:
            moves[key] = float(median(changes))
    return moves


def apply_movement(
    probabilities: Mapping[tuple, float], moves: Mapping[tuple, float]
) -> tuple[dict[tuple, float], int]:
    """The probabilities moved with the market, and how many moved."""
    out = dict(probabilities)
    moved = 0
    for key, change in moves.items():
        if key not in out or not change:
            continue
        shift = max(-MAX_SHIFT, min(MAX_SHIFT, WEIGHT * change))
        out[key] = min(0.999, max(0.001, out[key] + shift))
        moved += 1
    return out, moved


def opening_snapshot(archive_dir: Path | None, day: str) -> pd.DataFrame | None:
    """The day's first priced snapshot, or None when there is none yet."""
    path = snapshots_dir(archive_dir) / f"{day}.csv"
    if not path.is_file():
        return None
    frame, _ = read_snapshot(path)
    return frame
