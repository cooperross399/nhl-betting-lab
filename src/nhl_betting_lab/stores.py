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
