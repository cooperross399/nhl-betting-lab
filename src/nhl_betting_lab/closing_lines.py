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
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.models.value import (
    OddsError,
    american_to_decimal,
    devig_two_way,
)
from nhl_betting_lab.reports.card_pricing import selection_key


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
        existing = pd.read_csv(path)
        existing_rows = len(existing)
        combined = pd.concat([existing, frame], ignore_index=True)
    if len(combined) < existing_rows:
        raise ValueError(
            f"Refusing to write {len(combined)} capture rows over "
            f"{existing_rows}. The store is append-only."
        )
    combined.to_csv(path, index=False, lineterminator="\n")
    return len(frame)


def load_captures(processed_dir: Path | None = None) -> pd.DataFrame:
    path = captures_path(processed_dir)
    if not path.is_file():
        return pd.DataFrame(columns=list(CAPTURE_COLUMNS))
    return pd.read_csv(path)


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


def closing_prices(captures: pd.DataFrame) -> dict[tuple, dict[str, object]]:
    """The last price captured strictly before each game started.

    A capture at or after the listed start is discarded rather than used: it
    is a live price, and the card's opinion was frozen hours earlier.
    """
    closing: dict[tuple, dict[str, object]] = {}
    if captures.empty:
        return closing
    for row in captures.itertuples():
        captured = str(getattr(row, "captured_at", ""))
        commence = str(getattr(row, "commence_time", ""))
        if not captured or not commence or captured >= commence:
            continue
        key = _key_of(row)
        current = closing.get(key)
        if current is not None and str(current["captured_at"]) >= captured:
            continue
        closing[key] = {
            "captured_at": captured,
            "american_odds": float(getattr(row, "american_odds")),
            "book": str(getattr(row, "book", "")),
        }
    return closing


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


def clv_rows(
    opinions: pd.DataFrame, captures: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Every opinion joined to the market's last word, with three measures.

    Returns `(rows, counts)`. `counts` reconciles: every opinion is either
    matched to a closing price, or counted as unmatched with a reason. An
    opinion that silently vanished from a CLV table would flatter the model
    exactly where the market moved away from us — a selection the books
    pulled is the one most likely to have been wrong.
    """
    counts = {"opinions": int(len(opinions)), "matched": 0, "no_close": 0}
    if opinions.empty:
        return pd.DataFrame(), counts
    closing = closing_prices(captures)
    rows: list[dict[str, object]] = []
    for row in opinions.itertuples():
        key = _key_of(row)
        close = closing.get(key)
        if close is None:
            counts["no_close"] += 1
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
            if other is not None:
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
                "market": str(getattr(row, "market", "")).strip(),
                "selection": str(getattr(row, "selection", "")),
                "player": str(getattr(row, "player", "") or ""),
                "edge": float(getattr(row, "edge", 0.0) or 0.0),
                "taken_odds": float(getattr(row, "american_odds")),
                "closing_odds": float(close["american_odds"]),
                "closing_book": str(close["book"]),
                "closed_at": str(close["captured_at"]),
                "beat_close": bool(taken_decimal > close_decimal),
                "clv_pct": (taken_decimal / close_decimal) - 1.0,
                "ev_at_close": ev_at_close,
            }
        )
    return pd.DataFrame(rows), counts


def _summarise(frame: pd.DataFrame) -> dict:
    from nhl_betting_lab.stats import roi_interval, wilson_interval

    if frame.empty:
        return {"bets": 0}
    beat = int(frame["beat_close"].sum())
    low, high = wilson_interval(beat, len(frame))
    clv = roi_interval([float(value) for value in frame["clv_pct"]])
    priced = frame[frame["ev_at_close"].notna()]
    summary = {
        "bets": int(len(frame)),
        "beat_close": beat,
        "beat_rate": beat / len(frame),
        "beat_low": low,
        "beat_high": high,
        "mean_clv_pct": float(frame["clv_pct"].mean()),
        "clv_low": clv.low,
        "clv_high": clv.high,
        "ev_rows": int(len(priced)),
    }
    if not priced.empty:
        ev = roi_interval([float(value) for value in priced["ev_at_close"]])
        summary["mean_ev"] = float(priced["ev_at_close"].mean())
        summary["ev_low"] = ev.low
        summary["ev_high"] = ev.high
    return summary


def _verdict(low: float, high: float, mean: float, quantity: str) -> str:
    """The house sentence. An interval spanning zero says so, in those words."""
    if low <= 0.0 <= high:
        return (
            f"The interval includes zero, which means **no demonstrated "
            f"{quantity}**."
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

    rows, counts = clv_rows(opinions, captures)
    report: dict = {"counts": counts, "markets": {}}
    if rows.empty:
        return report

    def _is_bet(row) -> bool:
        market = MARKETS_BY_KEY.get(str(row.market))
        bar = MIN_PROP_EDGE if market is not None and market.is_prop else MIN_EDGE
        return float(row.edge) >= bar

    rows = rows.copy()
    rows["is_bet"] = [_is_bet(row) for row in rows.itertuples()]
    report["overall"] = {
        "opinions": _summarise(rows),
        "bets": _summarise(rows[rows["is_bet"]]),
    }
    for market, subset in rows.groupby("market"):
        report["markets"][str(market)] = {
            "opinions": _summarise(subset),
            "bets": _summarise(subset[subset["is_bet"]]),
        }
    return report


def _summary_line(summary: dict) -> str:
    if not summary.get("bets"):
        return "| — | 0 | — | — | — |"
    ev = (
        f"{summary['mean_ev']:+.1%} ({summary['ev_rows']})"
        if "mean_ev" in summary
        else "—"
    )
    return (
        f"| {summary['bets']} | {summary['beat_close']} "
        f"| {summary['beat_rate']:.1%} "
        f"[{summary['beat_low']:.1%}, {summary['beat_high']:.1%}] "
        f"| {summary['mean_clv_pct']:+.2%} "
        f"[{summary['clv_low']:+.2%}, {summary['clv_high']:+.2%}] | {ev} |"
    )


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
    lines += [
        f"- Opinions considered: **{counts.get('opinions', 0)}**; "
        f"matched to a closing price: **{counts.get('matched', 0)}**; "
        f"no closing price found: **{counts.get('no_close', 0)}**.",
        "",
        "A closing price is the last price captured **strictly before** the",
        "listed start. An opinion with none is counted here, never dropped:",
        "a selection the books pulled before puck drop is exactly the one",
        "most likely to have been wrong, and silently excluding it would",
        "flatter the model precisely where it deserves scrutiny.",
        "",
    ]
    if not report.get("overall"):
        lines += [
            "## Nothing to measure yet",
            "",
            "No opinion has been matched to a closing price. Before the",
            "season, and on any day the capture job has not run, this is the",
            "correct state and not a fault.",
            "",
        ]
        return "\n".join(lines)

    for view in ("opinions", "bets"):
        summary = report["overall"][view]
        lines += [
            f"## All {view}",
            "",
            "| Rows | Beat close | Beat rate [95%] | Mean CLV% [95%] | EV at close (n) |",
            "|-----:|-----------:|:----------------|:----------------|:----------------|",
            _summary_line(summary),
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

    lines += [
        "## By market",
        "",
        "| Market | View | Rows | Beat close | Beat rate [95%] | Mean CLV% [95%] | EV at close (n) |",
        "|:-------|:-----|-----:|-----------:|:----------------|:----------------|:----------------|",
    ]
    for market in sorted(report["markets"]):
        for view in ("opinions", "bets"):
            summary = report["markets"][market][view]
            lines.append(
                f"| `{market}` | {view} " + _summary_line(summary)[1:]
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
