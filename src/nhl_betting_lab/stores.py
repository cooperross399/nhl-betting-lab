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


def existing_row_count(path: Path | str) -> int:
    """Data rows in an existing CSV, cheaply: line count minus the header.

    Lives here because every shrink guard in the repository needs it and
    there must be one of it. "The file exists" is not "the file holds data" —
    a header-only file left by a permitted first empty build once made a
    guard raise falsely on the second.
    """
    target = Path(path)
    if not target.is_file():
        return 0
    try:
        with target.open("r", encoding="utf-8") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    except OSError:
        return 0


#: What makes a historical price row the same quote as another *within one
#: snapshot window*. Deliberately excludes the timestamps: `snapshot` is the
#: moment that was asked for and `fetched_at` the moment it was written, and
#: two labels of the same moment are one quote, not two.
#:
#: It is not the whole key. Across windows the window itself is part of the
#: identity — see `dedupe_prices` — because a quote at four hours and a quote
#: at nine and a half are two different prices on two different boards.
PRICE_IDENTITY = (
    "provider_event_id",
    "market",
    "player",
    "selection",
    "line",
    "book",
)

#: What `label_phases` needs to say which window a row belongs to. Without
#: both, two windows are indistinguishable and deduplication silently keeps
#: one of them.
PRICE_WINDOW_INPUTS = ("commence_time", "snapshot")


def dedupe_prices(frame: "pd.DataFrame") -> "pd.DataFrame":
    """One row per quote, whatever the timestamps say.

    The store deduplicated on the whole row and called itself idempotent. It
    was not: two purchases of the same window labelled the same quotes with
    two different snapshot strings, nothing collapsed, and the file came back
    holding every price exactly twice. The backtest then counted every bet
    twice — which leaves the ROI unchanged and shrinks its confidence
    interval by a factor of root two, so a duplicated store does not look
    wrong. It looks *significant*.

    **Every identity column is required.** This used to dedupe on whatever
    subset of `PRICE_IDENTITY` the caller happened to pass, which is a far
    worse failure than the one it was written to fix: a frame read without
    `provider_event_id` has nothing telling one date from another, so every
    night's quote on the same player-market-line-book collapses onto a
    single row. Asked to dedupe 2,675,428 rows that way it returned 64,253
    and reported success. Silent 40x data loss inside a function whose whole
    job is to be trusted is not a fallback, it is a trap. Read the store
    with all of `PRICE_IDENTITY` in `usecols`.

    **The window is part of the identity, and leaving it out cost 89.5% of a
    window.** `PRICE_IDENTITY` is right that two timestamp *labels* of one
    moment are one quote. It is wrong that two *moments* are. On 2026-08-31 a
    second purchase priced the same 2,710 events at 9.5 hours before face-off
    where the first had priced them at 4.0, appended it to the same store, and
    every 9.5-hour quote landed on the identity of the 4.0-hour quote it
    matched. `keep="last"` handed the collision to the new window: 1,126,739
    of the 1,259,312 four-hour rows were overwritten, leaving 132,573 — only
    the quotes whose line or book happened not to recur. Nothing raised,
    nothing shrank suspiciously, and the store still held 2.7 million rows.
    The canonical report went on naming a population that no longer existed
    on disk, and the 4.0-hour window was recoverable only because every
    response is cached raw.

    So the key is `PRICE_IDENTITY` **plus the window** `label_phases` derives.
    That is the granularity every measurement in this repository already
    slices on, which is what makes it the right one: two quotes it treats as
    one window are two quotes the backtest would collapse to one bet anyway,
    and two quotes it treats as different windows are exactly the pair that
    must never be merged. Over-collapsing inside a window costs the
    measurement nothing; under-collapsing across windows costs it a window.
    """
    if frame.empty:
        return frame
    missing = [c for c in PRICE_IDENTITY if c not in frame.columns]
    if missing:
        raise ValueError(
            "dedupe_prices needs every identity column and is missing "
            f"{missing}. Deduplicating on the remaining subset would "
            "collapse rows that are genuinely different quotes and report "
            f"success. Read the store with usecols covering "
            f"{list(PRICE_IDENTITY)}."
        )
    undated = [c for c in PRICE_WINDOW_INPUTS if c not in frame.columns]
    if undated:
        raise ValueError(
            f"dedupe_prices cannot tell one snapshot window from another "
            f"without {undated}, so a second window appended to this store "
            "would overwrite the first on the shared quote identity — which "
            "is how 1,126,739 of 1,259,312 four-hour rows were lost. Read "
            f"the store with usecols covering {list(PRICE_WINDOW_INPUTS)}."
        )
    work = frame.reset_index(drop=True)
    windowed = label_phases(work)
    keep = windowed.drop_duplicates(
        subset=[*PRICE_IDENTITY, "phase"], keep="last"
    ).index
    return work.loc[keep].reset_index(drop=True)


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
