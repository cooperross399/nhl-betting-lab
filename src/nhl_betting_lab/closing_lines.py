"""Closing-line value: did the card's price beat the market's last word?

This is the fastest honest signal this lab has, and until now it had none.

The problem it solves: the price backtest needs thousands of settled bets
before its interval stops including zero, and a season is 185 game days. CLV
answers a narrower question on a fraction of the sample — *were we taking
prices the market later disagreed with, in our favour?* A model that
consistently beats the closing line is finding something. One that does not,
but is winning, is being paid by variance, and this file exists to say so
before a hot month is mistaken for an edge.

What is measured, in increasing order of how much it assumes:

* **Beat the close** — did we take a longer price than the market closed at?
  Assumes nothing beyond both prices being real.
* **CLV%** — `decimal_taken / decimal_close - 1`. The price basis, vig
  included on both sides, so it is directly comparable across bets.
* **EV at close** — the money question. De-vigs the closing pair
  proportionally and asks what the bet is worth *if the closing line is
  right*. Only computed where the opposite side also closed; where it did
  not, the row carries no EV rather than a guessed one.

The closing price is the last price captured **strictly before** the game's
listed start. Never one captured after: a price observed at 19:05 for a 19:00
puck drop is not a closing line, it is a live one, and comparing an opinion
frozen at 09:30 against it would flatter or damn the model with information it
could not have had.

Nor one captured hours earlier. The close must also be within
`CLOSE_MAX_LEAD` of the start: a 14:00Z price for a 23:00Z game is an
intraday price, not the market's last word. A selection whose only
pre-start price is older than that has no close near face-off, and is
counted as such rather than scored or dropped.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from nhl_betting_lab.stores import CorruptStoreError, existing_row_count, read_store

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.models.value import (
    OddsError,
    american_to_decimal,
    devig_two_way,
)
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.season import row_game_date


CAPTURES_FILENAME = "closing_line_captures.csv"

CAPTURE_COLUMNS = (
    "captured_at",
    "commence_time",
    "home_team",
    "away_team",
    "market",
    "player",
    "selection",
    "line",
    "american_odds",
    "book",
)


def captures_path(processed_dir: Path | None = None) -> Path:
    return (Path(processed_dir) if processed_dir else PROCESSED_DIR) / (
        CAPTURES_FILENAME
    )


def moment(value: object) -> datetime | None:
    """An aware instant, or None if the stamp cannot be trusted.

    These were compared as raw strings, which is wrong twice over. The
    provider stamps `commence_time` as `...Z` while this lab writes
    `captured_at` with `+00:00`, and `"2026-10-08T23:00:00+00:00" <
    "2026-10-08T23:00:00Z"` is true for the string and false for the instant
    — so a capture taken at puck drop could pass a guard that exists to
    exclude exactly that. A stamp that will not parse is refused rather than
    ordered by luck.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _decimal(value: object) -> float | None:
    try:
        return american_to_decimal(value)
    except (OddsError, TypeError, ValueError):
        return None


def best_prices(prices: pd.DataFrame, *, captured_at: str) -> pd.DataFrame:
    """One row per selection, at the best price any book was showing.

    The card quotes the best reachable price, so the closing comparison has to
    use the same basis. Comparing our best-of-twenty against one book's close
    would measure the book, not the model.
    """
    if prices.empty:
        return pd.DataFrame(columns=list(CAPTURE_COLUMNS))
    best: dict[tuple, dict[str, object]] = {}
    for row in prices.itertuples():
        decimal = _decimal(getattr(row, "american_odds", None))
        if decimal is None:
            continue
        line = getattr(row, "line", None)
        try:
            line_value = None if line is None or pd.isna(line) else float(line)
        except (TypeError, ValueError):
            line_value = None
        key = selection_key(
            row,
            market=str(getattr(row, "market", "")).strip(),
            selection=str(getattr(row, "selection", "")).strip().lower(),
            line=line_value,
        )
        current = best.get(key)
        if current is not None and float(current["_decimal"]) >= decimal:
            continue
        best[key] = {
            "captured_at": captured_at,
            "commence_time": str(getattr(row, "commence_time", "")),
            "home_team": str(getattr(row, "home_team", "")),
            "away_team": str(getattr(row, "away_team", "")),
            "market": str(getattr(row, "market", "")).strip(),
            "player": (
                ""
                if getattr(row, "player", None) is None
                or pd.isna(getattr(row, "player", None))
                else str(getattr(row, "player"))
            ),
            "selection": str(getattr(row, "selection", "")).strip().lower(),
            "line": line_value,
            "american_odds": float(getattr(row, "american_odds")),
            "book": str(getattr(row, "book", "")),
            "_decimal": decimal,
        }
    frame = pd.DataFrame(list(best.values()))
    if frame.empty:
        return pd.DataFrame(columns=list(CAPTURE_COLUMNS))
    return frame[list(CAPTURE_COLUMNS)]


def append_captures(
    frame: pd.DataFrame, *, processed_dir: Path | None = None
) -> int:
    """Append a capture to the store. Append-only, like the ledger."""
    if frame.empty:
        return 0
    path = captures_path(processed_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    combined = frame
    existing_rows = 0
    if path.is_file():
        existing = read_store(path, columns=CAPTURE_COLUMNS, for_append=True)
        # THE FLOOR COMES FROM THE FILE, NOT FROM THE READ IT GUARDS. It was
        # `len(existing)`, and `existing` plus new rows can never be shorter
        # than `existing`, so this guard could not fire for any input. A file
        # with two stray quotes parses 6 of its 10 rows without an error, and
        # the append then rewrote it at 7. The line count is the floor every
        # other shrink guard here uses.
        existing_rows = max(len(existing), existing_row_count(path))
        combined = pd.concat([existing, frame], ignore_index=True)
    if len(combined) < existing_rows:
        raise ValueError(
            f"Refusing to write {len(combined)} capture rows over "
            f"{existing_rows}. The store is append-only."
        )
    combined.to_csv(path, index=False, lineterminator="\n")
    return len(frame)


#: Where the line-movement capture writes. It runs five times a day in
#: season and records every field a closing price needs — for the markets it
#: asks for, which are the per-event markets and their alternate ladders only.
#: It never asks for the bulk moneyline, puck line or total, so those have no
#: closing price here (see `uncaptured_markets`).
MOVEMENT_DIRNAME = "line_movement"


def load_movement_captures(processed_dir: Path | None = None) -> pd.DataFrame:
    """Closing-line captures, taken from the line-movement store.

    For the per-event markets and their alternate ladders, the dedicated
    closing-line capture and this one ask the provider the same question. NOT
    for the bulk team markets: the dedicated capture also bought `h2h`,
    `spreads` and `totals`, and the movement capture never asks for them, so
    no moneyline — and no featured puck line or total unless an alternate
    ladder happens to repeat it — ever reaches this store. The report names
    those opinions rather than blaming the books for them. The movement
    capture already runs five times a day through the
    evening — including a snapshot at face-off for a 19:00 ET start — and
    writes `captured_at` beside every price, which is the only column the
    closing rule needs. Scheduling a second job to fetch the same board again
    would cost about 24,600 credits a season to collect what is already on
    disk, and would add a scheduled surface that would need firing and fixing
    like every other one in this repository.

    So CLV reads the movement store when the dedicated one is empty. The
    closing rule is unchanged: the last price captured strictly before the
    face-off, chosen by `closing_prices`.

    ## One best-price row per selection per round, as the dedicated store

    The movement file keeps EVERY book's row for every round, and this used
    to hand them over as they were. `closing_prices` then kept the first row
    at the latest moment, which is one book chosen by file order, and it
    scored it against an opinion taken at the best of N. The finder's round
    listed BetMGM +105 first, then DraftKings +140 and FanDuel +135. Against
    an opinion taken at +130 the fallback reported a close of BetMGM +105,
    beat_close True, CLV +12.2%. The dedicated store's basis gives
    DraftKings +140, beat_close False, CLV -4.2%. The error could only
    flatter: a refuter replayed 291 real games on a market that did not
    move, and this path printed mean CLV +0.74% [+0.72%, +0.76%], "excludes
    zero on the positive side".

    Each round now goes through `best_prices` under its own `captured_at`,
    which is exactly what `scripts/capture_line_movement.py` writes to the
    dedicated store from the same fetch. The two stores therefore hold the
    same rows, and a report does not depend on which one it read.
    """
    empty = pd.DataFrame(columns=list(CAPTURE_COLUMNS))
    root = (
        Path(processed_dir) if processed_dir else PROCESSED_DIR
    ) / MOVEMENT_DIRNAME
    if not root.is_dir():
        return empty
    frames = []
    for path in sorted(root.glob("*.csv")):
        try:
            frame = pd.read_csv(path)
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
            continue
        missing = [c for c in CAPTURE_COLUMNS if c not in frame.columns]
        if missing:
            # A day's file that predates a schema change is skipped rather
            # than half-read: a capture missing `captured_at` cannot be
            # ordered against face-off and would silently become "closing".
            continue
        frames.append(frame)
    if not frames:
        return empty
    rows = pd.concat(frames, ignore_index=True)
    rounds = [
        best_prices(round_rows, captured_at=str(stamp))
        for stamp, round_rows in rows.groupby("captured_at", sort=False)
    ]
    rounds = [frame for frame in rounds if not frame.empty]
    if not rounds:
        return empty
    return pd.concat(rounds, ignore_index=True)


class UnreadableCaptureStore(CorruptStoreError):
    """The dedicated capture store holds rows that cannot all be read."""

    def __init__(
        self, path: Path, *, rows_on_disk: int, rows_read: int | None
    ) -> None:
        self.path = Path(path)
        self.rows_on_disk = int(rows_on_disk)
        #: None when the file does not parse at all.
        self.rows_read = rows_read
        how = (
            "does not parse"
            if rows_read is None
            else f"parses to only {rows_read} of them"
        )
        super().__init__(
            f"{self.path} holds {self.rows_on_disk} row(s) and {how}. "
            "Closing-line value was not measured from it, and not from the "
            "movement store in its place. Restore it from the branch that "
            "carries it, then re-run."
        )


def load_captures(processed_dir: Path | None = None) -> pd.DataFrame:
    """The dedicated capture store, falling back to the movement store.

    Both hold the same kind of row. The dedicated one wins when it has
    anything, so an explicit closing-line run is never ignored.

    ## A damaged store raises; only an empty one falls through

    This read the store with the forgiving reader, which returns an empty
    frame for a file that will not parse. A damaged store therefore fell
    through to the movement store. Gameday Refresh never has a movement
    store, so the result was 0 captures, and the report said "Nothing to
    measure yet ... the correct state and not a fault" while the closing
    prices sat on disk. One refuter's store held a capture matching its one
    opinion, plus an unterminated quote at the end. It reported "matched
    0; no closing price found: 1", where the undamaged store matched 1 of 1.
    Stray quotes were just as silent: they parse short without an error, so
    a 10-row store read as 6.

    `stores.py` lets a reader "treat that as absent and say so". This one
    now says so by raising `UnreadableCaptureStore`, whether the store does
    not parse at all or parses to fewer rows than its lines. A missing,
    zero-byte or header-only store still reads as empty: there is nothing
    in it to lose. The movement store is never used in place of a damaged
    dedicated one, because that would swap the data source without saying.
    """
    path = captures_path(processed_dir)
    if path.is_file():
        rows_on_disk = existing_row_count(path)
        try:
            # for_append=True is the strict reader: it refuses a file that
            # holds something unparseable instead of returning "nothing".
            dedicated = read_store(path, columns=CAPTURE_COLUMNS, for_append=True)
        except CorruptStoreError as exc:
            raise UnreadableCaptureStore(
                path, rows_on_disk=rows_on_disk, rows_read=None
            ) from exc
        if len(dedicated) < rows_on_disk:
            # The floor comes from the file, not from the read it guards.
            raise UnreadableCaptureStore(
                path, rows_on_disk=rows_on_disk, rows_read=len(dedicated)
            )
        if not dedicated.empty:
            return dedicated
    return load_movement_captures(processed_dir)


def _key_of(row) -> tuple:
    line = getattr(row, "line", None)
    try:
        line_value = None if line is None or pd.isna(line) else float(line)
    except (TypeError, ValueError):
        line_value = None
    return selection_key(
        row,
        market=str(getattr(row, "market", "")).strip(),
        selection=str(getattr(row, "selection", "")).strip().lower(),
        line=line_value,
    )


#: How far before face-off a capture may be and still count as the close.
#:
#: The close was the last capture strictly before puck drop however early it
#: was, so on a night the last round before face-off missed, a 14:00Z price
#: for a 23:00Z game was scored as that game's close. Scoring a price three
#: or four hours old as the close is the defect itself, so the bound stays
#: tight even where the schedule cannot meet it.
#:
#: What `.github/workflows/line-movement.yml` can meet: its in-season rounds
#: run at 14:00, 18:00, 21:00, 23:00 and 01:00 UTC, stamped with the wall
#: clock when they run (never early, often a few minutes late). A 19:00 EDT
#: start is 23:00 UTC, and the 23:00 round lands at or after face-off, so it
#: is never a close under the strictly-before rule; the 21:00 round, two
#: hours out, is the best that game can get. 60-90 minutes would therefore
#: put every 19:00 EDT game in the bucket on a night nothing went wrong.
#: The evening rounds are two hours apart, so every common evening start
#: (19:00, 19:30 and 22:00 ET, EDT and EST) has a round at most two hours
#: before it when every round runs on time. The half hour above two hours
#: is headroom, and it admits 12:30 EDT and 22:30 EST starts, whose nearest
#: round is exactly 150 minutes out.
#:
#: Lateness can cost a close. A late round that still lands before face-off
#: only shortens the lead, but one that slips past face-off is excluded,
#: and the close falls to the previous round, which may be over the bound.
#: So a round running more than about an hour late behaves as a missed one:
#: 19:00 EST and 22:00 EDT starts lose their close past 60 minutes late,
#: 19:30 EST past 90, 19:00 EDT and 22:00 EST past 120. Only 19:30 EDT keeps
#: a close however late its nearest round runs (its fallback is the 21:00
#: round, exactly 150 minutes out).
#:
#: What it cannot meet, on a normal night with every round on time,
#: sweeping every half hour from 11:00 to 23:00 ET: starts from roughly
#: 13:00-14:00 EDT (13:00, 13:30, 14:00) and 12:00-13:00 EST (12:00, 12:30,
#: 13:00), plus 17:00 EDT, 16:00 EST and 23:00 EST, have NO round within
#: the bound, and neither do 19:00 EDT games on 29-30 September, when only
#: the 18:00 and 23:00 rounds are scheduled. Those games have no close near
#: face-off; their opinions are counted under `no_close_not_near_face_off`,
#: never scored. Only an extra round around 15:30-16:00 UTC would give the
#: afternoon starts a real close, and that spends credits, so it is
#: Cooper's decision. The bound itself is a judgement, and Cooper may
#: revise it.
CLOSE_MAX_LEAD = timedelta(minutes=150)


def closing_prices(
    captures: pd.DataFrame, *, max_lead: timedelta | None = CLOSE_MAX_LEAD
) -> dict[tuple, dict[str, object]]:
    """The last price captured strictly before each game started, and no
    more than `max_lead` before it.

    A capture at or after the listed start is discarded rather than used: it
    is a live price, and the card's opinion was frozen hours earlier. One
    captured more than `max_lead` before the start is discarded too: it is
    an intraday price, and scoring it as the close measures the day's drift
    rather than the market's last word. `max_lead=None` lifts only that
    bound, never the strictly-before rule; it answers "was this priced
    before face-off at all", which is how a stale selection is told apart
    from one never captured.

    At that latest moment the close is the BEST price, the same basis as
    `best_prices` and `collapse_to_best`. It used to be the first row seen
    at that moment, so when a store held several books at one instant the
    close was decided by row order. A movement file listing BetMGM +105
    before DraftKings +140 closed at +105, and the same rows reversed closed
    at +135. A longer price from an EARLIER round is still never the close.
    """
    closing: dict[tuple, dict[str, object]] = {}
    if captures.empty:
        return closing
    for row in captures.itertuples():
        captured = moment(getattr(row, "captured_at", ""))
        commence = moment(getattr(row, "commence_time", ""))
        # Strictly before, on parsed instants. A capture at the puck-drop
        # second is not a closing price, and an unparseable stamp is not an
        # ordering.
        if captured is None or commence is None or captured >= commence:
            continue
        # Near face-off, inclusive at the bound. An earlier price is not a
        # close even when it is the only one.
        if max_lead is not None and commence - captured > max_lead:
            continue
        key = _key_of(row)
        decimal = _decimal(getattr(row, "american_odds", None))
        current = closing.get(key)
        if current is not None:
            if current["moment"] > captured:  # type: ignore[operator]
                continue
            if current["moment"] == captured and not _pays_more(
                decimal, current["decimal"]
            ):
                continue
        closing[key] = {
            "captured_at": str(getattr(row, "captured_at", "")),
            "moment": captured,
            "american_odds": float(getattr(row, "american_odds")),
            "book": str(getattr(row, "book", "")),
            "decimal": decimal,
            "market_in_game": _market_in_game(row),
        }
    return closing


def _pays_more(decimal: float | None, than: object) -> bool:
    """Whether one price pays more than another; an unreadable one never does."""
    if decimal is None:
        return False
    return than is None or decimal > float(than)  # type: ignore[arg-type]


def _market_in_game(row) -> tuple:
    """(market, home, away, league game date): one market of one game."""
    return (
        str(getattr(row, "market", "")).strip(),
        str(getattr(row, "home_team", "")),
        str(getattr(row, "away_team", "")),
        row_game_date(row),
    )


def uncaptured_markets(
    opinions: pd.DataFrame, captures: pd.DataFrame
) -> dict[str, int]:
    """Opinions in a market the store holds NO pre-start price for, in their
    game — by market.

    Every one of them is also counted under "no closing price found", and
    the page used to explain all of those the same way: "a selection the
    books pulled before puck drop". For these it is false. Line Movement,
    which feeds the store, fetches only the per-event markets and their
    alternate ladders, so a moneyline opinion — frozen every game day from
    the bulk fetch — could never meet a close; the failure-shape audit
    replayed a card and two captures and found both moneyline opinions under
    "no closing price found", moneyline absent from the by-market table, and
    a moneyline-only day reading "Nothing to measure yet ... not a fault".
    No book pulled anything there. The capture never priced that market.
    """
    collapsed = collapse_to_best(opinions)
    if collapsed.empty:
        return {}
    # Unbounded in lead: a market priced for its game before face-off, only
    # too early, WAS captured. Those opinions are counted as having no close
    # near face-off instead, so the two explanations stay disjoint.
    captured = {
        entry["market_in_game"]
        for entry in closing_prices(captures, max_lead=None).values()
    }
    found: dict[str, int] = {}
    for row in collapsed.itertuples():
        where = _market_in_game(row)
        if where not in captured:
            found[where[0]] = found.get(where[0], 0) + 1
    return found


#: Markets whose two sides pair for a proportional de-vig. The regulation
#: three-way is deliberately absent: it has three outcomes, and de-vigging it
#: as a pair would report a fair probability that is simply wrong.
def opposite_selection(
    market: str, selection: str, line: float | None
) -> tuple[str, float | None] | None:
    """The other side of a two-way market, or None if it has no clean pair."""
    market = str(market).strip()
    selection = str(selection).strip().lower()
    if market == "moneyline":
        return ("away", line) if selection == "home" else (
            ("home", line) if selection == "away" else None
        )
    if market == "puck_line":
        if line is None or selection not in {"home", "away"}:
            return None
        # home -1.5 is priced against away +1.5: the same wager, other side.
        return ("away" if selection == "home" else "home", -float(line))
    if market == "team_total":
        side, _, direction = selection.partition("_")
        if side in {"home", "away"} and direction in {"over", "under"}:
            flipped = "under" if direction == "over" else "over"
            return (f"{side}_{flipped}", line)
        return None
    if selection == "over":
        return ("under", line)
    if selection == "under":
        return ("over", line)
    return None


def collapse_to_best(opinions: pd.DataFrame) -> pd.DataFrame:
    """One row per selection, at the best price — the card's own basis.

    The snapshot freezes every staged price row, which is one row per book.
    Scoring all of them would measure the books; scoring whichever row
    happened to survive a de-duplication would measure luck. Worse, the
    survivor decides whether the selection clears the staking bar at all, so
    an arbitrary pick silently moves bets in and out of the "bets" table —
    and it removes them exactly where the price was worst, which is where
    the losses live.

    The card quotes the best reachable price, so this does the same: highest
    decimal odds wins, ties broken by nothing because a tie is the same bet.
    """
    if opinions.empty:
        return opinions
    best: dict[tuple, tuple[float, int]] = {}
    for index, row in enumerate(opinions.itertuples()):
        decimal = _decimal(getattr(row, "american_odds", None))
        if decimal is None:
            continue
        key = _key_of(row)
        current = best.get(key)
        if current is None or decimal > current[0]:
            best[key] = (decimal, index)
    keep = sorted(index for _, index in best.values())
    return opinions.iloc[keep].reset_index(drop=True)


def clv_rows(
    opinions: pd.DataFrame, captures: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Every opinion joined to the market's last word, with three measures.

    Returns `(rows, counts)`. `counts` reconciles: every opinion is either
    matched to a closing price, or counted as unmatched with a reason. An
    opinion that silently vanished from a CLV table would flatter the model
    exactly where the market moved away from us — a selection the books
    pulled is the one most likely to have been wrong.

    `no_close_not_near_face_off` is the part of `no_close` whose selection
    WAS priced before face-off, but never within `CLOSE_MAX_LEAD` of it.
    It is a subset, not an extra bucket, so the reconciliation above holds.
    """
    opinions = collapse_to_best(opinions)
    counts = {
        "opinions": int(len(opinions)),
        "matched": 0,
        "no_close": 0,
        "no_close_not_near_face_off": 0,
    }
    if opinions.empty:
        return pd.DataFrame(), counts
    closing = closing_prices(captures)
    priced_before_start = closing_prices(captures, max_lead=None)
    rows: list[dict[str, object]] = []
    for row in opinions.itertuples():
        key = _key_of(row)
        close = closing.get(key)
        if close is None:
            counts["no_close"] += 1
            if key in priced_before_start:
                counts["no_close_not_near_face_off"] += 1
            continue
        taken_decimal = _decimal(getattr(row, "american_odds", None))
        close_decimal = _decimal(close["american_odds"])
        if taken_decimal is None or close_decimal is None:
            counts["no_close"] += 1
            continue
        counts["matched"] += 1

        # EV at close needs the other side's closing price to de-vig. Where
        # it never closed, the row carries no EV rather than a guessed one.
        ev_at_close: float | None = None
        line = getattr(row, "line", None)
        try:
            line_value = None if line is None or pd.isna(line) else float(line)
        except (TypeError, ValueError):
            line_value = None
        pair = opposite_selection(
            str(getattr(row, "market", "")),
            str(getattr(row, "selection", "")),
            line_value,
        )
        if pair is not None:
            other_key = selection_key(
                row, market=str(getattr(row, "market", "")).strip(),
                selection=pair[0], line=pair[1],
            )
            other = closing.get(other_key)
            # Both legs from the same capture round, or no de-vig. Two prices
            # taken hours apart are not a market's two sides at one moment;
            # the implied hold between them is part drift, and de-vigging on
            # it invents a fair probability the book never showed.
            if other is not None and other["moment"] == close["moment"]:
                try:
                    fair, _ = devig_two_way(
                        close["american_odds"], other["american_odds"]
                    )
                    ev_at_close = fair * (taken_decimal - 1.0) - (1.0 - fair)
                except (OddsError, TypeError, ValueError, ZeroDivisionError):
                    ev_at_close = None

        rows.append(
            {
                "snapshot_date": str(getattr(row, "snapshot_date", "")),
                # The game this row belongs to, which is the unit every
                # interval in the report counts. See `_game_of`.
                "home_team": str(getattr(row, "home_team", "")),
                "away_team": str(getattr(row, "away_team", "")),
                "game_date": row_game_date(row),
                "market": str(getattr(row, "market", "")).strip(),
                "selection": str(getattr(row, "selection", "")),
                "player": str(getattr(row, "player", "") or ""),
                "edge": float(getattr(row, "edge", 0.0) or 0.0),
                "taken_odds": float(getattr(row, "american_odds")),
                "closing_odds": float(close["american_odds"]),
                "closing_book": str(close["book"]),
                "closed_at": str(close["captured_at"]),
                "beat_close": bool(taken_decimal > close_decimal),
                "tied_close": bool(taken_decimal == close_decimal),
                "clv_pct": (taken_decimal / close_decimal) - 1.0,
                "ev_at_close": ev_at_close,
            }
        )
    return pd.DataFrame(rows), counts


def _game_of(frame: pd.DataFrame) -> list[tuple[str, str, str]]:
    """(home, away, league game date) for every row: one game.

    The date is the league game date `row_game_date` gives, so two meetings
    of the same clubs on different nights are two games.
    """
    return list(
        zip(
            frame["home_team"].astype(str),
            frame["away_team"].astype(str),
            frame["game_date"].astype(str),
        )
    )


def _summarise(frame: pd.DataFrame, *, looks: int = 1) -> dict:
    """One view's numbers. `looks` is how many markets share the table, so a
    per-market row is corrected for the search that produced it — the same
    rule every other report in this lab applies.

    Every interval is kept twice: the plain 95% one (`*_low/high`) and the
    one corrected for `looks` (`*_adjusted_low/high`). The two are equal
    when looks is 1. Only the CLV interval used to be corrected, and it was
    never rendered. The EV correction was computed and then dropped, and the
    beat-rate interval was never corrected at all.

    ## Every interval counts the game, not the row

    These were `wilson_interval(beat, decided)` and `roi_interval` over the
    rows, as if every row were an independent trial. A row is one selection
    at its best price, and the card freezes every priced row: one game
    brings both sides of a market, every rung of every alternate ladder and
    every player, and all of them move with that game's news. The
    failure-shape audit ran the real runner on the bought prices. One game
    of 162 rows printed beat rate 78.3% [64.4%, 87.7%] and "The interval
    excludes zero on the positive side". The first week of 2025-26 (48
    games, 8,552 rows) read [+0.251%, +0.404%], "excludes zero", where the
    game-clustered interval is [-0.015%, +0.670%]. The design effect on mean
    CLV was 17-23 for opinions and 1.2-1.6 for bets, and in a null
    simulation the row-level page said "excludes zero" in 41% of runs. Almost
    every flip flattered the model.

    The beat rate is now `clustered_wilson_interval` over per-game (beat,
    decided) tallies, and CLV% and EV at close are `clustered_mean_interval`
    over the game, both corrected with the same `bonferroni_z(looks)`. Each
    is exactly the old interval when every game holds one row, is never
    narrower than it, and cannot be bounded from one game.
    """
    from nhl_betting_lab.stats import (
        bonferroni_z,
        clustered_mean_interval,
        clustered_wilson_interval,
    )

    if frame.empty:
        return {"bets": 0, "no_close": 0}
    games = _game_of(frame)
    beat = int(frame["beat_close"].sum())
    tied = int(frame["tied_close"].sum())
    # A price that did not move is not a win over the market and not a loss
    # to it. Counting ties as misses would drag the rate below its true
    # value on exactly the markets that move least.
    decided = int(len(frame)) - tied
    tallies: dict[tuple, list[int]] = {}
    for game, won, tie in zip(games, frame["beat_close"], frame["tied_close"]):
        tally = tallies.setdefault(game, [0, 0])
        if not bool(tie):
            tally[0] += int(bool(won))
            tally[1] += 1
    pairs = [(won, count) for won, count in tallies.values()]
    low, high = clustered_wilson_interval(pairs)
    adjusted_low, adjusted_high = clustered_wilson_interval(
        pairs, z=bonferroni_z(looks)
    )
    clv = clustered_mean_interval(
        [float(value) for value in frame["clv_pct"]], games, looks=looks
    )
    has_ev = frame["ev_at_close"].notna()
    priced = frame[has_ev]
    summary = {
        "bets": int(len(frame)),
        "games": len(tallies),
        "beat_close": beat,
        "tied": tied,
        "decided": decided,
        "beat_rate": (beat / decided) if decided else 0.0,
        "beat_low": low,
        "beat_high": high,
        "beat_adjusted_low": adjusted_low,
        "beat_adjusted_high": adjusted_high,
        "mean_clv_pct": float(frame["clv_pct"].mean()),
        "clv_low": clv.low,
        "clv_high": clv.high,
        "clv_adjusted_low": clv.adjusted_low,
        "clv_adjusted_high": clv.adjusted_high,
        "ev_rows": int(len(priced)),
    }
    if not priced.empty:
        ev = clustered_mean_interval(
            [float(value) for value in priced["ev_at_close"]],
            [game for game, keep in zip(games, has_ev) if keep],
            looks=looks,
        )
        summary["mean_ev"] = float(priced["ev_at_close"].mean())
        summary["ev_low"] = ev.low
        summary["ev_high"] = ev.high
        summary["ev_adjusted_low"] = ev.adjusted_low
        summary["ev_adjusted_high"] = ev.adjusted_high
    return summary


def _verdict(low: float, high: float, mean: float, quantity: str) -> str:
    """The house sentence, in the house's fixed words."""
    from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE

    if not (math.isfinite(low) and math.isfinite(high)):
        return (
            "The sample is too small to bound an interval, so this shows "
            f"**{NO_DEMONSTRATED_EDGE}** either way."
        )
    if low <= 0.0 <= high:
        return (
            f"The interval includes zero, which means **{NO_DEMONSTRATED_EDGE}** "
            f"({quantity})."
        )
    if mean > 0:
        return "The interval excludes zero on the positive side."
    return (
        "The interval excludes zero on the negative side: the market moved "
        "against these opinions more often than not."
    )


REPORT_FILENAME = "closing_line_value.md"


def build_clv_report(
    opinions: pd.DataFrame, captures: pd.DataFrame
) -> dict:
    """Opinions and bets, kept separate, because they answer two questions.

    **Opinions** is every priced row: it measures the model. **Bets** is the
    subset that cleared the staking bar: it measures what the bankroll would
    actually have done. Pooling them would let a large, weak opinion set bury
    a small, bad betting record — or the reverse.
    """
    from nhl_betting_lab.config import MIN_EDGE, MIN_PROP_EDGE
    from nhl_betting_lab.markets import MARKETS_BY_KEY

    def _is_bet(market_key: object, edge: object) -> bool:
        market = MARKETS_BY_KEY.get(str(market_key))
        bar = MIN_PROP_EDGE if market is not None and market.is_prop else MIN_EDGE
        try:
            return float(edge) >= bar
        except (TypeError, ValueError):
            return False

    # Classified BEFORE the join, so the reconciliation can say how many
    # *bets* went unmatched. Counting only opinions would let a bet whose
    # price the books pulled vanish from every number on the page — and a
    # pulled price is the one most likely to have been wrong.
    collapsed = collapse_to_best(opinions)
    staked_total = 0
    if not collapsed.empty:
        staked_total = int(
            sum(
                1
                for row in collapsed.itertuples()
                if _is_bet(getattr(row, "market", ""), getattr(row, "edge", 0.0))
            )
        )

    rows, counts = clv_rows(opinions, captures)
    counts["bets"] = staked_total
    uncaptured = uncaptured_markets(opinions, captures)
    counts["no_close_uncaptured"] = sum(uncaptured.values())
    counts["store_has_closes"] = bool(closing_prices(captures))
    # Gates the uncaptured split: a store whose only prices are too early to
    # close anything still says which markets it priced for which game.
    counts["store_has_pre_start_prices"] = bool(
        closing_prices(captures, max_lead=None)
    )
    report: dict = {"counts": counts, "markets": {}, "uncaptured": uncaptured}
    if rows.empty:
        counts["bets_matched"] = 0
        counts["bets_no_close"] = staked_total
        return report

    rows = rows.copy()
    rows["is_bet"] = [
        _is_bet(row.market, row.edge) for row in rows.itertuples()
    ]
    bets = rows[rows["is_bet"]]
    counts["bets_matched"] = int(len(bets))
    counts["bets_no_close"] = staked_total - int(len(bets))

    markets = sorted({str(value) for value in rows["market"]})
    looks = max(1, len(markets))
    report["looks"] = looks
    report["overall"] = {
        "opinions": {
            **_summarise(rows),
            "no_close": counts.get("no_close", 0),
        },
        "bets": {
            **_summarise(bets),
            "no_close": counts.get("bets_no_close", 0),
        },
    }
    for market, subset in rows.groupby("market"):
        report["markets"][str(market)] = {
            "opinions": _summarise(subset, looks=looks),
            "bets": _summarise(subset[subset["is_bet"]], looks=looks),
        }
    return report


def unreadable_store_report(
    opinions: pd.DataFrame, error: UnreadableCaptureStore
) -> dict:
    """The report for a run whose capture store could not be read.

    It counts the opinions and scores none of them. It never reports them as
    having no close, and `render_clv` never calls this the pre-season state.
    """
    return {
        "counts": {"opinions": int(len(collapse_to_best(opinions)))},
        "markets": {},
        "unreadable_store": {
            "name": error.path.name,
            "rows_on_disk": error.rows_on_disk,
            "rows_read": error.rows_read,
        },
    }


#: The columns every CLV table carries, in order. One definition, so a row
#: and its header cannot drift apart — they did, and every per-market number
#: rendered one column left of its heading with the sample size swallowed by
#: the cell before it. `Games` is the unit every interval counts; it is last
#: so no column the earlier tables printed moves.
TABLE_COLUMNS = (
    "Rows",
    "Beat close",
    "Tied",
    "Beat rate [95%]",
    "Mean CLV% [95%]",
    "EV at close [95%] (n)",
    "Games",
)


def _interval(low: float, high: float, fmt: str = "+.2%") -> str:
    """An interval, or a plain statement that the sample cannot bound one."""
    if not (math.isfinite(low) and math.isfinite(high)):
        return "n too small"
    return f"[{low:{fmt}}, {high:{fmt}}]"


def _summary_cells(summary: dict, *, corrected: bool = False) -> list[str]:
    """One table row. `corrected` prints the intervals corrected for the
    markets sharing the table, which is what the By-market heading promises.
    It used to print the plain 95% ones there, so every by-market interval
    was about 18% too narrow at three markets (z 1.960 against 2.394)."""
    if not summary.get("bets"):
        return ["0", "0", "0", "—", "—", "—", "0"]
    bound = "adjusted_" if corrected else ""
    ev = "—"
    if "mean_ev" in summary:
        ev = (
            f"{summary['mean_ev']:+.1%} "
            f"{_interval(summary[f'ev_{bound}low'], summary[f'ev_{bound}high'], '+.1%')} "
            f"({summary['ev_rows']})"
        )
    return [
        str(summary["bets"]),
        str(summary["beat_close"]),
        str(summary.get("tied", 0)),
        f"{summary['beat_rate']:.1%} "
        + _interval(
            summary[f"beat_{bound}low"], summary[f"beat_{bound}high"], ".1%"
        ),
        f"{summary['mean_clv_pct']:+.2%} "
        + _interval(summary[f"clv_{bound}low"], summary[f"clv_{bound}high"]),
        ev,
        str(summary["games"]),
    ]


def _row(*cells: str) -> str:
    return "| " + " | ".join(cells) + " |"


def _unreadable_snapshot_lines(report: dict) -> list[str]:
    """One bullet per priced snapshot the runner could not read.

    Before these were named, a damaged snapshot either stopped the runner
    (half a character: no report at all) or left its day out of the counts
    without a word (an unclosed quote, zero bytes, half a header: the audit's
    run counted 64 of 128 frozen rows and exited 0). Printed above every
    other line, in every shape of the report, so no count below is read
    without it.
    """
    damaged = report.get("unreadable_snapshots") or []
    if not damaged:
        return []
    lines = [
        f"- **{len(damaged)}** priced snapshot file(s) could not be read, so "
        "no opinion frozen only in them is counted below:",
    ]
    for entry in damaged:
        held = int(entry.get("ledger_rows", 0) or 0)
        counted = (
            f"the forward ledger holds {held} row(s) frozen that day, and "
            "those are counted"
            if held
            else "no row frozen that day is counted"
        )
        lines.append(f"  - `{entry.get('name')}` ({entry.get('reason')}): {counted}.")
    return lines


def _lead_text(lead: timedelta) -> str:
    """`CLOSE_MAX_LEAD` in words, e.g. "150 minutes"."""
    return f"{int(lead.total_seconds() // 60)} minutes"


def render_clv(report: dict, *, generated: str = "") -> str:
    counts = report.get("counts", {})
    lines = [
        "# Closing-line value",
        "",
        "Did the card take prices the market later disagreed with, in our",
        "favour? This answers that on a far smaller sample than the price",
        "backtest needs, which is the whole reason it exists — but it answers",
        "a *narrower* question. Beating the close is evidence of finding",
        "something; it is not profit, and this file never calls it profit.",
        "",
    ]
    if generated:
        lines += [f"- Generated: {generated}"]
    lines += _unreadable_snapshot_lines(report)
    unreadable = report.get("unreadable_store")
    if unreadable:
        # Never "Nothing to measure yet" and never "no closing price found":
        # the closing prices may be in the part of the file that did not
        # parse, so neither the heading nor the counts would be true.
        read = unreadable.get("rows_read")
        how = (
            "it does not parse"
            if read is None
            else f"only {read} of them parse"
        )
        lines += [
            f"- Opinions considered: **{counts.get('opinions', 0)}**; none "
            "was scored.",
            "",
            "## The capture store could not be read",
            "",
            f"`{unreadable.get('name', CAPTURES_FILENAME)}` holds "
            f"{unreadable.get('rows_on_disk', 0)} row(s) on disk, and {how}.",
            "No opinion was scored against a closing price, and none is",
            "counted as having no close, because the closing prices may be",
            "in the part of the file that could not be read. The line-movement",
            "store was not used in its place: that would change where the",
            "closes came from without saying so.",
            "",
            "This is a fault, not the pre-season state. Restore the store",
            "from the branch that carries it, then re-run.",
            "",
        ]
        return "\n".join(lines)
    lines += [
        f"- Opinions considered: **{counts.get('opinions', 0)}**; "
        f"matched to a closing price: **{counts.get('matched', 0)}**; "
        f"no closing price found: **{counts.get('no_close', 0)}**.",
        # Printed every time, zero included, so a game with no capture near
        # face-off (a round missed, or none scheduled that close) cannot
        # pass unseen.
        "- Within that count, priced before face-off but no close near face-off: "
        f"**{counts.get('no_close_not_near_face_off', 0)}** — no capture "
        f"was taken within {_lead_text(CLOSE_MAX_LEAD)} of face-off (a round "
        "missed, or none is scheduled that close). An older price is an "
        "intraday price, not the market's last word, so they are not scored.",
    ]
    # Split, not added to: every opinion below is already in the count above.
    # All of them used to be explained by the paragraph after this, as
    # selections the books pulled — including every moneyline opinion, in a
    # market the capture has never once asked for. An empty store is left to
    # the "Nothing to measure yet" section: with no capture at all, every
    # opinion is trivially uncaptured and the split would say nothing new.
    uncaptured = 0
    if counts.get("store_has_pre_start_prices", counts.get("store_has_closes")):
        uncaptured = int(counts.get("no_close_uncaptured", 0) or 0)
    stale = int(counts.get("no_close_not_near_face_off", 0) or 0)
    if uncaptured:
        named = ", ".join(
            f"`{market}` ({count})"
            for market, count in sorted((report.get("uncaptured") or {}).items())
        )
        lines += [
            f"- Of those, **{uncaptured}** are in a market the store holds no "
            f"price for, in their game, from before face-off: {named}. No "
            "book pulled these. The capture never priced that market for that "
            "game — it does not ask for it, or no capture ran before face-off "
            "— so they are a gap in what is captured and say nothing about "
            "the model.",
        ]
        others = int(counts.get("no_close", 0)) - uncaptured - stale
        if others:
            lines += [
                f"- The other **{others}** are in a market that was captured "
                "for their game, but their own line or side never was before "
                "face-off: the books pulled or moved it, or the capture's "
                "ladders did not carry that line.",
            ]
    lines += [
        "",
        "A closing price is the last price captured **strictly before** the",
        f"listed start, and no more than {_lead_text(CLOSE_MAX_LEAD)} before it.",
        "An opinion with none is counted here, never dropped:",
        "a selection the books pulled before puck drop is exactly the one",
        "most likely to have been wrong, and silently excluding it would",
        "flatter the model precisely where it deserves scrutiny.",
        "",
    ]
    if report.get("overall"):
        lines += [
            "Every interval below is clustered by game. One game brings both",
            "sides of a market, every rung of a ladder and every player, and",
            "they all move with that game's news, so they are not independent",
            "trials. `Games` is the count each interval rests on. No interval",
            "here is narrower than one on the rows would be, and one game",
            "cannot bound an interval at all.",
            "",
        ]
    if not report.get("overall"):
        lines += ["## Nothing to measure yet", ""]
        if uncaptured:
            # "Not a fault" was printed here on a day whose only opinions
            # were moneylines, while the store held that day's prop closes.
            lines += [
                "No opinion has been matched to a closing price. This is NOT",
                "the empty state before a season: the store holds prices",
                f"from before face-off, and {uncaptured} of these opinions are",
                "in a market it never priced for their game. That is a gap in",
                "what is captured.",
                "",
            ]
        elif stale:
            # Prices were captured, but none near enough face-off: a round
            # missed, or the schedule has none that close to this start.
            lines += [
                "No opinion has been matched to a closing price. This is NOT",
                "the empty state before a season: the store holds prices from",
                f"before face-off, but for {stale} of these opinions no capture",
                f"was taken within {_lead_text(CLOSE_MAX_LEAD)} of face-off (a",
                "round missed, or none is scheduled that close).",
                "",
            ]
        elif report.get("unreadable_snapshots"):
            # "Not a fault" would sit under a list of damaged evidence files.
            lines += [
                "No opinion has been matched to a closing price. On its own",
                "that is the state before a season, or on a day the capture",
                "job has not run. This run is still not clean: the snapshot",
                "file(s) named above could not be read.",
                "",
            ]
        else:
            lines += [
                "No opinion has been matched to a closing price. Before the",
                "season, and on any day the capture job has not run, this is the",
                "correct state and not a fault.",
                "",
            ]
        return "\n".join(lines)

    for view in ("opinions", "bets"):
        summary = report["overall"][view]
        unmatched = summary.get("no_close", 0)
        lines += [
            f"## All {view}",
            "",
            _row(*TABLE_COLUMNS),
            _row(*(["---"] * len(TABLE_COLUMNS))),
            _row(*_summary_cells(summary)),
            "",
            f"{unmatched} {view[:-1]}(s) had no closing price and are not in "
            "this table.",
            "",
        ]
        if summary.get("bets"):
            lines += [
                _verdict(
                    summary["clv_low"],
                    summary["clv_high"],
                    summary["mean_clv_pct"],
                    "closing-line value",
                ),
                "",
            ]
            if "mean_ev" in summary:
                lines += [
                    "On expected value at the close — the money figure: "
                    + _verdict(
                        summary["ev_low"],
                        summary["ev_high"],
                        summary["mean_ev"],
                        "value against the closing line",
                    ),
                    "",
                ]

    # The heading said every interval here was corrected, and the cells
    # printed the plain 95% ones. The corrected ones are printed now, the
    # column labels name the family, and the factor is on the page.
    from nhl_betting_lab.stats import Z95, bonferroni_z

    looks = int(report.get("looks") or max(1, len(report["markets"])))
    corrected = looks > 1
    if corrected:
        family = f"[95% family-wise, {looks} markets]"
        columns = tuple(
            column.replace("[95%]", family) for column in TABLE_COLUMNS
        )
        preamble = [
            f"Every interval here is corrected for the {looks} markets that",
            "share the table (Bonferroni: z = "
            f"{bonferroni_z(looks):.3f} in place of {Z95:.3f}), because a",
            "row that only looks remarkable among a dozen is not remarkable.",
        ]
    else:
        columns = TABLE_COLUMNS
        preamble = [
            "Only one market has a matched close, so there is no family to",
            "correct for: these are the plain 95% intervals.",
        ]
    header = ("Market", "View") + columns
    lines += [
        "## By market",
        "",
        *preamble,
        "",
        _row(*header),
        _row(*(["---"] * len(header))),
    ]
    for market in sorted(report["markets"]):
        for view in ("opinions", "bets"):
            summary = report["markets"][market][view]
            lines.append(
                _row(
                    f"`{market}`",
                    view,
                    *_summary_cells(summary, corrected=corrected),
                )
            )
    lines += [
        "",
        "## How to read this",
        "",
        "- **Beat close** counts opinions taken at a longer price than the",
        "  market's last. A rate meaningfully above 50% on a real sample is",
        "  the earliest honest sign a model is finding something.",
        "- **CLV%** is `decimal_taken / decimal_close - 1`, vig included on",
        "  both sides, so it compares across bets and markets.",
        "- **EV at close** de-vigs the closing pair proportionally and asks",
        "  what the bet is worth *if the closing line is right*. It is the",
        "  money figure, and it is the most assumption-laden: it is computed",
        "  only where the opposite side also closed, and the regulation",
        "  three-way is excluded entirely because a three-outcome market",
        "  cannot be de-vigged as a pair.",
        "- **Games** is the sample each interval counts. A thousand rows",
        "  from ten games are ten games of evidence, not a thousand.",
        "- Positive CLV with a losing record is variance against us; a",
        "  winning record with negative CLV is variance *for* us, and this",
        "  lab treats the second as the more dangerous of the two.",
        "",
    ]
    return "\n".join(lines)


def save_clv_report(
    report: dict, *, output_dir: Path | None = None, generated: str = ""
) -> Path:
    from nhl_betting_lab.config import OUTPUTS_DIR

    directory = Path(output_dir) if output_dir else OUTPUTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / REPORT_FILENAME
    path.write_text(render_clv(report, generated=generated), encoding="utf-8")
    return path
