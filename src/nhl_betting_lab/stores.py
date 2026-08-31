"""Reading the append-only stores, where an empty file and a broken one differ.

A run once bought 157,870 credits of historical prices, held 1.26 million
rows in memory, and then died on the last line — `pd.read_csv` on a
zero-byte file that a restored artifact had left behind. The prices were
recoverable only because every response is cached raw. That is not a margin
to rely on twice.

The distinction this module exists to make:

* **Missing, or present but empty.** There is nothing to lose. Read it as an
  empty frame and carry on; the caller writes what it has.
* **Present, non-empty, and unparseable.** Something *is* in there and the
  parser cannot see it. A reader may treat that as absent and say so. A
  writer must not: concatenating "nothing" onto new rows and saving would
  replace a truncated file with a shorter one, turning a recoverable problem
  into a permanent one.

So `for_append=True` refuses the second case rather than guessing.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd


class CorruptStoreError(RuntimeError):
    """A store holds something, and it cannot be read. Never overwrite it."""


def read_store(
    path: Path | str,
    *,
    columns: Sequence[str] = (),
    for_append: bool = False,
) -> pd.DataFrame:
    """The store's rows, or an empty frame — never a silent truncation."""
    target = Path(path)
    empty = pd.DataFrame(columns=list(columns))
    if not target.is_file():
        return empty
    try:
        if target.stat().st_size == 0:
            return empty
    except OSError:
        return empty
    try:
        return pd.read_csv(target)
    except pd.errors.EmptyDataError:
        # A header-less, contentless file. Nothing is lost by replacing it.
        return empty
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        if for_append:
            raise CorruptStoreError(
                f"{target} holds data that cannot be parsed ({exc}). Refusing "
                "to append, because writing now would replace a damaged file "
                "with a shorter one. Restore it from the raw cache or the "
                "branch that carries it, then re-run."
            ) from exc
        return empty


#: What makes a historical price row the same quote as another. Deliberately
#: excludes the timestamps: `snapshot` is the moment that was *asked* for and
#: `fetched_at` the moment it was written, and neither changes which price a
#: book was showing for which selection.
PRICE_IDENTITY = (
    "provider_event_id",
    "market",
    "player",
    "selection",
    "line",
    "book",
)


def dedupe_prices(frame: "pd.DataFrame") -> "pd.DataFrame":
    """One row per quote, whatever the timestamps say.

    The store deduplicated on the whole row and called itself idempotent. It
    was not: two purchases of the same window labelled the same quotes with
    two different snapshot strings, nothing collapsed, and the file came back
    holding every price exactly twice. The backtest then counted every bet
    twice — which leaves the ROI unchanged and shrinks its confidence
    interval by a factor of root two, so a duplicated store does not look
    wrong. It looks *significant*.
    """
    if frame.empty:
        return frame
    keys = [column for column in PRICE_IDENTITY if column in frame.columns]
    if not keys:
        return frame.drop_duplicates()
    return frame.drop_duplicates(subset=keys, keep="last").reset_index(drop=True)


def best_price_per_wager(frame, key):
    """One bet per wager, at the best price any book quoted on it.

    `dedupe_prices` removes duplicate QUOTES. This removes duplicate BETS,
    which is a different and less obvious problem: eight books quoting one
    selection are eight quotes on one wager, and counting each as its own
    bet measures a strategy no card runs — every book at its average price —
    while narrowing every interval by about the square root of the number of
    books, because those eight rows share a single outcome.

    That defect published "-1.6% over 73,918 bets, interval excluding zero"
    as a demonstrated loss where the card's own policy over the same data
    gives -0.3% over 25,949 wagers, spanning zero.

    `key` is the wager as a person would place it. American odds are ranked
    by payout rather than by magnitude, because +150 pays more than -110,
    which pays more than -200.
    """
    import pandas as pd

    columns = [column for column in key if column in frame.columns]
    if len(columns) != len(key) or "american_odds" not in frame.columns:
        return frame
    odds = pd.to_numeric(frame["american_odds"], errors="coerce")
    payout = odds.where(odds < 0, odds / 100.0)
    payout = payout.where(odds > 0, -100.0 / odds)
    ordered = frame.assign(_payout=payout).sort_values(
        "_payout", ascending=False, kind="mergesort"
    )
    return (
        ordered.groupby(columns, as_index=False, dropna=False)
        .first()
        .drop(columns=["_payout"])
    )


#: How far before puck drop a snapshot was taken decides what it can measure.
#: A card-time price and a near-kickoff price are different questions, and
#: mixing them is not a smaller error than mixing two books — it is worse,
#: because the best of two moments is a price nobody could have taken.
PHASE_BOUNDS = {"late": 6.0, "card": 12.0}


def label_phases(frame):
    """Add `hours_before` and `phase` from the snapshot and the face-off.

    Derived rather than stored, so it is correct for prices already bought.
    Everything at or inside six hours is `late`; out to twelve is `card`;
    anything earlier is `early`. A row missing either timestamp gets
    `unknown` and is never silently folded in with the rest.

    The sibling football lab learned this the expensive way: without a phase
    label the best-price collapse takes the better of a card-time quote and a
    closing quote for one wager, which inflates every measured edge by an
    amount nobody can see.
    """
    import pandas as pd

    out = frame.copy()
    if "commence_time" not in out.columns or "snapshot" not in out.columns:
        out["hours_before"] = float("nan")
        out["phase"] = "unknown"
        return out
    commence = pd.to_datetime(out["commence_time"], errors="coerce", utc=True)
    snapshot = pd.to_datetime(out["snapshot"], errors="coerce", utc=True)
    hours = (commence - snapshot).dt.total_seconds() / 3600.0
    out["hours_before"] = hours
    out["phase"] = "early"
    out.loc[hours <= PHASE_BOUNDS["card"], "phase"] = "card"
    out.loc[hours <= PHASE_BOUNDS["late"], "phase"] = "late"
    out.loc[hours.isna(), "phase"] = "unknown"
    return out
