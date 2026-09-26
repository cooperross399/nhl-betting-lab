#!/usr/bin/env python3
"""Site history for one lab's board. Sport-agnostic. Run right after the board is built:

    python web/site_history.py --data dist/data [--slot morning]

Does three things, all inside --data:
  1. Freezes today's board the first time it is built (history/<date>[_<slot>].json).
     That frozen copy is the published opinion. It is replaced only by a board
     built on later results, and only while no game on either board has
     started (see `supersedes`); from the first puck drop it is never overwritten.
  2. Appends the current market values to history/lines/<date>.json, one point per
     build, and injects the series into board.json as `lineHistory[gameId][key]`
     so the page can draw the movement.
  3. Rewrites history/index.json, newest first, with game and best-bet counts.

The workflow restores the previous run's history artifact into --data/history before
this runs and uploads it again afterwards, so the series survive between builds.
Nothing here fetches odds, spends a credit, or places a bet.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date as calendar_date, datetime, timezone
from pathlib import Path

#: series key -> candidate paths into a game dict, first numeric hit wins.
SERIES = {
    "ml_home": [("moneyline", "current", "home")],
    "pl_price": [("puckLine", "price")],
    "spread": [("spread", "current")],
    "total": [("total", "current")],
    "total_over": [("total", "over")],
    "btts_yes": [("btts", "yes")],
    "dnb_home": [("drawNoBet", "home")],
}


def dig(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d if isinstance(d, (int, float)) and not isinstance(d, bool) else None


def board_date(board: dict) -> str:
    for k in ("boardDate", "slateDate", "windowStart"):
        if board.get(k):
            return str(board[k])[:10]
    return datetime.now(timezone.utc).date().isoformat()


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def dump(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def _results_day(value) -> str | None:
    """A board's `resultsThrough` as a YYYY-MM-DD string, or None."""
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return calendar_date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _start(value) -> datetime | None:
    """A game's `startUtc` as an aware instant, or None when it cannot be read."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def supersedes(board: dict, standing, moment: datetime) -> bool:
    """Whether `board` may replace `standing`, the day's frozen board, at `moment`.

    This used to be "never": the first board built for a day was frozen for
    good. Publish Site builds on its own cron and again after each Gameday
    Refresh, and the restore takes only completed runs, so a cron build that
    started while today's run was queued or running (or after GitHub dropped
    the 13:30 primary) was built on YESTERDAY's state, froze first, and
    stood. Its results stop two league days back: every back-to-back flag is
    lost and the model is fitted without last night's games. Replayed on
    2025-26 (167 game days, 1,312 games), a stale-state board drops all 430
    back-to-back flags on 358 games, flips 40 projected winners, and grades
    685 right straight up against 697 for the board built on last night's
    results — which the live board showed within the hour, and the Results
    page never graded.

    So a board replaces the frozen one only when BOTH hold:

    * it was built on later results: its `resultsThrough` (the last league
      date the model was fitted on) is later than the frozen board's. A
      frozen board with none (built without the model, or before this field
      existed) counts as earlier than any date; a later board with none, or
      the same or an earlier date, never replaces. Within one state the
      day's first published opinion still stands.
    * no game on either board has started. A start at or before `moment`,
      or one that cannot be read, counts as started, so the doubt falls on
      leaving the record alone. From the first puck drop the frozen board
      is the record, whatever arrives later.

    A board with no `resultsThrough` — every other sport this generator
    serves, and every preseason board — therefore never replaces anything,
    which is exactly the old behaviour.
    """
    if not isinstance(standing, dict):
        return False
    newer = _results_day(board.get("resultsThrough"))
    if newer is None:
        return False
    if standing.get("resultsThrough") is not None:
        older = _results_day(standing["resultsThrough"])
        if older is None or newer <= older:
            return False
    for shown in (standing, board):
        games = shown.get("games")
        if not isinstance(games, list):
            return False
        for game in games:
            start = _start(game.get("startUtc")) if isinstance(game, dict) else None
            if start is None or start <= moment:
                return False
    return True


def freeze(board: dict, frozen: Path, moment: datetime) -> str:
    """Write the day's frozen board. Returns "froze", "replaced" or "kept".

    A frozen file that cannot be read is kept as it is: it is the record,
    and a build is not the place to decide it was wrong.
    """
    if not frozen.exists():
        dump(frozen, board)
        return "froze"
    try:
        standing = json.loads(frozen.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "kept"
    if not supersedes(board, standing, moment):
        return "kept"
    dump(frozen, board)
    return "replaced"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="dist/data")
    ap.add_argument("--slot", default="", help="Card slot suffix for sports with several cards a day.")
    args = ap.parse_args(argv)
    data = Path(args.data)
    board_path = data / "board.json"
    board = load(board_path, None)
    if board is None:
        print("no board.json; nothing to record")
        return 0
    date = board_date(board)
    slot = args.slot or board.get("cardSlot") or ""
    hist = data / "history"
    lines_path = hist / "lines" / f"{date}.json"

    # 2. line series
    lines = load(lines_path, {})
    stamp = board.get("generatedAt") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    for g in board.get("games", []):
        gid = str(g.get("id"))
        series = lines.setdefault(gid, {})
        for key, paths in SERIES.items():
            v = next((x for x in (dig(g, p) for p in paths) if x is not None), None)
            if v is None:
                continue
            pts = series.setdefault(key, [])
            if not pts or pts[-1]["v"] != v:
                pts.append({"t": stamp, "v": v})
            elif pts[-1]["t"] != stamp:
                pts[-1] = {"t": stamp, "v": v}  # same value, newer confirmation
    dump(lines_path, lines)
    board["lineHistory"] = {gid: {k: v for k, v in s.items() if len(v) >= 2} for gid, s in lines.items()}
    board["lineHistory"] = {gid: s for gid, s in board["lineHistory"].items() if s}
    dump(board_path, board)

    # 1. freeze. This was `if not frozen.exists()`, so the day's first board
    # stood even when it was built on yesterday's state; see `supersedes`.
    fname = f"{date}_{slot}.json" if slot else f"{date}.json"
    frozen = hist / fname
    done = freeze(board, frozen, datetime.now(timezone.utc))
    if done != "kept":
        print(f"{done} {fname}")

    # 3. index
    entries = []
    for p in sorted(hist.glob("*.json")):
        if p.name == "index.json":
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:_(\w+))?\.json$", p.name)
        if not m:
            continue
        b = load(p, {})
        games = b.get("games", [])
        bets = sum(1 for g in games if isinstance(g.get("pick"), dict) and g["pick"].get("kind", "bet") == "bet")
        e = {"date": m.group(1), "file": p.name, "games": len(games), "bets": bets}
        if m.group(2):
            e["slot"] = m.group(2)
        if b.get("phase") == "preseason":
            e["note"] = "exhibition"
        entries.append(e)
    entries.sort(key=lambda e: (e["date"], e.get("slot", "")), reverse=True)
    dump(hist / "index.json", {"generatedAt": stamp, "dates": entries})
    print(f"history: {len(entries)} boards indexed; lines recorded for {len(lines)} games. No bet was placed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
