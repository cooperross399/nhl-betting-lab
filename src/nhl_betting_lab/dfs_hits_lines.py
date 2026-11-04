"""Hits lines from PrizePicks, with the model's chance: a list, never a bet.

No sportsbook the lab can reach has quoted NHL hits since the 2026-10-27
card. The only source still posting them is PrizePicks, a pick'em app in
the provider's `us_dfs` region, whose quotes are lines with fixed pick'em
payouts, not sportsbook odds. Cooper chose "Add as lines only" on
2026-11-04: the card shows each PrizePicks hits line with the model's chance
of the over and the under, and stakes nothing, until a sportsbook posts hits
again.

It is a LIST, like the stat sides and the Due List: no units, no stake, no
price shown as odds, nothing in the best bets, leans or passes, the
selection fingerprint, the frozen snapshot, the forward ledger or its
report. The lines are read from their own staging file
(`LINES_FILENAME`), which the card's priced inputs never include, and the
card prices them into a map of their own that is never merged into the
card's, so PrizePicks can never become a book the card stakes or records.

A line is listed only when the model has an opinion on it (absence means no
opinion, never a default). A game that has started, or whose start cannot
be confirmed, is not listed (the puck-drop guard).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.puck_drop import apply_puck_drop_guard
from nhl_betting_lab.reports.card_pricing import _line, selection_key

SECTION_TITLE = "Hits lines (PrizePicks)"
LINES_FILENAME = "dfs_hits_lines.csv"
DFS_REGION = "us_dfs"
MARKET = "hits"
SIDES = ("over", "under")


@dataclass
class HitsLines:
    rows: list[dict[str, Any]] = field(default_factory=list)
    #: Whether a lines file was on disk for this run at all.
    fetched: bool = False
    #: Lines left out because their game has started or cannot be confirmed.
    removed_by_guard: int = 0
    #: Lines the model holds no opinion on (a name that did not resolve, a
    #: player out tonight, too few games).
    without_opinion: int = 0


def load_lines(staging_dir: Path) -> pd.DataFrame | None:
    """The staged PrizePicks hits rows, or None when no file was written."""
    path = Path(staging_dir) / LINES_FILENAME
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()
    if frame.empty or "market" not in frame.columns:
        return frame.iloc[0:0]
    return frame[frame["market"].astype(str).str.strip() == MARKET].reset_index(drop=True)


def _distinct_lines(lines: pd.DataFrame, day: str | None) -> pd.DataFrame:
    """One row per game, player and line, whichever sides were posted."""
    if lines is None or lines.empty:
        return pd.DataFrame()
    frame = lines.copy()
    frame["line_value"] = frame["line"].map(_line)
    frame = frame[frame["line_value"].notna()]
    frame = frame[frame["player"].notna() & (frame["player"].astype(str).str.strip() != "")]
    if day is not None and "date" in frame.columns:
        # Keyed as the card keys a row: the league game date.
        from nhl_betting_lab.season import row_game_date

        frame = frame[[str(row_game_date(r)) == str(day) for r in frame.itertuples()]]
    keys = ["home_team", "away_team", "player", "line_value"]
    return frame.drop_duplicates(subset=keys).reset_index(drop=True)


def pricing_frame(lines: pd.DataFrame | None, *, day: str | None = None) -> pd.DataFrame:
    """Both sides of every posted line, for `card_pricing.price_props`.

    PrizePicks often posts one side only, and the pricer gives an opinion
    only on the selections it is handed, so each line is priced as an over
    and as an under.
    """
    distinct = _distinct_lines(lines, day) if lines is not None else pd.DataFrame()
    if distinct.empty:
        return pd.DataFrame(columns=list(lines.columns) if lines is not None else [])
    frames = []
    for side in SIDES:
        copy = distinct.drop(columns=["line_value"]).copy()
        copy["selection"] = side
        frames.append(copy)
    return pd.concat(frames, ignore_index=True)


def build_hits_lines(
    lines: pd.DataFrame | None,
    probabilities: Mapping[tuple, float],
    *,
    now: datetime | None = None,
    day: str | None = None,
) -> HitsLines:
    """Every posted hits line the model prices, soonest game first."""
    out = HitsLines(fetched=lines is not None)
    distinct = _distinct_lines(lines, day) if lines is not None else pd.DataFrame()
    if distinct.empty:
        return out
    candidates: list[dict[str, Any]] = []
    for row in distinct.itertuples():
        line = float(row.line_value)
        over = probabilities.get(
            selection_key(row, market=MARKET, selection="over", line=line)
        )
        under = probabilities.get(
            selection_key(row, market=MARKET, selection="under", line=line)
        )
        if over is None or under is None:
            out.without_opinion += 1
            continue
        candidates.append(
            {
                "commence_time": str(getattr(row, "commence_time", "")),
                "home_team": str(row.home_team),
                "away_team": str(row.away_team),
                "player": str(row.player).strip(),
                "line": line,
                "over_probability": round(float(over), 4),
                "under_probability": round(float(under), 4),
                "model_side": "over" if float(over) >= float(under) else "under",
            }
        )
    guarded = apply_puck_drop_guard(candidates, now=now or datetime.now(timezone.utc))
    out.removed_by_guard = len(guarded.quarantined)
    out.rows = sorted(
        (dict(r) for r in guarded.playable),
        key=lambda r: (
            r["commence_time"],
            -max(r["over_probability"], r["under_probability"]),
            r["player"],
        ),
    )
    return out


def render_section(hits: HitsLines | None, start_text) -> list[str]:
    """The card's section. `start_text` formats a row's puck drop."""
    if hits is None:
        return []
    lines = [
        f"## {SECTION_TITLE}",
        "",
        "No sportsbook the lab can reach has posted hits since October 27. "
        "PrizePicks still posts hits lines, so each one is listed with the "
        "model's chance of the over and the under. PrizePicks is a pick'em "
        "app, not a sportsbook: its lines carry no odds to beat, so nothing "
        "here is a bet.",
        "",
    ]
    if hits.rows:
        lines += [
            "| Game | Puck drop | Player | Line | Over | Under | Model leans |",
            "|:--|:--|:--|--:|--:|--:|:--|",
        ]
        for row in hits.rows:
            line = float(row["line"])
            line_text = f"{line:g}"
            lines.append(
                f"| {row['away_team']} @ {row['home_team']} | {start_text(row)} "
                f"| {row['player']} | {line_text} "
                f"| {float(row['over_probability']) * 100:.1f}% "
                f"| {float(row['under_probability']) * 100:.1f}% "
                f"| {str(row['model_side']).capitalize()} |"
            )
        lines += [
            "",
            "A list, not bets: no units, no stakes, nothing frozen into the "
            "forward ledger. Measured on real prices, the hits model has no "
            "demonstrated edge.",
            "",
        ]
    elif not hits.fetched:
        lines += ["_PrizePicks' hits lines were not fetched this run._", ""]
    else:
        lines += ["_PrizePicks has not posted a hits line for tonight's games yet._", ""]
    notes = []
    if hits.removed_by_guard:
        notes.append(
            f"- {hits.removed_by_guard} line(s) not listed: the game started, "
            "or its start could not be confirmed."
        )
    if hits.without_opinion:
        notes.append(
            f"- {hits.without_opinion} line(s) not listed: the model holds no "
            "opinion on the player (a name that did not resolve, or out tonight)."
        )
    if notes:
        lines += notes + [""]
    return lines
